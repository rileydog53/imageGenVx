"""Clarity fix: relation labels that drift far from their arrow shaft get a
hairline leader tethering them back to the shaft.

Symptom (showcase Fig 1): a node with several outgoing edges (AKT → mTORC1 /
GSK-3β / FOXO1) forces collision avoidance to push one relation label
("Thr24") ~40 px away, where it floats beside an unrelated box with no visible
link to its arrow. Labels that sit comfortably beside their shaft (the common
case) must NOT get a leader — that would just add clutter.

This pins:
  1. pathway_extlabel_leaders emits a leader for a relation label whose distance
     to its shaft exceeds _RELATION_LEADER_MIN_GAP, and none for a close label.
  2. The leader's shaft endpoint lies on the arrow shaft; the label endpoint
     sits between the label center and the shaft (edge-to-edge, ordered).
  3. _nearest_point_on_polyline projects onto the closest segment (clamped).
"""
from __future__ import annotations

import math

from imageGen.ir.schema import RelationType
from imageGen.layout.label_placement import _label_primitive
from imageGen.layout.pathway_layout import (
    _RELATION_LEADER_MIN_GAP,
    RELATION_TO_ARROW,
    _leader_line,
    _nearest_point_on_polyline,
    pathway_extlabel_leaders,
)
from imageGen.layout.types import LayoutEntry

# The concrete arrow primitive a relation maps to (an activation arrow); pulled
# from the registry so the test never hard-codes the function name.
_ARROW_PRIM = RELATION_TO_ARROW[RelationType.ACTIVATES]


def _arrow(ir_id: str, start, end, waypoints=None) -> LayoutEntry:
    return LayoutEntry(
        primitive=_ARROW_PRIM,
        args=(start, end),
        kwargs={"waypoints": waypoints},
        position=(0.0, 0.0),
        ir_id=ir_id,
    )


def _label(ir_id: str, text: str, center) -> LayoutEntry:
    return LayoutEntry(
        primitive=_label_primitive,
        args=(text, center),
        kwargs={},
        position=(0.0, 0.0),
        ir_id=ir_id,
    )


# ---------------------------------------------------------------------------
# _nearest_point_on_polyline
# ---------------------------------------------------------------------------

def test_nearest_point_projects_onto_segment():
    pts = [(0.0, 0.0), (100.0, 0.0)]
    q, d = _nearest_point_on_polyline((40.0, 25.0), pts)
    assert q == (40.0, 0.0)
    assert d == 25.0


def test_nearest_point_clamps_to_endpoint():
    pts = [(0.0, 0.0), (100.0, 0.0)]
    q, d = _nearest_point_on_polyline((-30.0, 40.0), pts)
    assert q == (0.0, 0.0)
    assert d == math.hypot(30.0, 40.0)


def test_nearest_point_picks_closest_of_multiple_segments():
    # An L-shaped shaft; point is nearest the vertical leg.
    pts = [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)]
    q, d = _nearest_point_on_polyline((90.0, 60.0), pts)
    assert q == (100.0, 60.0)
    assert d == 10.0


# ---------------------------------------------------------------------------
# Leader emission for drifted relation labels
# ---------------------------------------------------------------------------

def test_far_relation_label_gets_leader_close_one_does_not():
    shaft_y = 100.0
    far_gap = _RELATION_LEADER_MIN_GAP + 20.0
    close_gap = _RELATION_LEADER_MIN_GAP - 15.0
    entries = [
        _arrow("rfar", (0.0, shaft_y), (200.0, shaft_y)),
        _arrow("rclose", (0.0, 300.0), (200.0, 300.0)),
        _label("label_rfar", "Thr24", (100.0, shaft_y + far_gap)),
        _label("label_rclose", "Ser9", (100.0, 300.0 + close_gap)),
    ]
    out = pathway_extlabel_leaders(entries)
    leaders = {e.ir_id: e for e in out if e.primitive is _leader_line}
    assert "leader_rfar" in leaders, "drifted label must be tethered"
    assert "leader_rclose" not in leaders, "nearby label must not be tethered"


def test_relation_leader_endpoints_touch_shaft_and_label():
    shaft_y = 100.0
    label_center = (100.0, shaft_y + _RELATION_LEADER_MIN_GAP + 30.0)
    entries = [
        _arrow("r0", (0.0, shaft_y), (200.0, shaft_y)),
        _label("label_r0", "Thr24", label_center),
    ]
    out = pathway_extlabel_leaders(entries)
    leader = next(e for e in out if e.primitive is _leader_line)
    label_exit, shaft_exit = leader.args
    # Shaft endpoint sits on the (horizontal) shaft.
    assert shaft_exit[1] == shaft_y
    # Both endpoints lie between the shaft and the label center (label_exit is
    # the label-side, nearer the label; shaft_exit is on the shaft).
    assert shaft_y < label_exit[1] < label_center[1]


def test_no_leader_when_no_matching_arrow():
    """A label whose key matches no arrow (e.g. a sublabel) is ignored."""
    entries = [
        _arrow("r0", (0.0, 100.0), (200.0, 100.0)),
        _label("label_x_sublabel", "note", (100.0, 400.0)),
    ]
    out = pathway_extlabel_leaders(entries)
    assert out is entries
    assert not any(e.primitive is _leader_line for e in out)
