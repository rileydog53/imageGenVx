"""V3 scene-chassis keystone — anchor-return protocol + figure-global registry.

This is the vertical slice that de-risks the whole chassis before any schema or
layout-engine work: prove that a primitive can publish named anchor points, that
those points survive the cell-offset boundary through the registry, and that an
intra-scene dashed bond and a cross-cell transition arrow (clamped to a shared
midline rail) resolve to the right coordinates and actually render.

Two anchored aspirin molecules stand in for two scene cells. The test asserts
coordinate correctness (the real proof) and emits a PNG to tests/figures/ for
visual confirmation that anchors land on the intended atoms.
"""
from __future__ import annotations

import math
from pathlib import Path

import pytest
import svgwrite.container
import svgwrite.path
import svgwrite.shapes
import svgwrite.text

from imageGen.layout.anchors import AnchorRegistry, Rail, _inset_toward
from imageGen.layout.types import LayoutEntry
from imageGen.primitives._anchors import AnchoredGroup
from imageGen.primitives.chemistry import DEFAULT_STYLE, _arrow, render_molecule_anchored
from tests._helpers import render_entries_to_png

FIGURES_DIR = Path(__file__).parent / "figures"

# Aspirin with atom-map numbers on three chemically meaningful atoms:
#   :1 acetyl carbonyl carbon, :2 carboxyl carbon, :4 ring attachment carbon.
ASPIRIN_MAPPED = "C[C:1](=O)O[c:4]1ccccc1[C:2](=O)O"
ANCHOR_NAMES = {1: "acetyl_C", 2: "carboxyl_C", 4: "ring_C1"}
MOL_SIZE = (200, 150)

# End-to-end slice uses a REAL minimal transformation so the figure is not a lie:
# aspirin undergoes acyl-oxygen ester cleavage to salicylic acid (+ acetate). The
# bond that breaks is the acetyl carbonyl-C : ester-O bond (:1 - :3); after
# cleavage the ester O stays on the ring as salicylic acid's phenol -OH. molA and
# molB are genuinely different molecules; the arrow is a frame-level reaction edge.
ASPIRIN_CLEAVE = "C[C:1](=O)[O:3]c1ccccc1C(=O)O"  # :1 acetyl carbonyl C, :3 ester O
ASPIRIN_CLEAVE_NAMES = {1: "acetyl_C", 3: "ester_O"}
SALICYLIC = "O=C(O)c1ccccc1O"  # 2-hydroxybenzoic acid (the real product)


# ---------------------------------------------------------------------------
# Anchor protocol: render_molecule_anchored
# ---------------------------------------------------------------------------

def test_anchored_molecule_returns_named_anchors():
    ag = render_molecule_anchored(
        ASPIRIN_MAPPED, size=MOL_SIZE, anchor_names=ANCHOR_NAMES
    )
    assert isinstance(ag, AnchoredGroup)
    assert isinstance(ag.group, svgwrite.container.Group)
    # atom-map aliases, human aliases, and index fallbacks all present
    for name in ("a1", "a2", "a4", "acetyl_C", "carboxyl_C", "ring_C1", "atom0"):
        assert name in ag.anchors, f"missing anchor {name!r}"
    # human alias and its atom-map alias point at the same atom
    assert ag.anchors["acetyl_C"] == ag.anchors["a1"]
    assert ag.anchors["carboxyl_C"] == ag.anchors["a2"]


def test_anchored_points_are_within_local_bbox():
    ag = render_molecule_anchored(ASPIRIN_MAPPED, size=MOL_SIZE)
    w, h = MOL_SIZE
    for name, (x, y) in ag.anchors.items():
        assert 0 <= x <= w, f"{name} x={x} out of [0,{w}]"
        assert 0 <= y <= h, f"{name} y={y} out of [0,{h}]"


