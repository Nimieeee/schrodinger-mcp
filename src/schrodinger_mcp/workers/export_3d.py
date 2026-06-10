"""Worker: export a protein-ligand complex / docked pose as receptor + ligand PDBs
plus the hydrogen-bond geometry, for an interactive 3D web viewer.

Payload: {"path", "ligand_index"|None, "ligand_asl"|None, "out_dir"}
Returns: {receptor_pdb, ligand_pdb, ligand_title, n_receptor_atoms, n_ligand_atoms, hbonds}

Reuses the complex/ligand splitting and residue labelling from the interactions worker.
"""

import os

import _wio
import interactions as ix  # sibling worker module
from schrodinger.structutils import analyze


def run(payload):
    out_dir = payload["out_dir"]
    os.makedirs(out_dir, exist_ok=True)

    combined, ligset, ligand, _ = ix._build_complex(payload)
    rec_atoms = [a.index for a in combined.atom if a.index not in ligset]
    receptor = combined.extract(rec_atoms) if rec_atoms else None

    rec_path = os.path.join(out_dir, "receptor.pdb")
    lig_path = os.path.join(out_dir, "ligand.pdb")
    if receptor is not None:
        receptor.write(rec_path)
    ligand.write(lig_path)

    # Hydrogen bonds between the ligand and the receptor (world coordinates, shared by
    # both exported models since extract() preserves coordinates).
    hbonds = []
    liglist = sorted(ligset)
    for a1, a2 in analyze.hbond_iterator(combined, atoms=liglist):
        lig_a = a1 if a1.index in ligset else a2
        pro_a = a2 if a1.index in ligset else a1
        if pro_a.index in ligset:
            continue
        hbonds.append(
            {
                "residue": ix._res_label(pro_a),
                "lx": round(lig_a.x, 3), "ly": round(lig_a.y, 3), "lz": round(lig_a.z, 3),
                "px": round(pro_a.x, 3), "py": round(pro_a.y, 3), "pz": round(pro_a.z, 3),
                "distance": round(combined.measure(lig_a.index, pro_a.index), 2),
            }
        )

    return {
        "receptor_pdb": rec_path if receptor is not None else None,
        "ligand_pdb": lig_path,
        "ligand_title": ligand.title,
        "n_receptor_atoms": receptor.atom_total if receptor is not None else 0,
        "n_ligand_atoms": ligand.atom_total,
        "hbonds": hbonds,
    }


if __name__ == "__main__":
    _wio.main(run)
