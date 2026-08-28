"""Deep approval gates — enhanced from Hermes Agent's tools/approval.py.

Layer 1 (existing): Pattern-matching for shell commands (safe/guard/block)
Layer 2 (new):       File content analysis (injection, malware, XSS detection)
Layer 3 (new):       URL safety analysis (SSRF, phishing, suspicious patterns)
Layer 4 (new):       Context-aware risk scoring (role-based, history-aware)
Layer 5 (new):       Persistent audit trail (SQLite)
Layer 6 (new):       Smart auto-approve / auto-reject rules

All layers compose into a single classify() call that returns an
ApprovalDecision with full reasoning.
"""

import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# =========================================================
# Layer 1: Shell command patterns (from existing approval.py)
# =========================================================

BLOCK_PATTERNS = [
    re.compile(r"\brm\s+(-\w*r\w*\s+)?/", re.I),
    re.compile(r"\brm\s+(-\w*r\w*\s+)~", re.I),
    re.compile(r"\bmkfs\b", re.I),
    re.compile(r"\bdd\s+if=.*of=/dev/", re.I),
    re.compile(r"\bformat\s+[a-zA-Z]:", re.I),
    re.compile(r"\b(SYSTEM|SAM|SECURITY|boot)\s+registry\b", re.I),
    re.compile(r"\bcd\s+/\s*&&", re.I),
    re.compile(r":\(\)\{\s*:\|:\s*&\s*\}", re.I),
    re.compile(r">\s*/dev/sd[a-z]", re.I),
    re.compile(r"shutdown|reboot|poweroff|halt", re.I),
    re.compile(r"chmod\s+777\s+/", re.I),
    re.compile(r"\bsudo\s+rm\b", re.I),
]

GUARD_PATTERNS = [
    re.compile(r"\b(pip\s+install|npm\s+i|npm\s+install|yarn\s+add|apt\s+(install|remove|purge)|brew\s+install)\b", re.I),
    re.compile(r"\b(curl|wget|ssh|scp|rsync|sftp)\b", re.I),
    re.compile(r"\bdocker\s+(run|exec|rm|stop|kill|push|pull)\b", re.I),
    re.compile(r"\bkubectl\b", re.I),
    re.compile(r"\bdocker\s+compose\b", re.I),
    re.compile(r"\brm\s+(-[a-zA-Z]*\s+)*\S+", re.I),
    re.compile(r"\bmv\s+.+/\s*$", re.I),
    re.compile(r">\s*\S+", re.I),
    re.compile(r"\benv\b.*=", re.I),
    re.compile(r"\bexport\b.*=", re.I),
    re.compile(r"\bcurl\s.*\|\s*(bash|sh)\b", re.I),
    re.compile(r"\bchmod\b", re.I),
    re.compile(r"\bchown\b", re.I),
    re.compile(r"\bsudo\b", re.I),
    re.compile(r"\bDROP\s+TABLE\b", re.I),
    re.compile(r"\bDELETE\s+FROM\b", re.I),
    re.compile(r"\bTRUNCATE\b", re.I),
    re.compile(r"\bkill\s+-9\b", re.I),
    re.compile(r"\bpkill\b", re.I),
    re.compile(r"\bunzip\b", re.I),
    re.compile(r"\btar\s+.*x\w*f\b", re.I),
    re.compile(r"\b7z\s+(x|e)\b", re.I),
]

SAFE_PATTERNS = [
    re.compile(r"\b(python|python3|node|npm)\s+-c\b", re.I),
    re.compile(r"\bgit\s+(status|log|diff|branch|show|remote|tag)\b", re.I),
    re.compile(r"\b(ls|pwd|echo|date|whoami|which|cat|head|tail|wc|grep|find|sort|uniq)\b", re.I),
    re.compile(r"\b(pytest|unittest|ruff|black|isort|mypy)\b", re.I),
    re.compile(r"\bpip\s+(list|show|freeze)\b", re.I),
]

# =========================================================
# Layer 2: File content analysis patterns
# =========================================================

