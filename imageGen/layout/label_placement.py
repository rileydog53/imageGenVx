"""Greedy automated label placement.

Phase 3 Step 4. A pure, IR-agnostic post-pass: callers hand a list of
positioned `LayoutEntry` items (from any layout engine) plus a list of
`LabelRequest` records, and the engine returns the original entries with
new label `LayoutEntry` items appended in placement order. The Phase 5
renderer composes both lists by simply executing them.

Decoupling:
  Layout engines (`pathway_layout`, `panel_layout`, …) do not auto-invoke
  this module. Each engine that wants to render labels exposes a sibling
  helper that walks its IR shape and emits `LabelRequest` records;
  see `pathway_layout.pathway_label_requests` for the canonical example.
  This keeps the placement engine generic — it never imports IR types.

Algorithm:
  Greedy. For each request in submission order, evaluate candidate
  positions in the request's `priority` tuple ("right", "below",
  "above", "left", "center"). Pick the first candidate whose label bbox
  doesn't overlap any *known-bbox* entry from the input list, nor any
  previously placed label. If every candidate overlaps, accumulate into
  a failure list and raise `LabelPlacementError` at the end so partial
  work is visible.

  Force-directed placement is a v2 stretch — flagged in the SKILL plan.

Bbox sources:
  - Entity entries: looked up via `ENTITY_BBOX` from `layout._geom`
    (a small per-`EntityType` table shared with `pathway_layout`).
  - Compartment bands and panel chrome: treated as no-bbox. These
    primitives are full-width decorative backgrounds, not obstructions —
    labels are expected to render on top of them. Including them would
    block every candidate position because they span the entire canvas.
  - Other primitives (arrows, label primitives, etc.): also no-bbox.
    Arrows are thin shafts; allowing label-on-shaft overlap in v1 keeps
    the engine simple. Phase 6 `legibility_check` will surface any
    visible problem.

  Label bboxes are estimated from text length × font size with a fixed
  width-to-height aspect (no font-metric library at this stage; svgwrite
  has no measurement API). The estimator is monotonic in both inputs and
  has an explicit unit test.

Phase 4 / 5 coupling:
  - `LABEL_DEFAULT_PARAMS` keys use the `label_*` prefix so the master
    preset can union them alongside primitive `DEFAULT_STYLE` dicts
    without collision (matches the convention in `pathway_layout`,
    `panel_layout`, etc.).
  - Label `LayoutEntry` items use `position=(0.0, 0.0)`; the absolute
    SVG coordinates are baked into the args, mirroring how
    `pathway_layout` emits its entity entries. The renderer's
    `translate(position)` is a no-op for these.
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

import svgwrite.container

from imageGen.layout._geom import ENTITY_BBOX, ENTITY_TO_PRIMITIVE, PRIMITIVE_REGISTRY
from imageGen.layout.types import LayoutEntry
from imageGen.primitives import proteins
from imageGen.primitives._text import centered_label as _centered_label


# Relax-and-retry knobs for the v2 placement fallback ladder. A label that
# can't be placed at full size first shrinks one step, then tries small
# anchor nudges, and only then (in lenient mode) lands with an overlap flag.
_FONT_SHRINK_FACTOR = 0.85          # one 15%-smaller retry step (stays ≥ 6pt floor)
_ANCHOR_NUDGES: tuple[tuple[float, float], ...] = (
    (8.0, 0.0), (-8.0, 0.0), (0.0, 8.0), (0.0, -8.0),
)
# Larger corridor nudges tried *after* _ANCHOR_NUDGES — handles short arrows
# beside wide nodes where all nearby slots collide with the node label (L24).
# Offsets are ±24 and ±40 px in both axes, covering perpendicular positions
# both above/below a horizontal arrow and left/right of a vertical one.
_LARGE_NUDGES: tuple[tuple[float, float], ...] = (
    (0.0, -24.0), (0.0, 24.0), (-24.0, 0.0), (24.0, 0.0),
    (0.0, -40.0), (0.0, 40.0), (-40.0, 0.0), (40.0, 0.0),
)


# ---------------------------------------------------------------------------
# Layout knobs (flat namespaced keys; Phase 4 master preset will union these
# alongside primitive DEFAULT_STYLE dicts).
# ---------------------------------------------------------------------------

LABEL_DEFAULT_PARAMS: dict[str, Any] = {
    "label_anchor_gap":        4.0,   # px between anchor bbox and label bbox
    "label_collision_margin":  1.0,   # px slack when testing overlap
}


_VALID_PRIORITIES: tuple[str, ...] = ("right", "below", "above", "left", "center")


# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class LabelRequest:
    """One label to place near an anchor.

    Attributes:
        text: The label string.
        anchor: (x, y) center the label should sit near (e.g., the
            midpoint of a relation arrow, or the center of an entity).
        anchor_size: (w, h) bbox of the anchor itself; the label is
            offset by half this plus `label_anchor_gap` along the chosen
            direction so it doesn't sit on top of the anchor.
        priority: Ordered tuple of candidate-position names tried in
            sequence. Each must be in
            {"right", "below", "above", "left", "center"}.
        ir_id: Raw IR id of the entity/relation this label belongs to.
            The compositor uses this to set `data-ir-id="label_{ir_id}"`
            on the emitted SVG element (D1). None for engine-internal labels.
    """
    text: str
    anchor: tuple[float, float]
    anchor_size: tuple[float, float]
    priority: tuple[str, ...] = _VALID_PRIORITIES
    ir_id: str | None = None

    def __post_init__(self) -> None:
        unknown = [p for p in self.priority if p not in _VALID_PRIORITIES]
        if unknown:
            raise ValueError(
                f"LabelRequest.priority contains unknown name(s) {unknown!r}; "
                f"allowed values: {list(_VALID_PRIORITIES)}"
            )


class LabelPlacementError(RuntimeError):
    """Raised when one or more LabelRequests cannot be placed without overlap.

    The `failures` attribute is a list of the LabelRequest items that
    could not be placed at any priority. Successful placements before
    the failure are still returned in `entries` for inspection.
    """

    def __init__(
        self,
        failures: list[LabelRequest],
        entries: list[LayoutEntry],
    ) -> None:
        self.failures = failures
        self.entries = entries
        texts = ", ".join(repr(f.text) for f in failures)
        super().__init__(
            f"Could not place {len(failures)} label(s) without overlap: {texts}"
        )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

# (label, x, y, w, h) → axis-aligned bbox (x0, y0, x1, y1)
Bbox = tuple[float, float, float, float]


def _estimate_text_bbox(text: str, font_size: float) -> tuple[float, float]:
    """Estimate (width, height) for `text` at `font_size`.

    Uses font_size * char_count * 0.6 for width, font_size * 1.2 for
    height. Sans-serif characters average ~0.6 em wide; line-height is
    conventionally ~1.2x font size. Good enough for collision checks at
    v1 — Phase 6 `legibility_check` validates final output independently.
    """
    return (max(1, len(text)) * font_size * 0.6, font_size * 1.2)


def _candidate_center(
    name: str,
    anchor: tuple[float, float],
    anchor_size: tuple[float, float],
    label_size: tuple[float, float],
    gap: float,
) -> tuple[float, float]:
    """Compute the (x, y) center of a candidate label bbox by direction name."""
    ax, ay = anchor
    aw, ah = anchor_size
    lw, lh = label_size
    if name == "right":
        return (ax + aw / 2 + gap + lw / 2, ay)
    if name == "left":
        return (ax - aw / 2 - gap - lw / 2, ay)
    if name == "above":
        return (ax, ay - ah / 2 - gap - lh / 2)
    if name == "below":
        return (ax, ay + ah / 2 + gap + lh / 2)
    if name == "center":
        return (ax, ay)
    raise ValueError(f"unknown candidate name {name!r}")  # validated upstream


def _bbox_from_center(center: tuple[float, float], size: tuple[float, float]) -> Bbox:
    cx, cy = center
    w, h = size
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


def _overlaps(a: Bbox, b: Bbox, margin: float) -> bool:
    """Axis-aligned bbox overlap with a small `margin` of slack."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return (
        ax0 < bx1 + margin
        and ax1 + margin > bx0
        and ay0 < by1 + margin
        and ay1 + margin > by0
    )


