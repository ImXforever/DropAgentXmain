"""Read-only USDT verification plus provider-backed payouts.

The verifier never signs transactions and never holds private keys. It reads
confirmed token transfers from a configured indexer/RPC and returns a typed
result. Payouts are delegated to an external, idempotent payout service via
PAYOUT_API_URL; keeping signing outside this process avoids putting private
keys in the bot container.
"""

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import os
from typing import Any

import httpx


# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


@dataclass(frozen=True)
class Verification:
    verified: bool
    network: str
    txid: str
    amount_usdt: Decimal = Decimal("0")
    confirmations: int = 0
    sender: str = ""
    reason: str = ""


class ChainUnavailable(RuntimeError):
    pass


def _dec(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _required_confirmations(network: str) -> int:
    return max(1, int(os.getenv(f"CONFIRMATIONS_{network.upper()}",
                               os.getenv("CHAIN_CONFIRMATIONS", "12"))))


def _wallet(network: str) -> str:
    return os.getenv(f"WALLET_{network.upper()}", "").strip()


def _token(network: str) -> str:
    return os.getenv(f"USDT_{network.upper()}_TOKEN", "").strip()


def _rpc_url(network: str) -> str:
    return os.getenv(f"{network.upper()}_RPC_URL", "").strip()


def _ok(network: str, txid: str, amount: Decimal, confirmations: int,
        sender: str = "", reason: str = "") -> Verification:
    need = _required_confirmations(network)
    return Verification(
        verified=amount > 0 and confirmations >= need,
        network=network,
        txid=txid,
        amount_usdt=amount,
        confirmations=confirmations,
        sender=sender,
        reason=reason or ("confirmed" if confirmations >= need else
                          f"waiting for {need} confirmations"),
    )


def _norm_address(value: str | dict | None) -> str:
    if isinstance(value, dict):
        value = value.get("address") or value.get("raw") or ""
    return str(value or "").strip().lower()


async def verify_deposit(network: str, txid: str, expected_amount_usdt: Decimal,
                         expected_wallet: str | None = None) -> Verification:
    """Verify one transfer; return unverified instead of guessing on errors."""
    network = (network or "").strip().lower()
    txid = (txid or "").strip()
    expected_wallet = (expected_wallet or _wallet(network)).strip()
    expected_amount_usdt = _dec(expected_amount_usdt)
    if network not in {"ton", "bsc", "base", "sol", "trx"}:
        return Verification(False, network, txid, reason="unsupported network")
    if not txid or expected_amount_usdt <= 0 or not expected_wallet:
        return Verification(False, network, txid, reason="missing verification configuration")
    try:
        if network == "trx":
            return await _verify_tron(txid, expected_amount_usdt, expected_wallet)
        if network in {"bsc", "base"}:
            return await _verify_evm(network, txid, expected_amount_usdt, expected_wallet)
        if network == "sol":
            return await _verify_solana(txid, expected_amount_usdt, expected_wallet)
        return await _verify_ton(txid, expected_amount_usdt, expected_wallet)
    except (httpx.HTTPError, ChainUnavailable, ValueError, KeyError, TypeError, AttributeError) as exc:
        return Verification(False, network, txid, reason=f"provider error: {type(exc).__name__}")


async def _json_rpc(url: str, method: str, params: list) -> Any:
    if not url:
        raise ChainUnavailable("RPC URL is not configured")
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(url, json={"jsonrpc": "2.0", "id": 1,
                                                 "method": method, "params": params})
        response.raise_for_status()
        data = response.json()
    if data.get("error"):
        raise ChainUnavailable(str(data["error"])[:200])
    return data.get("result")


async def _verify_evm(network: str, txid: str, expected: Decimal,
                      wallet: str) -> Verification:
    receipt = await _json_rpc(_rpc_url(network), "eth_getTransactionReceipt", [txid])
    if not receipt:
        return Verification(False, network, txid, reason="transaction not mined")
    if str(receipt.get("status", "")).lower() != "0x1":
        return Verification(False, network, txid, reason="transaction failed")
    block = int(receipt.get("blockNumber", "0x0"), 16)
    latest = int(await _json_rpc(_rpc_url(network), "eth_blockNumber", []), 16)
    confirmations = max(0, latest - block + 1)
    token = _norm_address(_token(network))
    if not token:
        return Verification(False, network, txid, confirmations=confirmations,
                            reason="USDT token contract is not configured")
    target = _norm_address(wallet)
    total = Decimal("0")
    sender = ""
    for log in receipt.get("logs") or []:
        topics = log.get("topics") or []
        if len(topics) < 3 or str(topics[0]).lower() != TRANSFER_TOPIC:
            continue
        if token and _norm_address(log.get("address")) != token:
            continue
        to_addr = "0x" + str(topics[2])[-40:]
        if _norm_address(to_addr) != target:
            continue
        raw = int(str(log.get("data", "0x0")), 16)
        decimals = int(os.getenv(f"USDT_{network.upper()}_DECIMALS", "6"))
        amount = Decimal(raw) / (Decimal(10) ** decimals)
        total += amount
        sender = "0x" + str(topics[1])[-40:]
    if total <= 0:
        return Verification(False, network, txid, confirmations=confirmations,
                            reason="no matching USDT Transfer event")
    if total < expected:
        return Verification(False, network, txid, total, confirmations, sender,
                            f"amount too low: {total} < {expected}")
    return _ok(network, txid, total, confirmations, sender)


async def _verify_tron(txid: str, expected: Decimal, wallet: str) -> Verification:
    base = os.getenv("TRONGRID_URL", "https://api.trongrid.io").rstrip("/")
    headers = {}
    if os.getenv("TRONGRID_API_KEY"):
        headers["TRON-PRO-API-KEY"] = os.getenv("TRONGRID_API_KEY")
    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        info_response = await client.post(
            f"{base}/wallet/gettransactioninfobyid", json={"value": txid})
        info_response.raise_for_status()
        info = info_response.json()
        receipt = info.get("receipt") or {}
        if receipt.get("result") not in (None, "SUCCESS"):
            return Verification(False, "trx", txid, reason="transaction failed")
        events_response = await client.get(f"{base}/v1/transactions/{txid}/events")
        events_response.raise_for_status()
        events = events_response.json().get("data") or []
        latest_response = await client.post(f"{base}/wallet/getnowblock", json={})
        latest_response.raise_for_status()
        latest = (latest_response.json().get("block_header") or {}).get("raw_data", {}).get("number", 0)
    block = int(info.get("blockNumber") or 0)
    confirmations = max(0, int(latest) - block + 1) if block else 0
    token = _norm_address(_token("trx"))
    if not token:
        return Verification(False, "trx", txid, confirmations=confirmations,
                            reason="USDT token contract is not configured")
    total = Decimal("0")
    sender = ""
    for event in events:
        if event.get("event_name") != "Transfer":
            continue
        contract = _norm_address(event.get("contract_address") or
                                 event.get("address") or "")
        if token and contract != token:
            continue
        result = event.get("result") or {}
        if _norm_address(result.get("to")) != _norm_address(wallet):
            continue
        decimals = int(os.getenv("USDT_TRX_DECIMALS", "6"))
        total += Decimal(str(result.get("value", "0"))) / (Decimal(10) ** decimals)
        sender = str(result.get("from") or "")
    if total <= 0:
        return Verification(False, "trx", txid, confirmations=confirmations,
                            reason="no matching TRC20 Transfer event")
    if total < expected:
        return Verification(False, "trx", txid, total, confirmations, sender,
                            f"amount too low: {total} < {expected}")
    return _ok("trx", txid, total, confirmations, sender)


async def _verify_solana(txid: str, expected: Decimal, wallet: str) -> Verification:
    result = await _json_rpc(_rpc_url("sol"), "getTransaction", [
        txid, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}
    ])
    if not result:
        return Verification(False, "sol", txid, reason="transaction not found")
    meta = result.get("meta") or {}
    if meta.get("err") is not None:
        return Verification(False, "sol", txid, reason="transaction failed")
    mint = _norm_address(_token("sol"))
    if not mint:
        return Verification(False, "sol", txid, reason="USDT mint is not configured")
    post = meta.get("postTokenBalances") or []
    pre = meta.get("preTokenBalances") or []
    pre_map = {(x.get("accountIndex"), _norm_address(x.get("mint")),
                _norm_address(x.get("owner"))): int((x.get("uiTokenAmount") or {}).get("amount", 0))
               for x in pre}
    total_raw = 0
    sender = ""
    decimals = int(os.getenv("USDT_SOL_DECIMALS", "6"))
    for item in post:
        key = (item.get("accountIndex"), _norm_address(item.get("mint")),
               _norm_address(item.get("owner")))
        if mint and key[1] != mint:
            continue
        if key[2] != _norm_address(wallet):
            continue
        now = int((item.get("uiTokenAmount") or {}).get("amount", 0))
        delta = now - pre_map.get(key, 0)
        if delta > 0:
            total_raw += delta
    slot = int(result.get("slot") or 0)
    latest = await _json_rpc(_rpc_url("sol"), "getSlot", [{"commitment": "finalized"}])
    confirmations = max(0, int(latest or 0) - slot + 1)
    total = Decimal(total_raw) / (Decimal(10) ** decimals)
    if total <= 0:
        return Verification(False, "sol", txid, confirmations=confirmations,
                            reason="no matching USDT token balance delta")
    if total < expected:
        return Verification(False, "sol", txid, total, confirmations, sender,
                            f"amount too low: {total} < {expected}")
    return _ok("sol", txid, total, confirmations, sender)