INJECTION_PATTERNS = [
    re.compile(r"\{\{.*eval.*\}\}", re.I),              # template injection
    re.compile(r"\{\{.*exec.*\}\}", re.I),
    re.compile(r"<script[^>]*>", re.I),                   # XSS
    re.compile(r"on\w+\s*=\s*['\"]?\s*javascript:", re.I),  # event handler injection
    re.compile(r"__import__\s*\(", re.I),                 # Python import injection
    re.compile(r"subprocess\.(?:call|run|Popen)", re.I),  # subprocess injection
    re.compile(r"os\.(?:system|popen)\s*\(", re.I),        # OS command injection
    re.compile(r"eval\s*\(", re.I),                        # eval injection
    re.compile(r"exec\s*\(", re.I),                        # exec injection
    re.compile(r"UNION\s+SELECT", re.I),                   # SQL injection
    re.compile(r"';?\s*DROP\s", re.I),                      # SQL drop
    re.compile(r"\bbase64\b.*\bdecode\b.*\bexec\b", re.I),  # base64→exec
    re.compile(r"\\x[0-9a-f]{2}.*\\x[0-9a-f]{2}.*\\x[0-9a-f]{2}", re.I),  # hex-encoded commands
    re.compile(r"\bcurl\b.*\|\s*(?:bash|sh|zsh)\b", re.I),    # pipe to shell
    re.compile(r"\bwget\b.*\|\s*(?:bash|sh|zsh)\b", re.I),
    re.compile(r"\bsh\s*-c\b", re.I),
]

MALWARE_INDICATORS = [
    re.compile(r"reverse\s+shell", re.I),
    re.compile(r"nc\s+-l[ep]", re.I),                      # netcat listener
    re.compile(r"bash\s+-i\b", re.I),                       # interactive bash
    re.compile(r"/dev/tcp/", re.I),                          # bash reverse shell
    re.compile(r"msfvenom|metasploit", re.I),
    re.compile(r"keylogger|backdoor|trojan", re.I),
    re.compile(r"crypto\s*mining|stratum\+tcp", re.I),       # mining
]


# =========================================================
# Layer 3: URL safety analysis
# =========================================================

PHISHING_INDICATORS = [
    re.compile(r"(?:login|signin|verify|secure|account|paypal|apple|microsoft)\b.*\.(?!com|org|net)", re.I),
    re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", re.I),  # raw IP URL
    re.compile(r"\.onion\b", re.I),                              # tor
    re.compile(r"bit\.ly|tinyurl|t\.co", re.I),                  # shorteners
]

SSRF_PATTERNS = [
    re.compile(r"169\.254\.", re.I),
    re.compile(r"127\.0\.", re.I),
    re.compile(r"10\.\d+\.\d+\.\d+", re.I),
    re.compile(r"172\.(1[6-9]|2\d|3[01])\.", re.I),
    re.compile(r"192\.168\.", re.I),
    re.compile(r"metadata\.google", re.I),
    re.compile(r"localhost", re.I),
]


# =========================================================
# Layer 1: Shell command classification
# =========================================================

def classify_shell(command: str) -> str:
    """Classify shell command: safe / guard / block."""
    if not command or not command.strip():
        return "block"
    cmd = command.strip()
    for pat in BLOCK_PATTERNS:
        if pat.search(cmd):
            return "block"
    for pat in GUARD_PATTERNS:
        if pat.search(cmd):
            return "guard"
    for pat in SAFE_PATTERNS:
        if pat.search(cmd):
            return "safe"
    return "guard"  # unknown = guard


# =========================================================
# Layer 2: File content analysis
# =========================================================

