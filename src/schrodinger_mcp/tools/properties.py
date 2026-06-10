"""ADMET & site-analysis tools: QikProp, molecular descriptors, SiteMap, shape screen."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .. import runner
from ..errors import InvalidInput, WorkerError
from . import _async, _common


def _to_mae(path: Path) -> Path:
    if path.suffix.lower() in (".mae", ".maegz"):
        return path
    out = _common.results_dir("toconv") / (path.stem + ".maegz")
    runner.run_launcher([_common.utility("structconvert"), str(path), str(out)], timeout=300)
    return out


def qikprop(input_path: str, fast: bool = False, outname: str = "qikprop") -> dict:
    """Predict ~50 ADMET properties (aqueous solubility, Caco-2/MDCK permeability, logP,
    logBB, CNS activity, HERG, etc.) for ligands with QikProp. Accepts most structure
    formats. Long-running — returns a job_id; results land as a <outname>.CSV plus
    structures annotated with QP* properties. Use structure_info on the output .mae to read them."""
    inp = _common.validate_input_path(input_path)
    argv = [_common.launcher("qikprop"), "-outname", outname]
    if fast:
        argv.append("-fast")
    argv += [inp.name, "-HOST", "localhost", "-WAIT"]
    return _async.submit_async(
        "qikprop", argv, label=f"qikprop:{inp.name}", stage_copy=[str(inp)],
        extra={"expected_csv": f"{outname}.CSV"},
    )


def compute_descriptors(input_path: str, output_path: Optional[str] = None) -> dict:
    """Compute 2D physicochemical molecular descriptors (MW, logP, TPSA, H-bond
    donors/acceptors, rotatable bonds, ring counts, etc.) with Canvas. Synchronous —
    returns the path to a CSV of descriptors, one row per molecule."""
    inp = _common.validate_input_path(input_path)
    mae = _to_mae(inp)
    out = _common.resolve_output_path(
        output_path, default_dir=_common.results_dir("descriptors"), default_name="descriptors.csv"
    )
    argv = [_common.utility("canvasMolDescriptors"), "-imae", str(mae), "-All", "-ocsv", str(out)]
    proc = runner.run_launcher(argv, timeout=600, check=False)
    if not out.exists():
        raise WorkerError(
            "canvasMolDescriptors produced no output", stderr=(proc.stderr or proc.stdout or "")[-1000:]
        )
    nrows = max(0, len(out.read_text().splitlines()) - 1)
    return {
        "input": str(inp),
        "output_path": str(out),
        "num_molecules": nrows,
        "outputs": [str(out)],
        "summary": f"Computed descriptors for {nrows} molecules → {out.name}",
    }


def sitemap(input_path: str, num_sites: int = 5, jobname: str = "sitemap") -> dict:
    """Detect and score potential ligand-binding sites on a protein with SiteMap.
    Accepts a prepared protein structure (.mae). Long-running — returns a job_id; site
    maps and SiteScore/Dscore are written to <jobname>_out.maegz and per-site files."""
    inp = _common.validate_input_path(input_path)
    mae = _to_mae(inp)
    argv = [
        _common.launcher("sitemap"),
        "-j", jobname,
        "-prot", mae.name,
        "-maxsites", str(int(num_sites)),
        "-keepvolpts",
        "-HOST", "localhost", "-WAIT",
    ]
    return _async.submit_async("sitemap", argv, label=f"sitemap:{inp.name}", stage_copy=[str(mae)])


def shape_screen(
    query_path: str,
    screen_path: str,
    jobname: str = "shape",
    njobs: Optional[int] = None,
) -> dict:
    """Shape-based similarity screen: rank the 3D structures in `screen_path` by shape
    similarity to the `query_path` molecule. Both must be 3D structure files (prep ligands
    first). Long-running — returns a job_id; ranked hits with Shape_Sim scores are written
    to <jobname>_align.maegz."""
    query = _common.validate_input_path(query_path)
    screen = _common.validate_input_path(screen_path)
    argv = [
        _common.launcher("shape_screen"),
        "-shape", query.name,
        "-screen", screen.name,
        "-JOB", jobname,
        "-HOST", f"localhost:{_async.njobs(njobs)}",
        "-WAIT",
    ]
    return _async.submit_async(
        "shape_screen", argv, label=f"shape:{query.name}", stage_copy=[str(query), str(screen)],
        extra={"expected_output": f"{jobname}_align.maegz"},
    )


def register(mcp) -> None:
    for fn in (qikprop, compute_descriptors, sitemap, shape_screen):
        mcp.tool()(fn)
