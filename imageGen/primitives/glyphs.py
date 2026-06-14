"""Expansion entity-glyph primitives (v2.x add-on set).

Schematic entity glyphs wired into ``ENTITY_TO_PRIMITIVE`` dispatch via the
``PRIMITIVE_REGISTRY`` override mechanism (set ``entity.style["primitive"] =
"<name>"``). They are *not* new ``EntityType``s — the IR schema is load-bearing
— so an author opts into any of these on top of an existing entity type
(usually ``protein``, ``organelle``, ``equipment``, or ``sample``).

Every public function follows the canonical entity-primitive calling
convention used by ``proteins.generic_protein`` so layout dispatch works
transparently::

    fn(label, position, size=(w, h), color=None, style_dict=None) -> Group

The defining shape is always the **first** child added to the group (before
the label), because ``convention_check`` keys an entity's expected shape off
the first shape-tag it finds. The shape occupies the upper portion of the
bounding box and the label sits below it, mirroring ``gene_helix`` so the
collision footprint matches ``ENTITY_BBOX``.

Glyph set:
  Cell / signalling: antibody, ion_channel, transporter, pump, phosphatase,
    ribosome, vesicle
  Lab equipment:     flask, centrifuge, flow_cytometer, sequencer,
    petri_dish, syringe
"""
from __future__ import annotations

from typing import Optional

import svgwrite
import svgwrite.container
import svgwrite.path
import svgwrite.shapes
import svgwrite.text

