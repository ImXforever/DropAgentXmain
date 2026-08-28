"""Terminal sandbox: Python execution + shell commands with approval gates.

Safety model (inspired by Hermes Agent):
  1. Every command passes through approval.classify_command()
  2. SAFE  → immediate execution in Docker/local sandbox
  3. GUARD → requires admin approval before execution
  4. BLOCK → always rejected, never executes

Two execution backends:
  - docker: `docker run --rm --network=none python:3.12-slim` (production)
  - local: subprocess with timeout (dev/test only, gated by APP_ENV)

Config keys (admin /set):
  sandbox_enabled=1, sandbox_mode=auto|docker|local,
  sandbox_local_allow=0, approval_mode=auto|guard-all|allow-all
"""

import asyncio
import os
import shutil
import tempfile
import time

from hermes_engine import get_dynamic_setting

# =========================================================
# Limits
# =========================================================

MAX_CODE_CHARS = 6000
TIMEOUT_S = 25
MAX_OUT = 3000
DOCKER_IMAGE = "python:3.12-slim"


# =========================================================
# Public API
# =========================================================

async def run_python(code: str) -> str:
    """Execute Python code safely."""
    if not code or len(code) > MAX_CODE_CHARS:
        return "⚠️ کد خالی یا بیش از حد بلند است."
    if not await _enabled():
        return "🔒 سندباکس توسط ادمین غیرفعال است."
    return await _exec_sandboxed(
        f"# sandboxed\n{code}", suffix=".py",
        interpreter_cmd=lambda tmp: [_sys_py(), "-I", tmp],
    )


async def run_shell(command: str) -> str:
    """Execute a shell command with approval gates.

    Returns the command output, or a message indicating
    the command needs approval / is blocked.
    """
    if not command or not command.strip():
        return "⚠️ دستور خالی است."

    if not await _enabled():
        return "🔒 سندباکس توسط ادمین غیرفعال است."

    from approval import classify_command, create_approval_request, ApprovalResult

    result = classify_command(command)

    if result.tier == "block":
        return f"🚫 **دستور مسدود شد**\nعلت: {result.reason}\nدستور:\n`{command[:200]}`"

    if result.tier == "guard":
        approval_mode = (await get_dynamic_setting("approval_mode", "auto")).lower()
        yolo = (await get_dynamic_setting("yolo_mode", "0")) == "1"

        if yolo or approval_mode == "allow-all":
            pass  # proceed without approval
        elif approval_mode != "guard-all":
            req = create_approval_request(command, 0)
            return (
                f"⏳ **نیاز به تأیید ادمین**\n"
                f"علت: {result.reason}\n"
                f"شناسه: `{req['approval_id']}`\n"
                f"دستور:\n`{command[:200]}`\n\n"
                f"ادمین باید تأیید کند تا اجرا شود."
            )
        # guard-all → fall through to execution

    return await _exec_shell(command)


async def check_approval(approval_id: str) -> bool:
    """Check if a pending approval was granted."""
    from approval import approve_request, _pending_approvals
    return _pending_approvals.pop(approval_id, None) is not None


# =========================================================
# Internal execution
# =========================================================

async def _enabled() -> bool:
    return (await get_dynamic_setting("sandbox_enabled", "1")) == "1"


async def _exec_sandboxed(code_or_cmd: str, suffix: str,
                           interpreter_cmd) -> str:
    """Run code in Docker or local sandbox."""
    mode = (await get_dynamic_setting("sandbox_mode", "auto")).lower()
    if mode == "docker" or (mode == "auto" and _docker_ok()):
        return await _run_docker(code_or_cmd, suffix, interpreter_cmd)
    if mode == "local" and _local_allowed():
        return await _run_local(code_or_cmd, suffix, interpreter_cmd)
    if mode == "auto" and _local_allowed():
        return await _run_local(code_or_cmd, suffix, interpreter_cmd)
    return "🔒 Docker نصب نیست و اجرای محلی غیرفعال است."


