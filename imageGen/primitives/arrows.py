"""
Primitive arrow functions for scientific figure generation.

All public functions return ``svgwrite.container.Group`` — never raw SVG strings (Hard Rule #2).
All public functions accept a ``style`` dict; pass ``None`` to fall back to ``DEFAULT_STYLE``.

Phase 2 note: ``DEFAULT_STYLE`` provides fallback values for every parameter consumed here.
When Phase 4 (style presets) lands, the compositor will forward a loaded preset dict instead.
Callers that pass ``style_dict=None`` will need to forward the active preset at that point.
"""
from __future__ import annotations

import math
from typing import Optional

import svgwrite
import svgwrite.container
import svgwrite.path
import svgwrite.shapes
import svgwrite.text

from imageGen.primitives._text import formula_text as _formula_text

DEFAULT_STYLE: dict = {
    "stroke": "#222222",
    "stroke_width": 2.0,
    "arrow_head_size": 10,   # pixels; applied to both filled and open heads
    "t_bar_width": 12,       # total width of the T-bar used in inhibition arrows
    "dash_array": "6,4",     # stroke-dasharray for translocation dashes
    # v2.x expansion relation arrows
    "catalysis_circle_radius": 5.0,   # open-circle terminus (catalysis convention)
    "block_arrow_width": 11.0,        # body width of the hollow transport block arrow
    "recruit_dash": "3,3",            # finer dash for the recruitment shaft
    "recruit_dot_radius": 3.5,        # filled-dot terminus for recruitment
    "cleave_tick_len": 7.0,           # length of the scissors cut-mark ticks
    # Labels (shared across all primitive modules — keep these values
    # synchronized with proteins.py, membranes.py, nucleic_acids.py, cells.py,
    # chemistry.py, lab_equipment.py so the Phase 4 master preset union
    # produces a single coherent label style)
    "label_font_family": "Helvetica, Arial, sans-serif",
    "label_font_size": 11,
    "label_font_color": "#1A1A1A",
}


# ---------------------------------------------------------------------------
# Private geometry helpers
# ---------------------------------------------------------------------------

def _waypoint_path(
    waypoints: list[tuple[float, float]],
    stroke: str,
    sw: float,
    dash: str | None = None,
) -> svgwrite.path.Path:
    """Straight-segment polyline through *waypoints* as an SVG path element."""
    d = f"M {waypoints[0][0]:.2f},{waypoints[0][1]:.2f}"
    for x, y in waypoints[1:]:
        d += f" L {x:.2f},{y:.2f}"
    p = svgwrite.path.Path(d=d, fill="none", stroke=stroke)
    p["stroke-width"] = sw
    p["stroke-linejoin"] = "miter"
    if dash:
        p["stroke-dasharray"] = dash
    return p


def _unit_vector(
    start: tuple[float, float], end: tuple[float, float]
) -> tuple[float, float]:
    """Return the unit vector pointing from *start* toward *end*."""
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    length = math.hypot(dx, dy)
    return (dx / length, dy / length) if length else (1.0, 0.0)


def _perp_vector(dx: float, dy: float) -> tuple[float, float]:
    """Return a unit vector perpendicular to (dx, dy): (−dy, dx)."""
    return (-dy, dx)


def _filled_triangle_head(
    tip: tuple[float, float],
    dx: float,
    dy: float,
    size: float,
    color: str,
) -> svgwrite.shapes.Polygon:
    """Filled triangular arrowhead with apex at *tip* pointing in direction (dx, dy)."""
    px, py = _perp_vector(dx, dy)
    half = size * 0.4
    bx = tip[0] - dx * size
    by = tip[1] - dy * size
    pts = [tip, (bx + px * half, by + py * half), (bx - px * half, by - py * half)]
    return svgwrite.shapes.Polygon(points=pts, fill=color, stroke="none")


def _open_triangle_head(
    tip: tuple[float, float],
    dx: float,
    dy: float,
    size: float,
    stroke: str,
    stroke_width: float,
) -> svgwrite.path.Path:
    """Open (stroke-only) triangular arrowhead with apex at *tip*."""
    px, py = _perp_vector(dx, dy)
    half = size * 0.4
    bx = tip[0] - dx * size
    by = tip[1] - dy * size
    left = (bx + px * half, by + py * half)
    right = (bx - px * half, by - py * half)
    d = (
        f"M {left[0]:.2f},{left[1]:.2f} "
        f"L {tip[0]:.2f},{tip[1]:.2f} "
        f"L {right[0]:.2f},{right[1]:.2f}"
    )
    p = svgwrite.path.Path(d=d, fill="none", stroke=stroke)
    p["stroke-width"] = stroke_width
    p["stroke-linejoin"] = "miter"
    return p


