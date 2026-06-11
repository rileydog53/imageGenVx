"""Per-arrow annotation glyph helpers for the pathway engine (V2 / L4).

Extracted from ``pathway_layout`` (Phase R1.a) as a self-contained leaf: the
phosphorylation 'P' badge and its geometry. ``pathway_layout`` re-imports these
names, so they stay importable from ``pathway_layout`` for back-compat
(``label_placement`` lazy-imports ``phospho_badge_occupied_bbox`` from there).

The badge has a single source of truth for placement (``_phospho_badge_geom``)
shared by the renderer (``_phosphorylation_arrow``) and the label engine's
collision-reservation (``phospho_badge_occupied_bbox``) so the drawn glyph and
its reserved footprint can never drift apart.
"""
from __future__ import annotations

import svgwrite.container
import svgwrite.shapes

from imageGen.primitives import arrows
from imageGen.primitives._text import centered_label as _centered_label


# Style fallbacks for the phosphorylation badge.  These keys are present in
# proteins.DEFAULT_STYLE; replicated here so pathway_layout stays independent
# of the proteins module.
_PHOSPHO_BADGE_DEFAULTS: dict = {
    "kinase_badge_fill":       "#D32F2F",
    "kinase_badge_text_color": "#FFFFFF",
    "label_font_size":          11,
    "label_font_family":       "Helvetica, Arial, sans-serif",
    "label_font_color":        "#1A1A1A",
    "protein_stroke":          "#1F4E79",
    "protein_stroke_width":     0.5,
}


def _midpoint_of_path(
    waypoints: list[tuple[float, float]],
) -> tuple[float, float]:
    """Return the geometric midpoint of a polyline (list of ≥ 2 points).

    For a two-point path this is the exact midpoint of the segment. For a
    multi-waypoint elbow path it returns the midpoint of the middle segment
    so the badge sits on the longest visible shaft rather than at a corner.
    """
    if len(waypoints) < 2:
        return waypoints[0]
    if len(waypoints) == 2:
        (x1, y1), (x2, y2) = waypoints
        return ((x1 + x2) / 2, (y1 + y2) / 2)
    mid_i = len(waypoints) // 2
    (x1, y1) = waypoints[mid_i - 1]
    (x2, y2) = waypoints[mid_i]
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _relation_glyph(
    group: svgwrite.container.Group,
    cx: float,
    cy: float,
    text: str,
    style: dict,
) -> None:
    """Append a small circular badge carrying ``text`` to ``group`` at (cx, cy).

    The badge uses ``kinase_badge_fill`` / ``kinase_badge_text_color`` style
    keys so it picks up preset overrides automatically. Badge radius scales
    with ``label_font_size`` so it stays proportional across presets.
    """
    font_size = float(style.get("label_font_size", 11))
    r = max(7.0, font_size * 0.75)
    badge = svgwrite.shapes.Circle(
        center=(cx, cy), r=r,
        fill=style.get("kinase_badge_fill", "#D32F2F"),
        stroke=style.get("protein_stroke", "#1F4E79"),
    )
    badge["stroke-width"] = float(style.get("protein_stroke_width", 0.5))
    group.add(badge)
    group.add(_centered_label(
        text, cx, cy, style,
        weight="bold",
        color=style.get("kinase_badge_text_color", "#FFFFFF"),
        size_override=font_size * 0.9,
    ))


def _phospho_badge_geom(
    pts: list[tuple[float, float]],
    style: dict,
) -> tuple[tuple[float, float], float]:
    """Return the ('P' badge center, radius) for a phosphorylation shaft.

    Single source of truth for the badge placement: both
    ``_phosphorylation_arrow`` (which draws it) and
    ``phospho_badge_occupied_bbox`` (which reserves its footprint in the
    label engine) call this, so the rendered glyph and the collision box
    can never drift apart. Radius mirrors ``_relation_glyph``.
    """
    cx, cy = _midpoint_of_path(pts)
    font_size = float(style.get("label_font_size", 11))
    r = max(7.0, font_size * 0.75)
    return (cx, cy), r


def _phosphorylation_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    style_dict: dict | None = None,
    waypoints: list[tuple[float, float]] | None = None,
) -> svgwrite.container.Group:
    """Activation arrow annotated with a 'P' badge at the shaft midpoint.

    V2 / L4. Calls ``arrows.activation_arrow`` for the shaft/head, then
    overlays a phosphorylation badge so the PHOSPHORYLATES relation type is
    visually distinct from a plain ACTIVATES arrow.
    """
    g = arrows.activation_arrow(start, end, style_dict=style_dict, waypoints=waypoints)
    s = {**_PHOSPHO_BADGE_DEFAULTS, **(style_dict or {})}
    pts = waypoints if waypoints else [start, end]
    (cx, cy), _r = _phospho_badge_geom(pts, s)
    _relation_glyph(g, cx, cy, "P", s)
    return g


def phospho_badge_occupied_bbox(entry) -> tuple[float, float, float, float] | None:
    """Bbox of the 'P' badge for a phosphorylation-arrow ``LayoutEntry``.

    LT3. The badge carries a ``<text>`` 'P' that the legibility audit treats
    as a label; without reserving its footprint, a relation label anchored at
    the same shaft midpoint renders on top of it. ``label_placement._entry_bbox``
    calls this so the badge joins the placement ``occupied`` set and labels are
    steered clear. Returns ``None`` for any non-phosphorylation entry.
    """
    if entry.primitive is not _phosphorylation_arrow:
        return None
    start, end = entry.args
    waypoints = entry.kwargs.get("waypoints")
    style = {**_PHOSPHO_BADGE_DEFAULTS, **(entry.kwargs.get("style_dict") or {})}
    pts = waypoints if waypoints else [start, end]
    (cx, cy), r = _phospho_badge_geom(pts, style)
    return (cx - r, cy - r, cx + r, cy + r)
