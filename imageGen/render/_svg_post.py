"""Post-write SVG passes + figure-title chrome.

Internals of :mod:`imageGen.render.compositor` (R5 split). Holds the helpers that
operate on the *written* SVG file (autocrop, frame-to-content expansion, page
background paint, frame-box parsing) and the figure-title heading construction
(`_figure_title_group`, `_title_entry`). These are the "finishing" passes the
orchestrator runs after `_write_svg`; they import nothing from the compositor, so
the dependency is one-directional (`compositor` → `_svg_post`).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import svgwrite

from imageGen.ir.schema import Archetype, Figure
from imageGen.layout.types import LayoutEntry

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Page background painted behind every figure (Issue: figures shipped with a
# transparent canvas that composites to pure black in many viewers — the
# "void" on figs 05/07/09). White is the publication page colour; a preset can
# override it via a ``page_bg_fill`` style key.
_PAGE_BG_DEFAULT = "#FFFFFF"

# Figure-title heading (rendered above the figure for the archetypes that
# otherwise ship headless). Defaults are overridable via the ``figure_title_*``
# style keys; size falls back a few px above the body label size.
_TITLE_SIZE_DEFAULT = 14.0
_TITLE_GAP = 10.0  # px between the title baseline's descenders and content top

# Archetypes whose top-level figures render the spec title. Pathway / reaction /
# cellular figures are intentionally left out of this batch (see report).
_TITLED_ARCHETYPES = frozenset({Archetype.MECHANISM_CARTOON, Archetype.WORKFLOW})


def _autocrop_svg(svg_path: Path) -> None:
    """Trim the SVG viewport in-place to its content bbox + small margin (L22).

    Consumes the ``needs_crop`` signal from ``legibility_check``: when any
    canvas edge has more than 15% dead whitespace, the SVG's ``viewBox``
    and ``width``/``height`` are updated so the figure ships without dead
    margin. The original SVG file is overwritten; callers that want to
    preserve the original should copy it first.
    """
    from imageGen.render.crop import crop_box, _rewrite_svg_frame  # noqa: PLC0415
    from imageGen.verify.legibility_check import (  # noqa: PLC0415
        content_bounds,
        _needs_crop,
        DEFAULT_CROP_WHITESPACE_FRACTION,
    )
    content, canvas = content_bounds(svg_path)
    if not _needs_crop(content, canvas, DEFAULT_CROP_WHITESPACE_FRACTION):
        return
    box = crop_box(content, canvas, margin_frac=0.05)
    _rewrite_svg_frame(svg_path, box, set_size=True)


def _expand_svg_to_content(svg_path: Path) -> None:
    """Grow the SVG frame in-place to enclose content drawn past its edge (FR3).

    Measures the rendered content bounds (which include label text boxes), and
    if any label/annotation overflows the canvas, rewrites the ``viewBox`` and
    ``width``/``height`` so the figure ships without truncation. No-op when
    everything already fits — golden-image figures stay byte-identical.
    """
    from imageGen.render.crop import expand_box, _rewrite_svg_frame  # noqa: PLC0415
    from imageGen.verify.legibility_check import content_bounds  # noqa: PLC0415

    content, canvas = content_bounds(svg_path)
    box = expand_box(content, canvas)
    if box is not None:
        _rewrite_svg_frame(svg_path, box, set_size=True)


# Frame parsing for the background pass. Mirrors crop._SVG_OPEN but kept local
# so the compositor doesn't depend on crop's private regexes.
_SVG_OPEN_RE = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)
_VIEWBOX_RE = re.compile(r'viewBox="\s*([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s+([-\d.eE+]+)\s*"', re.IGNORECASE)
_WIDTH_RE = re.compile(r'\bwidth="\s*([-\d.eE+]+)\s*"', re.IGNORECASE)
_HEIGHT_RE = re.compile(r'\bheight="\s*([-\d.eE+]+)\s*"', re.IGNORECASE)


def _frame_box(svg_open_tag: str) -> tuple[float, float, float, float] | None:
    """Return the visible frame ``(x, y, w, h)`` of an ``<svg …>`` opening tag.

    Prefers the ``viewBox`` (set whenever expand/autocrop rewrote the frame);
    falls back to ``width``/``height`` at origin ``(0, 0)`` for the svgwrite
    default (no viewBox). Returns ``None`` when neither is parseable.
    """
    vb = _VIEWBOX_RE.search(svg_open_tag)
    if vb:
        return (float(vb.group(1)), float(vb.group(2)), float(vb.group(3)), float(vb.group(4)))
    w = _WIDTH_RE.search(svg_open_tag)
    h = _HEIGHT_RE.search(svg_open_tag)
    if w and h:
        return (0.0, 0.0, float(w.group(1)), float(h.group(1)))
    return None


def _paint_page_background(svg_path: Path, style_dict: dict[str, Any]) -> None:
    """Insert a full-frame background rect (page colour) behind all content.

    Figures otherwise ship with a transparent canvas that composites to pure
    black in many viewers (the "void" on figs 05/07/09). This paints an opaque
    page-colour rect covering the *finalized* frame so the output is
    deterministic regardless of the viewer's compositing.

    Runs after ``_expand_svg_to_content`` / ``_autocrop_svg`` so it always
    matches the shipped ``viewBox``. The rect is tagged
    ``data-role="background"`` so the crop / content-bounds passes (see
    ``legibility_check._walk``) never treat it as content — e.g. a later
    ``--crop`` still reframes onto real content. The fill is
    ``style_dict['page_bg_fill']`` when present, else white.
    """
    fill = (style_dict or {}).get("page_bg_fill", _PAGE_BG_DEFAULT)
    text = svg_path.read_text()
    m = _SVG_OPEN_RE.search(text)
    if m is None:
        return
    box = _frame_box(m.group(0))
    if box is None:
        return
    x, y, w, h = box
    rect = (
        f'<rect data-role="background" x="{x}" y="{y}" '
        f'width="{w}" height="{h}" fill="{fill}" />'
    )
    svg_path.write_text(text[: m.end()] + rect + text[m.end():])


def _figure_title_group(
    title: str,
    cx: float,
    baseline_y: float,
    *,
    font_size: float,
    font_family: str,
    color: str,
) -> svgwrite.container.Group:
    """A centered, bold ``<text>`` heading at ``(cx, baseline_y)``."""
    g = svgwrite.container.Group()
    t = svgwrite.text.Text(
        title, insert=(cx, baseline_y),
        font_family=font_family, font_size=font_size, fill=color,
    )
    t["text-anchor"] = "middle"
    t["font-weight"] = "bold"
    g.add(t)
    return g


def _title_entry(
    ir: Figure,
    canvas: tuple[float, float],
    style_dict: dict[str, Any],
) -> LayoutEntry | None:
    """Build the figure-title heading entry, or ``None`` when no title applies.

    Returns ``None`` for panel figures (they carry per-panel titles), for
    tiered figures (the TITLE tier owns titling — rendering ``Figure.title`` too
    would double up), for archetypes outside ``_TITLED_ARCHETYPES``, and when
    the spec has no title. The heading is centered on the canvas width and
    placed in negative-y headroom above the content; ``_expand_svg_to_content``
    grows the frame to include it and ``_paint_page_background`` (run after)
    covers it.
    """
    if ir.panels or ir.tiers or ir.archetype not in _TITLED_ARCHETYPES or not ir.title:
        return None
    cw, _ch = canvas
    fs = float(style_dict.get("figure_title_size", _TITLE_SIZE_DEFAULT))
    family = style_dict.get(
        "figure_title_family",
        style_dict.get("label_font_family", "Helvetica, Arial, sans-serif"),
    )
    color = style_dict.get(
        "figure_title_color", style_dict.get("label_font_color", "#1A1A1A")
    )
    # Baseline sits a gap above the content top (y=0); descenders (~0.2 em) clear
    # the gap, ascenders (~0.8 em) define how far the frame grows upward.
    baseline_y = -(_TITLE_GAP + fs * 0.2)
    return LayoutEntry(
        _figure_title_group,
        (ir.title, cw / 2.0, baseline_y),
        {"font_size": fs, "font_family": family, "color": color},
        position=(0.0, 0.0),
        ir_id="figure_title",
    )