def analyze_file_content(content: str) -> dict:
    """Analyze file content for injections, malware, XSS.

    Returns {"risk_level": 0-10, "findings": list[str]}.
    """
    findings = []
    risk = 0

    for pat in INJECTION_PATTERNS:
        if pat.search(content):
            findings.append(f"تزریق: {pat.pattern[:30]}")
            risk += 3

    for pat in MALWARE_INDICATORS:
        if pat.search(content):
            findings.append(f"بدافزار: {pat.pattern[:30]}")
            risk += 5

    # Suspicious: lots of imports or eval in Python
    if re.search(r"(?:import\s+\w+\s*,?\s*){8,}", content):
        findings.append("ورودی‌های غیرعادی زیاد")
        risk += 2

    # Suspicious: encoded strings (base64 blocks)
    b64_blocks = re.findall(r"[A-Za-z0-9+/]{40,}={0,2}", content)
    if len(b64_blocks) > 3:
        findings.append("بلوک‌های base64 زیاد")
        risk += 2

    return {"risk_level": min(risk, 10), "findings": findings}


# =========================================================
# Layer 3: URL safety
# =========================================================

def analyze_url_safety(url: str) -> dict:
    """Analyze URL for phishing, SSRF, suspicious patterns.

    Returns {"risk_level": 0-10, "findings": list[str]}.
    """
    findings = []
    risk = 0

    if not url:
        return {"risk_level": 0, "findings": []}

    for pat in PHISHING_INDICATORS:
        if pat.search(url):
            findings.append(f"فishing: {pat.pattern[:30]}")
            risk += 4

    for pat in SSRF_PATTERNS:
        if pat.search(url):
            findings.append(f"SSRF: {pat.pattern[:30]}")
            risk += 5

    # Suspicious TLDs
    if re.search(r"\.(ru|cn|tk|ml|ga|cf|gq|pw)\b", url, re.I):
        findings.append("TLD مشکوک")
        risk += 1

    return {"risk_level": min(risk, 10), "findings": findings}


# =========================================================
# Layer 4: Context-aware risk scoring
# =========================================================

# Role-based risk multipliers
ROLE_RISK_MULTIPLIER = {
    "admin": 0.5,       # admins can do more
    "godfather": 0.3,   # godfather least restricted
    "underboss": 0.6,
    "capo": 0.8,
    "soldier": 1.0,     # normal risk
    "associate": 1.3,   # higher risk for unproven users
}


def context_risk_modifier(risk: int, role: str = "associate", recent_blocks: int = 0) -> int:
    """Modify risk based on user context."""
    multiplier = ROLE_RISK_MULTIPLIER.get(role, 1.0)
    # Increase risk if user has been blocked recently (suspicious behavior)
    modifier = multiplier * (1.0 + recent_blocks * 0.3)
    return max(0, min(10, int(risk * modifier)))


# =========================================================
# Layer 5: Audit trail (SQLite)
# =========================================================