def _t_bar(
    tip: tuple[float, float],
    px: float,
    py: float,
    width: float,
    stroke: str,
    stroke_width: float,
) -> svgwrite.shapes.Line:
    """T-bar terminus: a perpendicular stroke at *tip* (inhibition convention)."""
    half = width / 2
    line = svgwrite.shapes.Line(
        start=(tip[0] + px * half, tip[1] + py * half),
        end=(tip[0] - px * half, tip[1] - py * half),
        stroke=stroke,
    )
    line["stroke-width"] = stroke_width
    line["stroke-linecap"] = "square"
    return line


# ---------------------------------------------------------------------------
# Public arrow functions
# ---------------------------------------------------------------------------

def activation_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    curved: bool = False,
    waypoints: Optional[list[tuple[float, float]]] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """
    Activation arrow: solid line with a filled triangular head at *end*.

    Scientific convention: solid line + filled triangular head = activation / stimulation.
    Set ``curved=True`` for a quadratic-bezier shaft; the control point is offset
    perpendicular from the midpoint by 40% of the shaft length.

    Args:
        start:     tail position (x, y) in SVG coordinates
        end:       tip position (x, y) in SVG coordinates
        curved:    if True, shaft is a quadratic bezier; otherwise a straight line
        waypoints: optional list of (x, y) points for an orthogonal elbow shaft.
                   When provided, ``start``/``end`` are ignored for the shaft (the
                   first and last waypoints serve as tail and tip respectively), and
                   the arrowhead direction is taken from the last segment.
        style_dict: presentation attributes dict; falls back to DEFAULT_STYLE

    Returns:
        svgwrite.container.Group containing shaft and filled arrowhead
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    stroke = s["stroke"]
    sw = float(s["stroke_width"])
    hs = float(s["arrow_head_size"])

    if waypoints and len(waypoints) >= 2:
        dx, dy = _unit_vector(waypoints[-2], waypoints[-1])
        tip = waypoints[-1]
        shaft_tip = (tip[0] - dx * hs, tip[1] - dy * hs)
        g.add(_waypoint_path(list(waypoints[:-1]) + [shaft_tip], stroke, sw))
        g.add(_filled_triangle_head(tip, dx, dy, hs, stroke))
        return g

    dx, dy = _unit_vector(start, end)
    shaft_end = (end[0] - dx * hs, end[1] - dy * hs)

    if curved:
        mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        px, py = _perp_vector(dx, dy)
        cp = (mid[0] + px * length * 0.4, mid[1] + py * length * 0.4)
        d = (
            f"M {start[0]:.2f},{start[1]:.2f} "
            f"Q {cp[0]:.2f},{cp[1]:.2f} {shaft_end[0]:.2f},{shaft_end[1]:.2f}"
        )
        shaft = svgwrite.path.Path(d=d, fill="none", stroke=stroke)
        shaft["stroke-width"] = sw
        g.add(shaft)
    else:
        line = svgwrite.shapes.Line(start=start, end=shaft_end, stroke=stroke)
        line["stroke-width"] = sw
        g.add(line)

    g.add(_filled_triangle_head(end, dx, dy, hs, stroke))
    return g


def inhibition_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    curved: bool = False,
    waypoints: Optional[list[tuple[float, float]]] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """
    Inhibition arrow: solid line with a T-bar terminus at *end*.

    Scientific convention: solid line + flat T-bar = inhibition / repression.
    A T-bar must never be replaced with a triangular arrowhead — they carry
    different biological meanings.

    Args:
        start:     tail position (x, y) in SVG coordinates
        end:       tip / T-bar position (x, y) in SVG coordinates
        curved:    if True, shaft is a quadratic bezier; otherwise a straight line
        waypoints: optional orthogonal elbow waypoints (see activation_arrow)
        style_dict: presentation attributes dict; falls back to DEFAULT_STYLE

    Returns:
        svgwrite.container.Group containing shaft and T-bar
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    stroke = s["stroke"]
    sw = float(s["stroke_width"])
    t_width = float(s["t_bar_width"])

    if waypoints and len(waypoints) >= 2:
        dx, dy = _unit_vector(waypoints[-2], waypoints[-1])
        tip = waypoints[-1]
        g.add(_waypoint_path(waypoints, stroke, sw))
        px, py = _perp_vector(dx, dy)
        g.add(_t_bar(tip, px, py, t_width, stroke, sw + 1))
        return g

    dx, dy = _unit_vector(start, end)
    if curved:
        mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
        length = math.hypot(end[0] - start[0], end[1] - start[1])
        px, py = _perp_vector(dx, dy)
        cp = (mid[0] + px * length * 0.4, mid[1] + py * length * 0.4)
        d = (
            f"M {start[0]:.2f},{start[1]:.2f} "
            f"Q {cp[0]:.2f},{cp[1]:.2f} {end[0]:.2f},{end[1]:.2f}"
        )
        shaft = svgwrite.path.Path(d=d, fill="none", stroke=stroke)
        shaft["stroke-width"] = sw
        g.add(shaft)
    else:
        line = svgwrite.shapes.Line(start=start, end=end, stroke=stroke)
        line["stroke-width"] = sw
        g.add(line)

    px, py = _perp_vector(dx, dy)
    # T-bar is slightly thicker than the shaft to make the termination obvious
    g.add(_t_bar(end, px, py, t_width, stroke, sw + 1))
    return g


