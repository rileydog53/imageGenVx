"""Auto-legend (Issue #4): a small inset key explaining the glyph conventions
a figure actually uses (relation arrow types + the phosphorylation 'P' badge).

Opt-in: ``render_figure(..., legend=True)`` / the ``--legend`` CLI flag. The
legend is detected from the figure's relations (and any phosphorylated kinase
entity), deduplicated by *glyph appearance* so the three relation types that
share a filled-triangle arrow (activates / transcribes / generic) collapse to a
single "Activation" row, then drawn as a bordered, semi-opaque box anchored at a
canvas corner (top-right by default).

The legend is emitted as a normal ``LayoutEntry`` so it flows through the same
``_write_svg`` execution path as every other primitive.
"""
from __future__ import annotations

import svgwrite.container
import svgwrite.shapes
import svgwrite.text

from imageGen.ir.schema import Figure, RelationType
from imageGen.primitives import arrows

# Each relation type maps to a *glyph key* (its visual appearance). Types that
# render with the same glyph share a key so the legend shows one row per glyph.
_RELATION_GLYPH_KEY: dict[RelationType, str] = {
    RelationType.ACTIVATES:      "activation",
    RelationType.TRANSCRIBES:    "activation",
    RelationType.GENERIC:        "activation",
    RelationType.INHIBITS:       "inhibition",
    RelationType.BINDS:          "binding",
    RelationType.TRANSLOCATES:   "translocation",
    RelationType.PHOSPHORYLATES: "phosphorylation",
    RelationType.CATALYZES:      "catalysis",
    RelationType.CLEAVES:        "cleavage",
    RelationType.TRANSPORTS:     "transport",
    RelationType.RECRUITS:       "recruitment",
}

# Canonical render order + human-readable caption for each glyph key.
_GLYPH_ORDER: list[str] = [
    "activation", "inhibition", "binding", "phosphorylation", "catalysis",
    "translocation", "transport", "recruitment", "cleavage",
]
_GLYPH_CAPTION: dict[str, str] = {
    "activation":     "Activation",
    "inhibition":     "Inhibition",
    "binding":        "Binding",
    "phosphorylation": "Phosphorylation",
    "catalysis":      "Catalysis",
    "translocation":  "Translocation",
    "transport":      "Transport",
    "recruitment":    "Recruitment",
    "cleavage":       "Cleavage",
}
# Arrow primitive used to draw each glyph's sample (phosphorylation is special-
# cased to the 'P' badge so it is not just another filled-triangle arrow).
_GLYPH_SAMPLE_FN = {
    "activation":    arrows.activation_arrow,
    "inhibition":    arrows.inhibition_arrow,
    "binding":       arrows.binding_arrow,
    "catalysis":     arrows.catalysis_arrow,
    "translocation": arrows.translocation_arrow,
    "transport":     arrows.transport_arrow,
    "recruitment":   arrows.recruitment_arrow,
    "cleavage":      arrows.cleavage_arrow,
}

# Badge fallbacks mirror the phosphorylation badge in pathway_layout.
_BADGE_FILL = "#D32F2F"
_BADGE_TEXT = "#FFFFFF"

# Box geometry (px, in canvas units before raster scaling).
_PAD = 10.0
_ROW_H = 20.0
_SAMPLE_W = 34.0
_GAP = 8.0
_FONT = 11.0
_TITLE = "Key"
_TITLE_FONT = 12.0
_TITLE_H = 18.0


def legend_glyph_keys_for_figure(figure: Figure) -> list[str]:
    """Return the ordered, deduplicated glyph keys a figure uses.

    Driven by relation types, plus the phosphorylation badge for any kinase
    entity flagged ``phosphorylated`` in its style (the badge can appear on an
    entity even without a PHOSPHORYLATES relation). Empty when nothing maps.
    """
    present: set[str] = set()
    for r in figure.relations:
        key = _RELATION_GLYPH_KEY.get(r.type)
        if key is not None:
            present.add(key)
    for e in figure.entities:
        if (e.style or {}).get("phosphorylated"):
            present.add("phosphorylation")
    return [k for k in _GLYPH_ORDER if k in present]


def _estimate_text_w(text: str, font_size: float) -> float:
    """Rough monospace-ish width estimate (matches the 0.6 factor used elsewhere)."""
    return max(1, len(text)) * font_size * 0.6


