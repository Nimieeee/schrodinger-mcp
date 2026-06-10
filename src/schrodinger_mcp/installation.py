"""Locate and describe the Schrödinger installation (macOS, Linux, Windows).

Resolution order:
1. ``$SCHRODINGER`` environment variable (if valid).
2. Autodetect the platform's default install location, highest version wins:
   - Linux:   ``/opt/schrodinger/suites*``
   - macOS:   ``/opt/schrodinger/suites*``, ``/Applications/SchrodingerSuites*``
   - Windows: ``%SCHRODINGER%``, ``C:\\Program Files\\Schrodinger*``, ``Schrodinger\\*``

A candidate is valid iff a ``run`` launcher (``run``/``run.exe``/``run.bat``) and
``version.txt`` exist. The resolved root is cached for the life of the process.
"""

from __future__ import annotations

import functools
import os
import platform
import re
import subprocess
from pathlib import Path
from typing import Optional

from . import platformutil
from .errors import InstallationNotFound

# Match version tokens in folder names: "suites2026-1", "Schrodinger2026-1", etc.
_SUITE_RE = re.compile(r"(\d{4})-(\d+)")


def _is_valid_root(root: Path) -> bool:
    return platformutil.is_executable(root / "run") and (root / "version.txt").exists()


def _suite_sort_key(path: Path):
    m = _SUITE_RE.search(path.name)
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))


def _glob_sorted(base: Path, pattern: str) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(base.glob(pattern), key=_suite_sort_key, reverse=True)


def _candidate_roots() -> list[Path]:
    candidates: list[Path] = []
    env = os.environ.get("SCHRODINGER")
    if env:
        candidates.append(Path(env))

    if platformutil.IS_WINDOWS:
        for base_env in ("ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"):
            base = os.environ.get(base_env)
            if base:
                candidates += _glob_sorted(Path(base), "Schrodinger*")
                candidates += _glob_sorted(Path(base) / "Schrodinger", "*")
        for drive in ("C:\\", "D:\\"):
            candidates += _glob_sorted(Path(drive), "Schrodinger*")
    else:
        for base in ("/opt/schrodinger", str(Path.home() / "schrodinger")):
            candidates += _glob_sorted(Path(base), "suites*")
        candidates += _glob_sorted(Path("/Applications"), "SchrodingerSuites*")
    return candidates


@functools.lru_cache(maxsize=1)
def find_root() -> Path:
    """Return the validated Schrödinger install root, or raise InstallationNotFound."""
    tried = []
    for cand in _candidate_roots():
        tried.append(str(cand))
        if _is_valid_root(cand):
            return cand
    example = (
        r"C:\Program Files\Schrodinger2026-1"
        if platformutil.IS_WINDOWS
        else "/opt/schrodinger/suites2026-1"
    )
    raise InstallationNotFound(
        "Could not locate a valid Schrödinger installation. Set the SCHRODINGER "
        f"environment variable to the install root (e.g. {example}).",
        tried=",".join(tried) or "none",
    )


def run_path() -> Path:
    """Absolute path to the ``run`` launcher (``run``/``run.exe``/``run.bat``)."""
    resolved = platformutil.resolve_executable(find_root() / "run")
    return resolved or (find_root() / "run")


def tool_path(name: str, *, utility: bool = False) -> Path:
    """Resolve a launcher/utility by base name to its platform-specific executable."""
    root = find_root()
    base = (root / "utilities" / name) if utility else (root / name)
    return platformutil.resolve_executable(base) or base


def child_env(extra: Optional[dict] = None) -> dict:
    """Environment for child processes: inherit ours but pin SCHRODINGER explicitly."""
    env = dict(os.environ)
    env["SCHRODINGER"] = str(find_root())
    if extra:
        env.update({k: str(v) for k, v in extra.items()})
    return env