def binding_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    waypoints: Optional[list[tuple[float, float]]] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """
    Binding arrow: bidirectional line with small filled heads at both ends.

    Scientific convention: double-headed arrow = binding / molecular interaction /
    equilibrium. Head size is 70% of the activation arrow to visually distinguish it.

    Args:
        start:     one endpoint (x, y)
        end:       other endpoint (x, y)
        waypoints: optional orthogonal elbow waypoints (see activation_arrow).
                   Heads are placed at waypoints[0] and waypoints[-1].
        style_dict: presentation attributes dict; falls back to DEFAULT_STYLE

    Returns:
        svgwrite.container.Group containing shaft and two filled arrowheads
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    stroke = s["stroke"]
    sw = float(s["stroke_width"])
    hs = float(s["arrow_head_size"]) * 0.7  # slightly smaller heads for binding

    if waypoints and len(waypoints) >= 2:
        dx0, dy0 = _unit_vector(waypoints[1], waypoints[0])   # reverse: tail direction
        dxN, dyN = _unit_vector(waypoints[-2], waypoints[-1])  # forward: head direction
        tail = waypoints[0]
        tip = waypoints[-1]
        shaft_tail = (tail[0] - dx0 * hs, tail[1] - dy0 * hs)
        shaft_tip = (tip[0] - dxN * hs, tip[1] - dyN * hs)
        g.add(_waypoint_path([shaft_tail] + list(waypoints[1:-1]) + [shaft_tip], stroke, sw))
        g.add(_filled_triangle_head(tip, dxN, dyN, hs, stroke))
        g.add(_filled_triangle_head(tail, dx0, dy0, hs, stroke))
        return g

    dx, dy = _unit_vector(start, end)
    shaft_start = (start[0] + dx * hs, start[1] + dy * hs)
    shaft_end = (end[0] - dx * hs, end[1] - dy * hs)

    line = svgwrite.shapes.Line(start=shaft_start, end=shaft_end, stroke=stroke)
    line["stroke-width"] = sw
    g.add(line)
    g.add(_filled_triangle_head(end, dx, dy, hs, stroke))
    g.add(_filled_triangle_head(start, -dx, -dy, hs, stroke))
    return g


def translocation_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    waypoints: Optional[list[tuple[float, float]]] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """
    Translocation arrow: dashed line with an open (unfilled) triangular head at *end*.

    Scientific convention: dashed shaft = movement / translocation between compartments.
    The open head distinguishes translocation from activation (which uses a filled head).

    Args:
        start:     tail position (x, y)
        end:       tip position (x, y)
        waypoints: optional orthogonal elbow waypoints (see activation_arrow)
        style_dict: presentation attributes dict; falls back to DEFAULT_STYLE

    Returns:
        svgwrite.container.Group containing dashed shaft and open arrowhead
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    stroke = s["stroke"]
    sw = float(s["stroke_width"])
    hs = float(s["arrow_head_size"])
    dash = s["dash_array"]

    if waypoints and len(waypoints) >= 2:
        dx, dy = _unit_vector(waypoints[-2], waypoints[-1])
        tip = waypoints[-1]
        shaft_tip = (tip[0] - dx * hs, tip[1] - dy * hs)
        g.add(_waypoint_path(list(waypoints[:-1]) + [shaft_tip], stroke, sw, dash=str(dash)))
        g.add(_open_triangle_head(tip, dx, dy, hs, stroke, sw))
        return g

    dx, dy = _unit_vector(start, end)
    shaft_end = (end[0] - dx * hs, end[1] - dy * hs)
    line = svgwrite.shapes.Line(start=start, end=shaft_end, stroke=stroke)
    line["stroke-width"] = sw
    line["stroke-dasharray"] = dash
    g.add(line)
    g.add(_open_triangle_head(end, dx, dy, hs, stroke, sw))
    return g


