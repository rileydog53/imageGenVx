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

import math
import re

from imageGen.ir import Figure, Scene
from imageGen.ir.schema import SceneEdgeType, StepSequence, Tier
from imageGen.layout.tier_layout import (
    _EDGE_DEFAULTS,
    _arrow_head,
    _edge_group,
    _transition_label_pos,
    expand_step_sequence,
    layout_tiers,
    tier_rendered_scenes,
)
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


def test_transition_standoff_is_separate_and_larger_than_edge_standoff():
    # D5 (pub-grade): cross-cell transition arrows stand off the scene content
    # edge by more than intra-scene atom edges, so the arrowhead clears the next
    # structure. The default must keep that ordering...
    from imageGen.layout.tier_layout import TIER_DEFAULT_PARAMS
    assert (TIER_DEFAULT_PARAMS["tier_transition_standoff"]
            > TIER_DEFAULT_PARAMS["tier_edge_standoff"])

    # ...and the standoff must flow ONLY to the cross-cell transition: inflating
    # it moves the transition arrow but leaves intra-scene atom edges untouched.
    fig = _aspirin_hydrolysis_figure()

    def edge_svg(extra: dict, ir_id: str) -> str:
        entries = layout_tiers(
            fig, layout_params={"tier_canvas": (600, 300), **extra})
        e = next(x for x in entries if x.ir_id == ir_id)
        return e.primitive(*e.args, **e.kwargs).tostring()

    tedge = "tedge_s_aspirin@right_s_salicylic@left"
    bond = "edge_mol.acetyl_C_mol.ester_O"
    assert edge_svg({}, tedge) != edge_svg({"tier_transition_standoff": 60.0}, tedge)
    assert edge_svg({}, bond) == edge_svg({"tier_transition_standoff": 60.0}, bond)


def test_transition_lane_keeps_slot_labels_off_the_arrow():
    # A cross-cell transition (s@right -> s@left) runs horizontally through the
    # scene's content vertical centre. Before the lane reservation, a side-by-side
    # slot's label placed `right`/`left` at that height landed on the (tier-level,
    # later-drawn) arrow and rendered struck-through (corpus fig 03 "hydroxide").
    # The reserved transition lanes push such labels above/below the row instead.
    import json
    from pathlib import Path

    from imageGen.layout.label_placement import _label_primitive

    fig = Figure.model_validate(
        json.loads(Path("showcase/corpus/03_sn2_substitution.json").read_text()))
    entries = layout_tiers(fig, layout_params={})
    ys = {
        e.args[0]: e.args[1][1]
        for e in entries
        if e.primitive is _label_primitive and e.ir_id
        and e.ir_id.startswith("label_slot_s1_")
    }
    # The two side-by-side molecules' labels straddle the row centre by well more
    # than the lane half-height — neither sits in the mid-row arrow lane.
    lane_hw = 12.0  # == tier_caption_font_size default
    mid = (ys["hydroxide"] + ys["methyl bromide"]) / 2.0
    assert abs(ys["hydroxide"] - mid) > lane_hw
    assert abs(ys["methyl bromide"] - mid) > lane_hw
    # Specifically, the nuc label sits above the row and the sub label below it.
    assert ys["hydroxide"] < mid < ys["methyl bromide"]


def test_transition_label_pos_rides_above_horizontal_shaft():
    # D4: a horizontal arrow's label sits at the midpoint, offset straight up.
    pos = _transition_label_pos((0.0, 0.0), (100.0, 0.0), 10.0)
    assert pos == (50.0, -10.0)


def test_transition_label_pos_vertical_falls_back_to_the_side():
    # A near-vertical arrow has no "above" — the label offsets to the right.
    x, y = _transition_label_pos((0.0, 0.0), (0.0, 100.0), 10.0)
    assert (round(x, 6), round(y, 6)) == (10.0, 50.0)


def test_labeled_transition_emits_a_label_entry_above_the_arrow():
    # D4: a TierEdge.label was silently dropped (only the arrow drew). It must now
    # lower to a `<tedge_id>_label` text entry, placed above the shaft midpoint.
    fig = _aspirin_hydrolysis_figure()
    fig.tiers[1].transitions[0].label = "hydrolysis"
    entries = layout_tiers(fig, layout_params={"tier_canvas": (600, 300)})

    tedge = "tedge_s_aspirin@right_s_salicylic@left"
    labels = [e for e in entries if e.ir_id == f"{tedge}_label"]
    assert len(labels) == 1, "exactly one transition-label entry should lower"
    # Text is baked into the entry's closure; render it to confirm the label.
    assert "hydrolysis" in labels[0].primitive(*labels[0].args, **labels[0].kwargs).tostring()
    # Same figure without the label emits no label entry (purely additive).
    plain = _aspirin_hydrolysis_figure()
    plain_entries = layout_tiers(plain, layout_params={"tier_canvas": (600, 300)})
    assert not [e for e in plain_entries if e.ir_id == f"{tedge}_label"]


def _scene_row_figure(scene_dict: dict, height_frac: float = 0.8) -> Figure:
    return Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [
            {"id": "t", "role": "title", "height_frac": 1.0 - height_frac,
             "label": "T"},
            {"id": "row", "role": "scene_row", "height_frac": height_frac,
             "scenes": [scene_dict]},
        ],
    })


def test_multislot_scene_widens_the_canvas():
    # Pub-grade containment: a scene that spreads several slots horizontally must
    # get a wider cell than a single-slot scene, else it overflows into its
    # neighbour ("steps out of the box"). Canvas width is content-driven.
    from imageGen.layout.tier_layout import tier_canvas
    one = _scene_row_figure({
        "id": "s", "slots": [{"id": "a", "kind": "glyph",
                              "style": {"glyph": "tablet"}}]})
    three = _scene_row_figure({
        "id": "s",
        "slots": [{"id": "a", "kind": "glyph", "style": {"glyph": "tablet"}},
                  {"id": "b", "kind": "glyph", "style": {"glyph": "tablet"}},
                  {"id": "c", "kind": "glyph", "style": {"glyph": "tablet"}}],
        "attach": [{"child": "b", "parent": "a", "edge": "right", "offset": [70, 0]},
                   {"child": "c", "parent": "b", "edge": "right", "offset": [70, 0]}]})
    assert tier_canvas(three)[0] > tier_canvas(one)[0]


def test_small_frac_band_keeps_its_natural_height_floor():
    # A small height_frac must not starve a band below the room its content +
    # labels need; the canvas grows so every band's frac-share clears its natural
    # height (the "summary band too short, labels spill" fix).
    from imageGen.layout.tier_layout import (
        _tier_natural_height, _tier_rects, TIER_DEFAULT_PARAMS, tier_canvas,
    )
    fig = _scene_row_figure({
        "id": "s", "slots": [{"id": "a", "kind": "glyph",
                              "style": {"glyph": "tablet"}}]},
        height_frac=0.15)  # deliberately tiny summary-style band
    canvas = tier_canvas(fig)
    rects = _tier_rects(fig.tiers, canvas, float(TIER_DEFAULT_PARAMS["tier_margin"]),
                        TIER_DEFAULT_PARAMS)
    for tier, (_x, _y, _w, h) in rects:
        assert h >= _tier_natural_height(tier, TIER_DEFAULT_PARAMS) - 1e-6


