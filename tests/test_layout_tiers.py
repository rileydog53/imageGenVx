"""Step-3 vertical slice: lower a tiered IR Figure through the real engine.

This is the chassis-driven counterpart to the hand-assembled keystone slice
(test_anchor_keystone.py). The same aspirin -> salicylic acid scene is authored
as a ``Figure`` with tiers and lowered by ``layout_tiers`` into LayoutEntries,
proving the schema -> engine -> SVG path end to end. Coordinate-math correctness
is already covered by the keystone tests; here we assert the IR lowers to the
expected tagged entries and renders.
"""
from __future__ import annotations

import pytest

from imageGen.ir import Figure
from imageGen.layout.tier_layout import layout_tiers
from tests._helpers import render_entries_to_png

ASPIRIN = "C[C:1](=O)[O:3]c1ccccc1C(=O)O"   # :1 acetyl C, :3 ester O
SALICYLIC = "O=C(O)c1ccccc1O"


def _aspirin_hydrolysis_figure() -> Figure:
    return Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [
            {"id": "title", "role": "title", "height_frac": 0.18,
             "label": "Aspirin hydrolysis", "subtitle": "acyl-oxygen cleavage"},
            {"id": "row", "role": "scene_row", "layout": "equal_columns",
             "height_frac": 0.82,
             "rails": [{"name": "midline", "axis": "y", "at": 0.5}],
             "scenes": [
                 {"id": "s_aspirin", "badge": "1",
                  "slots": [
                      {"id": "mol", "kind": "molecule",
                       "style": {"smiles": ASPIRIN,
                                 "anchor_names": {"1": "acetyl_C", "3": "ester_O"}}},
                      {"id": "cap", "kind": "text", "label": "aspirin"},
                  ],
                  "attach": [{"child": "cap", "parent": "mol", "edge": "bottom",
                              "offset": [0, 10]}],
                  "connect": [{"from_anchor": "mol.acetyl_C",
                               "to_anchor": "mol.ester_O", "type": "dashed"}]},
                 {"id": "s_salicylic", "badge": "2",
                  "slots": [
                      {"id": "mol", "kind": "molecule",
                       "style": {"smiles": SALICYLIC}},
                      {"id": "cap", "kind": "text", "label": "salicylic acid"},
                  ],
                  "attach": [{"child": "cap", "parent": "mol", "edge": "bottom",
                              "offset": [0, 10]}]},
             ],
             "transitions": [{"from_ref": "s_aspirin@right",
                              "to_ref": "s_salicylic@left",
                              "type": "transition", "on_rail": "midline"}]},
        ],
    })


def test_tiered_figure_lowers_to_entries():
    fig = _aspirin_hydrolysis_figure()
    entries = layout_tiers(fig, layout_params={"tier_canvas": (600, 300)})
    assert entries, "expected non-empty LayoutEntry list"
    ir_ids = {e.ir_id for e in entries if e.ir_id}
    # title + both molecules + the intra-scene bond + the cross-cell arrow
    assert "tier_title_title" in ir_ids
    assert "s_aspirin.mol" in ir_ids
    assert "s_salicylic.mol" in ir_ids
    assert "edge_mol.acetyl_C_mol.ester_O" in ir_ids
    assert "tedge_s_aspirin@right_s_salicylic@left" in ir_ids


def test_every_entry_primitive_is_callable_and_returns_group():
    import svgwrite.container
    entries = layout_tiers(_aspirin_hydrolysis_figure(),
                           layout_params={"tier_canvas": (600, 300)})
    for e in entries:
        g = e.primitive(*e.args, **e.kwargs)
        assert isinstance(g, svgwrite.container.Group)


def test_tiered_slice_renders_to_png():
    entries = layout_tiers(_aspirin_hydrolysis_figure(),
                           layout_params={"tier_canvas": (600, 300)})
    out = render_entries_to_png(entries, "tier_slice_aspirin.png", canvas=(600, 300))
    assert out.exists() and out.stat().st_size > 0


def test_empty_tiers_rejected():
    with pytest.raises(ValueError, match="tiers populated"):
        layout_tiers(Figure.model_validate(
            {"archetype": "pathway",
             "entities": [{"id": "a", "type": "protein", "label": "A"}]}))


def test_step_sequence_not_yet_supported():
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row",
         "step_sequence": {"id": "q", "base": {"id": "b"}, "steps": []}}]})
    with pytest.raises(NotImplementedError, match="step_sequence"):
        layout_tiers(fig)


def test_unsupported_slot_kind_raises():
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [{"id": "b", "kind": "blob"}]}]}]})
    with pytest.raises(NotImplementedError, match="SlotKind"):
        layout_tiers(fig)


def test_molecule_slot_requires_smiles():
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [{"id": "m", "kind": "molecule"}]}]}]})
    with pytest.raises(ValueError, match="style\\['smiles'\\]"):
        layout_tiers(fig)


# ---------------------------------------------------------------------------
# Attach solver robustness (from the Step-3 adversarial review)
# ---------------------------------------------------------------------------

def _scene_with_attach(attach):
    from imageGen.ir import Scene
    return Scene.model_validate({
        "id": "s",
        "slots": [{"id": "a", "kind": "text"}, {"id": "b", "kind": "text"},
                  {"id": "c", "kind": "text"}],
        "attach": attach,
    })


def test_attach_resolves_regardless_of_declaration_order():
    from imageGen.layout.tier_layout import _solve_slot_centers
    # declared child-first (c<-b before b<-a); must still resolve topologically
    scene = _scene_with_attach([
        {"child": "c", "parent": "b", "edge": "right"},
        {"child": "b", "parent": "a", "edge": "right"},
    ])
    centers = _solve_slot_centers(scene, (0.0, 0.0, 300.0, 100.0), (50.0, 40.0))
    # a is the only root -> cell centre; b/c step right by half a slot width each
    assert centers["a"] == (150.0, 50.0)
    assert centers["b"] == (175.0, 50.0)
    assert centers["c"] == (200.0, 50.0)


def test_attach_cycle_raises():
    from imageGen.layout.tier_layout import _solve_slot_centers
    scene = _scene_with_attach([
        {"child": "a", "parent": "b", "edge": "right"},
        {"child": "b", "parent": "a", "edge": "right"},
    ])
    with pytest.raises(ValueError, match="cyclic or unresolvable"):
        _solve_slot_centers(scene, (0.0, 0.0, 300.0, 100.0), (50.0, 40.0))


def test_unsupported_attach_edge_raises():
    from imageGen.layout.tier_layout import _solve_slot_centers
    scene = _scene_with_attach([{"child": "b", "parent": "a", "edge": "cavity_top"}])
    with pytest.raises(NotImplementedError, match="attach edge"):
        _solve_slot_centers(scene, (0.0, 0.0, 300.0, 100.0), (50.0, 40.0))


def test_rail_endpoint_transition_not_supported():
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row",
         "rails": [{"name": "midline", "axis": "y", "at": 0.5}],
         "scenes": [{"id": "a", "slots": [
             {"id": "m", "kind": "molecule", "style": {"smiles": "CCO"}}]}],
         "transitions": [{"from_ref": "rail:midline", "to_ref": "a@right"}]}]})
    with pytest.raises(NotImplementedError, match="rail.*endpoint"):
        layout_tiers(fig)
