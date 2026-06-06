"""Legibility verification — Phase 6 Step 2.

Re-parses a rendered SVG and audits its text labels, then reports
whether the drawn content wastes enough canvas to warrant an
intelligent crop downstream.

Checks (fail-loud — the first failure raises ``LegibilityCheckError``):
  * font size — no ``<text>`` may render below ``min_font_size``.
  * overlap — no two label bounding boxes may overlap.

This mirrors the fail-loud precedent of ``SemanticCheckError`` /
``LabelPlacementError``. The label-placement engine already avoids
overlap *at placement time*, but the compositor stacks layers
independently — ``legibility_check`` is the after-the-fact audit.

Crop signal:
  Unlike ``semantic_check`` (which returns ``None``), a passing
  ``legibility_check`` returns a ``LegibilityResult`` whose
  ``needs_crop`` flag tells the next step (intelligent zoom/crop) that
  the content occupies only part of the canvas. ``content_bbox`` is the
  union of every drawable element's box — text plus geometry (``rect``,
  ``line``, ``polygon`` ...) and nested molecule ``<svg>`` viewports —
  so the crop can frame the subjects.

Bounding boxes:
  An SVG ``<text>`` carries no intrinsic box; it is re-derived with
  ``_estimate_text_bbox`` from ``layout/label_placement.py`` (the same
  heuristic the placement engine uses), anchor-corrected via the
  element's ``text-anchor`` / ``dominant-baseline``.

Limitations:
  Only ``translate(...)`` transforms are resolved; ``rotate`` / ``scale``
  / ``matrix`` are ignored — the current renderer emits only
  ``translate``. ``content_bbox`` treats a nested molecule ``<svg>`` as
  an opaque box (its placement viewport), not its path interior.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from imageGen.layout.label_placement import Bbox, _estimate_text_bbox, _overlaps

_Kind = Literal["overlap", "font_size"]

DEFAULT_MIN_FONT_SIZE = 6.0
DEFAULT_CROP_WHITESPACE_FRACTION = 0.15

_GEOMETRY_TAGS = frozenset({"rect", "circle", "ellipse", "line", "polygon", "polyline"})
_NUMBER = re.compile(r"-?\d*\.?\d+")
_TRANSLATE = re.compile(r"translate\(([^)]*)\)")


class LegibilityCheckError(RuntimeError):
    """Raised when a rendered figure has illegible text.

    Attributes:
        kind: ``"overlap"`` (two label boxes collide) or ``"font_size"``
            (a label is below the readable floor).
        labels: The offending label text(s) — two for an overlap, one
            for an undersized font.
        detail: Human-readable specifics (sizes or boxes).
    """

    def __init__(self, kind: _Kind, labels: tuple[str, ...], detail: str) -> None:
        self.kind = kind
        self.labels = labels
        self.detail = detail
        super().__init__(f"Illegible figure ({kind}): {detail}")


@dataclass(frozen=True)
class LegibilityResult:
    """Outcome of a passing legibility check.

    Attributes:
        needs_crop: True when drawn content leaves excess whitespace on
            some canvas edge — the signal for the downstream crop step.
        content_bbox: Union of every drawable element's box.
        canvas_bbox: ``(0, 0, svg_width, svg_height)``.
    """

    needs_crop: bool
    content_bbox: Bbox
    canvas_bbox: Bbox


def _tag(el: ET.Element) -> str:
    """Local tag name, stripped of the ``{namespace}`` prefix."""
    return el.tag.split("}")[-1]


def _f(value: str | None, default: float = 0.0) -> float:
    """Leading number of an SVG attribute (tolerates units like ``px``)."""
    if value is None:
        return default
    m = _NUMBER.match(value.strip())
    return float(m.group()) if m else default


def _canvas_box(root: ET.Element) -> Bbox:
    """Visible frame of the SVG as ``(x0, y0, x1, y1)``.

    Prefers ``viewBox`` (min-x, min-y, w, h) when present so a cropped figure
    is measured against its real frame. L22 autocrop trims by shifting the
    viewBox origin (not by translating content), so without this the crop
    signal would compare absolute content coords against ``(0, 0, w, h)`` and
    spuriously report dead margin on an already-tight figure. Falls back to
    ``width``/``height`` when there is no viewBox (the default render frame).
    """
    vb = root.get("viewBox")
    if vb:
        nums = [float(n) for n in _NUMBER.findall(vb)]
        if len(nums) == 4:
            minx, miny, w, h = nums
            return (minx, miny, minx + w, miny + h)
    return (0.0, 0.0, _f(root.get("width")), _f(root.get("height")))


def _parse_translate(transform: str | None) -> tuple[float, float]:
    """Extract ``(tx, ty)`` of a ``translate(...)``; ``(0, 0)`` otherwise."""
    if not transform:
        return (0.0, 0.0)
    m = _TRANSLATE.search(transform)
    if not m:
        return (0.0, 0.0)
    nums = _NUMBER.findall(m.group(1))
    if not nums:
        return (0.0, 0.0)
    tx = float(nums[0])
    ty = float(nums[1]) if len(nums) > 1 else 0.0
    return (tx, ty)


def _shift(box: Bbox, ox: float, oy: float) -> Bbox:
    """Translate a box by ``(ox, oy)``."""
    return (box[0] + ox, box[1] + oy, box[2] + ox, box[3] + oy)


def _label_box(el: ET.Element) -> tuple[str, float, Bbox, bool]:
    """Return ``(text, font_size, bbox, intentional_overlap)`` for a ``<text>``.

    The box is in the element's local frame; callers apply translate offsets.
    ``intentional_overlap`` is True when the element carries
    ``data-overlap="true"`` — a deliberate last-resort placement from the
    label engine's fallback ladder, which the overlap audit must not treat
    as a defect.
    """
    text = (el.text or "").strip()
    font_size = _f(el.get("font-size"))
    x = _f(el.get("x"))
    y = _f(el.get("y"))
    w, h = _estimate_text_bbox(text, font_size)
    anchor = el.get("text-anchor", "start")
    if anchor == "middle":
        x0 = x - w / 2
    elif anchor == "end":
        x0 = x - w
    else:
        x0 = x
    if el.get("dominant-baseline", "") in ("central", "middle"):
        y0 = y - h / 2
    else:
        y0 = y - h * 0.8  # `y` is the text baseline; box extends mostly above
    intentional_overlap = el.get("data-overlap") == "true"
    return text, font_size, (x0, y0, x0 + w, y0 + h), intentional_overlap


def _geometry_box(el: ET.Element) -> Bbox | None:
    """Bounding box of a basic shape element in its local frame.

    Callers apply translate offsets; this returns un-shifted coordinates.
    """
    tag = _tag(el)
    if tag == "rect":
        x, y = _f(el.get("x")), _f(el.get("y"))
        return (x, y, x + _f(el.get("width")), y + _f(el.get("height")))
    if tag == "line":
        x1, x2 = _f(el.get("x1")), _f(el.get("x2"))
        y1, y2 = _f(el.get("y1")), _f(el.get("y2"))
        return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
    if tag == "circle":
        cx, cy, r = _f(el.get("cx")), _f(el.get("cy")), _f(el.get("r"))
        return (cx - r, cy - r, cx + r, cy + r)
    if tag == "ellipse":
        cx, cy = _f(el.get("cx")), _f(el.get("cy"))
        rx, ry = _f(el.get("rx")), _f(el.get("ry"))
        return (cx - rx, cy - ry, cx + rx, cy + ry)
    if tag in ("polygon", "polyline"):
        nums = [float(n) for n in _NUMBER.findall(el.get("points", ""))]
        if len(nums) < 2:
            return None
        xs, ys = nums[0::2], nums[1::2]
        return (min(xs), min(ys), max(xs), max(ys))
    return None


def _walk(
    el: ET.Element,
    ox: float,
    oy: float,
    labels: list[tuple[str, float, Bbox, bool]],
    boxes: list[Bbox],
) -> None:
    """Collect label tuples and drawable boxes, resolving translate offsets.

    Each label tuple is ``(text, font_size, bbox, intentional_overlap)``.
    A nested ``<svg>`` is treated as an opaque box (its placement
    viewport) and not descended into — its interior is a separate
    coordinate frame. ``<defs>`` is skipped: it holds reusable
    definitions that are not themselves drawn.
    """
    for child in el:
        ctag = _tag(child)
        if ctag == "defs":
            continue
        # Skip decorative compartment bands entirely — both their full-width
        # background rect and their corner label are chrome, not figure
        # content. Including them would make `content_bbox` span the whole
        # canvas and defeat whitespace/crop detection.
        if child.get("data-role") == "band":
            continue
        tx, ty = _parse_translate(child.get("transform"))
        cx, cy = ox + tx, oy + ty
        if ctag == "svg":
            x, y = _f(child.get("x")), _f(child.get("y"))
            w, h = _f(child.get("width")), _f(child.get("height"))
            boxes.append(_shift((x, y, x + w, y + h), cx, cy))
            continue
        if ctag == "text":
            text, font_size, box, intentional = _label_box(child)
            if text:
                box = _shift(box, cx, cy)
                labels.append((text, font_size, box, intentional))
                boxes.append(box)
        elif ctag in _GEOMETRY_TAGS:
            box = _geometry_box(child)
            if box is not None:
                boxes.append(_shift(box, cx, cy))
        _walk(child, cx, cy, labels, boxes)


def _union(boxes: list[Bbox]) -> Bbox:
    """Smallest box enclosing every box in ``boxes`` (which must be non-empty)."""
    return (
        min(b[0] for b in boxes),
        min(b[1] for b in boxes),
        max(b[2] for b in boxes),
        max(b[3] for b in boxes),
    )


def content_bounds(svg_path: str | Path) -> tuple[Bbox, Bbox]:
    """Return ``(content_bbox, canvas_bbox)`` for a rendered SVG.

    ``content_bbox`` is the union of every drawable element's box **excluding
    decorative compartment bands** (``data-role="band"``). ``canvas_bbox`` is
    the visible frame: the ``viewBox`` when present, else ``(0, 0, width,
    height)``. When the figure has no drawable content (only chrome),
    ``content_bbox`` falls back to ``canvas_bbox``.

    This is the shared primitive behind both the legibility crop signal and
    the renderer's ``--crop`` feature, so the two always agree on where the
    figure actually is.
    """
    root = ET.parse(str(svg_path)).getroot()
    labels: list[tuple[str, float, Bbox, bool]] = []
    boxes: list[Bbox] = []
    _walk(root, 0.0, 0.0, labels, boxes)
    canvas = _canvas_box(root)
    content = _union(boxes) if boxes else canvas
    return content, canvas


def _needs_crop(content: Bbox, canvas: Bbox, fraction: float) -> bool:
    """True when any canvas edge has whitespace beyond ``fraction`` of its span."""
    cw = canvas[2] - canvas[0]
    ch = canvas[3] - canvas[1]
    if cw <= 0 or ch <= 0:
        return False
    return (
        content[0] - canvas[0] > fraction * cw
        or canvas[2] - content[2] > fraction * cw
        or content[1] - canvas[1] > fraction * ch
        or canvas[3] - content[3] > fraction * ch
    )


def legibility_check(
    svg_path: str | Path,
    *,
    min_font_size: float = DEFAULT_MIN_FONT_SIZE,
    overlap_margin: float = 0.0,
    crop_whitespace_fraction: float = DEFAULT_CROP_WHITESPACE_FRACTION,
    off_canvas_margin: float = 1.0,
) -> LegibilityResult:
    """Audit a rendered SVG's text legibility and report a crop signal.

    Args:
        svg_path: Path to an SVG produced by ``render_figure``.
        min_font_size: Readable floor in user units; smaller labels raise.
        overlap_margin: Slack passed to ``_overlaps``; 0 flags any touch.
        crop_whitespace_fraction: An edge with more than this fraction of
            the canvas as whitespace sets ``needs_crop``.
        off_canvas_margin: Slack (user units) a label box may exceed the
            canvas before it is flagged. FR6: catches text truncated past the
            frame edge (the FR3 symptom) — after frame-expansion every label
            should sit inside the viewport, so any overflow is a regression.

    Returns:
        LegibilityResult: When every label is legible.

    Raises:
        LegibilityCheckError: On the first undersized font, label overlap, or
            label drawn past the canvas edge.
    """
    root = ET.parse(str(svg_path)).getroot()
    labels: list[tuple[str, float, Bbox, bool]] = []
    boxes: list[Bbox] = []
    _walk(root, 0.0, 0.0, labels, boxes)
    canvas = _canvas_box(root)

    for text, font_size, box, _intentional in labels:
        if font_size < min_font_size:
            raise LegibilityCheckError(
                "font_size",
                (text,),
                f"label {text!r} font-size {font_size} below minimum {min_font_size}",
            )
        if (
            box[0] < canvas[0] - off_canvas_margin
            or box[1] < canvas[1] - off_canvas_margin
            or box[2] > canvas[2] + off_canvas_margin
            or box[3] > canvas[3] + off_canvas_margin
        ):
            raise LegibilityCheckError(
                "off_canvas",
                (text,),
                f"label {text!r} box {tuple(round(v, 1) for v in box)} extends "
                f"past the canvas {tuple(round(v, 1) for v in canvas)}",
            )

    for i in range(len(labels)):
        for j in range(i + 1, len(labels)):
            # A label flagged data-overlap="true" is a deliberate last-resort
            # placement from the fallback ladder — its collisions are expected,
            # not defects, so don't raise on any pair involving one.
            if labels[i][3] or labels[j][3]:
                continue
            if _overlaps(labels[i][2], labels[j][2], overlap_margin):
                raise LegibilityCheckError(
                    "overlap",
                    (labels[i][0], labels[j][0]),
                    f"labels {labels[i][0]!r} {labels[i][2]} and "
                    f"{labels[j][0]!r} {labels[j][2]} overlap",
                )

    content = _union(boxes) if boxes else canvas
    return LegibilityResult(
        needs_crop=_needs_crop(content, canvas, crop_whitespace_fraction),
        content_bbox=content,
        canvas_bbox=canvas,
    )