def test_empty_tiers_rejected():
    with pytest.raises(ValueError, match="tiers populated"):
        layout_tiers(Figure.model_validate(
            {"archetype": "pathway",
             "entities": [{"id": "a", "type": "protein", "label": "A"}]}))


# --- Step 6: StepSequence expansion (P6.1–P6.4) ---------------------------

def _step_seq(*, cumulative=True, steps=None, base=None):
    base = base or {"id": "base", "badge": "0",
                    "slots": [{"id": "a", "kind": "text", "label": "A"}]}
    if steps is None:
        steps = [
            {"id": "s1", "badge": "1", "label": "one"},
            {"id": "s2", "badge": "2", "label": "two", "deltas": [
                {"op": "add", "value": {"id": "b", "kind": "text", "label": "B"}}]},
        ]
    return StepSequence.model_validate(
        {"id": "q", "base": base, "cumulative": cumulative, "steps": steps})


def _step_seq_figure(**kw):
    seq = _step_seq(**kw).model_dump()
    return Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row",
         "rails": [{"name": "m", "axis": "y", "at": 0.5}],
         "step_sequence": seq,
         "transitions": [{"from_ref": "s1@right", "to_ref": "s2@left",
                          "type": "transition", "on_rail": "m"}]}]})


def test_step_sequence_expands_to_concrete_scenes():
    # P6.1: a step_sequence lowers to one concrete scene per step (scene id ==
    # step id), feeding the same column-layout path; the cross-step transition
    # (which references the step ids) resolves.
    entries = layout_tiers(_step_seq_figure(),
                           layout_params={"tier_canvas": (600, 300)})
    ids = {e.ir_id for e in entries}
    assert {"s1.a", "s2.a"} <= ids               # base slot present in both steps
    assert "s2.b" in ids and "s1.b" not in ids   # only s2 added slot "b"
    assert {"scene_s1_badge", "scene_s2_badge"} <= ids
    assert "tedge_s1@right_s2@left" in ids        # cross-step transition resolved


def test_step_sequence_cumulative_accumulates_deltas():
    # cumulative (default): each step builds on the previous.
    seq = _step_seq(steps=[
        {"id": "s1", "deltas": [{"op": "add",
                                 "value": {"id": "b", "kind": "text", "label": "B"}}]},
        {"id": "s2", "deltas": [{"op": "add",
                                 "value": {"id": "c", "kind": "text", "label": "C"}}]}])
    scenes = expand_step_sequence(seq)
    assert [s.id for s in scenes] == ["s1", "s2"]
    assert {sl.id for sl in scenes[0].slots} == {"a", "b"}        # base + s1
    assert {sl.id for sl in scenes[1].slots} == {"a", "b", "c"}   # + s2 (cumulative)


def test_step_sequence_non_cumulative_resets_to_base():
    seq = _step_seq(cumulative=False, steps=[
        {"id": "s1", "deltas": [{"op": "add",
                                 "value": {"id": "b", "kind": "text", "label": "B"}}]},
        {"id": "s2", "deltas": [{"op": "add",
                                 "value": {"id": "c", "kind": "text", "label": "C"}}]}])
    scenes = expand_step_sequence(seq)
    assert {sl.id for sl in scenes[1].slots} == {"a", "c"}        # base + s2 only


def test_step_delta_remove_drops_slot_and_dependent_edges():
    # P6.2: REMOVE also drops attach/connect referencing the slot, so the
    # rebuilt Scene re-validates (no dangling edge).
    base = {"id": "base", "slots": [
        {"id": "a", "kind": "text", "label": "A"},
        {"id": "b", "kind": "text", "label": "B"}],
        "attach": [{"child": "b", "parent": "a", "edge": "bottom"}],
        "connect": [{"from_anchor": "a.center", "to_anchor": "b.center",
                     "type": "dashed"}]}
    seq = StepSequence.model_validate({"id": "q", "base": base, "steps": [
        {"id": "s1", "deltas": [{"op": "remove", "target": "b"}]}]})
    scene = expand_step_sequence(seq)[0]
    assert {sl.id for sl in scene.slots} == {"a"}
    assert scene.attach == [] and scene.connect == []


def test_step_delta_replace_swaps_slot_keeping_id():
    base = {"id": "base", "slots": [{"id": "a", "kind": "text", "label": "old"}]}
    seq = StepSequence.model_validate({"id": "q", "base": base, "steps": [
        {"id": "s1", "deltas": [{"op": "replace", "target": "a",
                                 "value": {"kind": "text", "label": "new"}}]}]})
    a = expand_step_sequence(seq)[0].slots[0]
    assert a.id == "a" and a.label == "new"


def test_step_delta_add_label_sets_slot_label():
    # P6.3: ADD_LABEL lands as a Slot.label, so it rides scene_label_requests /
    # place_labels (the P5.2 pass) — not a fourth placement path.
    base = {"id": "base", "slots": [
        {"id": "a", "kind": "molecule", "style": {"smiles": "CCO"}}]}
    seq = StepSequence.model_validate({"id": "q", "base": base, "steps": [
        {"id": "s1", "deltas": [{"op": "add_label", "target": "a",
                                 "value": {"label": "ethanol"}}]}]})
    assert expand_step_sequence(seq)[0].slots[0].label == "ethanol"


def test_step_added_label_is_placed_by_the_scene_label_pass():
    # P6.3 end-to-end: a step-added molecule label shows up as a placed label
    # entry (same greedy pass as native scene labels).
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "step_sequence": {
            "id": "q", "base": {"id": "base", "slots": [
                {"id": "m", "kind": "molecule", "style": {"smiles": "CCO"}}]},
            "steps": [{"id": "s1", "deltas": [
                {"op": "add_label", "target": "m", "value": {"label": "ethanol"}}]}]}}]})
    entries = layout_tiers(fig, layout_params={"tier_canvas": (400, 300)})
    assert any(e.ir_id == "label_slot_s1_m_label" for e in entries)


def test_step_delta_unsupported_op_fails_loud():
    # P6.2: an op outside add/remove/replace/add_label (the GENERIC escape
    # hatch) raises rather than silently no-op'ing.
    base = {"id": "base", "slots": [{"id": "a", "kind": "text", "label": "A"}]}
    seq = StepSequence.model_validate({"id": "q", "base": base, "steps": [
        {"id": "s1", "deltas": [{"op": "generic", "target": "a"}]}]})
    with pytest.raises(ValueError, match="not supported by expansion"):
        expand_step_sequence(seq)


# --- P7.0: tier_rendered_scenes (verify-facing lockstep helper) ------------

def test_tier_rendered_scenes_lists_what_the_engine_draws():
    # The helper must enumerate exactly the scenes layout_tiers passes through
    # _layout_scene: a TITLE tier draws none; a SCENE_ROW step_sequence
    # contributes one scene per step (expanded, ids == step ids).
    fig = _step_seq_figure()
    title = Tier.model_validate({"id": "t", "role": "title", "label": "X"})
    assert tier_rendered_scenes(title) == []
    assert [s.id for s in tier_rendered_scenes(fig.tiers[0])] == ["s1", "s2"]


