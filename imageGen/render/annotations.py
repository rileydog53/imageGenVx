"""Annotation rendering (FR1): draw ``Figure.annotations`` on top of a figure.

Until this module landed, ``render_figure`` never read ``figure.annotations`` —
``label`` / ``caption`` / ``scale_bar`` entries were silent no-ops even though
fixtures relied on them. This module turns each :class:`~imageGen.ir.schema.Annotation`
into a ``LayoutEntry`` so it flows through the same ``_write_svg`` execution path
as every other primitive, drawn last so it sits above figure content.

Three annotation types (``AnnotationType``):
  - ``label``     — free-text callout placed at a point; given a semi-opaque
    white halo box so it stays legible over dense figure content.
  - ``caption``   — figure-level note (e.g. a method note or data disclaimer);
    italic, centered on its slot, no box.
  - ``scale_bar`` — a fixed-length rule with the text as its magnitude label
    below it. The schema carries no physical length, so the bar is a fixed
    drawn width and the text (e.g. "10 µm") is the caller-supplied magnitude.

Position resolution (``_resolve_position``):
  - ``NamedSlot`` → a canvas anchor with a small inset, plus the matching SVG
    ``text-anchor`` / vertical placement for that slot.
  - ``(x, y)`` tuple → **fractional** (fraction of canvas w/h) when both values
    are in ``[0, 1]``, else **absolute** canvas pixels. Fixtures author
    fractional points (e.g. ``[0.7, 0.55]``); absolute points are supported for
    precise placement. Anchored centered.
"""
from __future__ import annotations

import svgwrite.container
import svgwrite.shapes
import svgwrite.text

from imageGen.ir.schema import Annotation, AnnotationType, Figure, NamedSlot
from imageGen.layout.label_placement import (
    Bbox,
    LabelRequest,
    _place_with_fallback,
)
from imageGen.layout.types import LayoutEntry
from imageGen.render._measure import estimate_text_w as _estimate_text_w

# Inset (px) from the canvas edge for slot-anchored annotations.
_SLOT_INSET = 14.0
# Scale-bar geometry (px). Length is fixed — the schema carries no magnitude.
_SCALE_BAR_LEN = 60.0
_SCALE_BAR_THICK = 3.0
_SCALE_BAR_GAP = 4.0  # bar → label gap
# Halo box padding around label text (px).
_LABEL_PAD_X = 5.0
_LABEL_PAD_Y = 3.0

# Per-slot: (anchor_x_frac, anchor_y_frac, text_anchor, vertical) where vertical
# is one of "top" | "middle" | "bottom" — how the text sits relative to the y.
_SLOT_GEOM: dict[NamedSlot, tuple[float, float, str, str]] = {
    NamedSlot.TOP:          (0.5, 0.0, "middle", "top"),
    NamedSlot.BOTTOM:       (0.5, 1.0, "middle", "bottom"),
    NamedSlot.LEFT:         (0.0, 0.5, "start",  "middle"),
    NamedSlot.RIGHT:        (1.0, 0.5, "end",    "middle"),
    NamedSlot.TOP_LEFT:     (0.0, 0.0, "start",  "top"),
    NamedSlot.TOP_RIGHT:    (1.0, 0.0, "end",    "top"),
    NamedSlot.BOTTOM_LEFT:  (0.0, 1.0, "start",  "bottom"),
    NamedSlot.BOTTOM_RIGHT: (1.0, 1.0, "end",    "bottom"),
    NamedSlot.CENTER:       (0.5, 0.5, "middle", "middle"),
}


def _resolve_position(
    position: tuple[float, float] | NamedSlot,
    canvas: tuple[float, float],
) -> tuple[float, float, str, str]:
    """Resolve an annotation ``position`` to ``(x, y, text_anchor, vertical)``.

    Slots inset from the canvas edge so text doesn't kiss the border. A float
    tuple is fractional when both components are in ``[0, 1]`` (the fixture
    convention), otherwise absolute pixels; either way it is centered.
    """
    cw, ch = canvas
    if isinstance(position, NamedSlot):
        fx, fy, anchor, vertical = _SLOT_GEOM[position]
        x = fx * cw
        y = fy * ch
        # Pull slot anchors inward off the edges they touch.
        if fx == 0.0:
            x += _SLOT_INSET
        elif fx == 1.0:
            x -= _SLOT_INSET
        if fy == 0.0:
            y += _SLOT_INSET
        elif fy == 1.0:
            y -= _SLOT_INSET
        return x, y, anchor, vertical

    px, py = position
    if 0.0 <= px <= 1.0 and 0.0 <= py <= 1.0:
        return px * cw, py * ch, "middle", "middle"
    return px, py, "middle", "middle"