# Derived from PRIMITIVE_REGISTRY so any primitive added to the registry
# (including L6 overrides) automatically participates in collision detection.
_ENTITY_PRIMITIVES: frozenset = frozenset(PRIMITIVE_REGISTRY.values())


# ---------------------------------------------------------------------------
# Bug 2 / shaft avoidance: relation labels must not render on an arrow shaft.
# Arrow shafts are thin, so v1 treated them as zero-footprint (module
# docstring). That let labels land directly on the line. We now reserve a thin
# corridor along each shaft by sampling small boxes ALONG the polyline — not a
# single bounding rectangle, which for a diagonal shaft would over-block the
# whole rectangle between the two endpoints (e.g. a hub fan-out) and starve
# legitimate corner slots.
# ---------------------------------------------------------------------------

_SHAFT_HALF_WIDTH = 5.0     # px — half-thickness of the no-label corridor
_SHAFT_SAMPLE_STEP = 14.0   # px — spacing of sample boxes along the shaft

# Memoised lazily to avoid the pathway_layout <-> label_placement import cycle.
_ARROW_PRIMITIVES: frozenset | None = None


def _arrow_primitive_set() -> frozenset:
    """The set of arrow primitive callables, looked up once and cached."""
    global _ARROW_PRIMITIVES
    if _ARROW_PRIMITIVES is None:
        from imageGen.layout.pathway_layout import (  # noqa: PLC0415
            RELATION_TO_ARROW,
        )
        _ARROW_PRIMITIVES = frozenset(RELATION_TO_ARROW.values())
    return _ARROW_PRIMITIVES