def test_tier_rendered_scenes_appends_overlays_after_main():
    # Overlays share the band (gutter strip) and are laid out after the main
    # scenes, so the helper appends them — both must be auditable.
    row = Tier.model_validate({
        "id": "row", "role": "scene_row",
        "scenes": [{"id": "main", "slots": [
            {"id": "m", "kind": "text", "label": "M"}]}],
        "overlays": [{"id": "ov", "slots": [
            {"id": "o", "kind": "text", "label": "O"}]}]})
    assert [s.id for s in tier_rendered_scenes(row)] == ["main", "ov"]


def test_tier_rendered_scenes_matches_engine_tagged_slots():
    # Strong lockstep guard (drift in BOTH directions): every "<scene>.<slot>"
    # id the engine tags must come from a scene the helper lists, and vice versa.
    fig = _aspirin_hydrolysis_figure()
    tagged = {e.ir_id for e in layout_tiers(fig)
              if e.ir_id and "." in e.ir_id and not e.ir_id.startswith(
                  ("edge_", "tedge_", "label_"))}
    expected = {f"{s.id}.{sl.id}"
                for tier in fig.tiers
                for s in tier_rendered_scenes(tier)
                for sl in s.slots}
    assert tagged == expected


# --- Step 6 review-hardening (adversarial-verify findings) -----------------

def test_step_delta_replace_keeps_target_id_over_value_id():
    # REPLACE keeps the slot's identity even when value supplies a different id —
    # otherwise the original id silently vanishes and base refs to it dangle.
    base = {"id": "base", "slots": [{"id": "orig", "kind": "text", "label": "old"}]}
    seq = StepSequence.model_validate({"id": "q", "base": base, "steps": [
        {"id": "s1", "deltas": [{"op": "replace", "target": "orig",
                                 "value": {"id": "different", "kind": "text",
                                           "label": "new"}}]}]})
    slots = expand_step_sequence(seq)[0].slots
    assert [s.id for s in slots] == ["orig"]     # id preserved, not "different"
    assert slots[0].label == "new"


def test_step_delta_on_removed_slot_fails_loud():
    # Cumulative: a later delta targeting a slot a prior step removed validates
    # (the validator's `known` never drops it) but must fail loud, not no-op.
    base = {"id": "base", "slots": [{"id": "a", "kind": "text", "label": "A"},
                                    {"id": "b", "kind": "text", "label": "B"}]}
    seq = StepSequence.model_validate({"id": "q", "base": base, "steps": [
        {"id": "s1", "deltas": [{"op": "remove", "target": "a"}]},
        {"id": "s2", "deltas": [{"op": "replace", "target": "a",
                                 "value": {"kind": "text", "label": "back"}}]}]})
    with pytest.raises(ValueError, match="does not resolve to a live"):
        expand_step_sequence(seq)


def test_step_delta_on_nested_slot_fails_loud():
    # A target that resolves to a nested GROUP-slot id validates but the
    # slot-granular ops only act on the top level — fail loud, not silent no-op.
    base = {"id": "base", "slots": [
        {"id": "g", "kind": "group", "slots": [
            {"id": "inner", "kind": "text", "label": "orig"}]}]}
    seq = StepSequence.model_validate({"id": "q", "base": base, "steps": [
        {"id": "s1", "deltas": [{"op": "add_label", "target": "inner",
                                 "value": {"label": "x"}}]}]})
    with pytest.raises(ValueError, match="does not resolve to a live"):
        expand_step_sequence(seq)


def test_step_add_label_without_label_fails_loud():
    # add_label with no value['label'] must NOT silently erase an existing label.
    base = {"id": "base", "slots": [{"id": "t", "kind": "text", "label": "keep"}]}
    seq = StepSequence.model_validate({"id": "q", "base": base, "steps": [
        {"id": "s1", "deltas": [{"op": "add_label", "target": "t", "value": {}}]}]})
    with pytest.raises(ValueError, match="requires value"):
        expand_step_sequence(seq)


def test_step_delta_add_nested_slot_shape_strips_stray_parent():
    # The {"slot": {...}, "parent": ...} value shape strips a stray inner
    # 'parent' (not a Slot field) just like the flat shape, so it doesn't trip
    # Slot's extra='forbid'.
    base = {"id": "base", "slots": [{"id": "a", "kind": "text", "label": "A"}]}
    seq = StepSequence.model_validate({"id": "q", "base": base, "steps": [
        {"id": "s1", "deltas": [{"op": "add", "value": {
            "slot": {"id": "x", "kind": "text", "label": "X", "parent": "junk"},
            "parent": "a"}}]}]})
    scene = expand_step_sequence(seq)[0]
    assert {s.id for s in scene.slots} == {"a", "x"}
    assert [(at.child, at.parent) for at in scene.attach] == [("x", "a")]


def test_step_style_restyles_only_that_step():
    # P6.4: Step.style folds into the expanded scene's style → rides the P0b.2
    # content cascade as the outermost layer, with no per-step preset name.
    fig = _step_seq_figure(steps=[
        {"id": "s1"},
        {"id": "s2", "style": {"label_font_color": "#FF0000"}}])

    def _cap_fill(scene_slot_id):
        entries = layout_tiers(fig, layout_params={"tier_canvas": (600, 300)})
        e = next(x for x in entries if x.ir_id == scene_slot_id)
        g = e.primitive(*e.args, **e.kwargs)
        return next(el for el in g.elements if el.elementname == "text")["fill"]

    assert _cap_fill("s2.a") == "#FF0000"          # restyled step
    assert _cap_fill("s1.a") == "#1A1A1A"          # untouched step keeps default


def test_step_sequence_canvas_counts_steps():
    # The canvas sizer counts steps (a step_sequence tier has empty .scenes);
    # more steps → a wider canvas.
    from imageGen.layout.tier_layout import _tier_scene_count, tier_canvas

    def _bare(n):  # no transitions, so any step count is buildable
        return Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
            {"id": "row", "role": "scene_row", "step_sequence": {
                "id": "q", "base": {"id": "base", "slots": [
                    {"id": "a", "kind": "text", "label": "A"}]},
                "steps": [{"id": f"s{i}"} for i in range(1, n + 1)]}}]})

    assert _tier_scene_count(_bare(3).tiers[0]) == 3
    assert tier_canvas(_bare(3))[0] > tier_canvas(_bare(1))[0]


# --- Tier.overlays (gutter/free scenes) ------------------------------------

def test_overlays_render_in_a_bottom_gutter():
    # A SCENE_ROW tier's overlays lay out in a bottom gutter strip: the overlay
    # slot renders, and sits BELOW the main row's content.
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row",
         "scenes": [{"id": "s", "slots": [{"id": "m", "kind": "text", "label": "M"}]}],
         "overlays": [{"id": "ov", "slots": [
             {"id": "z", "kind": "text", "label": "OV"}]}]}]})
    entries = layout_tiers(fig, layout_params={"tier_canvas": (600, 300)})
    ids = {e.ir_id for e in entries}
    assert "s.m" in ids and "ov.z" in ids               # both rendered
    main = next(e for e in entries if e.ir_id == "s.m")
    ov = next(e for e in entries if e.ir_id == "ov.z")
    my = float(next(el for el in main.primitive(*main.args, **main.kwargs).elements
                    if el.elementname == "text")["y"])
    oy = float(next(el for el in ov.primitive(*ov.args, **ov.kwargs).elements
                    if el.elementname == "text")["y"])
    assert oy > my                                      # overlay below the main row