def _baseline_y(y: float, vertical: str, font_size: float) -> float:
    """Convert a vertical-placement intent + text y into an SVG baseline y.

    SVG text is baseline-anchored. "top" drops the baseline by one cap height so
    the text reads *below* the anchor; "bottom" lifts it so text reads *above*;
    "middle" centers on the cap.
    """
    if vertical == "top":
        return y + font_size * 0.8
    if vertical == "bottom":
        return y - font_size * 0.2
    return y + font_size * 0.35  # middle


def _label(
    ann: Annotation, x: float, y: float, anchor: str, vertical: str,
    style_dict: dict,
) -> svgwrite.container.Group:
    """Free-text label with a semi-opaque white halo box for legibility."""
    g = svgwrite.container.Group()
    font_size = float(style_dict.get("annotation_label_font_size",
                                     style_dict.get("label_font_size", 11)))
    font_family = style_dict.get("label_font_family", "Arial, sans-serif")
    color = style_dict.get("annotation_label_color",
                           style_dict.get("label_font_color", "#1A1A1A"))

    text_w = _estimate_text_w(ann.text, font_size)
    box_w = text_w + 2 * _LABEL_PAD_X
    box_h = font_size + 2 * _LABEL_PAD_Y
    # Box left edge from the text anchor.
    if anchor == "start":
        box_x = x - _LABEL_PAD_X
    elif anchor == "end":
        box_x = x - text_w - _LABEL_PAD_X
    else:  # middle
        box_x = x - text_w / 2 - _LABEL_PAD_X
    baseline = _baseline_y(y, vertical, font_size)
    box_y = baseline - font_size * 0.8 - _LABEL_PAD_Y

    box = svgwrite.shapes.Rect(
        insert=(box_x, box_y), size=(box_w, box_h), rx=3, ry=3,
        fill="#FFFFFF", stroke="none",
    )
    box["fill-opacity"] = 0.78
    g.add(box)

    t = svgwrite.text.Text(ann.text, insert=(x, baseline), fill=color)
    t["font-size"] = font_size
    t["font-family"] = font_family
    t["text-anchor"] = anchor
    g.add(t)
    return g


def _caption(
    ann: Annotation, x: float, y: float, anchor: str, vertical: str,
    style_dict: dict,
) -> svgwrite.container.Group:
    """Italic figure-level caption (no box)."""
    g = svgwrite.container.Group()
    font_size = float(style_dict.get("annotation_caption_font_size",
                                     style_dict.get("caption_font_size", 10)))
    font_family = style_dict.get("label_font_family", "Arial, sans-serif")
    color = style_dict.get("annotation_caption_color",
                           style_dict.get("caption_font_color", "#555555"))
    baseline = _baseline_y(y, vertical, font_size)
    t = svgwrite.text.Text(ann.text, insert=(x, baseline), fill=color)
    t["font-size"] = font_size
    t["font-family"] = font_family
    t["font-style"] = "italic"
    t["text-anchor"] = anchor
    g.add(t)
    return g


def _scale_bar(
    ann: Annotation, x: float, y: float, anchor: str, vertical: str,
    style_dict: dict,
) -> svgwrite.container.Group:
    """Fixed-length rule with the annotation text as its magnitude label."""
    g = svgwrite.container.Group()
    font_size = float(style_dict.get("annotation_label_font_size",
                                     style_dict.get("label_font_size", 11)))
    font_family = style_dict.get("label_font_family", "Arial, sans-serif")
    color = style_dict.get("annotation_label_color",
                           style_dict.get("label_font_color", "#1A1A1A"))
    half = _SCALE_BAR_LEN / 2
    # Center the bar on x for middle anchor; left/right align to the anchor.
    if anchor == "start":
        bx0, bx1 = x, x + _SCALE_BAR_LEN
    elif anchor == "end":
        bx0, bx1 = x - _SCALE_BAR_LEN, x
    else:
        bx0, bx1 = x - half, x + half
    bar = svgwrite.shapes.Line(start=(bx0, y), end=(bx1, y), stroke=color)
    bar["stroke-width"] = _SCALE_BAR_THICK
    bar["stroke-linecap"] = "butt"
    g.add(bar)
    t = svgwrite.text.Text(
        ann.text, insert=((bx0 + bx1) / 2, y + font_size + _SCALE_BAR_GAP),
        fill=color,
    )
    t["font-size"] = font_size
    t["font-family"] = font_family
    t["text-anchor"] = "middle"
    g.add(t)
    return g


