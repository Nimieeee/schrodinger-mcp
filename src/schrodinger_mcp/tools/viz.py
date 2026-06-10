"""Visualization tools.

2D rendering runs in the MCP venv (PyPI RDKit, which ships Cairo for PNG output) — the
Schrödinger worker only supplies SMILES / molblocks / interaction data. Tools return an
inline MCP Image plus write the PNG to disk, so Claude shows the picture and you keep a file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import Image

from .. import runner
from ..errors import InvalidInput, WorkerError
from . import _common

# Highlight colors per interaction type (RGB 0-1).
_INTERACTION_COLOR = {
    "hbond": (0.20, 0.45, 0.95),
    "salt_bridge": (0.90, 0.25, 0.25),
    "pi_pi": (0.30, 0.70, 0.35),
    "pi_cation": (0.85, 0.55, 0.10),
}


def _png_image(png: bytes, out_path: Path) -> Image:
    out_path.write_bytes(png)
    return Image(data=png, format="png")


def render_2d_structure(
    smiles: Optional[list[str]] = None,
    input_path: Optional[str] = None,
    labels: Optional[list[str]] = None,
    legend_property: Optional[str] = None,
    output_path: Optional[str] = None,
    max_structures: int = 30,
):
    """Render molecules as a 2D structure image (PNG) shown inline. Provide either a list
    of `smiles` or an `input_path` to a structure file (mae/sdf/pdb/...). For SMILES you can
    pass `labels` (one caption per molecule, e.g. drug names); otherwise the SMILES string
    is used. For files you can pass `legend_property` (e.g. 'r_i_docking_score') to label
    each structure with that value. Also writes the PNG to disk."""
    from rdkit import Chem
    from rdkit.Chem import AllChem, Draw
    from rdkit.Chem.Draw import rdMolDraw2D

    mols, legends = [], []
    if smiles:
        for i, s in enumerate(smiles):
            m = Chem.MolFromSmiles(s)
            if m is not None:
                AllChem.Compute2DCoords(m)
                mols.append(m)
                legends.append(labels[i] if labels and i < len(labels) else s)
    elif input_path:
        inp = _common.validate_input_path(input_path)
        data = runner.run_worker(
            "export_render",
            {"path": str(inp), "legend_property": legend_property, "max_structures": int(max_structures)},
        )
        for entry in data["structures"]:
            m = Chem.MolFromSmiles(entry["smiles"]) if entry.get("smiles") else None
            if m is not None:
                AllChem.Compute2DCoords(m)
                mols.append(m)
                legends.append(entry.get("legend") or "")
    else:
        raise InvalidInput("provide either smiles=[...] or input_path=<file>")

    if not mols:
        raise WorkerError("no renderable molecules (could not parse SMILES)")

    out = _common.resolve_output_path(
        output_path, default_dir=_common.results_dir("render2d"), default_name="structures.png"
    )
    if len(mols) == 1:
        d = rdMolDraw2D.MolDraw2DCairo(420, 360)
        d.drawOptions().legendFontSize = 18
        rdMolDraw2D.PrepareAndDrawMolecule(d, mols[0], legend=legends[0][:60])
        d.FinishDrawing()
        png = d.GetDrawingText()
    else:
        per_row = min(4, len(mols))
        img = Draw.MolsToGridImage(
            mols, molsPerRow=per_row, subImgSize=(300, 260),
            legends=[l[:40] for l in legends], useSVG=False,
        )
        import io

        buf = io.BytesIO()
        img.save(buf, format="PNG")
        png = buf.getvalue()

    return _png_image(png, out)


def analyze_interactions(
    input_path: str,
    ligand_asl: Optional[str] = None,
    ligand_index: Optional[int] = None,
) -> dict:
    """Analyze protein-ligand interactions (hydrogen bonds, salt bridges, pi-pi stacking,
    pi-cation) in a complex or Glide pose-viewer (*_pv.maegz) file. For a pose-viewer the
    first entry is the receptor and `ligand_index` (default 2) selects the pose; for a
    single complex give a `ligand_asl`. Returns a structured interaction report."""
    inp = _common.validate_input_path(input_path)
    data = runner.run_worker(
        "interactions",
        {"path": str(inp), "ligand_asl": ligand_asl, "ligand_index": ligand_index},
    )
    s = data["summary"]
    data["summary_text"] = (
        f"{data['ligand_title'] or 'ligand'}: {s['n_hbonds']} H-bond(s), "
        f"{s['n_salt_bridges']} salt bridge(s), {s['n_pi_pi']} pi-pi, "
        f"{s['n_pi_cation']} pi-cation"
    )
    data.pop("ligand_molblock", None)  # not useful as text
    return data


def ligand_interaction_diagram(
    input_path: str,
    ligand_asl: Optional[str] = None,
    ligand_index: Optional[int] = None,
    output_path: Optional[str] = None,
):
    """Render a 2D ligand-interaction diagram (PNG, shown inline) for a protein-ligand
    complex or Glide pose-viewer file: the ligand drawn in 2D with the atoms that make
    interactions highlighted by type (blue=H-bond, red=salt bridge, green=pi-pi,
    orange=pi-cation) and a legend mapping them to protein residues. Also writes the PNG."""
    from rdkit import Chem
    from rdkit.Chem import AllChem
    from rdkit.Chem.Draw import rdMolDraw2D

    inp = _common.validate_input_path(input_path)
    data = runner.run_worker(
        "interactions",
        {"path": str(inp), "ligand_asl": ligand_asl, "ligand_index": ligand_index},
    )
    molblock = data.get("ligand_molblock")
    if not molblock:
        raise WorkerError("could not export the ligand for depiction")
    mol = Chem.MolFromMolBlock(molblock, sanitize=True)
    if mol is None:
        mol = Chem.MolFromMolBlock(molblock, sanitize=False)
    if mol is None:
        raise WorkerError("RDKit could not parse the exported ligand")
    AllChem.Compute2DCoords(mol)

    highlight_atoms, highlight_radii, highlight_colors, legend_rows = [], {}, {}, []
    notes: dict[int, list[str]] = {}
    for it in data["interactions"]:
        a = int(it.get("ligand_atom", 0)) - 1  # 1-based -> 0-based
        color = _INTERACTION_COLOR.get(it["type"], (0.5, 0.5, 0.5))
        if 0 <= a < mol.GetNumAtoms():
            highlight_atoms.append(a)
            highlight_colors[a] = color
            highlight_radii[a] = 0.5
            notes.setdefault(a, []).append(it.get("residue", "?"))
        dist = f" {it['distance']}Å" if it.get("distance") else ""
        legend_rows.append((it["type"], it.get("residue", "?"), dist, color))

    # Label interacting atoms with the contacting residue(s).
    for a, residues in notes.items():
        mol.GetAtomWithIdx(a).SetProp("atomNote", ",".join(sorted(set(residues)))[:18])

    d = rdMolDraw2D.MolDraw2DCairo(620, 520)
    opts = d.drawOptions()
    opts.legendFontSize = 16
    opts.annotationFontScale = 0.8
    opts.highlightRadius = 0.5
    title = data.get("ligand_title") or "ligand"
    s = data["summary"]
    legend = f"{title}  ({s['n_hbonds']} HB, {s['n_salt_bridges']} SB, {s['n_pi_pi']} pi-pi)"
    rdMolDraw2D.PrepareAndDrawMolecule(
        d, mol, legend=legend[:70],
        highlightAtoms=highlight_atoms,
        highlightAtomColors=highlight_colors,
        highlightAtomRadii=highlight_radii,
    )
    d.FinishDrawing()
    png = d.GetDrawingText()

    out = _common.resolve_output_path(
        output_path, default_dir=_common.results_dir("lid"), default_name="interaction_diagram.png"
    )
    # Note: residue legend is returned as structured data alongside the image.
    image = _png_image(png, out)
    return [
        image,
        {
            "ligand": title,
            "summary": data["summary"],
            "interactions": [
                {"type": t, "residue": r, "distance": dist.strip()} for (t, r, dist, _c) in legend_rows
            ],
            "image_path": str(out),
            "legend": "blue=H-bond, red=salt bridge, green=pi-pi, orange=pi-cation",
        },
    ]


def generate_2d_report(
    input_path: str,
    properties: str = "all",
    output_format: str = "pdf",
    output_path: Optional[str] = None,
) -> dict:
    """Build a 2D structure report (PDF or HTML) of every structure in a file, each drawn
    in 2D and labeled with properties (e.g. docking scores from a pose-viewer). Great for
    sharing docking/screening results. `properties` is 'all' or a comma-separated list of
    property names. Returns the path to the report."""
    inp = _common.validate_input_path(input_path)
    fmt = output_format.lower()
    if fmt not in ("pdf", "html"):
        raise InvalidInput("output_format must be 'pdf' or 'html'")
    out = _common.resolve_output_path(
        output_path, default_dir=_common.results_dir("report2d"), default_name=f"report.{fmt}"
    )
    argv = [_common.utility("generate_2d_report"), str(inp), str(out)]
    if properties:
        argv += ["-property", properties]
    runner.run_launcher(argv, timeout=600)
    if not out.exists():
        raise WorkerError("generate_2d_report produced no output")
    return {
        "input": str(inp),
        "output_path": str(out),
        "format": fmt,
        "outputs": [str(out)],
        "summary": f"2D report written → {out.name}",
    }


def render_3d_view(
    input_path: str,
    ligand_index: Optional[int] = None,
    ligand_asl: Optional[str] = None,
    output_path: Optional[str] = None,
    spin: bool = False,
) -> dict:
    """Generate a self-contained interactive 3D viewer (HTML) of a protein-ligand complex
    or docked pose. Open the file in any web browser to rotate, zoom, and share — the
    protein is shown as a cartoon, the ligand as sticks, and hydrogen bonds as dashed
    lines with the contacting residues labelled. No Maestro required. For a Glide
    pose-viewer file, `ligand_index` (default 2) picks the pose; for a single complex you
    can pass a `ligand_asl`. Returns the path to the HTML file."""
    inp = _common.validate_input_path(input_path)
    out_dir = _common.results_dir("view3d")
    data = runner.run_worker(
        "export_3d",
        {
            "path": str(inp),
            "ligand_index": ligand_index,
            "ligand_asl": ligand_asl,
            "out_dir": str(out_dir),
        },
    )
    receptor_pdb = Path(data["receptor_pdb"]).read_text() if data.get("receptor_pdb") else ""
    ligand_pdb = Path(data["ligand_pdb"]).read_text()
    html = _build_3d_html(receptor_pdb, ligand_pdb, data["hbonds"], data.get("ligand_title"), spin)
    out = _common.resolve_output_path(
        output_path, default_dir=out_dir, default_name="viewer.html"
    )
    out.write_text(html)
    n = len(data["hbonds"])
    return {
        "output_path": str(out),
        "outputs": [str(out)],
        "ligand": data.get("ligand_title"),
        "n_hbonds": n,
        "n_receptor_atoms": data.get("n_receptor_atoms"),
        "summary": (
            f"Interactive 3D viewer for {data.get('ligand_title') or 'ligand'} "
            f"({n} H-bond{'s' if n != 1 else ''}) → open {out.name} in a web browser to "
            f"rotate/zoom/share."
        ),
    }


def _build_3d_html(receptor_pdb, ligand_pdb, hbonds, title, spin):
    import json

    title = title or "ligand"
    return f"""<!doctype html><html><head><meta charset="utf-8">