def test_overlays_render_with_step_sequence():
    # Overlays coexist with a step_sequence (the aspirin north-star shape):
    # expanded steps AND overlay all render.
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row",
         "step_sequence": {"id": "q", "base": {"id": "b", "slots": [
             {"id": "m", "kind": "text", "label": "M"}]},
             "steps": [{"id": "s1"}, {"id": "s2"}]},
         "overlays": [{"id": "ov", "slots": [
             {"id": "z", "kind": "text", "label": "OV"}]}]}]})
    ids = {e.ir_id for e in layout_tiers(
        fig, layout_params={"tier_canvas": (600, 300)})}
    assert {"s1.m", "s2.m", "ov.z"} <= ids


def test_tier_edge_connects_a_scene_to_an_overlay():
    # An overlay publishes anchors, so a TierEdge (e.g. a 'departs' arrow from a
    # row scene to the departing-fragment overlay) resolves without error.
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row",
         "scenes": [{"id": "s", "slots": [{"id": "m", "kind": "text", "label": "M"}]}],
         "overlays": [{"id": "ov", "slots": [
             {"id": "z", "kind": "text", "label": "OV"}]}],
         "transitions": [{"from_ref": "s@bottom", "to_ref": "ov@top",
                          "type": "departs"}]}]})
    ids = {e.ir_id for e in layout_tiers(
        fig, layout_params={"tier_canvas": (600, 300)})}
    assert "tedge_s@bottom_ov@top" in ids               # endpoint anchors resolved


def test_overlay_free_tier_uses_the_full_band():
    # Carving only happens when overlays exist: an overlay-free tier lays its
    # scene out on the full band (regression guard for the byte-identical path).
    spec = {"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row",
         "scenes": [{"id": "s", "slots": [{"id": "m", "kind": "text", "label": "M"}]}]}]}
    plain = layout_tiers(Figure.model_validate(spec),
                         layout_params={"tier_canvas": (600, 300)})
    m = next(e for e in plain if e.ir_id == "s.m")
    y_full = float(next(el for el in m.primitive(*m.args, **m.kwargs).elements
                        if el.elementname == "text")["y"])
    # adding an overlay carves the band → the main scene shifts UP (smaller y)
    spec2 = {"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row",
         "scenes": [{"id": "s", "slots": [{"id": "m", "kind": "text", "label": "M"}]}],
         "overlays": [{"id": "ov", "slots": [{"id": "z", "kind": "text", "label": "OV"}]}]}]}
    withov = layout_tiers(Figure.model_validate(spec2),
                          layout_params={"tier_canvas": (600, 300)})
    m2 = next(e for e in withov if e.ir_id == "s.m")
    y_carved = float(next(el for el in m2.primitive(*m2.args, **m2.kwargs).elements
                          if el.elementname == "text")["y"])
    assert y_carved < y_full


def test_unsupported_slot_kind_raises():
    # GENERIC is the escape-hatch kind the engine still doesn't render (blob /
    # glyph / residue all landed in P7.1/P7.3).
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [{"id": "b", "kind": "generic"}]}]}]})
    with pytest.raises(NotImplementedError, match="SlotKind"):
        layout_tiers(fig)


def test_molecule_slot_requires_smiles():
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [{"id": "m", "kind": "molecule"}]}]}]})
    with pytest.raises(ValueError, match="style\\['smiles'\\]"):
        layout_tiers(fig)


# --- P7.1: RESIDUE slots render as real fragments (MF-1) -------------------

def test_residue_slot_publishes_attach_and_reactive_anchors():
    # A RESIDUE slot renders through the molecule path and publishes both the
    # backbone attachment and the catalytic atom, scoped under the slot id, so a
    # SceneEdge can bind the residue to a ligand atom.
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import _layout_scene, TIER_DEFAULT_PARAMS
    scene = Scene.model_validate({"id": "site", "slots": [
        {"id": "ser", "kind": "residue", "style": {"residue": "ser530"}}]})
    reg = AnchorRegistry()
    _layout_scene(scene, (0.0, 0.0, 300.0, 200.0), reg, dict(TIER_DEFAULT_PARAMS))
    assert reg.has("site.ser.attach") and reg.has("site.ser.a1")


def test_residue_slot_curly_edge_binds_reactive_atom(tmp_path):
    # End-to-end MF-1∧MF-2 shape: aspirin (molecule) + Ser530 (residue), a curly
    # SceneEdge from the serine O (ser.a1) to aspirin's carbonyl C renders with
    # both slots and the edge tagged.
    from imageGen.render.compositor import render_figure
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "site", "slots": [
                {"id": "asp", "kind": "molecule", "style": {
                    "smiles": "C[C:1](=O)Oc1ccccc1C(=O)O",
                    "anchor_names": {"1": "carbonyl_C"}}},
                {"id": "ser", "kind": "residue", "style": {"residue": "ser530"}}],
             "attach": [{"child": "ser", "parent": "asp", "edge": "right"}],
             "connect": [{"from_anchor": "ser.a1", "to_anchor": "asp.carbonyl_C",
                          "type": "curly"}]}]}]})
    out = render_figure(fig, tmp_path / "mech.svg")
    txt = out.read_text()
    for sid in ("site.asp", "site.ser", "edge_ser.a1_asp.carbonyl_C"):
        assert f'id="{sid}"' in txt, f"missing {sid!r}"


def test_residue_slot_unknown_name_fails_loud():
    # A residue name with no '*' (resolved as raw SMILES that caps cleanly) fails
    # loud — the open valence is mandatory.
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [
                {"id": "r", "kind": "residue", "style": {"smiles": "CCO"}}]}]}]})
    with pytest.raises(ValueError, match="open-valence attachment"):
        layout_tiers(fig)


def test_residue_slot_requires_smiles_or_residue():
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [{"id": "r", "kind": "residue"}]}]}]})
    with pytest.raises(ValueError, match="style\\['residue'\\]"):
        layout_tiers(fig)


# --- P7.2: arrow-pushing curly arrow (handedness / arc / head, MF-2) --------

def _edge_path_d(edge_type, style):
    g = _edge_group((0.0, 0.0), (100.0, 0.0), edge_type, style)
    return re.search(r'd="([^"]+)"', g.tostring()).group(1)


def test_curly_default_arc_is_byte_identical():
    # Default curly (no curl/arc) keeps the historical symmetric quadratic bow,
    # so every existing curved edge renders unchanged.
    assert _edge_path_d(SceneEdgeType.CURLY, None) == \
        "M 0.00,0.00 Q 50.00,20.00 100.00,0.00"


def test_curly_handedness_flips_the_arc():
    # curl='cw' mirrors the control point to the other side (arrow-pushing
    # handedness) — the only change is the sign of the perpendicular offset.
    assert _edge_path_d(SceneEdgeType.CURLY, {"curl": "cw"}) == \
        "M 0.00,0.00 Q 50.00,-20.00 100.00,0.00"


