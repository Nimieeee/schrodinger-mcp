"""Preparation tools (async): LigPrep, Protein Preparation Wizard, Epik, ConfGen.

Each submits a Schrödinger job and returns a job_id. Inputs are copied into the job
directory and referenced by basename (several launchers require inputs in the cwd);
outputs land in the same job directory. Flag sets verified against Suite 2026-1.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .. import runner
from ..errors import InvalidInput
from . import _async, _common

_LIGPREP_IN = {".smi": "-ismi", ".csv": "-icsv", ".sdf": "-isd", ".sd": "-isd", ".mae": "-imae", ".maegz": "-imae"}


def _ligprep_in_flag(path: Path) -> str:
    suf = path.suffix.lower()
    if suf not in _LIGPREP_IN:
        raise InvalidInput(f"unsupported ligprep input format: {suf}", supported=".smi/.csv/.sdf/.mae")
    return _LIGPREP_IN[suf]


def _to_mae(path: Path) -> tuple[Path, Optional[str]]:
    """Return (mae_path, staged_name). If already mae/maegz, use as-is; else convert."""
    if path.suffix.lower() in (".mae", ".maegz"):
        return path, None
    out = _common.results_dir("toconv") / (path.stem + ".maegz")
    runner.run_launcher([_common.utility("structconvert"), str(path), str(out)], timeout=300)
    return out, None


def ligprep(
    input_path: str,
    use_epik: bool = True,
    ph: float = 7.0,
    ph_tolerance: float = 2.0,
    max_stereoisomers: int = 4,
    output_name: str = "ligprep_out.maegz",
) -> dict:
    """Prepare ligands for docking: add hydrogens, generate ionization/tautomeric states
    (via Epik), enumerate stereoisomers, and produce optimized 3D structures. Accepts
    .smi/.csv/.sdf/.mae. Long-running — returns a job_id. Prepared ligands are written to
    <output_name> in the job directory (fetch the path with get_job_results)."""
    inp = _common.validate_input_path(input_path)
    in_flag = _ligprep_in_flag(inp)
    argv = [_common.launcher("ligprep"), in_flag, inp.name, "-omae", output_name]
    if use_epik:
        argv += ["-epik", "-ph", str(ph), "-pht", str(ph_tolerance)]
    else:
        argv += ["-i", "1", "-ph", str(ph), "-pht", str(ph_tolerance)]
    argv += ["-s", str(int(max_stereoisomers))]
    argv += ["-HOST", "localhost", "-NJOBS", str(_async.njobs()), "-WAIT"]
    return _async.submit_async(
        "ligprep", argv, label=f"ligprep:{inp.name}", stage_copy=[str(inp)]
    )


def protein_prepwizard(
    input_path: str,
    fill_sidechains: bool = True,
    fill_loops: bool = False,
    epik_ph: float = 7.4,
    minimize: bool = True,
    output_name: str = "prepared.maegz",
) -> dict:
    """Prepare a protein structure for docking with the Protein Preparation Wizard:
    assign bond orders, add/optimize hydrogens, set het-group protonation states (Epik),
    optionally fill missing side chains/loops (Prime), and restrained-minimize. Accepts
    .pdb/.mae/.cif. Long-running — returns a job_id; prepared structure is <output_name>."""
    inp = _common.validate_input_path(input_path)
    argv = [_common.utility("prepwizard")]
    if fill_sidechains:
        argv.append("-fillsidechains")
    if fill_loops:
        argv.append("-fillloops")
    argv += ["-epik_pH", str(epik_ph), "-epik_pHt", "2.0"]
    if not minimize:
        argv.append("-noimpref")
    argv += ["-HOST", "localhost", "-WAIT", inp.name, output_name]
    return _async.submit_async(
        "prepwizard", argv, label=f"prepwizard:{inp.name}", stage_copy=[str(inp)]
    )


def epik(
    input_path: str,
    ph: float = 7.0,
    ph_tolerance: float = 2.0,
    max_states: int = 8,
    output_name: str = "epik_out.maegz",
) -> dict:
    """Enumerate protonation/tautomeric states and estimate pKa for ligands with Epik.
    Accepts a structure file (.mae/.maegz/.sdf — non-Maestro inputs are auto-converted).
    Long-running — returns a job_id; states with pKa/penalty properties in <output_name>."""
    inp = _common.validate_input_path(input_path)
    mae, _ = _to_mae(inp)
    argv = [
        _common.launcher("epik"),
        "-imae", mae.name,
        "-omae", output_name,
        "-ph", str(ph),
        "-pht", str(ph_tolerance),
        "-ms", str(int(max_states)),
        "-HOST", "localhost", "-WAIT",
    ]
    return _async.submit_async("epik", argv, label=f"epik:{inp.name}", stage_copy=[str(mae)])


def confgen(
    input_path: str,
    max_conformers: int = 50,
    optimize: bool = True,
    jobname: str = "confgen",
) -> dict:
    """Generate a conformer ensemble for ligands with ConfGen. Input must contain explicit
    hydrogens (run ligprep first). Accepts .mae/.maegz/.mol2/.sdf. Long-running — returns a
    job_id; conformers are written to <jobname>-out.maegz in the job directory."""
    inp = _common.validate_input_path(input_path)
    argv = [_common.launcher("confgen"), "-m", str(int(max_conformers)), "-j", jobname]
    if optimize:
        argv.append("-optimize")
    argv += ["-HOST", "localhost", "-WAIT", inp.name]
    return _async.submit_async(
        "confgen", argv, label=f"confgen:{inp.name}", stage_copy=[str(inp)],
        extra={"expected_output": f"{jobname}-out.maegz"},
    )


def register(mcp) -> None:
    for fn in (ligprep, protein_prepwizard, epik, confgen):
        mcp.tool()(fn)
