"""Shared helpers for tool implementations: path validation and output locations."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from .. import config, installation
from ..errors import InvalidInput

#: Structure formats we accept / emit, mapped to a canonical file extension.
FORMAT_EXT = {
    "mae": ".mae",
    "maegz": ".maegz",
    "sdf": ".sdf",
    "sd": ".sdf",
    "pdb": ".pdb",
    "mol2": ".mol2",
    "smi": ".smi",
    "smiles": ".smi",
    "cif": ".cif",
}


def validate_input_path(path: str, *, must_exist: bool = True) -> Path:
    """Resolve and validate a user-supplied input path."""
    if not path or not str(path).strip():
        raise InvalidInput("empty input path")
    p = Path(path).expanduser().resolve()
    if must_exist and not p.exists():
        raise InvalidInput(f"input file does not exist: {p}")
    if must_exist and not p.is_file():
        raise InvalidInput(f"input path is not a file: {p}")
    return p


def _under_install(p: Path) -> bool:
    try:
        p.resolve().relative_to(installation.find_root())
        return True
    except (ValueError, Exception):
        return False


def results_dir(prefix: str) -> Path:
    """A fresh directory under SCHRODINGER_MCP_HOME for a tool's outputs."""
    config.ensure_dirs()
    d = config.home() / "results" / f"{prefix}_{uuid.uuid4().hex[:8]}"
    d.mkdir(parents=True, exist_ok=True)
    return d


def resolve_output_path(
    output_path: Optional[str],
    *,
    default_dir: Path,
    default_name: str,
) -> Path:
    """Resolve an output path, rejecting writes into the Schrödinger install or
    system directories. If ``output_path`` is None, place ``default_name`` in
    ``default_dir``.
    """
    if output_path:
        p = Path(output_path).expanduser().resolve()
    else:
        p = (default_dir / default_name).resolve()
    if _under_install(p):
        raise InvalidInput(f"refusing to write inside the Schrödinger install: {p}")
    if str(p) in ("/", "") or p.parent == p:
        raise InvalidInput(f"unsafe output path: {p}")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def normalize_format(fmt: str) -> str:
    fmt = (fmt or "").lower().lstrip(".")
    if fmt not in FORMAT_EXT:
        raise InvalidInput(
            f"unsupported format '{fmt}'", supported=",".join(sorted(set(FORMAT_EXT)))
        )
    return fmt


def ext_for(fmt: str) -> str:
    return FORMAT_EXT[normalize_format(fmt)]


def utility(name: str) -> str:
    """Absolute path to a $SCHRODINGER/utilities/<name> tool."""
    return str(installation.find_root() / "utilities" / name)


def launcher(name: str) -> str:
    """Absolute path to a top-level $SCHRODINGER/<name> launcher."""
    return str(installation.find_root() / name)