def test_curly_arc_s_draws_an_s_shaped_cubic():
    # arc='s' emits a cubic whose two control points bow to OPPOSITE sides
    # (electron flow swinging out and back).
    d = _edge_path_d(SceneEdgeType.CURLY, {"arc": "s"})
    assert d.startswith("M 0.00,0.00 C ")
    assert "33.33,20.00" in d and "66.67,-20.00" in d


def test_arrow_head_width_frac_narrows_the_base():
    def base_w(wf):
        poly = _arrow_head((0.0, 0.0), (100.0, 0.0), "#000", size=8.0, width_frac=wf)
        pts = [tuple(map(float, p.split(",")))
               for p in re.search(r'points="([^"]+)"', poly.tostring()).group(1).split()]
        return math.hypot(pts[1][0] - pts[2][0], pts[1][1] - pts[2][1])
    assert base_w(0.4) < base_w(0.5)


def test_curly_uses_a_narrower_head_than_a_transition():
    def head_base(edge_type):
        g = _edge_group((0.0, 0.0), (100.0, 0.0), edge_type, None)
        poly = re.search(r'<polygon[^>]*points="([^"]+)"', g.tostring()).group(1)
        pts = [tuple(map(float, p.split(","))) for p in poly.split()]
        return math.hypot(pts[1][0] - pts[2][0], pts[1][1] - pts[2][1])
    assert head_base(SceneEdgeType.CURLY) < head_base(SceneEdgeType.TRANSITION)


def test_curly_arrow_originates_on_a_bond_anchor(tmp_path):
    # MF-2 end-to-end: a curly arrow from the C=O bond midpoint (bond_a1_a2) to
    # the carbonyl oxygen renders with the edge tagged — no eyeballed coordinate.
    from imageGen.render.compositor import render_figure
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [
                {"id": "mol", "kind": "molecule", "style": {
                    "smiles": "C[C:1](=[O:2])Oc1ccccc1C(=O)O",
                    "anchor_names": {"1": "carbonyl_C", "2": "carbonyl_O"}}}],
             "connect": [{"from_anchor": "mol.bond_a1_a2", "to_anchor": "mol.a2",
                          "type": "curly", "style": {"arc": "s"}}]}]}]})
    out = render_figure(fig, tmp_path / "push.svg")
    assert 'id="edge_mol.bond_a1_a2_mol.a2"' in out.read_text()


# --- P7.3: blob + cavity, glyph slots, TS partial bond, inhibits T-bar ------

def test_blob_slot_publishes_cavity_anchors():
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import _layout_scene, TIER_DEFAULT_PARAMS
    scene = Scene.model_validate({"id": "enz", "slots": [
        {"id": "cox", "kind": "blob", "label": "COX-1"}]})
    reg = AnchorRegistry()
    _layout_scene(scene, (0.0, 0.0, 300.0, 200.0), reg, dict(TIER_DEFAULT_PARAMS))
    for a in ("enz.cox.cavity_center", "enz.cox.cavity_top", "enz.cox.cavity_bottom"):
        assert reg.has(a), f"missing cavity anchor {a}"


def test_residue_attaches_into_blob_cavity(tmp_path):
    # A cavity-attached residue lands INSIDE the blob (coincident with its centre)
    # — the de-overlap pass must NOT push it out of the pocket.
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import _layout_scene, TIER_DEFAULT_PARAMS
    scene = Scene.model_validate({"id": "site", "slots": [
        {"id": "cox", "kind": "blob"},
        {"id": "ser", "kind": "residue", "style": {"residue": "ser530"}}],
        "attach": [{"child": "ser", "parent": "cox", "edge": "cavity_center"}]})
    reg = AnchorRegistry()
    _layout_scene(scene, (0.0, 0.0, 300.0, 200.0), reg, dict(TIER_DEFAULT_PARAMS))
    cavity = reg.resolve("site.cox.cavity_center")
    # the residue's published attach point sits within the blob's slot box
    sw, sh = TIER_DEFAULT_PARAMS["tier_slot_size"]
    ax, ay = reg.resolve("site.ser.attach")
    assert abs(ax - cavity[0]) <= sw / 2.0 and abs(ay - cavity[1]) <= sh / 2.0


def test_two_center_attached_slots_still_deoverlap_with_a_cavity_sibling():
    # The cavity exemption must not disable de-overlap for genuine center-attached
    # tangles (MF-3): two center-bound children still spread apart.
    from imageGen.layout.tier_layout import _solve_slot_centers
    scene = Scene.model_validate({"id": "s", "slots": [
        {"id": "blob", "kind": "blob"},
        {"id": "his", "kind": "text"}, {"id": "lig", "kind": "text"}],
        "attach": [{"child": "his", "parent": "blob", "edge": "center"},
                   {"child": "lig", "parent": "blob", "edge": "center"}]})
    centers = _solve_slot_centers(scene, (0.0, 0.0, 300.0, 200.0), (60.0, 40.0))
    assert centers["his"][0] != centers["lig"][0]  # still separated


def test_glyph_slot_renders_a_registered_primitive(tmp_path):
    from imageGen.render.compositor import render_figure
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [
                {"id": "pill", "kind": "glyph", "style": {"glyph": "tablet"}},
                {"id": "pg", "kind": "glyph",
                 "style": {"glyph": "pg_cluster", "reduced": True}}]}]}]})
    out = render_figure(fig, tmp_path / "glyphs.svg")
    txt = out.read_text()
    assert 'id="s.pill"' in txt and 'id="s.pg"' in txt


def test_glyph_slot_unknown_glyph_fails_loud():
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [
                {"id": "g", "kind": "glyph", "style": {"glyph": "nope"}}]}]}]})
    with pytest.raises(ValueError, match="known style\\['glyph'\\]"):
        layout_tiers(fig)


def test_ts_partial_bond_is_a_thin_dashed_stub():
    # P7.3b: a 'partial' edge draws a finely-dashed line with no arrow/T-bar.
    g = _edge_group((0.0, 0.0), (40.0, 0.0), SceneEdgeType.DASHED, {"partial": True})
    xml = g.tostring()
    assert "stroke-dasharray" in xml
    assert "<polygon" not in xml          # no arrowhead
    assert 'stroke-linecap="square"' not in xml  # no T-bar


def test_inhibits_edge_draws_a_tbar_not_an_arrow():
    g = _edge_group((0.0, 0.0), (40.0, 0.0), SceneEdgeType.INHIBITS, None)
    xml = g.tostring()
    assert 'stroke-linecap="square"' in xml  # T-bar terminus
    assert "<polygon" not in xml             # never an arrowhead