def test_distinct_atoms_have_distinct_anchor_points():
    ag = render_molecule_anchored(ASPIRIN_MAPPED, size=MOL_SIZE, anchor_names=ANCHOR_NAMES)
    pts = {ag.anchors[n] for n in ("acetyl_C", "carboxyl_C", "ring_C1")}
    assert len(pts) == 3  # no two mapped atoms collapse to one point


def test_center_shifts_anchors_consistently():
    base = render_molecule_anchored(ASPIRIN_MAPPED, size=MOL_SIZE, anchor_names=ANCHOR_NAMES)
    w, h = MOL_SIZE
    centered = render_molecule_anchored(
        ASPIRIN_MAPPED, size=MOL_SIZE, center=(500, 400), anchor_names=ANCHOR_NAMES
    )
    # center places bbox-center at (500,400): translate = (500-w/2, 400-h/2)
    dx, dy = 500 - w / 2, 400 - h / 2
    bx, by = base.anchors["acetyl_C"]
    cx, cy = centered.anchors["acetyl_C"]
    assert cx == pytest.approx(bx + dx)
    assert cy == pytest.approx(by + dy)


def test_unknown_anchor_name_raises():
    with pytest.raises(ValueError, match="atom-map number"):
        render_molecule_anchored(ASPIRIN_MAPPED, anchor_names={9: "nope"})


# ---------------------------------------------------------------------------
# Registry: anchors survive the cell-offset boundary
# ---------------------------------------------------------------------------

def test_registry_offsets_into_figure_space():
    ag = render_molecule_anchored(ASPIRIN_MAPPED, size=MOL_SIZE, anchor_names=ANCHOR_NAMES)
    reg = AnchorRegistry()
    reg.publish_group("molA", ag, offset=(40.0, 75.0))
    lx, ly = ag.anchors["carboxyl_C"]
    assert reg.resolve("molA.carboxyl_C") == pytest.approx((lx + 40.0, ly + 75.0))


def test_registry_unknown_anchor_raises():
    reg = AnchorRegistry()
    with pytest.raises(ValueError, match="unknown anchor"):
        reg.resolve("ghost.nowhere")


def test_bare_rail_reference_is_not_a_point():
    reg = AnchorRegistry()
    reg.publish_rail("midline", "y", 150.0)
    with pytest.raises(ValueError, match="is a rail"):
        reg.resolve("rail:midline")


def test_resolve_on_rail_clamps_cross_axis():
    ag = render_molecule_anchored(ASPIRIN_MAPPED, size=MOL_SIZE, anchor_names=ANCHOR_NAMES)
    reg = AnchorRegistry()
    reg.publish_group("molA", ag, offset=(40.0, 75.0))
    reg.publish_rail("midline", "y", 150.0)
    x_only, _ = reg.resolve("molA.carboxyl_C")
    rx, ry = reg.resolve_on_rail("molA.carboxyl_C", "midline")
    assert ry == 150.0          # y forced onto the rail
    assert rx == pytest.approx(x_only)  # x preserved from the anchor


# ---------------------------------------------------------------------------
# Endpoint standoff — overlap avoidance so edges don't land inside atoms
# ---------------------------------------------------------------------------

def test_inset_toward_moves_along_the_line():
    # (0,0) -> (10,0), inset 3 along the line lands at (3,0)
    assert _inset_toward((0.0, 0.0), (10.0, 0.0), 3.0) == pytest.approx((3.0, 0.0))
    # zero / negative standoff is a no-op; coincident points are a no-op
    assert _inset_toward((5.0, 5.0), (9.0, 9.0), 0.0) == (5.0, 5.0)
    assert _inset_toward((5.0, 5.0), (5.0, 5.0), 3.0) == (5.0, 5.0)