_RENDERERS = {
    AnnotationType.LABEL: _label,
    AnnotationType.CAPTION: _caption,
    AnnotationType.SCALE_BAR: _scale_bar,
}


def annotation_group(
    ann: Annotation, canvas: tuple[float, float], style_dict: dict | None = None,
    *, position_override: tuple[float, float] | None = None,
) -> svgwrite.container.Group:
    """Render a single annotation to an svgwrite Group positioned on the canvas.

    ``position_override`` (P5.3): when set, the resolved ``(x, y)`` is replaced
    by this point — the occupancy-aware nudge that keeps a figure-level
    annotation off the scene-local labels. The slot's ``text_anchor`` /
    vertical placement are kept. ``None`` (default) renders at the authored
    position verbatim, so every non-tier path is byte-identical.
    """
    style_dict = style_dict or {}
    x, y, anchor, vertical = _resolve_position(ann.position, canvas)
    if position_override is not None:
        x, y = position_override
    return _RENDERERS[ann.type](ann, x, y, anchor, vertical, style_dict)


def _avoid_occupied(
    ann: Annotation, canvas: tuple[float, float], style_dict: dict,
    occupied: list[Bbox],
) -> tuple[float, float] | None:
    """Find a position override that keeps *ann* off *occupied*, reserving it.

    Reuses ``place_labels._place_with_fallback`` (not a second solver): the
    authored point is the anchor, with ``center`` tried first so a clear
    annotation stays exactly put — no override → byte-identical render — then
    the shrink / nudge ladder pushes a colliding one clear. The chosen bbox is
    appended to *occupied* so later annotations avoid it too. Returns the new
    point, or ``None`` when the annotation does not move (already clear, or the
    ladder exhausted to a last-resort overlap → keep the authored spot).
    """
    x, y, _anchor, _vertical = _resolve_position(ann.position, canvas)
    font_size = float(style_dict.get(
        "annotation_label_font_size", style_dict.get("label_font_size", 11)))
    req = LabelRequest(
        text=ann.text, anchor=(x, y), anchor_size=(0.0, 0.0),
        priority=("center", "below", "above", "right", "left"),
    )
    center, bbox, _font, overlap = _place_with_fallback(
        req, occupied, gap=4.0, margin=1.0, font_size=font_size, canvas=None)
    occupied.append(bbox)
    if overlap or center == (x, y):
        return None
    return center


def annotation_entries(
    figure: Figure, canvas: tuple[float, float], style_dict: dict | None = None,
    *, occupied: list[Bbox] | None = None,
) -> list[LayoutEntry]:
    """Return one ``LayoutEntry`` per ``figure.annotations`` entry (drawn last).

    Each entry calls :func:`annotation_group`, which positions the annotation in
    absolute canvas coordinates — so the entry's own ``position`` stays ``(0, 0)``.
    IR ids are synthetic (``annotation_0``, …) since annotations carry no id.

    ``occupied`` (P5.3): bboxes already taken by scene-local labels. When it is
    non-empty, LABEL / CAPTION annotations are nudged off those boxes (and off
    each other) via :func:`_avoid_occupied`; SCALE_BAR stays fixed. ``None`` /
    empty (every non-tier path, and tier figures with no scene labels) leaves
    every annotation at its authored position — byte-identical to before.
    """
    entries: list[LayoutEntry] = []
    occ: list[Bbox] = list(occupied) if occupied else []
    seed_active = bool(occ)
    for i, ann in enumerate(figure.annotations):
        kwargs: dict = {"style_dict": style_dict or {}}
        if seed_active and ann.type in (AnnotationType.LABEL, AnnotationType.CAPTION):
            override = _avoid_occupied(ann, canvas, style_dict or {}, occ)
            if override is not None:
                kwargs["position_override"] = override
        entries.append(LayoutEntry(
            annotation_group,
            (ann, canvas),
            kwargs,
            position=(0.0, 0.0),
            ir_id=f"annotation_{i}",
        ))
    return entries