def test_tier_inhibits_edge_passes_convention(tmp_path):
    from imageGen.render.compositor import render_figure
    from imageGen.verify.convention_check import convention_check
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row",
         "scenes": [
             {"id": "a", "slots": [{"id": "m", "kind": "text", "label": "aspirin"}]},
             {"id": "b", "slots": [{"id": "m", "kind": "text", "label": "COX-1"}]}],
         "transitions": [{"from_ref": "a@right", "to_ref": "b@left",
                          "type": "inhibits"}]}]})
    out = render_figure(fig, tmp_path / "inhib.svg")
    convention_check(fig, out)  # no exception — the transition drew a T-bar


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
    # b/c each step right by half a slot width; the chain is then centred in the
    # cell (its bbox midpoint sits on the cell centre x=150), so a/b/c shift left.
    assert centers["b"][0] - centers["a"][0] == 25.0
    assert centers["c"][0] - centers["b"][0] == 25.0
    assert (centers["a"][0] + centers["c"][0]) / 2.0 == 150.0  # block centred
    assert centers["a"][1] == centers["b"][1] == centers["c"][1] == 50.0


def test_attach_cycle_raises():
    from imageGen.layout.tier_layout import _solve_slot_centers
    scene = _scene_with_attach([
        {"child": "a", "parent": "b", "edge": "right"},
        {"child": "b", "parent": "a", "edge": "right"},
    ])
    with pytest.raises(ValueError, match="cyclic or unresolvable"):
        _solve_slot_centers(scene, (0.0, 0.0, 300.0, 100.0), (50.0, 40.0))


def test_unsupported_attach_edge_raises():
    # P5.1: cavity_* is now resolvable, so the unsupported-edge contract is
    # pinned by `custom` (anchor/custom + parent_anchor resolution land in Step 7).
    from imageGen.layout.tier_layout import _solve_slot_centers
    scene = _scene_with_attach([{"child": "b", "parent": "a", "edge": "custom"}])
    with pytest.raises(NotImplementedError, match="attach edge"):
        _solve_slot_centers(scene, (0.0, 0.0, 300.0, 100.0), (50.0, 40.0))


def test_cavity_edges_resolve_inside_parent():
    # P5.1: cavity_top / cavity_bottom drop a child a quarter-extent off the
    # parent centre (inside the parent box, a binding-pocket region).
    from imageGen.layout.tier_layout import _solve_slot_centers
    scene = _scene_with_attach([
        {"child": "b", "parent": "a", "edge": "cavity_top"},
        {"child": "c", "parent": "a", "edge": "cavity_bottom"},
    ])
    centers = _solve_slot_centers(scene, (0.0, 0.0, 300.0, 100.0), (50.0, 40.0))
    assert centers["a"] == (150.0, 50.0)            # sole root → cell centre
    assert centers["b"] == (150.0, 50.0 - 0.25 * 40.0)  # quarter up, inside
    assert centers["c"] == (150.0, 50.0 + 0.25 * 40.0)  # quarter down, inside


def test_two_center_attached_slots_do_not_overlap():
    # MF-3: two slots both bound at `center` previously landed on the same point
    # (the His513-vs-ligand tangle). The solver now spreads co-located boxes so
    # they are disjoint, centred symmetrically on the shared point.
    from imageGen.layout.tier_layout import _solve_slot_centers
    sw, sh = 60.0, 40.0
    scene = Scene.model_validate({
        "id": "s",
        "slots": [{"id": "his", "kind": "text"}, {"id": "lig", "kind": "text"}],
        "attach": [{"child": "his", "edge": "center"},
                   {"child": "lig", "edge": "center"}],
    })
    centers = _solve_slot_centers(scene, (0.0, 0.0, 300.0, 200.0), (sw, sh))
    his_maxx = centers["his"][0] + sw / 2.0
    lig_minx = centers["lig"][0] - sw / 2.0
    assert his_maxx <= lig_minx                                  # disjoint boxes
    assert (centers["his"][0] + centers["lig"][0]) / 2.0 == pytest.approx(150.0)
    assert centers["his"][1] == 100.0 and centers["lig"][1] == 100.0


def test_solve_slot_centers_is_deterministic():
    # Co-location de-overlap must be order-stable: solving twice yields an
    # identical dict (Kahn order + declaration tiebreak, no set iteration).
    from imageGen.layout.tier_layout import _solve_slot_centers
    scene = Scene.model_validate({
        "id": "s",
        "slots": [{"id": "his", "kind": "text"}, {"id": "lig", "kind": "text"}],
        "attach": [{"child": "his", "edge": "center"},
                   {"child": "lig", "edge": "center"}],
    })
    rect, size = (0.0, 0.0, 300.0, 200.0), (60.0, 40.0)
    assert _solve_slot_centers(scene, rect, size) == _solve_slot_centers(scene, rect, size)


def test_slot_extents_widen_the_parent_slide():
    # P5.1: when a per-slot extent is supplied, the child slide uses the
    # *parent's* real width (not the uniform slot size) so a wide parent pushes
    # its child clear of its actual box. Absent extents → uniform fallback.
    from imageGen.layout.tier_layout import _solve_slot_centers
    scene = Scene.model_validate({
        "id": "s",
        "slots": [{"id": "a", "kind": "text"}, {"id": "b", "kind": "text"}],
        "attach": [{"child": "b", "parent": "a", "edge": "right"}],
    })
    rect = (0.0, 0.0, 300.0, 100.0)
    # The invariant is the parent-slide DISTANCE (b − a): half the parent's
    # extent. (Absolute coords then shift when the chain is centred in the cell.)
    uniform = _solve_slot_centers(scene, rect, (50.0, 40.0))
    assert uniform["b"][0] - uniform["a"][0] == 25.0   # 0.5 * uniform 50
    # wide parent extent: the slide uses the parent's real width
    wide = _solve_slot_centers(scene, rect, (50.0, 40.0),
                               slot_extents={"a": (200.0, 40.0)})
    assert wide["b"][0] - wide["a"][0] == 100.0        # 0.5 * 200


def test_scene_label_requests_covers_caption_slot_and_edge():
    # P5.2: scene_label_requests emits the caption, a non-TEXT Slot.label, and a
    # SceneEdge.label (the latter two previously unrendered); a TEXT slot's label
    # is the body, never a separate request. ir_ids are preserved.
    from imageGen.layout.tier_layout import (
        TIER_DEFAULT_PARAMS, scene_label_requests,
    )
    scene = Scene.model_validate({
        "id": "s", "label": "caption",
        "slots": [
            {"id": "blob", "kind": "molecule", "label": "His513",
             "style": {"smiles": "CCO"}},
            {"id": "note", "kind": "text", "label": "ignored"},
        ],
        "connect": [{"from_anchor": "blob.center", "to_anchor": "note.center",
                     "type": "dashed", "label": "H-bond"}],
    })
    reqs = scene_label_requests(
        scene, content_extent=(0.0, 0.0, 100.0, 80.0),
        centers={"blob": (50.0, 40.0), "note": (50.0, 40.0)},
        slot_size=(60.0, 40.0),
        edge_anchors={"edge_blob.center_note.center": (50.0, 40.0)},
        params=dict(TIER_DEFAULT_PARAMS))
    ids = {r.ir_id for r in reqs}
    assert "scene_s_label" in ids                        # caption (line 0)
    assert "slot_s_blob_label" in ids                    # non-TEXT slot label
    assert "edge_blob.center_note.center_label" in ids   # scene-edge label
    assert not any(r.text == "ignored" for r in reqs)    # TEXT slot label skipped


