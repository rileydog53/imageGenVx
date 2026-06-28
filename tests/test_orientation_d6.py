"""D6 — molecule orientation (pub-grade dim 3).

The posing primitive (`_orient_conformer`) and its two entry points
(`render_molecule_anchored` for the draw, `molecule_natural_size` for the
pre-render size predictor) rigidly rotate a molecule so a chosen atom faces a
chosen direction. These pin the contract: directional correctness, rigidity,
predictor/renderer agreement, the deadband no-op, and — load-bearing — the
byte-identical guarantee on the leaf/panel path. See `D6_ORIENTATION_SCOPE.md`.
"""
import math

import pytest

from imageGen.primitives._mol_render import (
    _natural_box,
    _orient_conformer,
    _smiles_to_mol,
    molecule_natural_size,
    render_molecule_anchored,
    render_residue_anchored,
)

# aspirin, ester carbonyl C mapped :1 -> resolves to the 'a1' anchor
ASPIRIN = "CC(=O)Oc1ccccc1[C:1](=O)O"
BOND = 24.0


def _atom_centroid(ag):
    pts = [xy for k, xy in ag.anchors.items() if k.startswith("atom")]
    xs = [x for x, _ in pts]
    ys = [y for _, y in pts]
    return sum(xs) / len(xs), sum(ys) / len(ys)


@pytest.mark.parametrize(
    "direction,check",
    [
        # SVG frame: y grows downward, so 'up' = smaller y, 'down' = larger y.
        ("up", lambda tx, ty, cx, cy: ty < cy and abs(tx - cx) < abs(ty - cy)),
        ("down", lambda tx, ty, cx, cy: ty > cy and abs(tx - cx) < abs(ty - cy)),
        ("left", lambda tx, ty, cx, cy: tx < cx and abs(ty - cy) < abs(tx - cx)),
        ("right", lambda tx, ty, cx, cy: tx > cx and abs(ty - cy) < abs(tx - cx)),
    ],
)
def test_target_atom_faces_requested_direction(direction, check):
    ag = render_molecule_anchored(
        ASPIRIN, target_bond_px=BOND, orient_to="a1", orient_direction=direction
    )
    cx, cy = _atom_centroid(ag)
    tx, ty = ag.anchors["a1"]
    assert check(tx, ty, cx, cy), (
        f"a1 at ({tx:.1f},{ty:.1f}) not '{direction}' of centroid ({cx:.1f},{cy:.1f})"
    )


def test_rotation_is_rigid_bond_lengths_preserved():
    # Rigidity is a property of the conformer transform, not the drawn pixels
    # (the drawer autoscales to its box, so differently-shaped boxes scale
    # marginally differently). Assert every conformer bond length is unchanged
    # by orientation, to floating-point epsilon.
    from rdkit.Chem import rdDepictor

    def bond_lengths(mol):
        conf = mol.GetConformer()
        out = []
        for b in mol.GetBonds():
            p = conf.GetAtomPosition(b.GetBeginAtomIdx())
            q = conf.GetAtomPosition(b.GetEndAtomIdx())
            out.append(math.hypot(p.x - q.x, p.y - q.y))
        return out

    base = _smiles_to_mol(ASPIRIN)
    rdDepictor.Compute2DCoords(base)
    ref = bond_lengths(base)
    for d in ("up", "down", "left", "right"):
        mol = _smiles_to_mol(ASPIRIN)
        _orient_conformer(mol, "a1", d)
        drift = max(abs(a - b) for a, b in zip(ref, bond_lengths(mol)))
        assert drift < 1e-9, f"{d}: bond length drifted by {drift}"


def test_predictor_matches_drawn_box_under_orientation():
    for direction in ("up", "down", "left", "right"):
        pred = molecule_natural_size(
            ASPIRIN, BOND, orient_to="a1", orient_direction=direction
        )
        mol = _smiles_to_mol(ASPIRIN)
        _orient_conformer(mol, "a1", direction)
        drawn = _natural_box(mol, BOND, 16.0)
        assert pred == drawn, f"{direction}: predicted {pred} != drawn {drawn}"