async def _verify_ton(txid: str, expected: Decimal, wallet: str) -> Verification:
    """Verify through a normalized Tatum-style Jetton transfers endpoint.

    TON indexers expose different address/hash formats. Requiring an explicit
    indexer URL and matching the jetton master prevents a false positive from a
    generic transaction endpoint.
    """
    base = os.getenv("TON_INDEXER_URL", "").rstrip("/")
    api_key = os.getenv("TON_INDEXER_API_KEY", "")
    if not base:
        raise ChainUnavailable("TON_INDEXER_URL is not configured")
    params = {"owner_address": wallet, "limit": "100", "sort": "desc"}
    headers = {"x-api-key": api_key} if api_key else {}
    async with httpx.AsyncClient(timeout=20, headers=headers) as client:
        response = await client.get(f"{base}/jetton/transfers", params=params)
        response.raise_for_status()
        data = response.json()
    transfers = data.get("jetton_transfers") or data.get("transfers") or data.get("result") or []
    target_jetton = _norm_address(_token("ton"))
    if not target_jetton:
        return Verification(False, "ton", txid, reason="USDT jetton master is not configured")
    decimals = int(os.getenv("USDT_TON_DECIMALS", "6"))
    for item in transfers:
        h = str(item.get("transaction_hash") or item.get("tx_hash") or
                (item.get("transaction") or {}).get("hash") or "")
        if h != txid:
            continue
        to_addr = _norm_address(item.get("destination") or item.get("to") or
                                (item.get("to") or {}).get("address"))
        jetton = item.get("jetton_master") or item.get("jetton")
        if isinstance(jetton, dict):
            jetton = jetton.get("address")
        if to_addr != _norm_address(wallet) or (target_jetton and
                                                 _norm_address(str(jetton)) != target_jetton):
            return Verification(False, "ton", txid, reason="wrong recipient or jetton")
        amount = Decimal(str(item.get("amount") or 0)) / (Decimal(10) ** decimals)
        sender = str(item.get("source") or item.get("from") or "")
        if amount < expected:
            return Verification(False, "ton", txid, amount, _required_confirmations("ton"),
                                sender, f"amount too low: {amount} < {expected}")
        # The indexer result is already finalized at this API boundary.
        return _ok("ton", txid, amount, _required_confirmations("ton"), sender)
    return Verification(False, "ton", txid, reason="transaction not found in indexer")


async def request_payout(network: str, address: str, amount_usdt: Decimal,
                         idempotency_key: str) -> str:
    """Ask an external payout signer and return its txid.

    Expected response: {"ok": true, "txid": "..."}. The service must honor
    Idempotency-Key so worker retries cannot send twice.
    """
    url = os.getenv("PAYOUT_API_URL", "").strip()
    token = os.getenv("PAYOUT_API_TOKEN", "").strip()
    if not url or not token:
        raise ChainUnavailable("PAYOUT_API_URL/PAYOUT_API_TOKEN not configured")
    headers = {"Authorization": f"Bearer {token}",
               "Idempotency-Key": idempotency_key,
               "Content-Type": "application/json"}
    payload = {"network": network, "address": address,
               "amount_usdt": str(_dec(amount_usdt))}
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()
    txid = str(data.get("txid") or data.get("transaction_hash") or "").strip()
    if not data.get("ok") or not txid:
        raise ChainUnavailable("payout provider returned no txid")
    return txid