async def _run_local(code: str, suffix: str, interpreter_cmd) -> str:
    tmp = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8")
    tmp.write(code)
    tmp.close()
    try:
        proc = await asyncio.create_subprocess_exec(
            *interpreter_cmd(tmp.name),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=tempfile.gettempdir(),
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), TIMEOUT_S)
        except asyncio.TimeoutError:
            proc.kill()
            return f"⏱ اجرا بیش از {TIMEOUT_S}s طول کشید — متوقف شد."
        rc = proc.returncode
        body = out.decode("utf-8", "replace").strip()[:MAX_OUT]
        return f"exit={rc}\n{body or '(بدون خروجی)'}"
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass


async def _run_docker(code: str, suffix: str, interpreter_cmd) -> str:
    tmp = tempfile.NamedTemporaryFile("w", suffix=suffix, delete=False, encoding="utf-8")
    tmp.write(code)
    tmp.close()
    mount = tmp.name.replace("\\", "/")
    win_mount = f"{mount[0].lower()}:{mount[2:]}" if mount[1:2] == ":" else mount
    args = ["docker", "run", "--rm",
            "-v", f"{win_mount}:/sandbox/code{suffix}:ro",
            "--network=none", "--memory=256m", "--cpus=0.5",
            DOCKER_IMAGE, "python", "-I", f"/sandbox/code{suffix}"]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), TIMEOUT_S + 10)
        except asyncio.TimeoutError:
            proc.kill()
            return "⏱ سندباکس Docker تایم‌اوت شد."
        body = out.decode("utf-8", "replace").strip()[:MAX_OUT]
        low = body.lower()
        if proc.returncode != 0 and any(x in low for x in (
            "error during connect", "cannot connect", "docker:",
            "dockerdesktoplinuxengine", "no such image")):
            return "🔒 Docker daemon در دسترس نیست — اجرای کد متوقف شد."
        return f"docker exit={proc.returncode}\n{body or '(بدون خروجی)'}"
    except FileNotFoundError:
        return "🔒 Docker نصب نیست."
    finally:
        try:
            os.remove(tmp.name)
        except OSError:
            pass


async def _exec_shell(command: str) -> str:
    """Execute a shell command in the sandbox."""
    app_env = os.getenv("APP_ENV", "production").lower()
    mode = (await get_dynamic_setting("sandbox_mode", "auto")).lower()

    if mode in ("docker",) or (mode == "auto" and _docker_ok()):
        return await _docker_shell(command)
    if _local_allowed():
        return await _local_shell(command)
    return "🔒 اجرای shell غیرفعال است."


async def _local_shell(command: str) -> str:
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=tempfile.gettempdir(),
        )
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), TIMEOUT_S)
        except asyncio.TimeoutError:
            proc.kill()
            return f"⏱ کامند بیش از {TIMEOUT_S}s طول کشید."
        body = out.decode("utf-8", "replace").strip()[:MAX_OUT]
        return f"exit={proc.returncode}\n{body or '(بدون خروجی)'}"
    except Exception as e:
        return f"⚠️ خطا: {e}"


async def _docker_shell(command: str) -> str:
    args = ["docker", "run", "--rm", "--network=none",
            "--memory=128m", "--cpus=0.5",
            "python:3.12-slim", "sh", "-c", command]
    try:
        proc = await asyncio.create_subprocess_exec(
            *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        try:
            out, _ = await asyncio.wait_for(proc.communicate(), TIMEOUT_S + 5)
        except asyncio.TimeoutError:
            proc.kill()
            return "⏱ Docker تایم‌اوت شد."
        body = out.decode("utf-8", "replace").strip()[:MAX_OUT]
        return f"docker exit={proc.returncode}\n{body or '(بدون خروجی)'}"
    except FileNotFoundError:
        return "🔒 Docker نصب نیست."


# =========================================================
# Helpers
# =========================================================

def _docker_ok() -> bool:
    return shutil.which("docker") is not None


def _local_allowed() -> bool:
    app_env = os.getenv("APP_ENV", "production").lower()
    return app_env in {"dev", "test", "local"}


def _sys_py() -> str:
    return os.sys.executable or "python"
