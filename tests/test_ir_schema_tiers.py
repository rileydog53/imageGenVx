"""Schema tests for the V3 scene-chassis nodes (Tier / Scene / Step layers).

Covers the additive schema surface: a full tiered figure round-trips; the
three-way leaf/panels/tiers exclusivity holds; id-uniqueness and reserved-char
rules fire; scene attach/connect and tier transition references resolve; the
step-sequence delta targets validate; and the builder + compositor wiring works.
Existing leaf/panel figures are untouched (their coverage stays in
test_ir_schema.py).
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from imageGen.ir import (
    Figure,
    Rail,
    Scene,
    SceneEdge,
    SceneEdgeType,
    Slot,
    SlotKind,
    Step,
    StepDelta,
    StepOp,
    StepSequence,
    Tier,
    TierEdge,
    TierLayout,
    TierRole,
)
from imageGen.ir.builder import build


def _full_tiered_figure_dict() -> dict:
    """A reasonably complete tiered figure exercising most chassis fields."""
    return {
        "archetype": "mechanism_cartoon",
        "tiers": [
            {
                "id": "title",
                "role": "title",
                "label": "Aspirin hydrolysis",
                "subtitle": "minimal mechanism",
                "layout": "centered_title",
                "height_frac": 0.15,
            },
            {
                "id": "row",
                "role": "scene_row",
                "layout": "equal_columns",
                "height_frac": 0.6,
                "rails": [{"name": "midline", "axis": "y", "at": 0.5}],
                "step_sequence": {
                    "id": "seq",
                    "base": {
                        "id": "base",
                        "badge": "1",
                        "slots": [
                            {"id": "mol", "kind": "molecule",
                             "anchors": ["acetyl_C", "ester_O"]},
                            {"id": "lbl", "kind": "text", "label": "aspirin"},
                        ],
                        "attach": [
                            {"child": "lbl", "parent": "mol", "edge": "bottom"},
                        ],
                        "connect": [
                            {"from_anchor": "mol.acetyl_C",
                             "to_anchor": "mol.ester_O", "type": "dashed"},
                        ],
                    },
                    "steps": [
                        {"id": "s1", "badge": "1", "label": "intact"},
                        {"id": "s2", "badge": "2", "label": "cleaved",
                         "deltas": [
                             {"op": "remove", "target": "mol"},
                             {"op": "add",
                              "value": {"id": "prod", "kind": "molecule"}},
                         ]},
                    ],
                },
                "transitions": [
                    {"from_ref": "s1@right", "to_ref": "s2@left",
                     "type": "transition", "on_rail": "midline"},
                ],
                "overlays": [
                    {"id": "gutter", "slots": [
                        {"id": "acetate", "kind": "molecule"}]},
                ],
            },
            {
                "id": "bar",
                "role": "summary_bar",
                "layout": "two_section_bar",
                "height_frac": 0.15,
                "sections": ["reactant", "product"],
                "style": {"band_fill": "#EEF3FB", "divider": True},
            },
        ],
    }


# ---------------------------------------------------------------------------
# Happy path: full figure validates + round-trips
# ---------------------------------------------------------------------------

def test_full_tiered_figure_validates():
    fig = Figure.model_validate(_full_tiered_figure_dict())
    assert [t.id for t in fig.tiers] == ["title", "row", "bar"]
    row = fig.tiers[1]
    assert row.role == TierRole.SCENE_ROW
    assert row.layout == TierLayout.EQUAL_COLUMNS
    assert row.rails[0].name == "midline"
    assert row.step_sequence.base.slots[0].kind == SlotKind.MOLECULE


def test_tiered_figure_roundtrips():
    fig = Figure.from_dict(_full_tiered_figure_dict())
    fig2 = Figure.from_dict(json.loads(fig.to_json()))
    assert fig.model_dump(mode="json") == fig2.model_dump(mode="json")


def test_ir_id_properties():
    assert Scene(id="s").ir_id == "scene_s"
    assert Rail(name="midline").ir_id == "rail_midline"
    assert Tier(id="t", role="band").ir_id == "tier_t"
    assert SceneEdge(from_anchor="a.x", to_anchor="b.y").ir_id == "edge_a.x_b.y"
    assert TierEdge(from_ref="s@right", to_ref="rail:m").ir_id == "tedge_s@right_rail:m"
    assert StepSequence(id="q", base=Scene(id="b")).ir_id == "steps_q"


def test_defaults_are_sensible():
    rail = Rail(name="r")
    assert rail.axis.value == "y" and rail.at == 0.5
    tedge = TierEdge(from_ref="a", to_ref="b")
    assert tedge.type == SceneEdgeType.TRANSITION
    seq = StepSequence(id="q", base=Scene(id="b"))
    assert seq.cumulative is True


# ---------------------------------------------------------------------------
# Three-way exclusivity: leaf / panels / tiers
# ---------------------------------------------------------------------------

def test_tiers_and_entities_mutually_exclusive():
    with pytest.raises(ValidationError, match="at most one of"):
        Figure.model_validate({
            "archetype": "pathway",
            "entities": [{"id": "a", "type": "protein", "label": "A"}],
            "tiers": [{"id": "t", "role": "band"}],
        })


def test_tiers_and_panels_mutually_exclusive():
    with pytest.raises(ValidationError, match="at most one of"):
        Figure.model_validate({
            "archetype": "pathway",
            "panels": [{"id": "p", "grid": [0, 0, 1, 1],
                        "content": {"archetype": "pathway",
                                    "entities": [{"id": "x", "type": "protein",
                                                  "label": "X"}]}}],
            "tiers": [{"id": "t", "role": "band"}],
        })


def test_pure_leaf_figure_still_valid():
    # regression: a normal leaf figure is unaffected by the new field
    fig = Figure.model_validate({
        "archetype": "pathway",
        "entities": [{"id": "a", "type": "protein", "label": "A"}],
    })
    assert fig.tiers == []


# ---------------------------------------------------------------------------
# Id uniqueness + reserved characters
# ---------------------------------------------------------------------------

def test_duplicate_tier_ids_rejected():
    with pytest.raises(ValidationError, match="Tier ids must be unique"):
        Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
            {"id": "t", "role": "band"}, {"id": "t", "role": "band"}]})


def test_duplicate_scene_ids_across_figure_rejected():
    with pytest.raises(ValidationError, match="Scene ids must be unique"):
        Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
            {"id": "r1", "role": "scene_row", "scenes": [{"id": "dup"}]},
            {"id": "r2", "role": "scene_row", "scenes": [{"id": "dup"}]},
        ]})


def test_duplicate_slot_ids_within_scene_rejected():
    with pytest.raises(ValidationError, match="Slot ids must be unique within"):
        Scene.model_validate({"id": "s", "slots": [
            {"id": "m", "kind": "molecule"}, {"id": "m", "kind": "text"}]})


def test_slot_ids_may_repeat_across_scenes():
    # scene id namespaces slots, so reusing 'blob' in two scenes is allowed
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "r", "role": "scene_row", "scenes": [
            {"id": "sa", "slots": [{"id": "blob", "kind": "blob"}]},
            {"id": "sb", "slots": [{"id": "blob", "kind": "blob"}]},
        ]}]})
    assert len(fig.tiers[0].scenes) == 2


@pytest.mark.parametrize("bad", ["a.b", "a__b"])
def test_reserved_chars_rejected_in_ids(bad):
    with pytest.raises(ValidationError, match="reserved"):
        Scene.model_validate({"id": bad})
    with pytest.raises(ValidationError, match="reserved"):
        Slot.model_validate({"id": bad, "kind": "blob"})
    with pytest.raises(ValidationError, match="reserved"):
        Rail.model_validate({"name": bad})


# ---------------------------------------------------------------------------
# Scene reference resolution
# ---------------------------------------------------------------------------

def test_scene_attach_unknown_slot_rejected():
    with pytest.raises(ValidationError, match="unknown parent slot"):
        Scene.model_validate({"id": "s",
            "slots": [{"id": "a", "kind": "blob"}],
            "attach": [{"child": "a", "parent": "ghost"}]})


def test_scene_connect_unknown_slot_rejected():
    with pytest.raises(ValidationError, match="unknown slot"):
        Scene.model_validate({"id": "s",
            "slots": [{"id": "a", "kind": "blob"}],
            "connect": [{"from_anchor": "a.x", "to_anchor": "ghost.y"}]})


def test_scene_content_xor_slots():
    with pytest.raises(ValidationError, match="not both"):
        Scene.model_validate({"id": "s",
            "slots": [{"id": "a", "kind": "blob"}],
            "content": {"archetype": "pathway",
                        "entities": [{"id": "e", "type": "protein", "label": "E"}]}})


def test_scene_with_embedded_figure_content_ok():
    sc = Scene.model_validate({"id": "s",
        "content": {"archetype": "pathway",
                    "entities": [{"id": "e", "type": "protein", "label": "E"}]}})
    assert sc.content.archetype.value == "pathway"


# ---------------------------------------------------------------------------
# Tier exclusivity + ranges + transition refs
# ---------------------------------------------------------------------------

def test_tier_scenes_xor_step_sequence():
    with pytest.raises(ValidationError, match="at most one of"):
        Tier.model_validate({"id": "t", "role": "scene_row",
            "scenes": [{"id": "a"}],
            "step_sequence": {"id": "q", "base": {"id": "b"}}})


@pytest.mark.parametrize("frac", [0.0, 1.5, -0.2])
def test_tier_height_frac_range(frac):
    with pytest.raises(ValidationError, match="height_frac"):
        Tier.model_validate({"id": "t", "role": "band", "height_frac": frac})


@pytest.mark.parametrize("at", [-0.1, 1.1])
def test_rail_at_range(at):
    with pytest.raises(ValidationError, match="between 0 and 1"):
        Rail.model_validate({"name": "r", "at": at})


def test_tier_transition_on_rail_must_be_declared():
    with pytest.raises(ValidationError, match="on_rail"):
        Tier.model_validate({"id": "t", "role": "scene_row",
            "scenes": [{"id": "a"}, {"id": "b"}],
            "transitions": [{"from_ref": "a@right", "to_ref": "b@left",
                             "on_rail": "ghost"}]})


def test_tier_transition_unknown_scene_rejected():
    with pytest.raises(ValidationError, match="unknown scene"):
        Tier.model_validate({"id": "t", "role": "scene_row",
            "scenes": [{"id": "a"}],
            "transitions": [{"from_ref": "a@right", "to_ref": "ghost@left"}]})


def test_tier_transition_unknown_rail_ref_rejected():
    with pytest.raises(ValidationError, match="unknown rail"):
        Tier.model_validate({"id": "t", "role": "scene_row",
            "scenes": [{"id": "a"}],
            "transitions": [{"from_ref": "a@right", "to_ref": "rail:ghost"}]})


# ---------------------------------------------------------------------------
# Step sequence
# ---------------------------------------------------------------------------

def test_duplicate_step_ids_rejected():
    with pytest.raises(ValidationError, match="Step ids must be unique"):
        StepSequence.model_validate({"id": "q", "base": {"id": "b"},
            "steps": [{"id": "s"}, {"id": "s"}]})


def test_step_delta_unknown_target_rejected():
    with pytest.raises(ValidationError, match="does not resolve"):
        StepSequence.model_validate({"id": "q",
            "base": {"id": "b", "slots": [{"id": "mol", "kind": "molecule"}]},
            "steps": [{"id": "s", "deltas": [
                {"op": "remove", "target": "ghost"}]}]})


def test_step_delta_add_then_reference_ok():
    # an ADD introduces a new slot id that a later delta may target (cumulative)
    seq = StepSequence.model_validate({"id": "q",
        "base": {"id": "b", "slots": [{"id": "mol", "kind": "molecule"}]},
        "steps": [
            {"id": "s1", "deltas": [
                {"op": "add", "value": {"id": "prod", "kind": "molecule"}}]},
            {"id": "s2", "deltas": [
                {"op": "remove", "target": "prod"}]},
        ]})
    assert len(seq.steps) == 2


def test_step_op_slot_granular_only():
    # the enum has no set_style/swap (slot-granular by design)
    assert {o.value for o in StepOp} == {
        "add", "remove", "replace", "add_label", "generic"}


# ---------------------------------------------------------------------------
# Builder + compositor wiring
# ---------------------------------------------------------------------------

def test_builder_accepts_tiers():
    fig = build("mechanism_cartoon",
                tiers=[{"id": "t", "role": "title", "label": "Hi"}])
    assert fig.tiers[0].label == "Hi"


def test_compositor_dispatches_tiered_figure():
    # Step 4 wired the scene-chassis engine in: a tiered figure now lowers
    # through layout_tiers instead of raising. An empty BAND tier lays out to
    # no entries (it has no scenes or band chrome), but the call must succeed.
    from imageGen.render.compositor import _dispatch_layout
    fig = Figure.model_validate({"archetype": "mechanism_cartoon",
        "tiers": [{"id": "t", "role": "band"}]})
    assert _dispatch_layout(fig, style_dict={}, smiles_map=None) == []


def test_unknown_enum_values_rejected():
    with pytest.raises(ValidationError):
        Tier.model_validate({"id": "t", "role": "not_a_role"})
    with pytest.raises(ValidationError):
        Slot.model_validate({"id": "s", "kind": "not_a_kind"})
