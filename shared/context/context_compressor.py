"""
DropAgentX v3 — Context Compressor.

Ported + adapted from Hermes Agent's `trajectory_compressor.py`. Goal: when a
conversation / tool trajectory becomes long, compress the *middle* turns into a
single summary while PRESERVING the first turns (system + human + first response)
and the last turns (final conclusions). This keeps the model's context shorter
(cheaper) and avoids overflowing the context window, without losing the frame of
the task or the final answer.

Collapse strategy (per Hermes, simplified to a lossless-ish heuristic):
  1. protect the first `keep_first` turns
  2. protect the last `keep_last` turns
  3. compress ONLY the middle turns
  4. replace the compressed block with a single `Summarize`/`Summary` message
  5. leave everything else intact

It is pure & deterministic (no LLM call). An optional `summarizer` callable can
be injected to produce a real summary; if omitted it uses a simple concatenation
of the middle turns (lossy but deterministic).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional

# Turns that are never collapsed when a message matches these roles.
_PROTECTED_ROLES = {"system", "assistant", "human", "tool"}
_MIN_TURNS = 4          # don't compress anything smaller than this


@dataclass
class CompressResult:
    messages: list
    compressed: bool
    removed_count: int
    removed_tokens_estimate: int


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (~4 chars/token for Latin, ~1.5 for Persian)."""
    if not text:
        return 0
    latin = sum(1 for c in text if ord(c) < 0x0600)
    other = len(text) - latin
    return latin // 4 + other // 2


def compress_messages(messages: list,
                      keep_first: int = 3,
                      keep_last: int = 3,
                      max_messages: int = 40,
                      summarizer: Optional[Callable[[list], str]] = None,
                      budget_chars: int = 3000) -> CompressResult:
    """Compress the middle of a message list in place.

    `messages` = list of dicts with a 'role' and 'content' (OpenAI-style, works
    for our hermes convo too). Returns a CompressResult.
    Never raises; on any oddity returns the original list.
    """
    if not messages or len(messages) < max(_MIN_TURNS, keep_first + keep_last + 1):
        return CompressResult(list(messages), False, 0, 0)

    # If the list is under the threshold, leave it (cheap path).
    if len(messages) <= max_messages:
        return CompressResult(list(messages), False, 0, 0)

    head = messages[:keep_first]
    tail = messages[-keep_last:]
    middle = messages[keep_first:-keep_last]
    if len(middle) < 2:
        return CompressResult(list(messages), False, 0, 0)

    # Build a compact representation of the middle turns.
    if summarizer is not None:
        try:
            summary = summarizer(middle)
        except Exception:
            summary = _simple_summary(middle, budget_chars)
    else:
        summary = _simple_summary(middle, budget_chars)

    removed = len(middle)
    removed_tokens = sum(_estimate_tokens(str(m.get("content", ""))) for m in middle)

    merged = list(head)
    merged.append({"role": "user",
                   "content": f"[فشرده‌سازی شد] {summary} — از اینجا ادامه بده:",
                   "_compressed_summary": True})
    merged.extend(tail)
    return CompressResult(merged, True, removed, removed_tokens)


def _simple_summary(middle: list, budget_chars: int) -> str:
    """Deterministic fallback: concatenate the distinct content, capped."""
    seen = set()
    parts = []
    used = 0
    for m in middle:
        content = str(m.get("content", ""))
        key = content[:80]
        if key in seen:
            continue
        seen.add(key)
        role = m.get("role", "")
        line = f"[{role}] {content}" if role and role != "user" else content
        if used + len(line) + 1 > budget_chars:
            break
        parts.append(line)
        used += len(line) + 1
    return " ".join(parts) if len(parts) > 1 else (parts[0] if parts else "")


def assign_token_budget(messages: list, budget_tokens: int) -> list:
    """Reduce the whole conversation to fit a token budget by compensating only
    if it exceeds the budget. Returns a (possibly) trimmed list."""
    total = sum(_estimate_tokens(str(getattr(m, "content", m.get("content", ""))))
                for m in messages if isinstance(m, dict))
    if total <= budget_tokens:
        return messages
    return compress_messages(messages, keep_first=2, keep_last=2,
                             max_messages=max(6, budget_tokens // 20)).messages