def test_orientation_changes_the_box():
    # If orientation never changed the bbox, predictor parity would be moot.
    up = molecule_natural_size(ASPIRIN, BOND, orient_to="a1", orient_direction="up")
    right = molecule_natural_size(ASPIRIN, BOND, orient_to="a1", orient_direction="right")
    assert up != right


def test_deadband_is_a_noop():
    # A deadband wider than any possible correction must leave the canonical pose
    # untouched (byte-identical anchors to the no-orient tier render).
    base = render_molecule_anchored(ASPIRIN, target_bond_px=BOND)
    held = render_molecule_anchored(
        ASPIRIN, target_bond_px=BOND, orient_to="a1", orient_direction="up",
        orient_deadband_deg=180.0,
    )
    assert held.anchors == base.anchors


def test_leaf_path_is_byte_identical():
    # target_bond_px=None (leaf/panel) must IGNORE orient_* entirely.
    base = render_molecule_anchored(ASPIRIN, size=(200, 150))
    with_orient = render_molecule_anchored(
        ASPIRIN, size=(200, 150), orient_to="a1", orient_direction="up",
    )
    assert with_orient.anchors == base.anchors
    assert with_orient.group.tostring() == base.group.tostring()


def test_unresolvable_target_is_a_safe_noop():
    base = render_molecule_anchored(ASPIRIN, target_bond_px=BOND)
    bogus = render_molecule_anchored(
        ASPIRIN, target_bond_px=BOND, orient_to="nope", orient_direction="up",
    )
    assert bogus.anchors == base.anchors


def test_residue_orientation_aims_reactive_atom():
    # Serine's nucleophilic O (mapped :1 -> 'a1') should aim down toward a
    # substrate sitting below it.
    ag = render_residue_anchored(
        "ser", target_bond_px=BOND, orient_to="a1", orient_direction="down"
    )
    cx, cy = _atom_centroid(ag)
    _, ty = ag.anchors["a1"]
    assert ty > cy, "serine reactive O did not aim 'down'"


# --------------------------------------------------------------------------
# Corpus-grounded, end-to-end (through the real tier layout). These are the
# overfitting-resistant D6 checks: a geometric invariant in a laid-out figure,
# not a pixel hash. See D6_ORIENTATION_SCOPE.md §8.
# --------------------------------------------------------------------------
import json
import math
from pathlib import Path

from imageGen.ir.schema import Figure
from imageGen.layout.anchors import AnchorRegistry
from imageGen.layout.tier_layout import (
    _ORIENT_DEADBAND_DEG,
    _layout_scene,
    _scene_orientations,
    TIER_DEFAULT_PARAMS,
)
from imageGen.primitives._mol_render import (
    _DIRECTION_ANGLE,
    _resolve_atom_index,
    _RESIDUE_SMILES,
)
from rdkit.Chem import rdDepictor

_ROOT = Path(__file__).resolve().parent.parent
# (figure path, scene id) — the three D6 figures whose substrate is grossly
# mis-posed (the carbonyl points away from the attacking residue). 05 is the
# control: same archetype, but already reads fine, so it must NOT be re-posed.
_FIXED = [
    ("showcase/corpus/08_acetylcholinesterase_hydrolysis.json", "s2"),
    ("showcase/corpus/02_chymotrypsin_acylation.json", "s2"),
    ("showcase/aspirin_cox1_v3_acceptance.json", "s2"),
]
_CONTROL = ("showcase/corpus/05_imine_formation.json", "s2")


def _load_scene(rel_path, scene_id):
    fig = Figure.model_validate(json.loads((_ROOT / rel_path).read_text()))
    for tier in fig.tiers:
        for scene in tier.scenes or []:
            if scene.id == scene_id:
                return scene
    raise AssertionError(f"scene {scene_id} not in {rel_path}")


def _slot_smiles(slot):
    style = slot.style or {}
    if slot.kind.value == "residue":
        res = style.get("residue")
        return _RESIDUE_SMILES.get(res, res) if res else style.get("smiles")
    return style.get("smiles")