DEFAULT_STYLE: dict = {
    # Cell / signalling glyphs
    "antibody_fill": "#7BB6E0",
    "antibody_stroke": "#1F4E79",
    "channel_fill": "#9CC4A0",
    "channel_stroke": "#3D6B43",
    "transporter_fill": "#C19CD0",
    "transporter_stroke": "#5B3173",
    "pump_fill": "#F0B27A",
    "pump_stroke": "#935116",
    "pump_atp_fill": "#D32F2F",
    "phosphatase_fill": "#80CBC4",
    "phosphatase_stroke": "#00695C",
    "ribosome_large_fill": "#B0A8D0",
    "ribosome_small_fill": "#D4CEEA",
    "ribosome_stroke": "#4A4070",
    "vesicle_fill": "#FFE0B2",
    "vesicle_stroke": "#E08A2E",
    # Domain-canonical idioms (FR10)
    "voltage_trace_stroke": "#1F4E79",
    "voltage_trace_axis": "#888888",
    # Lab-equipment glyphs
    "equip_fill": "#CFD8DC",
    "equip_stroke": "#37474F",
    "equip_accent": "#1565C0",
    "glyph_stroke_width": 1.5,
    # Mechanism-figure minor glyphs (P7.3c)
    "tablet_fill": "#FAFBFC",      # aspirin tablet: a near-white scored disc
    "tablet_stroke": "#8A95A3",
    "pg_fill": "#E8A33D",          # prostaglandin dot-cluster (lipid mediator)
    "pg_stroke": "#9A6A12",
    # Shared label keys (keep synchronized with the other primitive modules
    # so the master-preset union stays coherent)
    "label_font_family": "Helvetica, Arial, sans-serif",
    "label_font_size": 11,
    "label_font_color": "#1A1A1A",
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _label_below(
    group: svgwrite.container.Group,
    label: str,
    cx: float,
    cy: float,
    h: float,
    s: dict,
) -> None:
    """Add a centered label in the bottom strip of the bounding box."""
    t = svgwrite.text.Text(
        label,
        insert=(round(cx, 2), round(cy + h * 0.40, 2)),
        font_family=str(s["label_font_family"]),
        font_size=float(s["label_font_size"]),
        fill=str(s["label_font_color"]),
    )
    t["text-anchor"] = "middle"
    t["dominant-baseline"] = "central"
    group.add(t)


def _sw(s: dict) -> float:
    return float(s["glyph_stroke_width"])


# ---------------------------------------------------------------------------
# Cell / signalling glyphs
# ---------------------------------------------------------------------------

def antibody(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (50, 50),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Immunoglobulin: the canonical Y-shape (two Fab arms + an Fc stem)."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["antibody_fill"]
    # Shape band: upper ~60% of the box.
    top = cy - h * 0.42
    fork = cy - h * 0.05          # where the two arms meet the stem
    bottom = cy + h * 0.18
    arm = w * 0.32
    d = (
        f"M {cx - arm:.2f},{top:.2f} L {cx:.2f},{fork:.2f} "
        f"L {cx + arm:.2f},{top:.2f} M {cx:.2f},{fork:.2f} "
        f"L {cx:.2f},{bottom:.2f}"
    )
    y = svgwrite.path.Path(d=d, fill="none", stroke=s["antibody_stroke"])
    y["stroke-width"] = _sw(s) * 3.0
    y["stroke-linecap"] = "round"
    y["stroke-linejoin"] = "round"
    g.add(y)
    # Antigen-binding tips, drawn as small filled discs on the Fab ends.
    for tx in (cx - arm, cx + arm):
        tip = svgwrite.shapes.Circle(
            center=(tx, top), r=max(2.5, h * 0.07),
            fill=fill, stroke=s["antibody_stroke"],
        )
        tip["stroke-width"] = _sw(s)
        g.add(tip)
    _label_below(g, label, cx, cy, h, s)
    return g


def ion_channel(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (40, 50),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Ion channel: two facing trapezoids with a central conducting pore."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["channel_fill"]
    top = cy - h * 0.42
    bot = cy + h * 0.18
    pore = w * 0.12
    half = w * 0.42
    for sign in (-1, 1):
        outer = cx + sign * half
        inner = cx + sign * pore
        pts = [
            (outer, top), (inner, top + h * 0.12),
            (inner, bot - h * 0.12), (outer, bot),
        ]
        poly = svgwrite.shapes.Polygon(points=pts, fill=fill, stroke=s["channel_stroke"])
        poly["stroke-width"] = _sw(s)
        g.add(poly)
    _label_below(g, label, cx, cy, h, s)
    return g


def transporter(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (40, 50),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Transporter: a membrane barrel with a clefted (occluded) center."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["transporter_fill"]
    top = cy - h * 0.42
    bot = cy + h * 0.18
    half = w * 0.40
    notch = w * 0.16
    pts = [
        (cx - half, top), (cx + half, top),
        (cx + half, bot), (cx + notch, bot),
        (cx + notch, cy - h * 0.05), (cx - notch, cy - h * 0.05),
        (cx - notch, bot), (cx - half, bot),
    ]
    body = svgwrite.shapes.Polygon(points=pts, fill=fill, stroke=s["transporter_stroke"])
    body["stroke-width"] = _sw(s)
    g.add(body)
    _label_below(g, label, cx, cy, h, s)
    return g


def pump(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (44, 52),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Active transport pump: a barrel with an ATP burst marking energy use."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["pump_fill"]
    top = cy - h * 0.42
    bot = cy + h * 0.16
    half = w * 0.34
    pts = [
        (cx - half, top), (cx + half, top),
        (cx + half * 0.7, bot), (cx - half * 0.7, bot),
    ]
    barrel = svgwrite.shapes.Polygon(points=pts, fill=fill, stroke=s["pump_stroke"])
    barrel["stroke-width"] = _sw(s)
    g.add(barrel)
    # ATP energy burst (small star) at the upper-right.
    bx, by, r = cx + half, top, max(4.0, h * 0.13)
    star = svgwrite.shapes.Circle(center=(bx, by), r=r, fill=s["pump_atp_fill"], stroke=s["pump_stroke"])
    star["stroke-width"] = _sw(s)
    g.add(star)
    g.add(_atp_text(bx, by, s))
    _label_below(g, label, cx, cy, h, s)
    return g


def _atp_text(bx: float, by: float, s: dict) -> svgwrite.text.Text:
    t = svgwrite.text.Text(
        "ATP", insert=(round(bx, 2), round(by, 2)),
        font_family=str(s["label_font_family"]),
        font_size=float(s["label_font_size"]) * 0.62,
        fill="#FFFFFF",
    )
    t["text-anchor"] = "middle"
    t["dominant-baseline"] = "central"
    t["font-weight"] = "bold"
    return t


def phosphatase(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (70, 32),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Phosphatase: an enzyme hexagon (teal), the dephosphorylating counterpart
    to the kinase glyph — same hexagon family, distinct palette."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["phosphatase_fill"]
    shape_cy = cy - h * 0.12
    half_w, half_h = w / 2, h * 0.36
    chamfer = (half_h * 2) * 0.4
    pts = [
        (cx - half_w + chamfer, shape_cy - half_h),
        (cx + half_w - chamfer, shape_cy - half_h),
        (cx + half_w, shape_cy),
        (cx + half_w - chamfer, shape_cy + half_h),
        (cx - half_w + chamfer, shape_cy + half_h),
        (cx - half_w, shape_cy),
    ]
    hexagon = svgwrite.shapes.Polygon(points=pts, fill=fill, stroke=s["phosphatase_stroke"])
    hexagon["stroke-width"] = _sw(s)
    g.add(hexagon)
    _label_below(g, label, cx, cy, h, s)
    return g


def ribosome(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (50, 50),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Ribosome: stacked large + small subunits (two nested ovals)."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    large_fill = color or s["ribosome_large_fill"]
    shape_cy = cy - h * 0.10
    large = svgwrite.shapes.Ellipse(
        center=(cx, shape_cy + h * 0.06), r=(w * 0.42, h * 0.26),
        fill=large_fill, stroke=s["ribosome_stroke"],
    )
    large["stroke-width"] = _sw(s)
    g.add(large)
    small = svgwrite.shapes.Ellipse(
        center=(cx, shape_cy - h * 0.18), r=(w * 0.34, h * 0.15),
        fill=s["ribosome_small_fill"], stroke=s["ribosome_stroke"],
    )
    small["stroke-width"] = _sw(s)
    g.add(small)
    _label_below(g, label, cx, cy, h, s)
    return g


def vesicle(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (44, 44),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Vesicle: a membrane-bound circle (lipid sphere)."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["vesicle_fill"]
    r = min(w, h) * 0.34
    circle = svgwrite.shapes.Circle(
        center=(cx, cy - h * 0.12), r=r, fill=fill, stroke=s["vesicle_stroke"],
    )
    circle["stroke-width"] = _sw(s) * 1.6
    g.add(circle)
    _label_below(g, label, cx, cy, h, s)
    return g


# ---------------------------------------------------------------------------
# Lab-equipment glyphs
# ---------------------------------------------------------------------------

def flask(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (44, 56),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Erlenmeyer flask: narrow neck flaring into a conical body."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["equip_fill"]
    top = cy - h * 0.44
    bot = cy + h * 0.16
    neck = w * 0.12
    base = w * 0.40
    shoulder = top + h * 0.22
    d = (
        f"M {cx - neck:.2f},{top:.2f} L {cx + neck:.2f},{top:.2f} "
        f"L {cx + neck:.2f},{shoulder:.2f} L {cx + base:.2f},{bot:.2f} "
        f"L {cx - base:.2f},{bot:.2f} L {cx - neck:.2f},{shoulder:.2f} Z"
    )
    body = svgwrite.path.Path(d=d, fill=fill, stroke=s["equip_stroke"])
    body["stroke-width"] = _sw(s)
    body["stroke-linejoin"] = "round"
    g.add(body)
    _label_below(g, label, cx, cy, h, s)
    return g


def centrifuge(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (54, 54),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Centrifuge: a circular rotor housing with a spin indicator."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["equip_fill"]
    shape_cy = cy - h * 0.10
    r = min(w, h) * 0.36
    housing = svgwrite.shapes.Circle(center=(cx, shape_cy), r=r, fill=fill, stroke=s["equip_stroke"])
    housing["stroke-width"] = _sw(s)
    g.add(housing)
    hub = svgwrite.shapes.Circle(center=(cx, shape_cy), r=r * 0.22, fill=s["equip_accent"], stroke=s["equip_stroke"])
    hub["stroke-width"] = _sw(s)
    g.add(hub)
    _label_below(g, label, cx, cy, h, s)
    return g


def flow_cytometer(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (64, 50),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Flow cytometer: an instrument box with a droplet-stream nozzle."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["equip_fill"]
    bw, bh = w * 0.7, h * 0.5
    bx, by = cx - bw / 2, cy - h * 0.42
    box = svgwrite.shapes.Rect(insert=(bx, by), size=(bw, bh), rx=3, ry=3, fill=fill, stroke=s["equip_stroke"])
    box["stroke-width"] = _sw(s)
    g.add(box)
    # Droplet stream below the nozzle.
    for i in range(3):
        drop = svgwrite.shapes.Circle(
            center=(cx, by + bh + (i + 1) * h * 0.10), r=max(1.6, h * 0.035),
            fill=s["equip_accent"], stroke="none",
        )
        g.add(drop)
    _label_below(g, label, cx, cy, h, s)
    return g


def sequencer(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (64, 48),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Sequencer: a benchtop instrument box with a status screen."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["equip_fill"]
    bw, bh = w * 0.78, h * 0.52
    bx, by = cx - bw / 2, cy - h * 0.42
    box = svgwrite.shapes.Rect(insert=(bx, by), size=(bw, bh), rx=4, ry=4, fill=fill, stroke=s["equip_stroke"])
    box["stroke-width"] = _sw(s)
    g.add(box)
    screen = svgwrite.shapes.Rect(
        insert=(bx + bw * 0.12, by + bh * 0.2), size=(bw * 0.5, bh * 0.5),
        rx=2, ry=2, fill=s["equip_accent"], stroke=s["equip_stroke"],
    )
    screen["stroke-width"] = _sw(s) * 0.7
    g.add(screen)
    _label_below(g, label, cx, cy, h, s)
    return g


def petri_dish(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (60, 40),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Petri dish: a shallow round dish seen at a slight top-down angle."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["equip_fill"]
    shape_cy = cy - h * 0.10
    dish = svgwrite.shapes.Ellipse(
        center=(cx, shape_cy), r=(w * 0.42, h * 0.26),
        fill=fill, stroke=s["equip_stroke"],
    )
    dish["stroke-width"] = _sw(s)
    g.add(dish)
    inner = svgwrite.shapes.Ellipse(
        center=(cx, shape_cy), r=(w * 0.34, h * 0.18),
        fill="none", stroke=s["equip_stroke"],
    )
    inner["stroke-width"] = _sw(s) * 0.6
    g.add(inner)
    _label_below(g, label, cx, cy, h, s)
    return g


def syringe(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (76, 30),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Syringe: a horizontal barrel with a plunger and needle."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["equip_fill"]
    shape_cy = cy - h * 0.12
    barrel_w, barrel_h = w * 0.5, h * 0.5
    bx = cx - w * 0.34
    barrel = svgwrite.shapes.Rect(
        insert=(bx, shape_cy - barrel_h / 2), size=(barrel_w, barrel_h),
        rx=2, ry=2, fill=fill, stroke=s["equip_stroke"],
    )
    barrel["stroke-width"] = _sw(s)
    g.add(barrel)
    # Plunger (left) and needle (right).
    plunger = svgwrite.shapes.Line(
        start=(bx - w * 0.14, shape_cy), end=(bx, shape_cy), stroke=s["equip_stroke"],
    )
    plunger["stroke-width"] = _sw(s) * 2.0
    g.add(plunger)
    needle = svgwrite.shapes.Line(
        start=(bx + barrel_w, shape_cy), end=(cx + w * 0.46, shape_cy), stroke=s["equip_stroke"],
    )
    needle["stroke-width"] = _sw(s)
    g.add(needle)
    _label_below(g, label, cx, cy, h, s)
    return g


# ---------------------------------------------------------------------------
# Domain-canonical idioms (FR10)
# ---------------------------------------------------------------------------

# Canonical neuronal action-potential waveform as (time_frac, voltage_frac)
# control points: resting → threshold → depolarization spike → repolarization →
# hyperpolarization undershoot → recovery. voltage_frac 0 = most negative, 1 =
# peak. Kept module-level so tests and styling can reference the shape.
_AP_WAVEFORM: tuple[tuple[float, float], ...] = (
    (0.00, 0.18), (0.20, 0.18), (0.27, 0.30), (0.34, 1.00),
    (0.42, 0.52), (0.50, 0.04), (0.64, 0.13), (1.00, 0.18),
)
_AP_THRESHOLD_FRAC = 0.30  # voltage_frac of the dashed threshold guide


def voltage_trace(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (150, 90),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
    *,
    phases: bool = True,
) -> svgwrite.container.Group:
    """Action-potential voltage trace — a canonical V-vs-time waveform (FR10).

    Draws the textbook neuronal action potential (resting → threshold → spike →
    repolarization → hyperpolarization → recovery) inside the bounding box, with
    V/t axes, a dashed threshold guide, and mV/ms unit labels. With ``phases``
    (default), the threshold guide is labelled in the clear resting region.

    Calling convention matches the other entity glyphs. The trace ``<path>`` is
    the first shape child (``convention_check`` keys an entity's shape off it).
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    stroke = color or s.get("voltage_trace_stroke", s["antibody_stroke"])
    axis_color = s.get("voltage_trace_axis", "#888888")

    # Plot rectangle inside the box: leave a left gutter for the y-axis label and
    # a bottom strip for the entity label (mirrors _label_below at cy + 0.40h).
    x0 = cx - w / 2 + w * 0.16
    x1 = cx + w / 2 - w * 0.04
    y_top = cy - h * 0.34
    y_bot = cy + h * 0.16

    def _px(t: float) -> float:
        return x0 + t * (x1 - x0)

    def _py(v: float) -> float:
        return y_bot - v * (y_bot - y_top)

    # Trace path FIRST (defining shape).
    pts = [(_px(t), _py(v)) for t, v in _AP_WAVEFORM]
    d = "M " + " L ".join(f"{x:.2f},{y:.2f}" for x, y in pts)
    trace = svgwrite.path.Path(d=d, fill="none", stroke=stroke)
    trace["stroke-width"] = _sw(s) * 1.6
    trace["stroke-linejoin"] = "round"
    trace["stroke-linecap"] = "round"
    g.add(trace)

    # Axes (y then x).
    for start, end in (((x0, y_top), (x0, y_bot)), ((x0, y_bot), (x1, y_bot))):
        ax = svgwrite.shapes.Line(start=start, end=end, stroke=axis_color)
        ax["stroke-width"] = _sw(s) * 0.8
        g.add(ax)

    # Dashed threshold guide.
    thr_y = _py(_AP_THRESHOLD_FRAC)
    thr = svgwrite.shapes.Line(start=(x0, thr_y), end=(x1, thr_y), stroke=axis_color)
    thr["stroke-width"] = _sw(s) * 0.6
    thr["stroke-dasharray"] = "3,3"
    g.add(thr)

    # Axis unit labels.
    def _unit(text, x, y, anchor):
        t = svgwrite.text.Text(text, insert=(round(x, 2), round(y, 2)),
                               font_family=str(s["label_font_family"]),
                               fill=axis_color)
        t["font-size"] = 8.0
        t["text-anchor"] = anchor
        return t

    g.add(_unit("mV", x0 - 3, y_top + 2, "end"))
    g.add(_unit("ms", x1, y_bot + 9, "end"))

    if phases:
        # Label the threshold guide in the clear resting region at the left. The
        # AP's three events (depolarization/repolarization/hyperpolarization)
        # cluster in x near the spike, so inline phase captions there collide in
        # a small glyph; the single threshold label reads cleanly instead.
        thr_label = svgwrite.text.Text(
            "threshold", insert=(round(x0 + 2, 2), round(thr_y - 3, 2)),
            font_family=str(s["label_font_family"]), fill=axis_color,
        )
        thr_label["font-size"] = 7.0
        thr_label["text-anchor"] = "start"
        g.add(thr_label)

    _label_below(g, label, cx, cy, h, s)
    return g


# ---------------------------------------------------------------------------
# Mechanism-figure minor glyphs (P7.3c)
# ---------------------------------------------------------------------------

def tablet(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (40, 40),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Aspirin tablet: a near-white scored disc (the drug-as-pill icon)."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    r = min(w, h) * 0.34
    disc_cy = cy - h * 0.12
    disc = svgwrite.shapes.Circle(
        center=(round(cx, 2), round(disc_cy, 2)), r=round(r, 2),
        fill=color or s["tablet_fill"], stroke=s["tablet_stroke"])
    disc["stroke-width"] = _sw(s) * 1.4
    g.add(disc)
    # Debossed score line across the tablet face.
    score = svgwrite.shapes.Line(
        start=(round(cx - r * 0.7, 2), round(disc_cy, 2)),
        end=(round(cx + r * 0.7, 2), round(disc_cy, 2)),
        stroke=s["tablet_stroke"])
    score["stroke-width"] = _sw(s)
    g.add(score)
    _label_below(g, label, cx, cy, h, s)
    return g


def pg_cluster(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (50, 50),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """Prostaglandin dot-cluster (a lipid-mediator pool).

    ``style['reduced']=True`` draws a sparser cluster — the depleted PG pool after
    COX-1 inhibition — so a before/after pair reads as "synthesis reduced"."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    reduced = bool(s.get("reduced", False))
    fill = color or s["pg_fill"]
    # Fractional (dx, dy) offsets of each dot within the box; 'reduced' keeps a
    # sparse subset so the depleted pool reads at a glance.
    offsets = [(-0.22, -0.12), (0.0, -0.2), (0.22, -0.12),
               (-0.12, 0.08), (0.14, 0.1), (0.0, -0.02)]
    if reduced:
        offsets = offsets[:2]
    rdot = min(w, h) * 0.12
    for ox, oy in offsets:
        dot = svgwrite.shapes.Circle(
            center=(round(cx + ox * w, 2), round(cy + oy * h - h * 0.1, 2)),
            r=round(rdot, 2), fill=fill, stroke=s["pg_stroke"])
        dot["stroke-width"] = _sw(s)
        g.add(dot)
    _label_below(g, label, cx, cy, h, s)
    return g
