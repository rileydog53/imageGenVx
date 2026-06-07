"""Unified info box: legend + abbreviations + credits in one bordered box.

Consolidates what used to be two separate elements — the relation/glyph
**legend** (a top-right corner overlay, ``render/legend.py``) and the
abbreviation **glossary** (a strip below the figure, ``render/glossary.py``) —
plus a new icon **credits** section, into a *single* box for ease of reading.

The box is drawn in a strip **below** the figure (the compositor grows the
canvas downward and anchors it top-left), so it never floats over figure
content. Each section is omitted when its content is empty; an all-empty box is
never emitted (the compositor checks before adding it).

Row/sample appearance is reused from ``legend`` (``_sample_glyph`` + glyph
captions) and ``glossary`` (``glossary_row``) so there is a single source of
truth for how each row looks. Emitted as a normal ``LayoutEntry`` (``id``/
``data-ir-id`` ``"info_box"``); the legend and abbreviations sub-groups keep
``data-ir-id="legend"`` / ``"glossary"`` so existing checks still find them.
"""
from __future__ import annotations

import svgwrite.container
import svgwrite.shapes
import svgwrite.text

from imageGen.primitives import arrows
from imageGen.render import glossary as _glossary
from imageGen.render import legend as _legend
from imageGen.render._measure import estimate_text_w as _estimate_text_w

# Box geometry (px, canvas units before raster scaling). Reuses legend's sample
# geometry so legend rows look identical to the standalone legend.
_PAD = 10.0
_SECTION_GAP = 8.0
_SUBTITLE_FONT = 12.0
_SUBTITLE_H = 18.0

_LEGEND_ROW_H = _legend._ROW_H        # 20
_LEGEND_SAMPLE_W = _legend._SAMPLE_W  # 34
_LEGEND_GAP = _legend._GAP            # 8
_ABBR_ROW_H = _glossary._ROW_H        # 18
_ABBR_FONT = _glossary._FONT          # 11
_CREDIT_ROW_H = 14.0
_CREDIT_FONT = 9.0
_BODY_FONT = 11.0

_LEGEND_TITLE = "Key"
_ABBR_TITLE = "Abbreviations"
_CREDIT_TITLE = "Credits"


def _section_specs(legend_keys, glossary_entries, credit_lines):
    """Yield (kind, title, rows, row_h) for each non-empty section, in order."""
    specs = []
    if legend_keys:
        specs.append(("legend", _LEGEND_TITLE, list(legend_keys), _LEGEND_ROW_H))
    if glossary_entries:
        specs.append(("glossary", _ABBR_TITLE, list(glossary_entries), _ABBR_ROW_H))
    if credit_lines:
        specs.append(("credits", _CREDIT_TITLE, list(credit_lines), _CREDIT_ROW_H))
    return specs


def _section_content_w(kind, title, rows) -> float:
    """Inner content width (px) a section needs, including its subtitle."""
    w_title = _estimate_text_w(title, _SUBTITLE_FONT)
    if kind == "legend":
        w_rows = max(
            _estimate_text_w(_legend._GLYPH_CAPTION[k], _BODY_FONT) for k in rows
        )
        w_rows += _LEGEND_SAMPLE_W + _LEGEND_GAP
    elif kind == "glossary":
        w_rows = max(_estimate_text_w(_glossary._row_text(e), _ABBR_FONT) for e in rows)
    else:  # credits
        w_rows = max(_estimate_text_w(line, _CREDIT_FONT) for line in rows)
    return max(w_title, w_rows)


def info_box_size(
    legend_keys, glossary_entries, credit_lines, style_dict=None,
) -> tuple[float, float]:
    """(width, height) of the unified box; (0, 0) when every section is empty."""
    specs = _section_specs(legend_keys, glossary_entries, credit_lines)
    if not specs:
        return (0.0, 0.0)
    box_w = 2 * _PAD + max(_section_content_w(k, t, r) for k, t, r, _h in specs)
    body_h = sum(_SUBTITLE_H + len(r) * rh for _k, _t, r, rh in specs)
    box_h = 2 * _PAD + body_h + _SECTION_GAP * (len(specs) - 1)
    return (box_w, box_h)


