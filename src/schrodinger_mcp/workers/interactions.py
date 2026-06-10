"""Worker: analyze protein-ligand interactions in a complex / pose-viewer file and
export the ligand for 2D depiction.

Payload: {"path": str, "ligand_asl": str|None, "ligand_index": int|None}
Returns: {ligand_title, ligand_smiles, ligand_molblock, summary, interactions[...]}

Each interaction references the LIGAND-LOCAL 1-based atom index (matching the exported
molblock atom order) so the renderer can highlight the right atoms.
"""

import _wio
from schrodinger import structure
from schrodinger.structutils import analyze, interactions


def _res_label(atom):
    try:
        return f"{atom.chain}:{atom.pdbres.strip()}{atom.resnum}".strip(":")
    except Exception:
        return f"res{getattr(atom, 'resnum', '?')}"


def _build_complex(payload):
    """Return (combined, ligand_atom_index_set, ligand_structure, sch_to_local).

    sch_to_local maps a combined-structure ligand atom index -> the 1-based atom index
    within ``ligand`` (so interactions can be mapped onto the exported ligand depiction).
    """
    sts = list(structure.StructureReader(payload["path"]))
    asl = payload.get("ligand_asl")
    if len(sts) >= 2 and asl is None:
        # Pose-viewer style: first entry receptor, a later entry is the ligand.
        idx = payload.get("ligand_index") or 2
        receptor = sts[0].copy()
        ligand = sts[idx - 1].copy()
        nrec = receptor.atom_total
        combined = receptor.merge(ligand)
        ligset = set(range(nrec + 1, combined.atom_total + 1))
        sch_to_local = {nrec + i: i for i in range(1, ligand.atom_total + 1)}
        return combined, ligset, ligand, sch_to_local
    # Single complex: identify the ligand by ASL. Default = the largest non-protein,
    # non-water/ion molecule (a small-molecule ligand). "ligand" is a valid ASL class;
    # fall back to a plain protein/water exclusion if a build lacks it.
    st = sts[0]
    if asl is None:
        lig_atoms = []
        for candidate in ("ligand", "not (protein or water or ions)", "(not protein) and (not water)"):
            try:
                lig_atoms = analyze.evaluate_asl(st, candidate)
            except Exception:
                continue
            if lig_atoms:
                asl = candidate
                break
    else:
        lig_atoms = analyze.evaluate_asl(st, asl)
    if not lig_atoms:
        raise ValueError(f"no ligand atoms matched ASL: {asl}")
    ligset = set(lig_atoms)
    ligand = st.extract(lig_atoms)
    sch_to_local = {orig: k + 1 for k, orig in enumerate(lig_atoms)}
    return st, ligset, ligand, sch_to_local


def run(payload):
    combined, ligset, ligand, sch_to_local = _build_complex(payload)
    liglist = sorted(ligset)

    # Heavy-atom ranking in the ligand: heavy-only molblock atom k (0-based) == the
    # k-th heavy atom in ligand order. Map a ligand-local index -> heavy rank (1-based).
    heavy_order = [a.index for a in ligand.atom if a.atomic_number > 1]
    heavy_rank = {idx: r + 1 for r, idx in enumerate(heavy_order)}

    def to_heavy_rank(combined_idx):
        """combined ligand atom -> 1-based heavy-atom rank (resolving H to its heavy neighbor)."""
        loc = sch_to_local.get(combined_idx)
        if loc is None:
            return None
        atom = ligand.atom[loc]
        if atom.atomic_number == 1:  # hydrogen -> the heavy atom it is bonded to
            heavy = next((b.atom2 for b in atom.bond if b.atom2.atomic_number > 1), None)
            if heavy is None:
                return None
            return heavy_rank.get(heavy.index)
        return heavy_rank.get(atom.index)

    found = []

    # Hydrogen bonds
    for a1, a2 in analyze.hbond_iterator(combined, atoms=liglist):
        lig_atom = a1 if a1.index in ligset else a2
        prot_atom = a2 if a1.index in ligset else a1
        if prot_atom.index in ligset:
            continue  # intramolecular
        rank = to_heavy_rank(lig_atom.index)
        found.append(
            {
                "type": "hbond",
                "ligand_atom": rank,
                "residue": _res_label(prot_atom),
                "distance": round(
                    combined.measure(lig_atom.index, prot_atom.index), 2
                ),
            }
        )

    # Salt bridges
    try:
        for sb in interactions.get_salt_bridges(combined, group1=liglist):
            # sb exposes anion/cation atom groups; label by the protein partner residue
            atoms = list(getattr(sb, "anion_atoms", []) or []) + list(
                getattr(sb, "cation_atoms", []) or []
            )
            prot = next((a for a in atoms if a.index not in ligset), None)
            lig = next((a for a in atoms if a.index in ligset), None)
            if prot and lig:
                found.append(
                    {
                        "type": "salt_bridge",
                        "ligand_atom": to_heavy_rank(lig.index),
                        "residue": _res_label(prot),
                    }
                )
    except Exception:
        pass

    # Pi-pi stacking
    try:
        for pp in interactions.find_pi_pi_interactions(combined, atoms1=liglist):
            r1 = getattr(pp, "ring1", None)
            r2 = getattr(pp, "ring2", None)
            atoms1 = list(getattr(r1, "atoms", []) or [])
            atoms2 = list(getattr(r2, "atoms", []) or [])
            lig_ring = atoms1 if (atoms1 and atoms1[0].index in ligset) else atoms2
            prot_ring = atoms2 if lig_ring is atoms1 else atoms1
            if lig_ring and prot_ring and prot_ring[0].index not in ligset:
                found.append(
                    {
                        "type": "pi_pi",
                        "ligand_atom": to_heavy_rank(lig_ring[0].index),
                        "residue": _res_label(prot_ring[0]),
                    }
                )
    except Exception:
        pass

    # Pi-cation
    try:
        for pc in interactions.find_pi_cation_interactions(combined, atoms1=liglist):
            cat = getattr(pc, "cation_atom", None) or getattr(pc, "cation_centroid", None)
            ring_atoms = list(getattr(getattr(pc, "pi_structure", None), "atom", []) or [])
            label = _res_label(cat) if cat is not None and hasattr(cat, "chain") else "pi-cation"
            found.append({"type": "pi_cation", "ligand_atom": 1, "residue": label})
    except Exception:
        pass

    # Export ligand for 2D depiction (hydrogen-free, so heavy-atom indices match the
    # heavy_rank values used in `interactions` above).
    try:
        from rdkit import Chem

        rdmol = Chem.RemoveHs(_wio.to_rdkit(ligand))
        molblock = Chem.MolToMolBlock(rdmol)
        smiles = Chem.MolToSmiles(rdmol)
    except Exception:
        molblock = None
        try:
            smiles = _wio.to_smiles(ligand)
        except Exception:
            smiles = None

    summary = {
        "n_hbonds": sum(1 for f in found if f["type"] == "hbond"),
        "n_salt_bridges": sum(1 for f in found if f["type"] == "salt_bridge"),
        "n_pi_pi": sum(1 for f in found if f["type"] == "pi_pi"),
        "n_pi_cation": sum(1 for f in found if f["type"] == "pi_cation"),
    }
    return {
        "ligand_title": ligand.title,
        "ligand_num_atoms": ligand.atom_total,
        "ligand_smiles": smiles,
        "ligand_molblock": molblock,
        "summary": summary,
        "interactions": found,
    }


if __name__ == "__main__":
    _wio.main(run)