def test_scene_caption_multiline_emits_one_request_per_line():
    # P5.2: a multi-line caption stacks one request per line; line 0 keeps the
    # canonical id so token assertions survive, later lines get a distinct id.
    from imageGen.layout.tier_layout import (
        TIER_DEFAULT_PARAMS, scene_label_requests,
    )
    scene = Scene.model_validate({"id": "s", "label": "line one\nline two",
                                  "slots": [{"id": "m", "kind": "text"}]})
    reqs = scene_label_requests(
        scene, content_extent=(0.0, 0.0, 100.0, 80.0),
        centers={"m": (50.0, 40.0)}, slot_size=(60.0, 40.0),
        edge_anchors={}, params=dict(TIER_DEFAULT_PARAMS))
    ids = [r.ir_id for r in reqs]
    assert ids == ["scene_s_label", "scene_s_label_l1"]
    assert reqs[1].anchor[1] > reqs[0].anchor[1]   # second line anchored lower


def test_rail_endpoint_transition_not_supported():
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row",
         "rails": [{"name": "midline", "axis": "y", "at": 0.5}],
         "scenes": [{"id": "a", "slots": [
             {"id": "m", "kind": "molecule", "style": {"smiles": "CCO"}}]}],
         "transitions": [{"from_ref": "rail:midline", "to_ref": "a@right"}]}]})
    with pytest.raises(NotImplementedError, match="rail.*endpoint"):
        layout_tiers(fig)


def test_scene_connect_aggregates_unresolved_anchor_refs():
    """P0a.5: two bad connect anchors surface in ONE error naming both (the
    schema validates the slot token at build time but not the anchor segment)."""
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [{"id": "m", "kind": "text", "label": "X"}],
             "connect": [{"from_anchor": "m.ghost1", "to_anchor": "m.ghost2"}]}]}]})
    with pytest.raises(ValueError, match="unresolved connect") as exc:
        layout_tiers(fig)
    msg = str(exc.value)
    assert "ghost1" in msg and "ghost2" in msg, msg


def test_tier_transition_aggregates_unresolved_refs():
    """P0a.5: two bad transition endpoints surface in ONE error."""
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "a", "slots": [{"id": "m", "kind": "text", "label": "A"}]},
            {"id": "b", "slots": [{"id": "m", "kind": "text", "label": "B"}]}],
         "transitions": [{"from_ref": "a.m.ghost", "to_ref": "b.m.ghost"}]}]})
    with pytest.raises(ValueError, match="unresolved transition") as exc:
        layout_tiers(fig)
    msg = str(exc.value)
    assert "a.m.ghost" in msg and "b.m.ghost" in msg, msg


# ---------------------------------------------------------------------------
# P5.4 placement nits
# ---------------------------------------------------------------------------

def test_text_parent_slide_uses_text_width():
    # Nit-1: a child attached to a TEXT parent slides by the parent's measured
    # text width (threaded via slot_extents), not the full molecule slot width.
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import (
        TIER_DEFAULT_PARAMS, _layout_scene, _slot_bbox_size,
    )
    params = dict(TIER_DEFAULT_PARAMS)
    scene = Scene.model_validate({"id": "s", "slots": [
        {"id": "p", "kind": "text", "label": "His"},
        {"id": "c", "kind": "text", "label": "x"}],
        "attach": [{"child": "c", "parent": "p", "edge": "right"}]})
    reg = AnchorRegistry()
    _layout_scene(scene, (0.0, 0.0, 400.0, 200.0), reg, params)
    px, _py = reg.resolve("s.p.center")
    cx_c, _cy = reg.resolve("s.c.center")
    sw, _sh = params["tier_slot_size"]
    parent_w = _slot_bbox_size(scene.slots[0], (sw, _sh), params)[0]
    assert cx_c == pytest.approx(px + 0.5 * parent_w)
    assert cx_c < px + 0.5 * sw  # strictly less than the old molecule-width slide


def test_content_sized_molecule_is_centred_on_the_cell():
    # Content-aware sizing renders the molecule at a derived box and centres it on
    # the cell centre (the renderer bakes center=, so the scene-frame centre — the
    # content centroid of a lone slot — lands on the cell centre).
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import TIER_DEFAULT_PARAMS, _layout_scene
    scene = Scene.model_validate({"id": "s", "slots": [
        {"id": "mol", "kind": "molecule", "style": {"smiles": "CCO"}}]})
    reg = AnchorRegistry()
    _layout_scene(scene, (0.0, 0.0, 400.0, 200.0), reg, dict(TIER_DEFAULT_PARAMS))
    cxr, cyr = reg.resolve("s.center")
    assert cxr == pytest.approx(200.0, abs=1.0) and cyr == pytest.approx(100.0, abs=1.0)
    # atom anchors straddle the cell centre (molecule really is centred there)
    xs = [reg.resolve(f"s.mol.atom{i}")[0] for i in range(3)]
    assert min(xs) < 200.0 < max(xs)


def test_text_slot_center_anchor_is_midline():
    # Nit-3: a text slot's published `center` anchor is the visual midline, and
    # the rendered baseline drops 0.35 em below it.
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import TIER_DEFAULT_PARAMS, _layout_scene
    params = dict(TIER_DEFAULT_PARAMS)
    scene = Scene.model_validate({"id": "s", "slots": [
        {"id": "t", "kind": "text", "label": "His"}]})
    reg = AnchorRegistry()
    entries = _layout_scene(scene, (0.0, 0.0, 200.0, 100.0), reg, params)
    _cx, cy_anchor = reg.resolve("s.t.center")
    assert (_cx, cy_anchor) == (100.0, 50.0)            # midline at cell centre
    text_entry = next(e for e in entries if e.ir_id == "s.t")
    g = text_entry.primitive(*text_entry.args, **text_entry.kwargs)
    txt = next(el for el in g.elements if el.elementname == "text")
    fs = int(params["tier_text_font_size"])
    assert float(txt["y"]) == pytest.approx(cy_anchor + fs * 0.35)


def test_base_preset_drives_tier_text_colour_and_family():
    # P0b.1: the journal preset's label_font_color / label_font_family map onto
    # the tier text params so a tiered figure honours its journal (it previously
    # dropped style_dict entirely). cell_press is byte-identical to the engine
    # defaults; acs (Times serif, #000000) visibly differs. Font SIZE is NOT
    # remapped (the engine owns title/subtitle/caption sizes).
    from imageGen.layout.tier_layout import _preset_tier_params
    from imageGen.styles.loader import load_style

    mapped = _preset_tier_params(load_style("acs"))
    assert mapped == {"tier_text_color": "#000000",
                      "tier_font_family": "Times, Times New Roman, serif"}
    assert "tier_text_font_size" not in mapped     # size is engine-owned
    assert _preset_tier_params(None) == {}
    assert _preset_tier_params({}) == {}

    fig = _aspirin_hydrolysis_figure()

    def _cap_attrs(style_dict):
        entries = layout_tiers(fig, layout_params={"tier_canvas": (600, 300)},
                               style_dict=style_dict)
        e = next(x for x in entries if x.ir_id == "s_aspirin.cap")  # TEXT slot
        g = e.primitive(*e.args, **e.kwargs)
        t = next(el for el in g.elements if el.elementname == "text")
        return t["fill"], t["font-family"]

    # acs visibly differs; cell_press (the default preset) is byte-identical to
    # passing no preset at all — so the default render is unchanged.
    assert _cap_attrs(load_style("acs")) == (
        "#000000", "Times, Times New Roman, serif")
    assert _cap_attrs(load_style("cell_press")) == _cap_attrs(None)
    assert _cap_attrs(None) == ("#1A1A1A", "Helvetica, Arial, sans-serif")