def _tagged_group(data_ir_id: str) -> svgwrite.container.Group:
    """A sub-group carrying ``data-ir-id`` (debug off so the attr is allowed)."""
    g = svgwrite.container.Group()
    g._parameter.debug = False
    g.attribs["data-ir-id"] = data_ir_id
    return g


def info_box(
    top_left: tuple[float, float],
    *,
    legend_keys=None,
    glossary_entries=None,
    credit_lines=None,
    style_dict=None,
) -> svgwrite.container.Group:
    """Render the unified info box with its top-left corner at ``top_left``.

    Sections (Key / Abbreviations / Credits) stack top-to-bottom; empty ones are
    skipped. Sized by :func:`info_box_size`.
    """
    legend_keys = list(legend_keys or [])
    glossary_entries = list(glossary_entries or [])
    credit_lines = list(credit_lines or [])
    specs = _section_specs(legend_keys, glossary_entries, credit_lines)

    s = {**arrows.DEFAULT_STYLE, **(style_dict or {})}
    font_family = s.get("label_font_family", "Arial, sans-serif")
    text_color = s.get("label_font_color", "#1A1A1A")
    # Compact, high-contrast sample glyphs (mirror legend()).
    sample_style = {
        **(style_dict or {}),
        "arrow_head_size": 8.0, "t_bar_width": 11.0, "stroke_width": 1.5,
        "catalysis_circle_radius": 4.0, "recruit_dot_radius": 3.0,
    }

    box_w, box_h = info_box_size(legend_keys, glossary_entries, credit_lines, s)
    x0, y0 = top_left

    g = svgwrite.container.Group()
    box = svgwrite.shapes.Rect(
        insert=(x0, y0), size=(box_w, box_h),
        rx=6, ry=6, fill="#FFFFFF", stroke="#9AA0A6",
    )
    box["stroke-width"] = 1.0
    box["fill-opacity"] = 0.92
    g.add(box)

    cursor_y = y0 + _PAD
    for kind, title, rows, row_h in specs:
        sub = _tagged_group(kind) if kind in ("legend", "glossary") else svgwrite.container.Group()
        # Section subtitle.
        st = svgwrite.text.Text(
            title, insert=(x0 + _PAD, cursor_y + _SUBTITLE_FONT * 0.8), fill=text_color,
        )
        st["font-size"] = _SUBTITLE_FONT
        st["font-weight"] = "bold"
        st["font-family"] = font_family
        sub.add(st)
        rows_top = cursor_y + _SUBTITLE_H

        if kind == "legend":
            sx0 = x0 + _PAD
            sx1 = x0 + _PAD + _LEGEND_SAMPLE_W
            text_x = sx1 + _LEGEND_GAP
            for i, key in enumerate(rows):
                cy = rows_top + i * row_h + row_h / 2
                sub.add(_legend._sample_glyph(key, sx0, sx1, cy, sample_style))
                cap = svgwrite.text.Text(
                    _legend._GLYPH_CAPTION[key], insert=(text_x, cy), fill=text_color,
                )
                cap["dominant-baseline"] = "central"
                cap["font-size"] = _BODY_FONT
                cap["font-family"] = font_family
                sub.add(cap)
        elif kind == "glossary":
            for i, entry in enumerate(rows):
                baseline = rows_top + i * row_h + _ABBR_FONT * 0.8
                sub.add(_glossary.glossary_row(
                    entry, x0 + _PAD, baseline, font_family, text_color))
        else:  # credits
            for i, line in enumerate(rows):
                baseline = rows_top + i * row_h + _CREDIT_FONT * 0.9
                t = svgwrite.text.Text(
                    line, insert=(x0 + _PAD, baseline), fill=text_color,
                )
                t["font-size"] = _CREDIT_FONT
                t["font-family"] = font_family
                sub.add(t)

        g.add(sub)
        cursor_y = rows_top + len(rows) * row_h + _SECTION_GAP

    return g