def _required_theta_deg(slot, atom_token, direction):
    """Magnitude of rotation the canonical pose needs to face *direction* — the
    value the layout deadband is compared against."""
    from imageGen.primitives._mol_render import _smiles_to_mol

    mol = _smiles_to_mol(str(_slot_smiles(slot)))
    rdDepictor.Compute2DCoords(mol)
    conf = mol.GetConformer()
    n = mol.GetNumAtoms()
    m2i = {a.GetAtomMapNum(): a.GetIdx() for a in mol.GetAtoms() if a.GetAtomMapNum()}
    names = {int(k): v for k, v in ((slot.style or {}).get("anchor_names") or {}).items()}
    idx = _resolve_atom_index(atom_token, m2i, names)
    cx = sum(conf.GetAtomPosition(i).x for i in range(n)) / n
    cy = sum(conf.GetAtomPosition(i).y for i in range(n)) / n
    p = conf.GetAtomPosition(idx)
    theta = _DIRECTION_ANGLE[direction] - math.atan2(p.y - cy, p.x - cx)
    return abs(math.degrees((theta + math.pi) % (2 * math.pi) - math.pi))


@pytest.mark.parametrize("rel_path,scene_id", _FIXED)
def test_fixed_substrate_faces_its_partner_after_layout(rel_path, scene_id):
    # After the real tier layout, the substrate's reactive (attacked) atom must
    # sit on the partner's side of the molecule — the curly arrow no longer
    # sweeps across the structure. We check the 'up'-aimed slot (the substrate;
    # its residue partner is attached at the top edge).
    scene = _load_scene(rel_path, scene_id)
    om = _scene_orientations(scene)
    up_slots = [sid for sid, (_, d) in om.items() if d == "up"]
    assert up_slots, f"{rel_path}: expected an 'up'-aimed substrate"
    slots = {s.id: s for s in scene.slots}
    reg = AnchorRegistry()
    _layout_scene(scene, (0.0, 0.0, 600.0, 420.0), reg, dict(TIER_DEFAULT_PARAMS))
    for sid in up_slots:
        from imageGen.primitives._mol_render import _smiles_to_mol

        mol = _smiles_to_mol(str(_slot_smiles(slots[sid])))
        n = mol.GetNumAtoms()
        ys = [reg.resolve(f"{scene.id}.{sid}.atom{i}")[1] for i in range(n)]
        cy = sum(ys) / n
        atok = om[sid][0]
        m2i = {a.GetAtomMapNum(): a.GetIdx()
               for a in mol.GetAtoms() if a.GetAtomMapNum()}
        names = {int(k): v
                 for k, v in ((slots[sid].style or {}).get("anchor_names") or {}).items()}
        ridx = _resolve_atom_index(atok, m2i, names)
        ry = reg.resolve(f"{scene.id}.{sid}.atom{ridx}")[1]
        # SVG y grows downward; 'up' (toward the top-attached residue) = smaller y.
        assert ry < cy, (
            f"{rel_path} {sid}: reactive atom y={ry:.1f} not above centroid "
            f"y={cy:.1f} — substrate not facing its partner")


def test_deadband_separates_control_from_fixed_targets():
    # The corpus invariant the 80° deadband encodes: the control (05) is already
    # close enough to read and must be left alone, while every fixed target is
    # grossly mis-posed. If RDKit's canonical poses drift or someone retunes the
    # deadband past this window, this fails loud.
    cscene = _load_scene(*_CONTROL)
    com = _scene_orientations(cscene)
    cslots = {s.id: s for s in cscene.slots}
    control_thetas = [_required_theta_deg(cslots[sid], atok, d)
                      for sid, (atok, d) in com.items()]
    assert max(control_thetas) < _ORIENT_DEADBAND_DEG, (
        f"control 05 needs {max(control_thetas):.1f}° (>= deadband "
        f"{_ORIENT_DEADBAND_DEG}°) — it would be re-posed and regress")

    for rel_path, scene_id in _FIXED:
        scene = _load_scene(rel_path, scene_id)
        om = _scene_orientations(scene)
        slots = {s.id: s for s in scene.slots}
        up = [sid for sid, (_, d) in om.items() if d == "up"][0]
        atok, d = om[up]
        theta = _required_theta_deg(slots[up], atok, d)
        assert theta >= _ORIENT_DEADBAND_DEG, (
            f"{rel_path} substrate needs only {theta:.1f}° (< deadband) — "
            "it would not be fixed")