def test_resolve_edge_shortens_by_both_standoffs():
    reg = AnchorRegistry()
    # two anchors 100px apart on a horizontal line
    reg.publish("L", {"p": (0.0, 0.0)})
    reg.publish("R", {"p": (100.0, 0.0)})
    p0, p1 = reg.resolve_edge("L.p", "R.p", from_standoff=10.0, to_standoff=15.0)
    assert p0 == pytest.approx((10.0, 0.0))
    assert p1 == pytest.approx((85.0, 0.0))
    # endpoints stay clear of the raw atoms by exactly their standoff
    assert math.dist(p0, (0.0, 0.0)) == pytest.approx(10.0)
    assert math.dist(p1, (100.0, 0.0)) == pytest.approx(15.0)


def test_resolve_edge_on_rail_clamps_then_insets():
    reg = AnchorRegistry()
    reg.publish("A", {"p": (0.0, 30.0)})
    reg.publish("B", {"p": (100.0, -40.0)})
    reg.publish_rail("mid", "y", 0.0)
    p0, p1 = reg.resolve_edge(
        "A.p", "B.p", from_standoff=5.0, to_standoff=5.0, on_rail="mid"
    )
    # both clamped to y=0, then pulled 5px toward each other
    assert p0[1] == 0.0 and p1[1] == 0.0
    assert p0[0] == pytest.approx(5.0)
    assert p1[0] == pytest.approx(95.0)


# ---------------------------------------------------------------------------
# End-to-end vertical slice: two cells, dashed bond, cross-cell arrow on a rail
# ---------------------------------------------------------------------------

def _curved_bond(p0, p1, bow=22.0):
    """A *curved* dashed interaction line between two points (intra-scene).

    Drawn as a quadratic Bézier bowed perpendicular to p0->p1 by *bow* px. The
    curve is the H-bond convention and bows the red line clear of the straight
    black bonds it would otherwise overlay (legibility).
    """
    (x0, y0), (x1, y1) = p0, p1
    mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy) or 1.0
    px, py = -dy / length, dx / length  # unit perpendicular
    cx, cy = mx + px * bow, my + py * bow
    g = svgwrite.container.Group()
    g.add(svgwrite.path.Path(
        d=f"M {x0:.2f},{y0:.2f} Q {cx:.2f},{cy:.2f} {x1:.2f},{y1:.2f}",
        fill="none", stroke="#CC2222", stroke_width=2.0, stroke_dasharray="4,3",
    ))
    return g


def _transition_arrow(p0, p1):
    """A solid transition arrow between two absolute points (cross-cell)."""
    g = svgwrite.container.Group()
    for elem in _arrow(p0, p1, DEFAULT_STYLE):
        g.add(elem)
    return g


def _legend(origin=(20.0, 252.0)):
    """A small legend keying the two edge styles drawn in the slice (ASCII only)."""
    ox, oy = origin
    g = svgwrite.container.Group()
    g.add(svgwrite.shapes.Rect(
        insert=(ox, oy), size=(252, 40), rx=4, ry=4,
        fill="#FFFFFF", stroke="#AAAAAA", stroke_width=1.0,
    ))
    # Row 1: red dashed = the bond cleaved by hydrolysis
    g.add(svgwrite.shapes.Line(
        start=(ox + 10, oy + 13), end=(ox + 40, oy + 13),
        stroke="#CC2222", stroke_width=2.0, stroke_dasharray="4,3",
    ))
    g.add(svgwrite.text.Text(
        "cleaved bond (acyl C-O ester)", insert=(ox + 48, oy + 17),
        font_size=11, fill="#1A1A1A", font_family="Helvetica, Arial, sans-serif",
    ))
    # Row 2: black arrow = the hydrolysis reaction
    for elem in _arrow((ox + 10, oy + 29), (ox + 40, oy + 29), DEFAULT_STYLE):
        g.add(elem)
    g.add(svgwrite.text.Text(
        "hydrolysis (loses acetyl)", insert=(ox + 48, oy + 33),
        font_size=11, fill="#1A1A1A", font_family="Helvetica, Arial, sans-serif",
    ))
    return g


