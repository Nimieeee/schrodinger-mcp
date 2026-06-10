"""Cross-platform helpers (POSIX + Windows).

Isolates every OS-specific operation the server needs: resolving executable names
(``run`` vs ``run.exe``/``run.bat``), spawning detached background processes,
killing a process tree, and liveness checks. POSIX behavior is unchanged; Windows
gets equivalent semantics via creation flags and ``taskkill``.
"""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Optional

IS_WINDOWS = os.name == "nt"

# Suffixes to try when resolving a Schrödinger launcher/utility by base name.
EXE_SUFFIXES = (".exe", ".bat", ".cmd", "") if IS_WINDOWS else ("",)


def resolve_executable(base: Path) -> Optional[Path]:
    """Given a path without extension (e.g. <root>/ligprep), return the first existing
    platform variant (ligprep, ligprep.exe, ligprep.bat, ...), or None."""
    for suffix in EXE_SUFFIXES:
        cand = base if suffix == "" else base.with_name(base.name + suffix)
        if cand.exists():
            return cand
    return None


def is_executable(base: Path) -> bool:
    return resolve_executable(base) is not None


def detached_popen_kwargs() -> dict:
    """Popen kwargs to launch a background process that survives the parent and does
    not pop a console window."""
    if IS_WINDOWS:
        flags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        return {"creationflags": flags}
    return {"start_new_session": True}


def kill_tree(pid: Optional[int]) -> bool:
    """Terminate a process and its children. Returns True if a signal was delivered."""
    if not pid:
        return False
    if IS_WINDOWS:
        proc = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
        )
        return proc.returncode == 0
    # POSIX: kill the whole process group started with start_new_session=True.
    try:
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        return True
    except (ProcessLookupError, PermissionError):
        try:
            os.kill(pid, signal.SIGTERM)
            return True
        except (ProcessLookupError, PermissionError):
            return False


def pid_alive(pid: Optional[int]) -> bool:
    if not pid:
        return False
    if IS_WINDOWS:
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True,
            text=True,
        )
        return str(pid) in (out.stdout or "")
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