# --------------------------------------------------------------------------
# orientation-v2 — cross-step consistency + H-bond drivers (landed 2026-06-28).
# See D6_ORIENTATION_SCOPE.md → "v2 — LANDED".
# --------------------------------------------------------------------------
from imageGen.layout.tier_layout import (  # noqa: E402
    _resolve_tier_orientations,
    _resolve_tier_scaffold,
    tier_rendered_scenes,
)


def _mech_scenes(rel_path):
    """The rendered scenes of a figure's first SCENE_ROW tier with scenes."""
    fig = Figure.model_validate(json.loads((_ROOT / rel_path).read_text()))
    for tier in fig.tiers:
        if tier.role.value == "scene_row" and (tier.scenes or tier.step_sequence):
            return tier_rendered_scenes(tier)
    raise AssertionError(f"no scene_row tier in {rel_path}")


def test_v2a_recurring_molecule_shares_one_pose():
    # v2-A: aspirin's `asp` (same SMILES in s1/s2/s3) posed canonical/rotated/
    # canonical under v1 and visibly flipped. The reconciled map must give it ONE
    # non-None orientation across every scene it appears in.
    scenes = _mech_scenes("showcase/aspirin_cox1_v3_acceptance.json")
    resolved = _resolve_tier_orientations(scenes)
    poses = {sc.id: resolved[sc.id].get("asp")
             for sc in scenes if any(s.id == "asp" for s in sc.slots)}
    assert len(poses) >= 3, f"expected asp in >=3 scenes, got {poses}"
    distinct = set(poses.values())
    assert distinct == {("carbonylC", "up")}, (
        f"asp should share one inferred pose across scenes, got {poses}")


def test_v2b_transforming_scaffold_aligns_non_template_members():
    # v2-B: beta-lactamase sub->ti->acyl->prod share a bicyclic core (different
    # SMILES). The non-template members get an alignment spec; the template (sub,
    # the constrained earliest member) does not.
    scenes = _mech_scenes("showcase/corpus/11_betalactamase_mechanism.json")
    orients = _resolve_tier_orientations(scenes)
    align = _resolve_tier_scaffold(scenes, orients)
    aligned = {slid for m in align.values() for slid in m}
    assert {"ti", "acyl", "prod"} <= aligned, f"core members not aligned: {aligned}"
    assert "sub" not in aligned, "template `sub` should not be self-aligned"
    # the spec is (reference_mol, mcs_pattern) and the pattern is a real shared core
    ref_mol, patt = align["s2"]["ti"]
    assert ref_mol.GetNumConformers() == 1
    assert patt.GetNumAtoms() >= 6


def test_v2b_water_and_unrelated_species_not_aligned():
    # Guard: a tiny fragment (water in s3) must never be pulled into the scaffold
    # series, and a single unique molecule has nothing to align to.
    scenes = _mech_scenes("showcase/corpus/11_betalactamase_mechanism.json")
    align = _resolve_tier_scaffold(scenes, _resolve_tier_orientations(scenes))
    assert "wat" not in align.get("s3", {}), "water should be excluded (too small)"


def test_drivers_hbond_orients_without_curly():
    # drivers: a binding step with only an H-bond edge (no curly) between two
    # directly-attached slots now aims donor/acceptor at each other.
    scene = _load_scene("showcase/corpus/01_aspirin_cox1_acetylation.json", "s1")
    assert not any(e.type.value == "curly" for e in scene.connect)
    om = _scene_orientations(scene)
    assert om, "H-bond-only step should now infer an orientation"
    assert om.get("asp") and om.get("ser"), f"donor/acceptor not posed: {om}"
