"""Worker: report structure-level info for a file (any format Schrödinger reads).

Payload: {"path": str, "max_structures": int}
Returns: counts + per-structure details (capped) + aggregate totals.
"""

import _wio
from schrodinger import structure


def _summarize_structure(st, index):
    info = {
        "index": index,
        "title": st.title,
        "num_atoms": st.atom_total,
        "num_bonds": len(st.bond),
        "formal_charge": st.formal_charge,
    }
    try:
        info["num_chains"] = len(list(st.chain))
        info["num_residues"] = len(list(st.residue))
    except Exception:
        pass
    try:
        mol_weight = sum(a.atomic_weight for a in st.atom)
        info["molecular_weight"] = round(mol_weight, 2)
    except Exception:
        pass
    # A small sample of named properties (skip internal m_/i_ noise where possible).
    props = {}
    for key in list(st.property.keys())[:25]:
        val = st.property[key]
        if isinstance(val, (int, float, str)):
            props[key] = val
    if props:
        info["properties"] = props
    return info


def run(payload):
    path = payload["path"]
    max_structures = int(payload.get("max_structures", 100))
    structures = []
    total_atoms = 0
    count = 0
    with structure.StructureReader(path) as reader:
        for i, st in enumerate(reader, start=1):
            count = i
            total_atoms += st.atom_total
            if len(structures) < max_structures:
                structures.append(_summarize_structure(st, i))
    return {
        "path": path,
        "num_structures": count,
        "total_atoms": total_atoms,
        "structures": structures,
        "truncated": count > len(structures),
    }


if __name__ == "__main__":
    _wio.main(run)
