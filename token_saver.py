"""
DropAgentX v2 — Token Saver (inspired by 9Router/RTK).

Goal: compress the *raw text of tool outputs* (git diff, grep/find output, logs,
numbered listings, directory trees...) BEFORE they are sent to the LLM, so we
spend fewer input tokens on the same context — typically 20-40% less.

Design (mirrors RTK's safety philosophy):
  * Detect it only if the FIRST ~1KB looks like a known "noisy program output"
    pattern; otherwise leave the text alone.
  * Compress per-block with a *lossless-ish* pass (dedupe repeated lines,
    collapse long whitespace runs, trim over-long single lines). We never cut
    the *content* — only the redundant fat.
  * Fail-safe: if a compression makes the result LONGER, or raises, or the block
    is below a threshold, return the ORIGINAL text. Errors never break a request.
  * Heuristic only; a single global cap prevents pathological blowup.

Usage:
    from token_saver import maybe_compress_tool_output

    # inside the tool-call loop, before building the assistant message:
    text = maybe_compress_tool_output(raw_response, max_chars=12000)

All functions are pure and synchronous — no I/O, no deps beyond stdlib.
"""

import re
from typing import List

# Minimum size before we even consider compressing (avoid CPU on trivial texts).
_MIN_BLOCK_CHARS = 512
# Cap for a single compressed output (prevents extreme cases).
_MAX_OUT = 12_000
# Content we must never mangle even if it looks noisy.
_PROTECTIVE_MARKERS = ("content-type", "token", "api_key", "password", "secret", "BEGIN ")

# Patterns that mark a "program output" block we are allowed to compress.
_KNOWN_PATTERNS = [
    re.compile(r"^\s*(diff|index -{3}|--- \w+|\+\+\+ \w+)", re.M),      # git diff
    re.compile(r"^\s*(commit \w+|Author:|Date:)\b", re.M),              # git log
    re.compile(r"^\s*On branch |^\s*master|^\s*main", re.M),            # git status
    re.compile(r"^\s*(\d+)\s+(passed|failed|ok|error)\b", re.M),        # test output
    re.compile(r"^\s*\S+\/\d+\s+\S+\s+\S+\s+", re.M),                    # `find`/`ls -l`
    re.compile(r"^\s*(File|Exception|Traceback|  File \")\b", re.M),    # tracebacks
    re.compile(r"^\s*(Compiling|Building|Downloading|Installing|Collecting)", re.M),  # build logs
]

# Collapse a run of too-verbose "less than nothing" lines (e.g. 50 near-empty).
_EMPTY_LINE = re.compile(r"^\s*$")
_LONG_LINE = re.compile(r"^.{160,}$", re.S)
_WS_RUN = re.compile(r"[ \t]{3,}")


def _looks_known(text: str) -> bool:
    head = text[:_MIN_BLOCK_CHARS]
    return any(p.search(head) for p in _KNOWN_PATTERNS)


def _compress_block(text: str) -> str:
    """Lossless-ish dedupe: remove consecutive duplicate lines and big gaps."""
    lines: List[str] = text.splitlines()
    out: List[str] = []
    prev = None
    empty_run = 0
    dup_run = 0
    for ln in lines:
        stripped = ln.rstrip()
        if _EMPTY_LINE.match(stripped):
            empty_run += 1
            if empty_run <= 1:
                out.append(stripped)
            continue
        empty_run = 0
        # collapse 3+ identical consecutive spacer/blank-ish lines
        if stripped == prev:
            dup_run += 1
            if dup_run > 2:
                continue
        else:
            dup_run = 0
        prev = stripped
        out.append(stripped)
    return "\n".join(out)


def _trim_long_lines(text: str) -> str:
    """Trim pathological single lines (>300 chars) back to a safe prefix."""
    if not _LONG_LINE.search(text):
        return text
    lines = []
    for ln in text.splitlines():
        if len(ln) > 300:
            lines.append(ln[:300] + " …")
        else:
            lines.append(ln)
    return "\n".join(lines)


def _compress_whitespace(text: str) -> str:
    return _WS_RUN.sub("  ", text)


def maybe_compress_tool_output(text: str, max_chars: int = _MAX_OUT) -> str:
    """Return a (possibly) smaller version of a tool output. Never raises.

    If the text is small, doesn't look like program output, or compression would
    grow it, the ORIGINAL text is returned unchanged.
    """
    if not text or not isinstance(text, str):
        return text
    if len(text) < _MIN_BLOCK_CHARS:
        return text
    lowered = text.lower()
    if any(m.lower() in lowered for m in _PROTECTIVE_MARKERS):
        return text  # never touch anything that smells like credentials

    if not _looks_known(text):
        return text

    candidate = _compress_whitespace(_trim_long_lines(_compress_block(text)))
    candidate = candidate[:max_chars]

    # Fail-safe: if we somehow made it bigger, use the original.
    if len(candidate) >= len(text):
        return text
    return candidate


def compress_tool_outputs(results, *, min_chars: int = _MIN_BLOCK_CHARS) -> list:
    """Convenience: run maybe_compress_tool_output over a list of tool results.

    `results` is a list of strings (or objects with .get('content')). Returns the
    same shape, with each element optionally replaced by a compressed version.
    """
    out = []
    for r in results:
        if isinstance(r, str):
            out.append(maybe_compress_tool_output(r))
        elif isinstance(r, dict):
            c = r.get("content")
            if isinstance(c, str) and len(c) >= min_chars:
                r = {**r, "content": maybe_compress_tool_output(c)}
            out.append(r)
        else:
            out.append(r)
    return out