def _arrow_polyline(entry: LayoutEntry) -> list[tuple[float, float]] | None:
    """Return the shaft polyline for an arrow entry, else None.

    An arrow entry's args are ``(start, end)``; an elbow/arch route carries the
    full point list in ``kwargs['waypoints']`` (used when present so the
    corridor follows the rendered bend rather than the straight chord).
    """
    if entry.primitive not in _arrow_primitive_set():
        return None
    wps = entry.kwargs.get("waypoints")
    if wps:
        return [tuple(p) for p in wps]
    if len(entry.args) >= 2:
        return [tuple(entry.args[0]), tuple(entry.args[1])]
    return None


def _shaft_bboxes(entry: LayoutEntry) -> list[Bbox]:
    """Small collision boxes sampled along an arrow's shaft (empty for non-arrows)."""
    pts = _arrow_polyline(entry)
    if not pts or len(pts) < 2:
        return []
    hw = _SHAFT_HALF_WIDTH
    boxes: list[Bbox] = []
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        seg_len = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        n = max(1, int(seg_len // _SHAFT_SAMPLE_STEP))
        for i in range(n + 1):
            t = i / n
            cx = x0 + t * (x1 - x0)
            cy = y0 + t * (y1 - y0)
            boxes.append((cx - hw, cy - hw, cx + hw, cy + hw))
    return boxes


def _entry_bbox(entry: LayoutEntry) -> Bbox | None:
    """Best-effort bbox extraction for a positioned LayoutEntry.

    Only entity primitives contribute a collision bbox. Compartment
    bands and panel chrome span the full canvas / cell and are treated
    as decorative backgrounds (see module docstring). Arrows, labels,
    and any other unknown primitives return None.

    Exception (LT3): a phosphorylation arrow carries a 'P' badge whose text
    the legibility audit treats as a label; its footprint is reserved here so
    relation labels anchored at the same shaft midpoint avoid it.
    """
    if entry.primitive not in _ENTITY_PRIMITIVES:
        # Lazy import breaks the pathway_layout ↔ label_placement cycle.
        from imageGen.layout.pathway_layout import (  # noqa: PLC0415
            phospho_badge_occupied_bbox,
        )
        return phospho_badge_occupied_bbox(entry)
    # entity-primitive args: (label, (cx, cy), ...) per pathway_layout
    label, center = entry.args[:2]
    cx, cy = center
    # Reverse-lookup the bbox via the per-EntityType table. Multiple
    # EntityTypes can share a primitive — pick the largest bbox among
    # them so collision checks stay conservative.
    candidates = [
        ENTITY_BBOX[t]
        for t, p in ENTITY_TO_PRIMITIVE.items()
        if p is entry.primitive
    ]
    if not candidates:
        return None
    w = max(c[0] for c in candidates)
    h = max(c[1] for c in candidates)
    # An entity's centered label can be wider than its shape (e.g.
    # "CD8⁺ T cell" in a 60px box). Include the rendered label extent so a
    # neighbouring relation label doesn't clip the entity's own text — the
    # collision footprint is the union of shape and label.
    label_w, label_h = _estimate_text_bbox(
        str(label), float(_DEFAULT_LABEL_STYLE["label_font_size"])
    )
    # Receptor places its label LEFT of the body (text-anchor: end, 6 px gap).
    # Extend the collision bbox leftward only so arrows don't route through it.
    if entry.primitive is proteins.receptor:
        _RECEPTOR_LABEL_GAP = 6.0
        return (
            cx - w / 2 - _RECEPTOR_LABEL_GAP - label_w,
            cy - h / 2,
            cx + w / 2,
            cy + h / 2,
        )
    w = max(w, label_w)
    h = max(h, label_h)
    return (cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2)


_DEFAULT_LABEL_STYLE: dict = {
    "label_font_family": "Helvetica, Arial, sans-serif",
    "label_font_size": 11,
    "label_font_color": "#1A1A1A",
}


def _label_primitive(
    text: str,
    center: tuple[float, float],
    style_dict: dict | None = None,
    overlap: bool = False,
) -> svgwrite.container.Group:
    """Render a single label as a centered Text wrapped in a Group.

    Delegates the Text construction to `primitives._text.centered_label`,
    the shared label-text contract for this codebase, so Phase 4
    master-preset `label_*` keys flow through one helper.

    When `overlap=True`, the rendered `<text>` carries `data-overlap="true"`
    so `legibility_check` knows the collision was a deliberate last-resort
    placement (the fallback ladder exhausted all clear slots) and reports it
    as a warning rather than raising.
    """
    style = {**_DEFAULT_LABEL_STYLE, **(style_dict or {})}
    cx, cy = center
    g = svgwrite.container.Group()
    label_el = _centered_label(text, cx, cy, style)
    if overlap:
        # debug=False lets svgwrite emit the non-allowlisted data-* attr,
        # mirroring how the compositor tags groups with data-ir-id.
        label_el._parameter.debug = False
        label_el.attribs["data-overlap"] = "true"
    g.add(label_el)
    return g


def _first_fit(
    request: LabelRequest,
    label_size: tuple[float, float],
    anchor: tuple[float, float],
    occupied: list[Bbox],
    gap: float,
    margin: float,
    canvas: tuple[float, float] | None = None,
) -> tuple[tuple[float, float], Bbox] | None:
    """Return (center, bbox) of the first priority slot that clears `occupied`.

    None when every candidate in `request.priority` overlaps something.
    When `canvas` is provided, candidates whose bbox falls outside
    ``[0, canvas_w] × [0, canvas_h]`` are skipped before the overlap check
    so labels are never rendered clipped at the SVG viewport edge (L18).
    """
    for name in request.priority:
        center = _candidate_center(name, anchor, request.anchor_size, label_size, gap)
        candidate_bbox = _bbox_from_center(center, label_size)
        if canvas is not None:
            cw, ch = canvas
            x0, y0, x1, y1 = candidate_bbox
            if x0 < 0 or x1 > cw or y0 < 0 or y1 > ch:
                continue
        if not any(_overlaps(candidate_bbox, b, margin) for b in occupied):
            return center, candidate_bbox
    return None


def _place_with_fallback(
    request: LabelRequest,
    occupied: list[Bbox],
    gap: float,
    margin: float,
    font_size: float,
    canvas: tuple[float, float] | None = None,
) -> tuple[tuple[float, float], Bbox, float, bool]:
    """Run the relax-and-retry ladder for a single request.

    Returns `(center, bbox, font_used, overlap)`:
      1. full font, first-fit;
      2. shrunk font (`_FONT_SHRINK_FACTOR`), first-fit;
      3. shrunk font at each `_ANCHOR_NUDGES` offset, first-fit;
      4. give up — first-choice slot at full font, `overlap=True`.

    Steps 1-3 return `overlap=False`. Step 4 is the only path that returns
    `overlap=True`; the caller decides whether to emit it (lenient) or treat
    it as a failure (strict).
    """
    full = _estimate_text_bbox(request.text, font_size)
    hit = _first_fit(request, full, request.anchor, occupied, gap, margin, canvas)
    if hit is not None:
        return (*hit, font_size, False)

    small_font = font_size * _FONT_SHRINK_FACTOR
    small = _estimate_text_bbox(request.text, small_font)
    hit = _first_fit(request, small, request.anchor, occupied, gap, margin, canvas)
    if hit is not None:
        return (*hit, small_font, False)

    ax, ay = request.anchor
    for dx, dy in _ANCHOR_NUDGES:
        hit = _first_fit(request, small, (ax + dx, ay + dy), occupied, gap, margin, canvas)
        if hit is not None:
            return (*hit, small_font, False)

    # Step 3.5 (L24): wider corridor nudges for labels on short arrows beside
    # wide nodes — all nearby priority slots may already be inside the node
    # label bbox, so push the label further out perpendicular to the shaft.
    for dx, dy in _LARGE_NUDGES:
        hit = _first_fit(request, small, (ax + dx, ay + dy), occupied, gap, margin, canvas)
        if hit is not None:
            return (*hit, small_font, False)

    # Last resort: land at the first-choice slot even though it collides.
    center = _candidate_center(
        request.priority[0], request.anchor, request.anchor_size, full, gap
    )
    return center, _bbox_from_center(center, full), font_size, True


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def place_labels(
    entries: list[LayoutEntry],
    label_requests: list[LabelRequest],
    layout_params: dict | None = None,
    style_dict: dict | None = None,
    *,
    canvas: tuple[float, float] | None = None,
    strict_labels: bool = False,
) -> list[LayoutEntry]:
    """Place each LabelRequest near its anchor, relaxing on collision.

    For each request the engine runs a fallback ladder (`_place_with_fallback`):
    full-size first-fit → 15%-smaller font → small anchor nudges → last-resort
    overlapping placement. Earlier requests reserve space before later ones.

    Args:
        entries: Positioned LayoutEntry items from a layout engine.
            Returned unchanged at the head of the result.
        label_requests: Labels to place, in submission order.
        layout_params: Optional overlay onto `LABEL_DEFAULT_PARAMS`.
            Notable keys: `label_anchor_gap`, `label_collision_margin`.
        style_dict: Optional preset overlay forwarded to every emitted
            label primitive. Its `label_font_size` (if any) seeds the bbox
            estimator so the collision check matches what renders. When the
            ladder shrinks a label, that label's entry carries a per-label
            `style_dict` with the reduced size so the render stays in sync.
        canvas: Optional ``(width, height)`` of the SVG viewport. When
            provided, candidate positions whose text bbox would extend
            outside ``[0, width] × [0, height]`` are discarded before the
            collision check, preventing clipped labels at the canvas edge
            (L18). None means no bounds check (v1 behaviour).
        strict_labels: When True, restore the v1 fail-loud contract — any
            request that reaches the last-resort (overlapping) rung is
            collected and raised as `LabelPlacementError` instead of being
            emitted. The earlier ladder rungs (shrink, nudge) still run, so
            strict mode places more than v1 did before giving up. Default
            False: overlapping labels are emitted with `data-overlap="true"`
            and a `UserWarning` is issued.

    Returns:
        `entries` followed by one new LayoutEntry per placed label. Each
        label entry has `position=(0.0, 0.0)`; coordinates are baked into args.

    Raises:
        LabelPlacementError: Only when `strict_labels=True` and at least one
            request exhausted the ladder. Carries the failed requests and the
            partial entry list.
    """
    params = {**LABEL_DEFAULT_PARAMS, **(layout_params or {})}
    gap = float(params["label_anchor_gap"])
    margin = float(params["label_collision_margin"])
    font_size = float((style_dict or {}).get("label_font_size", 11))

    occupied: list[Bbox] = [
        bbox for bbox in (_entry_bbox(e) for e in entries) if bbox is not None
    ]
    # Bug 2: reserve a thin corridor along every arrow shaft so relation
    # labels are not placed directly on a line (arrows are otherwise
    # zero-footprint to the placement engine).
    for _e in entries:
        occupied.extend(_shaft_bboxes(_e))

    out: list[LayoutEntry] = list(entries)
    failures: list[LabelRequest] = []
    overflowed: list[LabelRequest] = []

    for request in label_requests:
        center, bbox, font_used, overlap = _place_with_fallback(
            request, occupied, gap, margin, font_size, canvas
        )
        if overlap and strict_labels:
            failures.append(request)
            continue

        # Per-label kwargs: forward the base style, override the font size
        # when the ladder shrank it, and flag a last-resort overlap.
        kwargs: dict = {}
        if font_used != font_size:
            kwargs["style_dict"] = {**(style_dict or {}), "label_font_size": font_used}
        elif style_dict is not None:
            kwargs["style_dict"] = style_dict
        if overlap:
            kwargs["overlap"] = True
            overflowed.append(request)

        label_ir_id = (
            f"label_{request.ir_id}" if request.ir_id is not None else None
        )
        out.append(LayoutEntry(
            primitive=_label_primitive,
            args=(request.text, center),
            kwargs=kwargs,
            position=(0.0, 0.0),
            ir_id=label_ir_id,
        ))
        occupied.append(bbox)

    if strict_labels and failures:
        raise LabelPlacementError(failures=failures, entries=out)
    if overflowed:
        texts = ", ".join(repr(r.text) for r in overflowed)
        warnings.warn(
            f"Placed {len(overflowed)} label(s) with overlap after exhausting "
            f"the placement ladder: {texts}. Pass strict_labels=True to fail "
            f"loud instead. To clear the crowding, re-render with a larger "
            f"canvas (--canvas WxH), split the figure across panels, reduce the "
            f"entity count, or drop labels (--no-labels).",
            stacklevel=2,
        )
    return out


def label_entry_bbox(entry: LayoutEntry) -> Bbox | None:
    """Return the estimated bbox of a placed-label ``LayoutEntry``, else None.

    Lets a later pass treat already-placed labels as obstacles — e.g. the P5.3
    annotation occupancy seed, which keeps a figure-level annotation off the
    scene-local labels the tier engine already placed. Recomputes the same
    estimate ``place_labels`` used (``_estimate_text_bbox`` centred on the
    placed point), so the obstacle matches what renders. Non-label entries
    (anything whose primitive is not :func:`_label_primitive`) return None.
    """
    if entry.primitive is not _label_primitive or len(entry.args) < 2:
        return None
    text, center = entry.args[0], entry.args[1]
    font_size = float(
        (entry.kwargs.get("style_dict") or {}).get("label_font_size", 11)
    )
    return _bbox_from_center(center, _estimate_text_bbox(str(text), font_size))