def _two_text_scene(extra=None):
    spec = {"id": "s",
            "slots": [{"id": "a", "kind": "text", "label": "A"},
                      {"id": "b", "kind": "text", "label": "B"}],
            "connect": [{"from_anchor": "a.center", "to_anchor": "b.center",
                         "type": "dashed"}]}
    if extra:
        spec.update(extra)
    return Scene.model_validate(spec)


def _drawn_stroke(entry):
    g = entry.primitive(*entry.args, **entry.kwargs)
    el = next(e for e in g.elements if e.elementname in ("path", "line"))
    return el["stroke"]


def test_cascade_preset_does_not_recolour_semantic_edges():
    # P0b.2 correctness guard: the base preset's bare `stroke` (acs/nature) must
    # NOT bleed onto chassis edges — a dashed edge keeps its semantic red even
    # though acs sets a black bare stroke. (The literal {**preset, **edge.style}
    # fold the plan sketched would have blackened every semantic edge.)
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import (
        TIER_DEFAULT_PARAMS, _EDGE_DEFAULTS, _layout_scene)
    from imageGen.styles.loader import load_style

    acs = load_style("acs")
    assert acs.get("stroke") == "#1A1A1A"            # the colliding preset key
    reg = AnchorRegistry()
    entries = _layout_scene(_two_text_scene(), (0.0, 0.0, 300.0, 120.0), reg,
                            dict(TIER_DEFAULT_PARAMS), base_style=acs)
    edge = next(e for e in entries if e.ir_id.startswith("edge_"))
    assert _drawn_stroke(edge) == _EDGE_DEFAULTS["dashed"]["stroke"]  # #888888
    assert _drawn_stroke(edge) != acs["stroke"]                       # not black


def test_cascade_scene_style_overrides_content_and_edge():
    # P0b.2 content + structural channels: scene.style layers over the base for
    # text colour (content) and an explicit edge stroke (structural).
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import TIER_DEFAULT_PARAMS, _layout_scene

    scene = _two_text_scene({"style": {"label_font_color": "#FF0000",
                                       "stroke": "#00FF00"}})
    reg = AnchorRegistry()
    entries = _layout_scene(scene, (0.0, 0.0, 300.0, 120.0), reg,
                            dict(TIER_DEFAULT_PARAMS))
    a = next(e for e in entries if e.ir_id == "s.a")
    txt = next(el for el in a.primitive(*a.args, **a.kwargs).elements
               if el.elementname == "text")
    assert txt["fill"] == "#FF0000"                  # content channel
    edge = next(e for e in entries if e.ir_id.startswith("edge_"))
    assert _drawn_stroke(edge) == "#00FF00"          # structural channel


def test_cascade_preset_reaches_molecules():
    # P0b.2: tier molecules follow the journal preset (like the leaf path) —
    # acs recolours bonds; cell_press (the default) is byte-identical to no
    # preset, so the default tier render is unchanged.
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import TIER_DEFAULT_PARAMS, _layout_scene
    from imageGen.styles.loader import load_style

    scene = Scene.model_validate({"id": "s", "slots": [
        {"id": "mol", "kind": "molecule", "style": {"smiles": ASPIRIN}}]})

    def _mol_svg(style_dict):
        reg = AnchorRegistry()
        entries = _layout_scene(scene, (0.0, 0.0, 300.0, 200.0), reg,
                                dict(TIER_DEFAULT_PARAMS), base_style=style_dict)
        e = next(x for x in entries if x.ir_id == "s.mol")
        return e.primitive(*e.args, **e.kwargs).tostring()

    assert _mol_svg(load_style("acs")) != _mol_svg(None)          # journal reaches bonds
    assert _mol_svg(load_style("cell_press")) == _mol_svg(None)   # default unchanged


# --- Dim 4: edge colour semantics (layering/contrast) -----------------------

def _edge_stroke(edge_type, style=None):
    """Stroke colour of the first path/line element in an _edge_group output."""
    g = _edge_group((0.0, 0.0), (100.0, 0.0), edge_type, style)
    el = next(e for e in g.elements if e.elementname in ("path", "line"))
    return el["stroke"]


def _edge_stroke_width(edge_type, style=None):
    """Stroke-width of the first path/line element in an _edge_group output."""
    g = _edge_group((0.0, 0.0), (100.0, 0.0), edge_type, style)
    el = next(e for e in g.elements if e.elementname in ("path", "line"))
    return float(el["stroke-width"])


def test_dim4_hbond_defaults_to_biochem_blue():
    # dim-4: H-bonds are blue (#1A6FC9), not red — universal H-bond convention and
    # avoids semantic collision with inhibits (red T-bar).
    assert _EDGE_DEFAULTS["hbond"]["stroke"] == "#1A6FC9"
    assert _edge_stroke(SceneEdgeType.HBOND) == "#1A6FC9"


def test_dim4_dashed_defaults_to_neutral_gray():
    # dim-4: generic dashed interaction (partial/TS bond) is gray, not red.
    assert _EDGE_DEFAULTS["dashed"]["stroke"] == "#888888"
    assert _edge_stroke(SceneEdgeType.DASHED) == "#888888"


def test_dim4_curly_defaults_to_auburn_not_bond_black():
    # dim-4: electron-flow curly arrows are dark auburn (#8B2500), distinct from
    # molecular bond ink (#1A1A1A) so they remain readable when crossing bonds.
    assert _EDGE_DEFAULTS["curly"]["stroke"] == "#8B2500"
    assert _edge_stroke(SceneEdgeType.CURLY) == "#8B2500"
    assert _edge_stroke(SceneEdgeType.CURLY) != "#1A1A1A"


def test_dim4_inhibits_still_red_no_regression():
    # inhibits (T-bar) stays red (#CC2222) — the only semantic red after dim-4.
    assert _EDGE_DEFAULTS["inhibits"]["stroke"] == "#CC2222"
    assert _edge_stroke(SceneEdgeType.INHIBITS) == "#CC2222"


def test_dim4_hbond_thinner_than_curly():
    # hbond spec carries stroke_width=1.5 (delicate dash); curly uses the 2.0
    # global default — H-bonds are conventionally thinner than covalent-bond arrows.
    assert "stroke_width" in _EDGE_DEFAULTS["hbond"]
    assert _edge_stroke_width(SceneEdgeType.HBOND) == 1.5
    assert _edge_stroke_width(SceneEdgeType.CURLY) == 2.0


def test_dim4_per_type_stroke_width_overridable_by_style():
    # Edge-level style["stroke_width"] wins over the per-type spec default.
    assert _edge_stroke_width(SceneEdgeType.HBOND, {"stroke_width": 3.0}) == 3.0
