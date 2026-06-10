"""Foundation tools: installation probe, PDB fetch, format conversion, structure
info, SMILES→3D, split/merge. All synchronous (seconds) and mostly license-free.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .. import installation, runner
from ..errors import WorkerError
from . import _common


def detect_installation() -> dict:
    """Report the Schrödinger installation: root path, release/build, licensed
    products, configured job hosts, and GPU availability. Call this first to confirm
    the suite is found and to see which workflows are licensed. GPU-accelerated
    workflows (Desmond MD, FEP+) require an NVIDIA GPU and are unavailable on Apple Silicon."""
    return installation.describe()


def fetch_pdb(pdb_id: str, output_dir: Optional[str] = None) -> dict:
    """Download an experimental structure from the RCSB PDB by its 4-character ID
    (e.g. '1HSG'). Returns the path to the downloaded .pdb file. Use protein_prepwizard
    afterward to prepare it for docking."""
    pid = (pdb_id or "").strip()
    if len(pid) != 4 or not pid.isalnum():
        from ..errors import InvalidInput

        raise InvalidInput(f"PDB id must be 4 alphanumeric characters, got: {pdb_id!r}")
    out_dir = Path(output_dir).expanduser().resolve() if output_dir else _common.results_dir("pdb")
    out_dir.mkdir(parents=True, exist_ok=True)
    runner.run_launcher([_common.utility("getpdb"), pid.lower()], cwd=out_dir, timeout=120)
    hits = list(out_dir.glob(f"{pid.lower()}.pdb")) + list(out_dir.glob(f"{pid.upper()}.pdb"))
    if not hits:
        hits = list(out_dir.glob("*.pdb")) + list(out_dir.glob("*.cif"))
    if not hits:
        raise WorkerError(f"getpdb did not produce a file for {pid}", dir=str(out_dir))
    path = hits[0]
    return {
        "pdb_id": pid.upper(),
        "path": str(path),
        "size_bytes": path.stat().st_size,
        "outputs": [str(path)],
        "summary": f"Downloaded {pid.upper()} to {path}",
    }


def convert_structure(
    input_path: str,
    output_format: str,
    output_path: Optional[str] = None,
) -> dict:
    """Convert a structure file between formats (mae, maegz, sdf, pdb, mol2, smi, cif).
    Schrödinger infers the input format from its extension. Returns the output path."""
    inp = _common.validate_input_path(input_path)
    ext = _common.ext_for(output_format)
    out = _common.resolve_output_path(
        output_path,
        default_dir=_common.results_dir("convert"),
        default_name=inp.stem + ext,
    )
    runner.run_launcher([_common.utility("structconvert"), str(inp), str(out)], timeout=300)
    if not out.exists():
        raise WorkerError("structconvert reported success but no output file was created")
    return {
        "input": str(inp),
        "output_path": str(out),
        "output_format": _common.normalize_format(output_format),
        "size_bytes": out.stat().st_size,
        "outputs": [str(out)],
        "summary": f"Converted {inp.name} → {out.name}",
    }


def structure_info(input_path: str, max_structures: int = 100) -> dict:
    """Inspect a structure file: number of structures, per-structure atom/bond counts,
    title, formal charge, molecular weight, chains/residues, and a sample of named
    properties (e.g. docking scores). Works on any format Schrödinger reads."""
    inp = _common.validate_input_path(input_path)
    return runner.run_worker(
        "structure_info", {"path": str(inp), "max_structures": int(max_structures)}
    )


def smiles_to_3d(
    smiles: list[str],
    output_format: str = "sdf",
    output_path: Optional[str] = None,
    titles: Optional[list[str]] = None,
    require_stereo: bool = False,
) -> dict:
    """Generate single-conformer 3D structures from a list of SMILES strings and write
    them to one file. Good for quick 3D embedding; for full ligand preparation
    (ionization, tautomers, stereoisomer enumeration) use the ligprep tool instead.
    Returns per-molecule results and the output path."""
    if isinstance(smiles, str):
        smiles = [smiles]
    if not smiles:
        from ..errors import InvalidInput

        raise InvalidInput("smiles list is empty")
    ext = _common.ext_for(output_format)
    out = _common.resolve_output_path(
        output_path,
        default_dir=_common.results_dir("smiles3d"),
        default_name="ligands" + ext,
    )
    result = runner.run_worker(
        "smiles_to_3d",
        {
            "smiles": list(smiles),
            "titles": list(titles) if titles else [],
            "output_path": str(out),
            "require_stereo": bool(require_stereo),
        },
    )
    result["outputs"] = [result["output_path"]]
    n = result.get("num_written", 0)
    result["summary"] = f"Built {n}/{result.get('num_input')} 3D structures → {out.name}"
    return result


def split_structures(
    input_path: str,
    output_dir: Optional[str] = None,
    output_format: str = "mae",
) -> dict:
    """Split a multi-structure file into one file per structure. Returns the list of
    written files with their titles."""
    inp = _common.validate_input_path(input_path)
    fmt = _common.normalize_format(output_format)
    out_dir = (
        Path(output_dir).expanduser().resolve() if output_dir else _common.results_dir("split")
    )
    result = runner.run_worker(
        "split_merge",
        {"mode": "split", "path": str(inp), "output_dir": str(out_dir), "format": fmt},
    )
    result["outputs"] = [f["path"] for f in result.get("files", [])]
    result["summary"] = f"Split {inp.name} into {result.get('count')} files in {out_dir}"
    return result


def merge_structures(input_paths: list[str], output_path: str) -> dict:
    """Concatenate several structure files into one multi-structure file."""
    inps = [str(_common.validate_input_path(p)) for p in input_paths]
    out = _common.resolve_output_path(
        output_path, default_dir=_common.results_dir("merge"), default_name="merged.mae"
    )
    result = runner.run_worker("split_merge", {"mode": "merge", "paths": inps, "output_path": str(out)})
    result["outputs"] = [result["output_path"]]
    result["summary"] = f"Merged {len(inps)} files → {out.name} ({result.get('num_structures')} structures)"
    return result


def register(mcp) -> None:
    for fn in (
        detect_installation,
        fetch_pdb,
        convert_structure,
        structure_info,
        smiles_to_3d,
        split_structures,
        merge_structures,
    ):
        mcp.tool()(fn)