def legend_box_size(keys: list[str]) -> tuple[float, float]:
    """(width, height) of the legend box for the given glyph keys."""
    if not keys:
        return (0.0, 0.0)
    max_text = max(
        [_estimate_text_w(_GLYPH_CAPTION[k], _FONT) for k in keys]
        + [_estimate_text_w(_TITLE, _TITLE_FONT)]
    )
    box_w = _PAD * 2 + _SAMPLE_W + _GAP + max_text
    box_h = _PAD * 2 + _TITLE_H + _ROW_H * len(keys)
    return (box_w, box_h)


def _badge_sample(cx: float, cy: float, style_dict: dict) -> svgwrite.container.Group:
    g = svgwrite.container.Group()
    r = 7.0
    fill = style_dict.get("kinase_badge_fill", _BADGE_FILL)
    text_color = style_dict.get("kinase_badge_text_color", _BADGE_TEXT)
    circ = svgwrite.shapes.Circle(center=(cx, cy), r=r, fill=fill, stroke="none")
    g.add(circ)
    t = svgwrite.text.Text(
        "P", insert=(cx, cy),
        text_anchor="middle", fill=text_color,
    )
    t["dominant-baseline"] = "central"
    t["font-size"] = 9.0
    t["font-weight"] = "bold"
    t["font-family"] = style_dict.get("label_font_family", "Arial, sans-serif")
    g.add(t)
    return g


def _sample_glyph(
    key: str, x0: float, x1: float, cy: float, sample_style: dict
) -> svgwrite.container.Group:
    if key == "phosphorylation":
        return _badge_sample((x0 + x1) / 2, cy, sample_style)
    fn = _GLYPH_SAMPLE_FN[key]
    return fn((x0, cy), (x1, cy), style_dict=sample_style)


def legend(
    keys: list[str],
    top_right: tuple[float, float],
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """Render the legend box with its top-right corner at ``top_right``.

    ``keys`` is the output of :func:`legend_glyph_keys_for_figure`. Each row is a
    compact glyph sample plus its caption. The box is filled semi-opaque white so
    it stays readable even when floated over figure content.
    """
    s = {**arrows.DEFAULT_STYLE, **(style_dict or {})}
    # Compact, high-contrast sample glyphs.
    sample_style = {
        **(style_dict or {}),
        "arrow_head_size": 8.0,
        "t_bar_width": 11.0,
        "stroke_width": 1.5,
        "catalysis_circle_radius": 4.0,
        "recruit_dot_radius": 3.0,
    }
    font_family = s.get("label_font_family", "Arial, sans-serif")
    text_color = s.get("label_font_color", "#1A1A1A")

    box_w, box_h = legend_box_size(keys)
    rx_right, ry_top = top_right
    x0 = rx_right - box_w
    y0 = ry_top

    g = svgwrite.container.Group()
    box = svgwrite.shapes.Rect(
        insert=(x0, y0), size=(box_w, box_h),
        rx=6, ry=6, fill="#FFFFFF", stroke="#9AA0A6",
    )
    box["stroke-width"] = 1.0
    box["fill-opacity"] = 0.92
    g.add(box)

    title = svgwrite.text.Text(
        _TITLE, insert=(x0 + _PAD, y0 + _PAD + _TITLE_FONT * 0.8),
        fill=text_color,
    )
    title["font-size"] = _TITLE_FONT
    title["font-weight"] = "bold"
    title["font-family"] = font_family
    g.add(title)

    sample_x0 = x0 + _PAD
    sample_x1 = x0 + _PAD + _SAMPLE_W
    text_x = sample_x1 + _GAP
    for i, key in enumerate(keys):
        row_top = y0 + _PAD + _TITLE_H + i * _ROW_H
        cy = row_top + _ROW_H / 2
        g.add(_sample_glyph(key, sample_x0, sample_x1, cy, sample_style))
        cap = svgwrite.text.Text(
            _GLYPH_CAPTION[key], insert=(text_x, cy), fill=text_color,
        )
        cap["dominant-baseline"] = "central"
        cap["font-size"] = _FONT
        cap["font-family"] = font_family
        g.add(cap)

    return g