async def _ensure_audit_table():
    from database import raw_db
    async with raw_db() as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS approval_audit (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                actor_id INTEGER DEFAULT 0,
                action TEXT NOT NULL,
                target TEXT NOT NULL,
                risk_level INTEGER DEFAULT 0,
                decision TEXT NOT NULL,
                risk_tags TEXT DEFAULT '[]',
                timestamp REAL DEFAULT (strftime('%s','now'))
            )""")
        # Migration for databases that predate the actor column
        if "actor_id" not in await _table_cols(db):
            try:
                await db.execute("ALTER TABLE approval_audit ADD COLUMN actor_id INTEGER DEFAULT 0")
            except Exception:
                pass
        await db.commit()


async def _table_cols(db) -> list:
    try:
        cur = await db.execute("PRAGMA table_info(approval_audit)")
        rows = await cur.fetchall()
        return [r[1] for r in rows]
    except Exception:
        return []


async def audit_log(user_id: int, action: str, target: str, risk_level: int,
                    decision: str, risk_tags: list = None, actor_id: int = 0):
    """Log an approval decision to the audit trail.

    ``user_id`` is the REQUESTER (who issued the command); ``actor_id`` is the
    admin/operator who made the decision (0 = automated). Keeping both means the
    trail can answer "what did this user request?" as well as "who acted?".
    """
    logger = logging.getLogger(__name__)
    try:
        await _ensure_audit_table()
        from database import raw_db
        async with raw_db() as db:
            await db.execute(
                "INSERT INTO approval_audit (user_id, actor_id, action, target, risk_level, decision, risk_tags) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, actor_id, action, target[:500], risk_level, decision,
                 json.dumps(risk_tags or [])),
            )
            await db.commit()
    except Exception:
        logger.exception("approval.audit_log failed for user=%s action=%s", user_id, action)


async def audit_history(user_id: int = 0, limit: int = 20) -> list[dict]:
    """Get recent audit entries."""
    try:
        await _ensure_audit_table()
        from database import raw_db
        async with raw_db() as db:
            q = "SELECT * FROM approval_audit"
            params = []
            if user_id:
                q += " WHERE user_id = ?"
                params.append(user_id)
            q += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            cursor = await db.execute(q, params)
            return [dict(r) for r in await cursor.fetchall()]
    except Exception:
        return []


# =========================================================
# Layer 6: Smart auto-approve / auto-reject rules
# =========================================================

_AUTO_APPROVE_CONTEXTS = [
    # In a test suite, auto-approve test-related commands
    re.compile(r"(pytest|unittest|test_|_test\.py)\b", re.I),
    re.compile(r"\b(ruff|black|isort|mypy|flake8)\b", re.I),
]

_AUTO_REJECT_CONTEXTS = [
    re.compile(r"(format\s+[a-zA-Z]:|rm\s+-rf\s+/)", re.I),
    re.compile(r"eval\s*\(\s*input", re.I),   # never auto-approve eval(input())
]


def check_auto_rules(command: str, context: str = "") -> Optional[str]:
    """Check if command should be auto-approved or auto-rejected.
    Returns 'approve', 'reject', or None (needs manual review).
    """
    combined = f"{command} {context}"
    for pat in _AUTO_REJECT_CONTEXTS:
        if pat.search(combined):
            return "reject"
    for pat in _AUTO_APPROVE_CONTEXTS:
        if pat.search(combined):
            return "approve"
    return None


# =========================================================
# Main classification (unified Layer 1-6)
# =========================================================

@dataclass
class ApprovalDecision:
    """Unified output from all approval layers."""
    tier: str               # "safe", "guard", "block"
    risk_level: int         # 0-10 scale
    reason: str
    risk_tags: list = field(default_factory=list)
    auto_decision: str = "" # "approve", "reject", "" (from Layer 6)
    context_notes: str = ""

    @property
    def needs_approval(self) -> bool:
        return self.tier == "guard" and not self.auto_decision == "approve"

    @property
    def is_blocked(self) -> bool:
        return self.tier == "block" or self.auto_decision == "reject"


def classify_command(command: str, role: str = "associate",
                     recent_blocks: int = 0) -> ApprovalDecision:
    """Full classification pipeline (Layers 1-6)."""
    if not command or not command.strip():
        return ApprovalDecision("block", 10, "دستور خالی است")

    cmd = command.strip()

    # Layer 1: Shell command patterns
    shell_tier = classify_shell(cmd)
    risk_map = {"safe": 0, "guard": 5, "block": 10}
    risk = risk_map.get(shell_tier, 5)

    tag = _identify_risk(cmd) if shell_tier != "safe" else ""
    tags = [tag] if tag else []
    reason = {
        "safe": "دستور ایمن",
        "guard": f"نیاز به تأیید: {tag}" if tag else "نیاز به تأیید: نامشخص",
        "block": "مسدود شده",
    }.get(shell_tier, "")

    # Layer 2: If command writes files, check content
    # (this is called externally for file writes, not inline for commands)

    # Layer 4: Context modifier
    risk = context_risk_modifier(risk, role, recent_blocks)

    # Layer 6: Auto rules
    auto_decision = check_auto_rules(cmd)

    return ApprovalDecision(
        tier=shell_tier, risk_level=risk, reason=reason,
        risk_tags=tags, auto_decision=auto_decision,
    )


def classify_file_write(path: str, content: str, role: str = "associate") -> ApprovalDecision:
    """Classify a file write operation (Layers 1-6 for files)."""
    if not content:
        return ApprovalDecision("safe", 0, "فایل خالی")

    analysis = analyze_file_content(content)
    risk = analysis["risk_level"]
    findings = analysis["findings"]

    if risk >= 8:
        return ApprovalDecision("block", risk, f"محتوای خطرناک: {'; '.join(findings[:3])}",
                                risk_tags=findings)
    elif risk >= 4:
        return ApprovalDecision("guard", risk, f"محتوای مشکوک: {'; '.join(findings[:3])}",
                                risk_tags=findings)
    return ApprovalDecision("safe", risk, "محتوای فایل ایمن به نظر می‌رسد")


def classify_url(url: str, role: str = "associate") -> ApprovalDecision:
    """Classify a URL operation (Layer 3)."""
    analysis = analyze_url_safety(url)
    risk = analysis["risk_level"]
    findings = analysis["findings"]

    if risk >= 8:
        return ApprovalDecision("block", risk, f"URL خطرناک: {'; '.join(findings[:3])}",
                                risk_tags=findings)
    elif risk >= 4:
        return ApprovalDecision("guard", risk, f"URL مشکوک: {'; '.join(findings[:3])}",
                                risk_tags=findings)
    return ApprovalDecision("safe", risk, "URL به نظر ایمن می‌رسد")


# =========================================================
# Pending approval storage (in-memory, per session)
# =========================================================

_pending_approvals: dict[str, dict] = {}
import time


def _gen_approval_id(command: str, user_id: int) -> str:
    raw = f"{command}:{user_id}:{time.time()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:12]


def create_approval_request(command: str, user_id: int, role: str = "associate") -> dict:
    decision = classify_command(command, role)
    aid = _gen_approval_id(command, user_id)
    _pending_approvals[aid] = {
        "command": command, "user_id": user_id, "role": role,
        "risk_tags": decision.risk_tags, "reason": decision.reason,
        "risk_level": decision.risk_level,
        "timestamp": time.time(),
    }
    return {"approval_id": aid, "command": command, "reason": decision.reason,
            "risk_level": decision.risk_level, "risk_tags": decision.risk_tags}


async def approve_request(approval_id: str, admin_id: int = 0) -> bool:
    req = _pending_approvals.pop(approval_id, None)
    if req and time.time() - req["timestamp"] < 300:
        await audit_log(req["user_id"], "approve", req["command"],
                        req["risk_level"], "approved", req["risk_tags"],
                        actor_id=admin_id)
        return True
    return False


async def reject_request(approval_id: str, admin_id: int = 0) -> bool:
    req = _pending_approvals.pop(approval_id, None)
    if req:
        await audit_log(req["user_id"], "reject", req["command"],
                        req["risk_level"], "rejected", req["risk_tags"],
                        actor_id=admin_id)
        return True
    return False


def get_pending_approvals() -> list[dict]:
    now = time.time()
    expired = [k for k, v in _pending_approvals.items() if now - v["timestamp"] > 300]
    for k in expired:
        del _pending_approvals[k]
    return [{"approval_id": k, **v} for k, v in _pending_approvals.items()]


# =========================================================
# Legacy compatibility
# =========================================================

@dataclass
class ApprovalResult:
    tier: str
    reason: str
    needs_approval: bool = False
    risk_tags: list = None
    def __post_init__(self):
        if self.risk_tags is None:
            self.risk_tags = []


def _identify_risk(cmd: str, matched_pat=None) -> str:
    low = cmd.lower()
    if any(x in low for x in ("pip", "npm", "apt", "brew", "yarn")):
        return "📦 نصب بسته"
    if any(x in low for x in ("curl", "wget", "ssh", "scp", "rsync")):
        return "🌐 عملیات شبکه"
    if any(x in low for x in ("docker", "kubectl", "compose")):
        return "🐳 کانتینر"
    if "rm" in low:
        return "🗑 حذف فایل"
    if any(x in low for x in ("chmod", "chown", "sudo")):
        return "🔒 تغییر مجوزها"
    if any(x in low for x in ("env", "export")):
        return "⚙️ متغیر محیطی"
    if any(x in low for x in ("drop", "truncate", "delete")):
        return "🗄 عملیات دیتابیس"
    if any(x in low for x in ("kill", "pkill")):
        return "⚡ مدیریت پروسس"
    return "⚠️ نامشخص"