def catalysis_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    waypoints: Optional[list[tuple[float, float]]] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Catalysis: solid line with an open-circle terminus at *end*.

    Convention: an open circle (not a triangle or T-bar) marks catalysis /
    enzymatic stimulation — the enzyme is not consumed, so the head reads as a
    contact point rather than a directed conversion.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    stroke = s["stroke"]
    sw = float(s["stroke_width"])
    r = float(s["catalysis_circle_radius"])

    if waypoints and len(waypoints) >= 2:
        dx, dy = _unit_vector(waypoints[-2], waypoints[-1])
        tip = waypoints[-1]
    else:
        dx, dy = _unit_vector(start, end)
        tip = end
    center = (tip[0] - dx * r, tip[1] - dy * r)
    shaft_end = (center[0] - dx * r, center[1] - dy * r)

    if waypoints and len(waypoints) >= 2:
        g.add(_waypoint_path(list(waypoints[:-1]) + [shaft_end], stroke, sw))
    else:
        line = svgwrite.shapes.Line(start=start, end=shaft_end, stroke=stroke)
        line["stroke-width"] = sw
        g.add(line)

    circle = svgwrite.shapes.Circle(center=center, r=r, fill="none", stroke=stroke)
    circle["stroke-width"] = sw
    g.add(circle)
    return g


def cleavage_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    waypoints: Optional[list[tuple[float, float]]] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Cleavage / proteolysis: solid line + filled head, with a double-tick cut
    mark across the shaft near the tip (a schematic "scissors" cut)."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    stroke = s["stroke"]
    sw = float(s["stroke_width"])
    hs = float(s["arrow_head_size"])
    tick = float(s["cleave_tick_len"])

    if waypoints and len(waypoints) >= 2:
        dx, dy = _unit_vector(waypoints[-2], waypoints[-1])
        tip = waypoints[-1]
        shaft_tip = (tip[0] - dx * hs, tip[1] - dy * hs)
        g.add(_waypoint_path(list(waypoints[:-1]) + [shaft_tip], stroke, sw))
    else:
        dx, dy = _unit_vector(start, end)
        tip = end
        shaft_tip = (tip[0] - dx * hs, tip[1] - dy * hs)
        line = svgwrite.shapes.Line(start=start, end=shaft_tip, stroke=stroke)
        line["stroke-width"] = sw
        g.add(line)

    g.add(_filled_triangle_head(tip, dx, dy, hs, stroke))

    # Two short parallel ticks across the shaft, just behind the head.
    px, py = _perp_vector(dx, dy)
    for off in (hs * 1.6, hs * 2.3):
        cx, cy = tip[0] - dx * off, tip[1] - dy * off
        cut = svgwrite.shapes.Line(
            start=(cx + px * tick / 2, cy + py * tick / 2),
            end=(cx - px * tick / 2, cy - py * tick / 2),
            stroke=stroke,
        )
        cut["stroke-width"] = sw
        g.add(cut)
    return g


def transport_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    waypoints: Optional[list[tuple[float, float]]] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Transport / flux: a hollow block arrow conveying bulk movement of
    material (distinct from the thin activation line).

    Drawn straight from tail to tip; with waypoints, the first and last points
    serve as tail and tip (elbow routing is not used for the block body)."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    stroke = s["stroke"]
    sw = float(s["stroke_width"])
    bw = float(s["block_arrow_width"])

    if waypoints and len(waypoints) >= 2:
        tail, tip = waypoints[0], waypoints[-1]
    else:
        tail, tip = start, end
    dx, dy = _unit_vector(tail, tip)
    px, py = _perp_vector(dx, dy)
    head_len = bw * 1.6
    body_end = (tip[0] - dx * head_len, tip[1] - dy * head_len)
    hw = bw / 2  # body half-width

    def pt(base, along, perp):
        return (base[0] + dx * along + px * perp, base[1] + dy * along + py * perp)

    pts = [
        pt(tail, 0, hw), pt(body_end, 0, hw), pt(body_end, 0, bw),
        tip, pt(body_end, 0, -bw), pt(body_end, 0, -hw), pt(tail, 0, -hw),
    ]
    block = svgwrite.shapes.Polygon(points=pts, fill="none", stroke=stroke)
    block["stroke-width"] = sw
    block["stroke-linejoin"] = "miter"
    g.add(block)
    return g


