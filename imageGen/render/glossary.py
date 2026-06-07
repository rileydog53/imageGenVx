"""Abbreviation glossary box (FR9): a bordered key expanding the acronyms a
figure uses.

A non-empty ``Figure.glossary`` draws this automatically. The compositor grows
the canvas by a strip **below** the figure and anchors the box there (top-left),
so the glossary never floats over figure content — unlike the relation auto-legend
(``render/legend.py``), which is a corner overlay. Each row reads as a bold term
followed by its definition; the box is filled semi-opaque white for safety.

Emitted as a normal ``LayoutEntry`` so it flows through the same ``_write_svg``
path as every other primitive and gets an ``id="glossary"`` tag (so
``semantic_check`` can confirm it drew — the FR1/FR6 pattern).
"""
from __future__ import annotations

import svgwrite.container
import svgwrite.shapes
import svgwrite.text

from imageGen.render._measure import estimate_text_w as _estimate_text_w

# Box geometry (px, canvas units before raster scaling). Mirrors legend.py.
_PAD = 10.0
_ROW_H = 18.0
_FONT = 11.0
_TITLE = "Abbreviations"
_TITLE_FONT = 12.0
_TITLE_H = 18.0
_TERM_GAP = 6.0   # px between a bold term and its definition
_SEP = " — "


def _row_text(entry) -> str:
    """The flat 'TERM — definition' string for one entry (width estimate / fallback)."""
    return f"{entry.term}{_SEP}{entry.definition}"


def glossary_box_size(entries: list, style_dict: dict | None = None) -> tuple[float, float]:
    """(width, height) of the glossary box for ``entries`` (0,0 when empty)."""
    if not entries:
        return (0.0, 0.0)
    max_text = max(
        [_estimate_text_w(_row_text(e), _FONT) for e in entries]
        + [_estimate_text_w(_TITLE, _TITLE_FONT)]
    )
    box_w = _PAD * 2 + max_text
    box_h = _PAD * 2 + _TITLE_H + _ROW_H * len(entries)
    return (box_w, box_h)


def glossary_box(
    entries: list,
    top_left: tuple[float, float],
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """Render the glossary box with its top-left corner at ``top_left``.

    ``entries`` is a list of ``GlossaryEntry`` (``.term`` / ``.definition``). Each
    row renders the term in bold then its definition; the box is sized by
    :func:`glossary_box_size`.
    """
    s = style_dict or {}
    font_family = s.get("label_font_family", "Arial, sans-serif")
    text_color = s.get("label_font_color", "#1A1A1A")

    box_w, box_h = glossary_box_size(entries, s)
    x0, y0 = top_left

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

    for i, entry in enumerate(entries):
        row_baseline = y0 + _PAD + _TITLE_H + i * _ROW_H + _FONT * 0.8
        t = svgwrite.text.Text("", insert=(x0 + _PAD, row_baseline), fill=text_color)
        t["font-size"] = _FONT
        t["font-family"] = font_family
        term = svgwrite.text.TSpan(entry.term, x=[x0 + _PAD])
        term["font-weight"] = "bold"
        t.add(term)
        t.add(svgwrite.text.TSpan(f"{_SEP}{entry.definition}"))
        g.add(t)

    return g
