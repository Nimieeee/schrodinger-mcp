"""Worker: export structures from a file as SMILES + an optional legend property,
for 2D rendering in the (Cairo-enabled) MCP venv.

Payload: {"path": str, "legend_property": str|None, "max_structures": int}
Returns: {"structures": [{"title","smiles","legend"}], "count": int}
"""

import _wio
from schrodinger import adapter, structure


def run(payload):
    path = payload["path"]
    prop = payload.get("legend_property")
    limit = int(payload.get("max_structures", 30))
    out = []
    with structure.StructureReader(path) as reader:
        for i, st in enumerate(reader, start=1):
            if len(out) >= limit:
                break
            try:
                smiles = adapter.to_smiles(st)
            except Exception:
                from rdkit import Chem

                smiles = Chem.MolToSmiles(adapter.to_rdkit(st))
            legend = st.title or f"structure {i}"
            if prop and prop in st.property:
                val = st.property[prop]
                val = round(val, 3) if isinstance(val, float) else val
                legend = f"{legend}  [{prop.split('_')[-1]}={val}]"
            out.append({"title": st.title, "smiles": smiles, "legend": legend})
    return {"structures": out, "count": len(out)}


if __name__ == "__main__":
    _wio.main(run)