<title>3D viewer — {title}</title>
<script src="https://3Dmol.org/build/3Dmol-min.js"></script>
<style>
 *{{margin:0;padding:0;box-sizing:border-box}}
 html,body{{height:100%;background:#0b0f1a;font-family:-apple-system,Inter,system-ui,sans-serif}}
 #v{{position:fixed;inset:0}}
 .hud{{position:fixed;top:16px;left:16px;color:#e8ecff;z-index:10}}
 .hud h1{{font-size:18px;font-weight:700;letter-spacing:-.3px}}
 .hud p{{font-size:13px;color:#9aa6cc;margin-top:3px}}
 .legend{{position:fixed;bottom:16px;left:16px;color:#aab4dc;font-size:12px;z-index:10;
   background:rgba(8,12,24,.6);border:1px solid rgba(255,255,255,.1);border-radius:10px;padding:10px 14px}}
 .legend b{{color:#e8ecff}}
 .btns{{position:fixed;top:16px;right:16px;z-index:10;display:flex;gap:8px}}
 button{{background:rgba(255,255,255,.08);color:#e8ecff;border:1px solid rgba(255,255,255,.16);
   border-radius:9px;padding:9px 14px;font-size:13px;font-weight:600;cursor:pointer}}
 button:hover{{background:rgba(255,255,255,.16)}}
</style></head><body>
<div id="v"></div>
<div class="hud"><h1>{title}</h1><p>protein–ligand binding mode · {len(hbonds)} H-bonds</p></div>
<div class="btns">
  <button onclick="sp()">Spin</button>
  <button onclick="hb()">H-bonds</button>
  <button onclick="rv.zoomTo(lig);rv.zoom(0.7);rv.render()">Recenter</button>
</div>
<div class="legend">🟦 protein (cartoon) &nbsp; ⚪ ligand (sticks) &nbsp; <b>– – –</b> hydrogen bond (yellow)</div>
<script>
const REC={json.dumps(receptor_pdb)}, LIG={json.dumps(ligand_pdb)}, HB={json.dumps(hbonds)};
const rv=$3Dmol.createViewer("v",{{backgroundColor:"0x0b0f1a"}});
const rec=REC?rv.addModel(REC,"pdb"):null;
const lig=rv.addModel(LIG,"pdb");
if(rec){{ rec.setStyle({{}},{{cartoon:{{color:"spectrum",opacity:.92}}}}); }}
lig.setStyle({{}},{{stick:{{radius:.18}}}});
let shown=true, spinning={str(bool(spin)).lower()};
function drawHB(){{HB.forEach(h=>{{
  rv.addCylinder({{start:{{x:h.lx,y:h.ly,z:h.lz}},end:{{x:h.px,y:h.py,z:h.pz}},
    radius:.05,dashed:true,fromCap:1,toCap:1,color:"yellow"}});
  rv.addLabel(h.residue+"  "+h.distance+"\\u00c5",{{position:{{x:h.px,y:h.py,z:h.pz}},
    fontSize:11,fontColor:"white",backgroundColor:"0x111827",backgroundOpacity:.75,borderThickness:0,inFront:true}});
}}); rv.render();}}
function hb(){{shown=!shown; if(shown){{drawHB()}}else{{rv.removeAllShapes();rv.removeAllLabels();rv.render()}}}}
function sp(){{spinning=!spinning; rv.spin(spinning?"y":false)}}
drawHB();
rv.zoomTo({{model: lig.getID()}});
rv.zoom(0.6);
rv.render();
if(spinning) rv.spin("y");
window._rv=rv; window._lig=lig; window._rec=rec;  // for debugging/screenshots
</script></body></html>"""


def register(mcp) -> None:
    for fn in (
        render_2d_structure,
        analyze_interactions,
        ligand_interaction_diagram,
        render_3d_view,
        generate_2d_report,
    ):
        mcp.tool()(fn)