def _caption(text, cx, y):
    """An italic centered caption under a molecule."""
    return svgwrite.text.Text(
        text, insert=(cx, y), font_size=12, fill="#1A1A1A",
        font_family="Helvetica, Arial, sans-serif", text_anchor="middle",
        font_style="italic",
    )


def test_vertical_slice_renders_with_resolved_geometry():
    cell_a_off = (40.0, 60.0)
    cell_b_off = (360.0, 60.0)
    mol_w, mol_h = MOL_SIZE
    midline_y = cell_a_off[1] + mol_h / 2.0  # vertical centre of the molecule band

    # A real transformation: aspirin (reactant) -> salicylic acid (product).
    ag_a = render_molecule_anchored(
        ASPIRIN_CLEAVE, size=MOL_SIZE, anchor_names=ASPIRIN_CLEAVE_NAMES
    )
    ag_b = render_molecule_anchored(SALICYLIC, size=MOL_SIZE)

    reg = AnchorRegistry()
    reg.publish_group("molA", ag_a, offset=cell_a_off)
    reg.publish_group("molB", ag_b, offset=cell_b_off)
    # Frame-level anchors so the reaction arrow connects molecule EDGES (scenes),
    # not atoms — the two anchor granularities the chassis needs (atom + frame).
    frame = {"right": (mol_w, mol_h / 2.0), "left": (0.0, mol_h / 2.0)}
    reg.publish("molA", frame, offset=cell_a_off)
    reg.publish("molB", frame, offset=cell_b_off)
    reg.publish_rail("midline", "y", midline_y)

    # Atom-level intra-scene mark on the ester C-O bond that hydrolysis cleaves.
    bond_p0, bond_p1 = reg.resolve_edge(
        "molA.acetyl_C", "molA.ester_O", from_standoff=4.0, to_standoff=4.0,
    )
    # Frame-level cross-cell reaction arrow, level on the shared midline, sitting
    # in the gap between molecules (8px standoff off each molecule edge).
    arr_p0, arr_p1 = reg.resolve_edge(
        "molA.right", "molB.left",
        from_standoff=8.0, to_standoff=8.0, on_rail="midline",
    )

    # Overlap check: the arrowhead tip stays clear of molB's edge by its standoff.
    raw_target = reg.resolve_on_rail("molB.left", "midline")
    assert math.dist(arr_p1, raw_target) == pytest.approx(8.0)
    # The arrow is level on the rail and sits entirely in the inter-molecule gap.
    assert arr_p0[1] == midline_y and arr_p1[1] == midline_y
    assert cell_a_off[0] + mol_w <= arr_p0[0] and arr_p1[0] <= cell_b_off[0]

    entries = [
        LayoutEntry(lambda g=ag_a.group: g, (), {}, cell_a_off),
        LayoutEntry(lambda g=ag_b.group: g, (), {}, cell_b_off),
        LayoutEntry(lambda p0=bond_p0, p1=bond_p1: _curved_bond(p0, p1, bow=14.0), (), {}, (0.0, 0.0)),
        LayoutEntry(lambda p0=arr_p0, p1=arr_p1: _transition_arrow(p0, p1), (), {}, (0.0, 0.0)),
        LayoutEntry(lambda: _caption("aspirin", cell_a_off[0] + mol_w / 2.0, midline_y + mol_h / 2.0 + 6), (), {}, (0.0, 0.0)),
        LayoutEntry(lambda: _caption("salicylic acid", cell_b_off[0] + mol_w / 2.0, midline_y + mol_h / 2.0 + 6), (), {}, (0.0, 0.0)),
        LayoutEntry(lambda: _legend(), (), {}, (0.0, 0.0)),
    ]
    out = render_entries_to_png(entries, "anchor_keystone_slice.png", canvas=(600, 300))
    assert out.exists() and out.stat().st_size > 0
