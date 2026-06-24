"""dim-2 leader lines for the tier engine (``tier_label_leaders``).

Sibling of ``test_relation_label_leaders.py`` for the scene chassis. A scene-local
slot/edge label that ``place_labels`` pushed far from its anchor (the D1 residue
drift, the D3 edge-label flight) earns a hairline dashed tether back to the
structure it names; a label that landed snug beside its anchor gets none, and a
caption (absent from ``leader_anchors``) is never tethered.

Pins, against the post-pass directly so the geometry is exact:
  1. A drifted label (gap > ``_TIER_LEADER_MIN_GAP``) yields one ``_leader_line``
     entry, tagged ``leader_<id>``, inserted before the first label entry.
  2. A snug label (gap below the threshold) yields no leader.
  3. The leader's endpoints are ordered label-edge → anchor-box-edge (so it draws
     from the text toward the structure, not through either).
  4. End-to-end: the aspirin acceptance figure emits leaders that tether its
     drifting residue labels (``Ser530``).
"""
from __future__ import annotations

from imageGen.layout._pathway_labels import _leader_line
from imageGen.layout.label_placement import _label_primitive
from imageGen.layout.tier_layout import _TIER_LEADER_MIN_GAP, tier_label_leaders
from imageGen.layout.types import LayoutEntry


def _label(text: str, center: tuple[float, float], ir_id: str) -> LayoutEntry:
    return LayoutEntry(
        primitive=_label_primitive,
        args=(text, center),
        kwargs={},
        position=(0.0, 0.0),
        ir_id=ir_id,
    )


def test_drifted_label_gets_one_ordered_leader() -> None:
    # Anchor box centred at (100, 100), half-extent 10x10; label parked far below.
    anchor_center = (100.0, 100.0)
    far_label = _label("Ser530", (100.0, 100.0 + 80.0), "label_slot_s_x_label")
    leader_anchors = {"label_slot_s_x_label": (anchor_center, (10.0, 10.0))}

    out = tier_label_leaders([far_label], leader_anchors)

    leaders = [e for e in out if e.primitive is _leader_line]
    assert len(leaders) == 1, "a far-drifted slot label should earn exactly one tether"
    leader = leaders[0]
    assert leader.ir_id == "leader_slot_s_x_label"
    # Inserted before the (only) label entry.
    assert out.index(leader) < out.index(far_label)
    # Endpoints ordered label-edge → anchor-box-edge, both on the vertical line,
    # and strictly between the label center and the anchor center.
    (lx, ly), (bx, by) = leader.args
    assert lx == bx == 100.0
    assert anchor_center[1] < by < ly < far_label.args[1][1]


def test_snug_label_gets_no_leader() -> None:
    # Label sits just under the anchor box edge — inside the threshold → no tether.
    anchor_center = (100.0, 100.0)
    gap = _TIER_LEADER_MIN_GAP - 5.0
    snug = _label("His57", (100.0, 100.0 + 10.0 + gap), "label_slot_s_y_label")
    leader_anchors = {"label_slot_s_y_label": (anchor_center, (10.0, 10.0))}

    out = tier_label_leaders([snug], leader_anchors)

    assert not [e for e in out if e.primitive is _leader_line]
    assert out == [snug]  # exact no-op


def test_caption_not_in_anchor_map_is_never_tethered() -> None:
    # A caption is intentionally absent from leader_anchors, so even parked far it
    # earns no leader (captions are positional + band-clamped, not slot-owned).
    caption = _label("Tetrahedral", (300.0, 500.0), "label_scene_s_label")
    out = tier_label_leaders([caption], leader_anchors={})
    assert out == [caption]


def test_aspirin_acceptance_emits_residue_leaders() -> None:
    # End-to-end: the drifting Ser530 residue labels (D1) get tethered.
    import json
    import warnings
    from pathlib import Path

    from imageGen.ir import Figure
    from imageGen.render.compositor import render_figure

    spec = Path("showcase/aspirin_cox1_v3_acceptance.json")
    fig = Figure.model_validate(json.loads(spec.read_text()))
    out = Path("/tmp/_aspirin_leader_test.svg")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # tolerated D3 overlap warnings
        render_figure(fig, out)
    svg = out.read_text()
    assert 'data-ir-id="leader_slot_s1_ser_label"' in svg, (
        "the drifting Ser530 residue label should be tethered to its glyph"
    )
