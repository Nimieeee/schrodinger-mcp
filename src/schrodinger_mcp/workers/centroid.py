"""Worker: compute the geometric centroid of the first structure in a file.

Used to derive a Glide grid center from a bound/reference ligand.
Payload: {"path": str}  ->  {"centroid": [x, y, z], "num_atoms": int, "title": str}
"""

import _wio
from schrodinger import structure


def run(payload):
    st = structure.StructureReader.read(payload["path"])
    n = st.atom_total
    if n == 0:
        raise ValueError("structure has no atoms")
    sx = sy = sz = 0.0
    for atom in st.atom:
        sx += atom.x
        sy += atom.y
        sz += atom.z
    return {
        "centroid": [round(sx / n, 4), round(sy / n, 4), round(sz / n, 4)],
        "num_atoms": n,
        "title": st.title,
    }


if __name__ == "__main__":
    _wio.main(run)
