"""QM & MM-GBSA tools: Prime MM-GBSA rescoring and Jaguar quantum mechanics.

Both are CPU-feasible on this hardware for single complexes / small molecules.
"""

from __future__ import annotations

from typing import Optional

from .. import runner
from ..errors import InvalidInput
from . import _async, _common


def prime_mmgbsa(
    input_path: str,
    ligand_asl: Optional[str] = None,
    minimize: bool = True,
) -> dict:
    """Rescore a receptor-ligand complex (or Glide pose-viewer file) with Prime MM-GBSA
    to estimate binding free energy (dG bind). Accepts a *_pv.maegz or a complex .mae.
    Long-running — returns a job_id; the output structures carry r_psp_MMGBSA_dG_Bind."""
    inp = _common.validate_input_path(input_path)
    argv = [_common.launcher("prime_mmgbsa"), inp.name]
    if ligand_asl:
        argv += ["-ligand", ligand_asl]
    if not minimize:
        argv += ["-job_type", "ENERGY"]
    argv += ["-HOST", "localhost", "-WAIT"]
    return _async.submit_async(
        "prime_mmgbsa", argv, label=f"mmgbsa:{inp.name}", stage_copy=[str(inp)]
    )


def jaguar_qm(
    input_path: str,
    calculation: str = "optimization",
    basis: str = "6-31G**",
    functional: str = "B3LYP",
    charge: Optional[int] = None,
    multiplicity: int = 1,
) -> dict:
    """Run a Jaguar quantum-mechanics calculation on a small molecule. `calculation` is
    'optimization', 'energy', or 'frequency'. Accepts a structure file (.mae/.pdb/.sdf)
    — a Jaguar input is built automatically — or a prebuilt Jaguar .in file. Long-running;
    returns a job_id. Keep systems small (a few dozen atoms) on CPU-only hardware."""
    inp = _common.validate_input_path(input_path)
    calc = calculation.lower()
    if calc not in ("optimization", "energy", "frequency"):
        raise InvalidInput("calculation must be optimization, energy, or frequency")

    stage_files = {}
    stage_copy = []
    if inp.suffix.lower() == ".in":
        stage_files["jaguar.in"] = inp.read_text()
    else:
        built = runner.run_worker(
            "jaguar_input",
            {
                "path": str(inp),
                "calculation": calc,
                "basis": basis,
                "functional": functional,
                "charge": charge,
                "multiplicity": int(multiplicity),
            },
        )
        stage_files["jaguar.in"] = built["input_text"]
        # Stage any companion geometry file (e.g. jaguar.mae referenced by MAEFILE:).
        stage_copy = list(built.get("companions") or [])

    argv = [_common.launcher("jaguar"), "run", "-WAIT", "-HOST", "localhost", "jaguar.in"]
    return _async.submit_async(
        "jaguar",
        argv,
        label=f"jaguar:{inp.name}",
        stage_files=stage_files,
        stage_copy=stage_copy,
        extra={"calculation": calc},
    )


def register(mcp) -> None:
    for fn in (prime_mmgbsa, jaguar_qm):
        mcp.tool()(fn)