def version_info() -> dict:
    """Parse ``version.txt`` into {release, build, raw}."""
    root = find_root()
    raw = (root / "version.txt").read_text(errors="replace").strip()
    release = build = None
    m = re.search(r"(\d{4}-\d+)", raw)
    if m:
        release = m.group(1)
    m = re.search(r"[Bb]uild\s+(\d+)", raw)
    if m:
        build = m.group(1)
    return {"release": release, "build": build, "raw": raw}


# Workflow -> the launcher/utility that backs it. Presence on disk is what determines
# whether an MCP tool can run; license tokens are verified by Schrödinger at job time.
_WORKFLOW_ENTRYPOINTS = {
    "ligprep": ("top", "ligprep"),
    "epik": ("top", "epik"),
    "confgen": ("top", "confgen"),
    "glide": ("top", "glide"),
    "qikprop": ("top", "qikprop"),
    "sitemap": ("top", "sitemap"),
    "shape_screen": ("top", "shape_screen"),
    "prime_mmgbsa": ("top", "prime_mmgbsa"),
    "jaguar": ("top", "jaguar"),
    "desmond": ("top", "desmond"),
    "prepwizard": ("util", "prepwizard"),
    "structconvert": ("util", "structconvert"),
    "getpdb": ("util", "getpdb"),
    "generate_glide_grids": ("util", "generate_glide_grids"),
    "canvasMolDescriptors": ("util", "canvasMolDescriptors"),
}


def installed_workflows() -> dict:
    """Which workflow entry points are present on disk (-> the MCP tools that can run).

    This is more reliable than parsing the encrypted license file: it reports what is
    actually installed. License availability is enforced by Schrödinger at job submission.
    """
    out = {}
    for name, (kind, tool) in _WORKFLOW_ENTRYPOINTS.items():
        out[name] = platformutil.resolve_executable(_entrypoint_base(kind, tool)) is not None
    return out


def _entrypoint_base(kind: str, tool: str) -> Path:
    root = find_root()
    return (root / tool) if kind == "top" else (root / "utilities" / tool)


def hosts(timeout: int = 10) -> list[dict]:
    """Parse ``schrodinger.hosts`` into a list of {name, processors, schrodinger}."""
    root = find_root()
    path = root / "schrodinger.hosts"
    out: list[dict] = []
    if not path.exists():
        return out
    current: dict = {}
    for line in path.read_text(errors="replace").splitlines():
        line = line.split("#", 1)[0].rstrip()
        if not line.strip():
            if current:
                out.append(current)
                current = {}
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            current[key.strip()] = val.strip()
    if current:
        out.append(current)
    return out


def gpu_available() -> dict:
    """Report GPU situation. NVIDIA/CUDA is required for Desmond GPU-MD and FEP+."""
    info = {"nvidia": False, "platform": platform.platform(), "machine": platform.machine()}
    system = platform.system()
    try:
        if system == "Darwin":
            out = subprocess.run(
                ["system_profiler", "SPDisplaysDataType"],
                capture_output=True, text=True, timeout=20,
            ).stdout
            info["nvidia"] = "nvidia" in out.lower()
            m = re.search(r"Chipset Model:\s*(.+)", out)
            if m:
                info["chipset"] = m.group(1).strip()
        else:
            # Linux/Windows: nvidia-smi is the portable signal for a usable NVIDIA GPU.
            smi = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True, text=True, timeout=20,
            )
            if smi.returncode == 0 and smi.stdout.strip():
                info["nvidia"] = True
                info["chipset"] = smi.stdout.strip().splitlines()[0]
    except Exception:
        pass
    return info


def describe() -> dict:
    """Full installation summary used by detect_installation and the resource."""
    root = find_root()
    return {
        "schrodinger_root": str(root),
        "run": str(run_path()),
        "version": version_info(),
        "hosts": hosts(),
        "gpu": gpu_available(),
        "installed_workflows": installed_workflows(),
        "notes": (
            "Workflow availability is based on installed launchers; license tokens are "
            "verified by Schrödinger at job submission. GPU-accelerated workflows "
            "(Desmond MD, FEP+) require an NVIDIA/CUDA GPU and are not exposed when none "
            "is detected (e.g. Apple Silicon)."
        ),
    }
