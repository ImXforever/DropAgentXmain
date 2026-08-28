"""
DropAgentX v3 — Skills Guard.

Ported + adapted from Hermes Agent's `tools/skills_guard.py`. The purpose is to
keep *installable skills* (SKILL.md files, plugins, prompts) from smuggling
dangerous behaviour into the bot. Skills are the most dangerous "add-on" surface
because they can contain arbitrary instructions, shell commands or prompt
injection.

What it does (as a pure, dependency-light scanner):
  * `ScanResult` — outcome flags per skill.
  * `content_hash` — stable hash for provenance / lock files.
  * `TRUSTED_REPOS` — allow-listed origins for auto-trust.
  * `scan_skill_text(text, origin)` — the core: returns a ScanResult with
    booleans for dangerous/suspicious/trusted + reasons. Never raises.
  * `scan_skill_file(path)` — read + scan a SKILL.md on disk.

Design is *conservative*: default action is "flag" — any hit sets a flag and
returns reasons for an admin to review. It never silently executes anything.
"""

from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass, field
from typing import List

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Repos/skills we trust by default (no flagging). Kept minimal + explicit.
TRUSTED_REPOS = {
    "NousResearch/hermes-agent",
    "9router",
    "radius-workshop/radius-hermes-railway-template",
}

# Patterns that are outright BLOCKED (auto-reject) in skill content.
_BLOCK_PATTERNS = [
    re.compile(r"\brm\s+-rf?\s+/", re.I),
    re.compile(r"\b(shutdown|poweroff|reboot)\b", re.I),
    re.compile(r"curl\s+.*\|\s*(sh|bash)", re.I),   # curl | sh
    re.compile(r"base64\s+-d.*\|\s*(sh|bash)", re.I),
    re.compile(r"\beval\s*\(", re.I),
    re.compile(r"\bexec\s*\(\s*['\"]?\b(system|open)", re.I),
    re.compile(r"\b(wget|curl)\s+.*-o\s+/etc/", re.I),
]

# Patterns that are SUSPICIOUS (prompt-injection / exfiltration) — flag, don't block.
_SUSPICIOUS_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.I),
    re.compile(r"disregard\s+(all\s+)?prior\s+instructions", re.I),
    re.compile(r"you\s+are\s+now\s+(a\s+|an\s+)?(root|god|admin|without\s+restrictions)", re.I),
    re.compile(r"\[INST\]|<\/s>|<\|im_start\|>", re.I),         # LLM fence-markers
    re.compile(r"\b(system|user|assistant)\s*:\s*", re.I),      # role-spoofing
    re.compile(r"(api[_-]?key|password|secret|token)\b", re.I),
    re.compile(r"\b(http|https)://\S+", re.I),                    # unbounded URL fetch
    re.compile(r"\sssh\s|scp\s+", re.I),
]

_MAX_TEXT = 200_000  # never read more than this from a file


@dataclass
class ScanResult:
    ok: bool                  # True => safe to install / run
    blocked: bool             # hit a BLOCK pattern => reject
    suspicious: bool          # hit a SUSPICIOUS pattern => needs review
    trusted: bool             # origin is in TRUSTED_REPOS
    reasons: list = field(default_factory=list)
    sha: str = ""


def content_hash(text: str) -> str:
    """Stable SHA-256 for provenance / lock files."""
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _is_trusted(origin: str) -> bool:
    if not origin:
        return False
    o = origin.lower()
    return any(r.lower() in o for r in TRUSTED_REPOS)


def scan_skill_text(text: str, origin: str = "") -> ScanResult:
    """Scan skill content. Returns a ScanResult; never raises."""
    text = text or ""
    sha = content_hash(text)
    trusted = _is_trusted(origin)
    reasons: List[str] = []
    blocked = False
    suspicious = False

    for pat in _BLOCK_PATTERNS:
        m = pat.search(text)
        if m:
            blocked = True
            reasons.append(f"blocked: {m.group(0)[:60]}")
            break

    for pat in _SUSPICIOUS_PATTERNS:
        m = pat.search(text)
        if m:
            suspicious = True
            reasons.append(f"suspicious: {m.group(0)[:60]}")

    # Trusted repos: down-weight but don't blindly trust (still flag hard-broken).
    ok = (not blocked) and (not suspicious or trusted)
    return ScanResult(ok=ok, blocked=blocked, suspicious=suspicious,
                      trusted=trusted, reasons=reasons, sha=sha)


def scan_skill_file(path: str, origin: str = "") -> ScanResult:
    """Read + scan a SKILL.md / plugin file on disk."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            text = f.read(_MAX_TEXT)
    except OSError as e:
        return ScanResult(ok=False, blocked=True, suspicious=False, trusted=False,
                          reasons=[f"unreadable: {e}"], sha="")
    return scan_skill_text(text, origin=origin or os.path.basename(path))


# Convenience: filter a list of skill dicts, returning the ones deemed safe.
def filter_safe(skills: list, field_name: str = "content", origin_field: str = "origin") -> list:
    out = []
    for s in skills:
        text = s.get(field_name, "") if isinstance(s, dict) else str(s)
        origin = s.get(origin_field, "") if isinstance(s, dict) else ""
        r = scan_skill_text(text, origin=origin)
        if r.ok:
            out.append(s)
    return out
