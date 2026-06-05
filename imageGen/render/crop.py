"""Tight-crop a rendered figure onto its actual content.

A figure rendered on the default canvas can leave a lot of empty space around
the drawing (especially small pathways on the 800×600 floor). `apply_crop`
reframes the figure onto its content bounding box plus a comfortable margin
and writes a **sibling `*_cropped`** file, leaving the original render intact.

Two modes:

* **fit-content** (default): the crop rectangle is exactly the content box
  plus margin. Removes whitespace fully; the output image takes the content's
  own shape (a wide pathway becomes a wide, short image).
* **keep-aspect**: the rectangle is grown to the original canvas
  width:height ratio so every figure keeps a consistent shape. Note that
  because imageGen layouts usually fill one full dimension, this often crops
  little — it is the "uniform shape" option, not the "remove whitespace" one.

Mechanism (vector, lossless): the SVG's `viewBox` is set to the crop
rectangle. In fit-content mode the `width`/`height` are set to the box size
(a true 1:1 crop); in keep-aspect mode they stay at the canvas size so the
content scales up uniformly to fill the frame. PNG/PDF are re-exported from
the edited SVG.

Content bounds come from `legibility_check.content_bounds`, which excludes
decorative compartment bands (`data-role="band"`) so a full-canvas background
band doesn't defeat the crop.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from imageGen.render.export import svg_to_pdf, svg_to_png
from imageGen.verify.legibility_check import content_bounds

Bbox = tuple[float, float, float, float]

DEFAULT_CROP_MARGIN = 0.15  # "comfortable" — content + 15% on each side

_SVG_OPEN = re.compile(r"<svg\b[^>]*>", re.IGNORECASE)
_VIEWBOX_ATTR = re.compile(r'\s+viewBox="[^"]*"', re.IGNORECASE)
_WIDTH_ATTR = re.compile(r'\s+width="[^"]*"', re.IGNORECASE)
_HEIGHT_ATTR = re.compile(r'\s+height="[^"]*"', re.IGNORECASE)


def crop_box(
    content: Bbox,
    canvas: Bbox,
    margin_frac: float = DEFAULT_CROP_MARGIN,
    *,
    keep_aspect: bool = False,
) -> Bbox:
    """Compute the crop rectangle for `content` within `canvas`.

    Always pads the content box by `margin_frac` of its own size and clamps to
    the canvas. When `keep_aspect` is True, the padded box is additionally
    grown (centered, then shifted inside the canvas) so its width:height
    matches the canvas — yielding a uniform figure shape at the cost of
    cropping less.
    """
    cx0, cy0, cx1, cy1 = content
    cw = max(cx1 - cx0, 1.0)
    ch = max(cy1 - cy0, 1.0)

    mx, my = cw * margin_frac, ch * margin_frac
    x0, y0, x1, y1 = cx0 - mx, cy0 - my, cx1 + mx, cy1 + my

    canvas_w = canvas[2] - canvas[0]
    canvas_h = canvas[3] - canvas[1]

    if keep_aspect:
        bw, bh = x1 - x0, y1 - y0
        target = canvas_w / canvas_h if canvas_h else 1.0
        if bw / bh < target:
            new_bw = bh * target
            cx = (x0 + x1) / 2
            x0, x1 = cx - new_bw / 2, cx + new_bw / 2
        else:
            new_bh = bw / target
            cy = (y0 + y1) / 2
            y0, y1 = cy - new_bh / 2, cy + new_bh / 2

    # Clamp into the canvas. For a box that meets/exceeds a canvas dimension,
    # snap to the full extent; otherwise shift it inside (preserving size, so
    # keep-aspect ratios survive).
    bw, bh = x1 - x0, y1 - y0
    if bw >= canvas_w:
        x0, x1 = canvas[0], canvas[2]
    elif x0 < canvas[0]:
        x0, x1 = canvas[0], canvas[0] + bw
    elif x1 > canvas[2]:
        x0, x1 = canvas[2] - bw, canvas[2]
    if bh >= canvas_h:
        y0, y1 = canvas[1], canvas[3]
    elif y0 < canvas[1]:
        y0, y1 = canvas[1], canvas[1] + bh
    elif y1 > canvas[3]:
        y0, y1 = canvas[3] - bh, canvas[3]

    return (x0, y0, x1, y1)


def expand_box(
    content: Bbox,
    canvas: Bbox,
    *,
    margin: float = 6.0,
    epsilon: float = 0.5,
) -> Bbox | None:
    """Return a frame that grows `canvas` to enclose any `content` past its edge.

    FR3: external/relation labels (and annotations) can extend beyond the
    computed canvas, and both the SVG viewport and `crop_box` clamp *into* the
    canvas — so an off-canvas label is silently truncated at the frame edge.
    This grows the frame **outward only** on whichever sides content overflows,
    adding `margin` px of breathing room so the rescued label isn't flush
    against the new border. Sides without overflow keep the canvas exactly, so a
    figure whose content fits is unchanged.

    Returns the enlarged box, or `None` when no side overflows (no-op) — the
    caller can then skip rewriting the SVG and keep golden-identical output.
    """
    cx0, cy0, cx1, cy1 = content
    kx0, ky0, kx1, ky1 = canvas
    nx0 = cx0 - margin if cx0 < kx0 - epsilon else kx0
    ny0 = cy0 - margin if cy0 < ky0 - epsilon else ky0
    nx1 = cx1 + margin if cx1 > kx1 + epsilon else kx1
    ny1 = cy1 + margin if cy1 > ky1 + epsilon else ky1
    if (nx0, ny0, nx1, ny1) == (kx0, ky0, kx1, ky1):
        return None
    return (nx0, ny0, nx1, ny1)


def _rewrite_svg_frame(svg_path: Path, box: Bbox, *, set_size: bool) -> None:
    """Set the SVG's `viewBox` to `box`; optionally also set width/height to it.

    Edits the opening `<svg ...>` tag textually (not via ElementTree) to avoid
    re-serializing namespaces/attribute order that the verifiers and golden
    tests parse. `set_size=True` (fit-content) makes a true 1:1 crop;
    `set_size=False` (keep-aspect) leaves width/height so content scales up.
    """
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    text = svg_path.read_text()
    m = _SVG_OPEN.search(text)
    if m is None:
        raise ValueError(f"No <svg> tag found in {svg_path}")
    tag = _VIEWBOX_ATTR.sub("", m.group(0))
    if set_size:
        tag = _WIDTH_ATTR.sub("", tag, count=1)
        tag = _HEIGHT_ATTR.sub("", tag, count=1)
        tag = tag[:-1] + f' width="{w}" height="{h}"'
    else:
        tag = tag[:-1]
    tag += f' viewBox="{x0} {y0} {w} {h}">'
    svg_path.write_text(text[: m.start()] + tag + text[m.end():])


def cropped_path(path: Path) -> Path:
    """`figure.png` → `figure_cropped.png` (sibling, same suffix)."""
    return path.with_name(f"{path.stem}_cropped{path.suffix}")


def apply_crop(
    svg_path: Path,
    output_path: Path,
    fmt: str,
    *,
    margin_frac: float = DEFAULT_CROP_MARGIN,
    keep_aspect: bool = False,
    dpi: int = 300,
) -> tuple[Path, Bbox]:
    """Write a cropped sibling of the rendered figure; leave the original alone.

    Reads content bounds from `svg_path`, computes the crop box, copies the
    SVG to a `*_cropped.svg` sibling, reframes the copy, and exports the
    cropped PNG/PDF (or, for SVG output, the reframed copy is the deliverable).
    Returns `(cropped_output_path, crop_box)`.
    """
    content, canvas = content_bounds(svg_path)
    box = crop_box(content, canvas, margin_frac, keep_aspect=keep_aspect)

    cropped_svg = cropped_path(svg_path)
    shutil.copyfile(svg_path, cropped_svg)
    _rewrite_svg_frame(cropped_svg, box, set_size=not keep_aspect)

    out = cropped_path(output_path)
    if fmt == "png":
        svg_to_png(cropped_svg, out, dpi=dpi)
    elif fmt == "pdf":
        svg_to_pdf(cropped_svg, out, dpi=dpi)
    # for fmt == "svg", cropped_svg == out already (same path)
    return out, box