def recruitment_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    waypoints: Optional[list[tuple[float, float]]] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Recruitment: a finely-dashed line ending in a small filled dot, reading
    as "A is recruited to B" without implying catalysis or conversion."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    stroke = s["stroke"]
    sw = float(s["stroke_width"])
    r = float(s["recruit_dot_radius"])
    dash = str(s["recruit_dash"])

    if waypoints and len(waypoints) >= 2:
        dx, dy = _unit_vector(waypoints[-2], waypoints[-1])
        tip = waypoints[-1]
        shaft_end = (tip[0] - dx * r, tip[1] - dy * r)
        g.add(_waypoint_path(list(waypoints[:-1]) + [shaft_end], stroke, sw, dash=dash))
    else:
        dx, dy = _unit_vector(start, end)
        tip = end
        shaft_end = (tip[0] - dx * r, tip[1] - dy * r)
        line = svgwrite.shapes.Line(start=start, end=shaft_end, stroke=stroke)
        line["stroke-width"] = sw
        line["stroke-dasharray"] = dash
        g.add(line)

    dot = svgwrite.shapes.Circle(center=tip, r=r, fill=stroke, stroke="none")
    g.add(dot)
    return g


def reaction_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    conditions: Optional[str] = None,
    reagents: Optional[str] = None,
    yield_pct: Optional[float] = None,
    reversible: bool = False,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """
    Reaction arrow: solid line with optional text labels above and below the shaft.

    Chemistry convention: conditions and reagents go above the shaft midpoint;
    yield percentage goes below. A reversible reaction gets a backward head at *start*.

    Text is placed perpendicular to the shaft direction, so this works for both
    horizontal and diagonal arrows.

    Args:
        start:      tail position (x, y)
        end:        tip position (x, y)
        conditions: short condition string above the shaft (e.g. "Δ", "100 °C")
        reagents:   reagent string above the shaft, stacked below conditions if both set
        yield_pct:  numeric yield rendered below the shaft as "X%"
        reversible: if True, adds a filled arrowhead at *start* pointing backward
        style_dict:      presentation attributes dict; falls back to DEFAULT_STYLE for missing keys

    Returns:
        svgwrite.container.Group containing shaft, head(s), and any text elements
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    dx, dy = _unit_vector(start, end)
    stroke = s["stroke"]
    sw = float(s["stroke_width"])
    hs = float(s["arrow_head_size"])
    fs = float(s["label_font_size"])
    ff = s["label_font_family"]
    fc = s["label_font_color"]

    shaft_start = (start[0] + dx * hs, start[1] + dy * hs) if reversible else start
    shaft_end = (end[0] - dx * hs, end[1] - dy * hs)

    line = svgwrite.shapes.Line(start=shaft_start, end=shaft_end, stroke=stroke)
    line["stroke-width"] = sw
    g.add(line)

    g.add(_filled_triangle_head(end, dx, dy, hs, stroke))
    if reversible:
        g.add(_filled_triangle_head(start, -dx, -dy, hs, stroke))

    mid = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2)
    # _perp_vector(1,0) = (0,1) = downward in SVG, so (-px,-py) = upward = "above" the shaft
    px, py = _perp_vector(dx, dy)
    gap = fs * 1.4

    if conditions:
        g.add(_formula_text(
            conditions,
            (mid[0] - px * gap, mid[1] - py * gap),
            font_family=ff, font_size=fs, fill=fc,
        ))

    if reagents:
        n = 2 if conditions else 1
        g.add(_formula_text(
            reagents,
            (mid[0] - px * gap * n, mid[1] - py * gap * n),
            font_family=ff, font_size=fs, fill=fc,
        ))

    if yield_pct is not None:
        t = svgwrite.text.Text(
            f"{yield_pct:.0f}%",
            insert=(mid[0] + px * gap, mid[1] + py * gap),
            font_family=ff,
            font_size=fs,
            fill=fc,
        )
        t["text-anchor"] = "middle"
        g.add(t)

    return g
