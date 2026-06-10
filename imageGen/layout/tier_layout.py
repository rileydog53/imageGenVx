"""V3 scene-chassis layout engine — minimal vertical slice (Step 3).

Lowers a tiered ``Figure`` to a ``list[LayoutEntry]``, proving the
schema -> engine -> SVG path end to end through real engine code (not the
hand-assembled keystone slice).

Scope is deliberately a SLICE, not the finished chassis:
  - Tiers: a TITLE band (title + subtitle) and a SCENE_ROW of equal columns;
    SUMMARY_BAR / BAND render only their band background (no inner content yet).
  - Scenes: MOLECULE and TEXT slots, placed by a MINIMAL relative solver
    (roots centred, attach = parent-edge + offset). The full topological
    constraint solver and scene-local label collision are Step 5.
  - Edges: intra-scene ``SceneEdge`` (dashed / curved H-bond) and cross-cell
    ``TierEdge`` (transition arrow), resolved through the ``AnchorRegistry`` with
    endpoint standoff and optional rail clamping.
  - ``step_sequence`` and unsupported ``SlotKind``s raise ``NotImplementedError``
    (mirrors the compositor's unregistered-archetype guard) — they arrive in
    Steps 5/6 and the primitive refresh.

Coordinate model: every entry carries baked absolute coordinates. ``position``
is the slot's top-left for MOLECULE slots (the only entry whose primitive draws
at a local origin); it is ``(0, 0)`` for text, intra-scene edges, and transition
arrows, which bake their absolute points into the closure — the same pattern
``_write_svg`` already consumes. Anchors are published into a fresh per-call
``AnchorRegistry`` keyed ``"scene.slot.anchor"`` (atom anchors) and
``"scene.<frame>"`` (scene-edge anchors), the grammar the schema's reference
strings use.

Phase coupling: the compositor does not call this engine yet — Step 4 wires it
into ``render_figure`` (canvas sizing, band chrome, label placement, crop). For
now the engine is exercised directly (like the other layout engines in tests).
"""
from __future__ import annotations

import math
from typing import Any

import svgwrite.container
import svgwrite.path
import svgwrite.shapes
import svgwrite.text

from imageGen.ir.schema import (
    Figure,
    RailAxis,
    Scene,
    SceneEdge,
    SceneEdgeType,
    Slot,
    SlotKind,
    Tier,
    TierEdge,
    TierRole,
)
from imageGen.layout.anchors import AnchorRegistry
from imageGen.layout.types import LayoutEntry
from imageGen.primitives.chemistry import render_molecule_anchored


# ---------------------------------------------------------------------------
# Layout knobs (flat namespaced keys, Phase-4 preset union convention).
# ---------------------------------------------------------------------------

TIER_DEFAULT_PARAMS: dict[str, Any] = {
    # ``tier_canvas`` is a FALLBACK only: when ``layout_params`` does not pin it,
    # ``tier_canvas()`` computes a content-aware canvas (cols x cell width,
    # per-tier natural heights). Pinning it (the tests do) bypasses that.
    "tier_canvas": (600.0, 300.0),
    "tier_margin": 20.0,
    "tier_gutter": 24.0,
    "tier_slot_size": (180.0, 140.0),
    "tier_edge_standoff": 8.0,
    "tier_title_font_size": 18,
    "tier_subtitle_font_size": 13,
    # Title->subtitle baseline separation as a multiple of the title font size.
    # Must clear the legibility bbox heuristic (~0.24*title + 0.96*subtitle of
    # box height) regardless of how thin the TITLE band's height_frac makes it,
    # so the two lines never trip a false overlap report. 1.25 leaves margin.
    "tier_title_subtitle_em": 1.25,
    "tier_text_font_size": 12,
    "tier_text_color": "#1A1A1A",
    "tier_font_family": "Helvetica, Arial, sans-serif",
    # Content-aware sizing knobs (consumed by tier_canvas / _tier_rects).
    "tier_cell_pad_x": 45.0,       # horizontal slack each side of a slot in its cell
    "tier_scene_row_extra": 50.0,  # headroom for a scene row beyond the slot height
    "tier_title_band_height": 64.0,
    "tier_bar_band_height": 60.0,
    "tier_canvas_min": (400.0, 200.0),
    # Scene chrome.
    "tier_badge_radius": 11.0,
    "tier_badge_fill": "#444444",
    "tier_badge_text_color": "#FFFFFF",
    "tier_badge_inset": 6.0,       # badge centre inset from the cell top-left
    "tier_caption_font_size": 12,
    "tier_caption_gap": 12.0,      # gap below content before the scene caption
    "tier_caption_line_step": 1.25,  # line height as a multiple of font size
    # Band chrome defaults (a tier's ``style`` overrides per key).
    "tier_band_radius": 4.0,
    "tier_band_stroke_width": 1.0,
    "tier_divider_color": "#BBBBBB",
    "tier_divider_width": 1.0,
}

# Per-SceneEdgeType drawing defaults; ``edge.style`` overrides "stroke".
_EDGE_DEFAULTS: dict[str, dict[str, Any]] = {
    "hbond":      {"stroke": "#CC2222", "dash": "4,3", "curved": True,  "arrow": False},
    "dashed":     {"stroke": "#CC2222", "dash": "4,3", "curved": False, "arrow": False},
    "curly":      {"stroke": "#1A1A1A", "dash": None,  "curved": True,  "arrow": True},
    "transition": {"stroke": "#1A1A1A", "dash": None,  "curved": False, "arrow": True},
    "departs":    {"stroke": "#33AA33", "dash": None,  "curved": False, "arrow": True},
    "binds":      {"stroke": "#1A1A1A", "dash": None,  "curved": False, "arrow": True},
    "activates":  {"stroke": "#1A1A1A", "dash": None,  "curved": False, "arrow": True},
    "inhibits":   {"stroke": "#CC2222", "dash": None,  "curved": False, "arrow": True},
    "generic":    {"stroke": "#1A1A1A", "dash": None,  "curved": False, "arrow": True},
}


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _tier_natural_height(tier: Tier, params: dict[str, Any]) -> float:
    """A tier's intrinsic height for content-aware sizing, by role.

    A TITLE band needs only typography headroom; a SCENE_ROW needs a slot plus
    caption/badge headroom; SUMMARY_BAR / BAND are thin strips. Used both to
    size the canvas (``tier_canvas``) and to weight the band split when no
    ``height_frac`` is declared (``_tier_rects``)."""
    _sw, sh = params["tier_slot_size"]
    if tier.role == TierRole.TITLE:
        return float(params["tier_title_band_height"])
    if tier.role == TierRole.SCENE_ROW:
        return float(sh) + float(params["tier_scene_row_extra"])
    return float(params["tier_bar_band_height"])


def _tier_rects(
    tiers: list[Tier], canvas: tuple[float, float], margin: float,
    params: dict[str, Any],
) -> list[tuple[Tier, tuple[float, float, float, float]]]:
    """Stack tiers vertically, distributing the content height by weight.

    Weights are each tier's ``height_frac`` when *every* tier declares one
    (author intent), else each tier's role-based natural height (so a title
    band stays compact and a scene row gets room without manual fractions).
    Either way the weights are normalised to fill the inner height, so a pinned
    canvas is honoured exactly and an auto-sized canvas (whose inner height is
    the natural sum) is filled without remainder."""
    w, h = canvas
    inner_w = w - 2 * margin
    inner_h = h - 2 * margin
    fracs = [t.height_frac for t in tiers]
    if tiers and all(f is not None for f in fracs):
        weights = [float(f) for f in fracs]
    else:
        weights = [_tier_natural_height(t, params) for t in tiers]
    total = sum(weights) or 1.0
    heights = [inner_h * (wt / total) for wt in weights]
    rects: list[tuple[Tier, tuple[float, float, float, float]]] = []
    y = margin
    for tier, th in zip(tiers, heights):
        rects.append((tier, (margin, y, inner_w, th)))
        y += th
    return rects


def tier_canvas(
    figure: Figure, layout_params: dict[str, Any] | None = None
) -> tuple[float, float]:
    """Content-aware canvas ``(w, h)`` for a tiered figure.

    Width is driven by the widest SCENE_ROW (columns x cell width + gutters +
    margins); height is the sum of per-tier natural heights + margins. When
    ``layout_params`` pins ``tier_canvas`` it is returned verbatim (the tests
    and any caller that wants a fixed envelope), so the layout engine and the
    compositor's viewport agree by both routing through this one function.

    Mirrors ``pathway_layout.compute_pathway_canvas``: the size formula lives in
    one place so ``layout_tiers`` (which bakes absolute coords) and
    ``compositor._canvas_size`` (the SVG viewport) never drift apart."""
    if layout_params and "tier_canvas" in layout_params:
        w, h = layout_params["tier_canvas"]
        return (float(w), float(h))
    params = {**TIER_DEFAULT_PARAMS, **(layout_params or {})}
    margin = float(params["tier_margin"])
    gutter = float(params["tier_gutter"])
    sw, _sh = params["tier_slot_size"]
    cell_w = float(sw) + 2 * float(params["tier_cell_pad_x"])
    max_cols = max(
        (len(t.scenes) for t in figure.tiers if t.role == TierRole.SCENE_ROW),
        default=1,
    ) or 1
    width = 2 * margin + max_cols * cell_w + (max_cols - 1) * gutter
    height = 2 * margin + sum(
        _tier_natural_height(t, params) for t in figure.tiers
    )
    min_w, min_h = params["tier_canvas_min"]
    return (max(width, float(min_w)), max(height, float(min_h)))


def _column_rects(
    rect: tuple[float, float, float, float], n: int, gutter: float
) -> list[tuple[float, float, float, float]]:
    """Split ``rect`` into ``n`` equal-width columns separated by ``gutter``."""
    x, y, w, h = rect
    if n <= 0:
        return []
    col_w = (w - gutter * (n - 1)) / n
    return [(x + i * (col_w + gutter), y, col_w, h) for i in range(n)]


# ---------------------------------------------------------------------------
# Edge drawing
# ---------------------------------------------------------------------------

def _arrow_head(p0: tuple[float, float], p1: tuple[float, float], color: str,
                size: float = 8.0) -> svgwrite.shapes.Polygon:
    """A filled triangular arrowhead at ``p1`` pointing along p0->p1."""
    x0, y0 = p0
    x1, y1 = p1
    angle = math.atan2(y1 - y0, x1 - x0)
    bx = x1 - size * math.cos(angle)
    by = y1 - size * math.sin(angle)
    px, py = -math.sin(angle) * size * 0.5, math.cos(angle) * size * 0.5
    return svgwrite.shapes.Polygon(
        points=[(round(x1, 2), round(y1, 2)),
                (round(bx + px, 2), round(by + py, 2)),
                (round(bx - px, 2), round(by - py, 2))],
        fill=color, stroke="none",
    )


def _edge_group(
    p0: tuple[float, float], p1: tuple[float, float], edge_type: SceneEdgeType,
    edge_style: dict[str, Any] | None,
) -> svgwrite.container.Group:
    """Draw one edge p0->p1 per its type (dashed/curved line, arrow, or both)."""
    spec = _EDGE_DEFAULTS.get(edge_type.value, _EDGE_DEFAULTS["generic"])
    stroke = str((edge_style or {}).get("stroke", spec["stroke"]))
    width = float((edge_style or {}).get("stroke_width", 2.0))
    g = svgwrite.container.Group()
    head_from = p0  # arrowhead is aimed along this->p1; for a curve, the tangent
    if spec["curved"]:
        (x0, y0), (x1, y1) = p0, p1
        mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy) or 1.0
        bow = float((edge_style or {}).get("bow", min(20.0, length * 0.25)))
        cx, cy = mx - dy / length * bow, my + dx / length * bow
        attrs = {"fill": "none", "stroke": stroke, "stroke_width": width}
        if spec["dash"]:
            attrs["stroke_dasharray"] = spec["dash"]
        g.add(svgwrite.path.Path(
            d=f"M {x0:.2f},{y0:.2f} Q {cx:.2f},{cy:.2f} {x1:.2f},{y1:.2f}", **attrs))
        head_from = (cx, cy)  # quadratic Bézier arrives at p1 tangent to c->p1
    else:
        attrs = {"start": p0, "end": p1, "stroke": stroke, "stroke_width": width}
        if spec["dash"]:
            attrs["stroke_dasharray"] = spec["dash"]
        g.add(svgwrite.shapes.Line(**attrs))
    if spec["arrow"]:
        g.add(_arrow_head(head_from, p1, stroke))
    return g


# ---------------------------------------------------------------------------
# Scene + tier lowering
# ---------------------------------------------------------------------------

_SLOT_EDGE_OFFSETS = {
    "top": (0.0, -0.5), "bottom": (0.0, 0.5),
    "left": (-0.5, 0.0), "right": (0.5, 0.0), "center": (0.0, 0.0),
}


def _solve_slot_centers(
    scene: Scene, rect: tuple[float, float, float, float],
    slot_size: tuple[float, float],
) -> dict[str, tuple[float, float]]:
    """Minimal relative solver: root slots centred, attached slots placed at the
    parent's edge + offset.

    Attaches resolve in DEPENDENCY order (a parent is placed before its child),
    so author declaration order is irrelevant; a cyclic or unresolvable chain
    raises rather than silently overlapping. Only the basic edges in
    ``_SLOT_EDGE_OFFSETS`` are honoured here — cavity_*/anchor/custom and
    ``Attach.parent_anchor`` arrive with the full constraint solver (Step 5) and
    raise NotImplementedError until then.
    """
    cx, cy = rect[0] + rect[2] / 2.0, rect[1] + rect[3] / 2.0
    sw, sh = slot_size
    for att in scene.attach:
        if att.edge.value not in _SLOT_EDGE_OFFSETS:
            raise NotImplementedError(
                f"scene '{scene.id}' attach edge '{att.edge.value}' is not "
                "supported by the Step-3 slice (top/bottom/left/right/center only)")
    attached = {a.child for a in scene.attach}
    roots = [s.id for s in scene.slots if s.id not in attached]
    centers: dict[str, tuple[float, float]] = {}
    if len(roots) <= 1:
        for rid in roots:
            centers[rid] = (cx, cy)
    else:  # spread multiple roots horizontally across the cell
        step = rect[2] / (len(roots) + 1)
        for i, rid in enumerate(roots, start=1):
            centers[rid] = (rect[0] + step * i, cy)
    pending = list(scene.attach)
    while pending:
        still: list = []
        progressed = False
        for att in pending:
            if att.parent is None:
                parent_center = (cx, cy)
            elif att.parent in centers:
                parent_center = centers[att.parent]
            else:
                still.append(att)  # parent not placed yet — retry next pass
                continue
            ex, ey = _SLOT_EDGE_OFFSETS[att.edge.value]
            ox, oy = att.offset
            centers[att.child] = (parent_center[0] + ex * sw + ox,
                                  parent_center[1] + ey * sh + oy)
            progressed = True
        if not progressed:
            raise ValueError(
                f"scene '{scene.id}' has a cyclic or unresolvable attach chain: "
                f"{[a.child for a in still]}")
        pending = still
    return centers


def _layout_scene(
    scene: Scene, rect: tuple[float, float, float, float],
    registry: AnchorRegistry, params: dict[str, Any],
) -> list[LayoutEntry]:
    """Render a scene's slots into ``rect``, publish anchors, emit connect edges.

    Order matters: slots are solved and placed first so the scene-frame anchors
    can be published from the *content* extent (the union of slot boxes) rather
    than the cell rect — a cross-cell transition arrow then spans the visible
    molecule gap, not the narrow inter-cell gutter. Badge / caption chrome and
    intra-scene edges are emitted last (edges need the atom anchors above)."""
    sw, sh = params["tier_slot_size"]
    standoff = float(params["tier_edge_standoff"])
    cx, cy, cw, ch = rect
    entries: list[LayoutEntry] = []

    centers = _solve_slot_centers(scene, rect, (sw, sh))
    boxes: list[tuple[float, float, float, float]] = []
    for slot in scene.slots:
        center = centers.get(slot.id, (cx + cw / 2.0, cy + ch / 2.0))
        top_left = (center[0] - sw / 2.0, center[1] - sh / 2.0)
        scoped = f"{scene.id}.{slot.id}"
        if slot.kind == SlotKind.MOLECULE:
            style = slot.style or {}
            smiles = style.get("smiles")
            if not smiles:
                raise ValueError(
                    f"molecule slot '{scene.id}.{slot.id}' needs style['smiles']")
            names = {int(k): v for k, v in (style.get("anchor_names") or {}).items()}
            ag = render_molecule_anchored(str(smiles), size=(int(sw), int(sh)),
                                          anchor_names=names)
            registry.publish(scoped, ag.anchors, offset=top_left)
            entries.append(LayoutEntry(
                (lambda g=ag.group: g), (), {}, top_left, ir_id=scoped))
        elif slot.kind == SlotKind.TEXT:
            registry.publish(scoped, {"center": (0.0, 0.0)}, offset=center)
            entries.append(LayoutEntry(
                (lambda t=slot.label or "", c=center, p=params: _text_group(
                    t, c, int(p["tier_text_font_size"]), str(p["tier_text_color"]),
                    str(p["tier_font_family"]), anchor="middle")),
                (), {}, (0.0, 0.0), ir_id=scoped))
        else:
            raise NotImplementedError(
                f"SlotKind {slot.kind.value!r} is not yet supported by the "
                f"Step-3 tier-layout slice (slot '{scene.id}.{slot.id}')")
        boxes.append(_slot_bbox(slot, center, (sw, sh), params))

    # Scene-frame anchors from the CONTENT extent (cell-vs-content fix). Falls
    # back to the cell rect for an empty scene so the keys always resolve.
    if boxes:
        minx = min(b[0] for b in boxes); miny = min(b[1] for b in boxes)
        maxx = max(b[2] for b in boxes); maxy = max(b[3] for b in boxes)
    else:
        minx, miny, maxx, maxy = cx, cy, cx + cw, cy + ch
    fcx, fcy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    registry.publish(scene.id, {
        "left": (minx, fcy), "right": (maxx, fcy),
        "top": (fcx, miny), "bottom": (fcx, maxy),
        "center": (fcx, fcy),
    })

    # Step badge (top-left of the cell, so badges align across a row) + caption.
    if scene.badge:
        inset = float(params["tier_badge_inset"])
        r = float(params["tier_badge_radius"])
        entries.append(LayoutEntry(
            (lambda b=scene.badge, c=(cx + inset + r, cy + inset + r), p=params:
                _badge_group(b, c, p)),
            (), {}, (0.0, 0.0), ir_id=f"scene_{scene.id}_badge"))
    if scene.label:
        gap = float(params["tier_caption_gap"])
        base_y = maxy + gap + int(params["tier_caption_font_size"])
        entries.append(LayoutEntry(
            (lambda t=scene.label, x=fcx, y=base_y, p=params:
                _caption_group(t, x, y, p)),
            (), {}, (0.0, 0.0), ir_id=f"scene_{scene.id}_label"))

    # Intra-scene edges: refs are scene-local ("slot.anchor"); resolve_edge
    # applies (clamped) endpoint standoff so the line clears both atoms.
    for edge in scene.connect:
        q0, q1 = registry.resolve_edge(
            f"{scene.id}.{edge.from_anchor}", f"{scene.id}.{edge.to_anchor}",
            from_standoff=standoff, to_standoff=standoff)
        entries.append(LayoutEntry(
            (lambda a=q0, b=q1, t=edge.type, s=edge.style: _edge_group(a, b, t, s)),
            (), {}, (0.0, 0.0), ir_id=edge.ir_id))
    return entries


def _text_group(text: str, pos: tuple[float, float], size: int, color: str,
                family: str, anchor: str = "start", italic: bool = False,
                weight: str = "normal") -> svgwrite.container.Group:
    """A Group wrapping one Text element — keeps every entry's primitive
    returning a Group (the LayoutEntry contract / _tag_group target)."""
    g = svgwrite.container.Group()
    g.add(svgwrite.text.Text(
        text, insert=pos, font_size=size, fill=color, font_family=family,
        text_anchor=anchor,
        font_style="italic" if italic else "normal", font_weight=weight,
    ))
    return g


def _band_chrome(
    rect: tuple[float, float, float, float], tier_style: dict[str, Any],
    params: dict[str, Any],
) -> svgwrite.container.Group:
    """Background / border / top-divider chrome for one tier band.

    Driven by the tier's ``style`` bag (declarative, like every other primitive's
    visual intent): ``band_fill`` paints the rounded background, ``band_stroke``
    (+ ``band_stroke_width``) the border, and ``divider`` ('solid' | 'dashed')
    draws a rule across the tier's TOP edge — the convention that fences a
    summary bar off from the steps above it."""
    x, y, w, h = rect
    g = svgwrite.container.Group()
    fill = tier_style.get("band_fill")
    stroke = tier_style.get("band_stroke")
    if fill or stroke:
        g.add(svgwrite.shapes.Rect(
            insert=(x, y), size=(w, h),
            rx=float(params["tier_band_radius"]), ry=float(params["tier_band_radius"]),
            fill=str(fill) if fill else "none",
            stroke=str(stroke) if stroke else "none",
            stroke_width=float(tier_style.get(
                "band_stroke_width", params["tier_band_stroke_width"])) if stroke else 0,
        ))
    divider = tier_style.get("divider")
    if divider:
        attrs: dict[str, Any] = {
            "start": (x, y), "end": (x + w, y),
            "stroke": str(tier_style.get("divider_color", params["tier_divider_color"])),
            "stroke_width": float(tier_style.get(
                "divider_width", params["tier_divider_width"])),
        }
        if divider == "dashed":
            attrs["stroke_dasharray"] = "6,4"
        g.add(svgwrite.shapes.Line(**attrs))
    return g


def _badge_group(
    text: str, center: tuple[float, float], params: dict[str, Any],
) -> svgwrite.container.Group:
    """A small filled circle with a centred number — a scene's step badge.

    Vertical centring is done by nudging the baseline down ~0.35 em rather than
    relying on ``dominant-baseline`` (cairosvg ignores it on <text>)."""
    cx, cy = center
    r = float(params["tier_badge_radius"])
    g = svgwrite.container.Group()
    g.add(svgwrite.shapes.Circle(
        center=(cx, cy), r=r, fill=str(params["tier_badge_fill"]), stroke="none"))
    g.add(svgwrite.text.Text(
        text, insert=(cx, cy + r * 0.35), font_size=r * 1.1,
        fill=str(params["tier_badge_text_color"]),
        font_family=str(params["tier_font_family"]),
        text_anchor="middle", font_weight="bold"))
    return g


def _caption_group(
    text: str, cx: float, top_y: float, params: dict[str, Any],
) -> svgwrite.container.Group:
    """A centred, possibly multi-line scene caption below the content.

    ``\\n`` splits into stacked lines (the schema documents scene labels as
    multi-line); ``top_y`` is the baseline of the first line."""
    fs = int(params["tier_caption_font_size"])
    step = fs * float(params["tier_caption_line_step"])
    g = svgwrite.container.Group()
    for i, line in enumerate(text.split("\n")):
        g.add(svgwrite.text.Text(
            line, insert=(cx, top_y + i * step), font_size=fs,
            fill=str(params["tier_text_color"]),
            font_family=str(params["tier_font_family"]),
            text_anchor="middle", font_style="italic"))
    return g


def _slot_bbox(
    slot: Slot, center: tuple[float, float], slot_size: tuple[float, float],
    params: dict[str, Any],
) -> tuple[float, float, float, float]:
    """Absolute ``(minx, miny, maxx, maxy)`` a slot occupies around its centre.

    A MOLECULE fills the full slot box; a TEXT slot is roughly measured from its
    label. The union of these (computed by the caller) is the scene's *content*
    extent — what cross-cell transition arrows reach to, instead of the wider
    cell frame (the cell-vs-content fix)."""
    cxc, cyc = center
    if slot.kind == SlotKind.MOLECULE:
        sw, sh = slot_size
        return (cxc - sw / 2.0, cyc - sh / 2.0, cxc + sw / 2.0, cyc + sh / 2.0)
    if slot.kind == SlotKind.TEXT:
        fs = int(params["tier_text_font_size"])
        w = max(1, len(slot.label or "")) * fs * 0.6
        half_h = fs * 0.7
        return (cxc - w / 2.0, cyc - half_h, cxc + w / 2.0, cyc + half_h)
    return (cxc, cyc, cxc, cyc)


def _ref_to_key(ref: str) -> str:
    """Translate a TierEdge ref into a registry key: 'scene@edge' -> 'scene.edge';
    'scene.slot.anchor' is already a key."""
    return ref.replace("@", ".")


def layout_tiers(
    figure: Figure,
    layout_params: dict[str, Any] | None = None,
    style_dict: dict[str, Any] | None = None,
) -> list[LayoutEntry]:
    """Lower a tiered ``Figure`` to a flat ``list[LayoutEntry]`` (Step-3 slice).

    Args:
        figure: a ``Figure`` with ``tiers`` populated.
        layout_params: overrides merged onto ``TIER_DEFAULT_PARAMS``. Pin
            ``tier_canvas`` for a fixed envelope; otherwise the canvas is
            content-aware via :func:`tier_canvas`.
        style_dict: reserved for the Step-4 preset union (unused in the slice).

    Returns:
        Entries with baked absolute coordinates, ready for ``_write_svg`` /
        ``render_entries_to_png``.

    Raises:
        ValueError: the figure has no tiers, or a molecule slot lacks SMILES.
        NotImplementedError: a tier uses ``step_sequence`` (Step 6) or a slot
            uses a kind beyond molecule/text (primitive refresh).
    """
    if not figure.tiers:
        raise ValueError("layout_tiers requires a Figure with tiers populated")
    params = {**TIER_DEFAULT_PARAMS, **(layout_params or {})}
    # Self-size through tier_canvas so the baked coords match the compositor's
    # SVG viewport (which sizes through the same function).
    canvas = tier_canvas(figure, layout_params)
    margin = float(params["tier_margin"])
    gutter = float(params["tier_gutter"])
    registry = AnchorRegistry()
    entries: list[LayoutEntry] = []

    for tier, rect in _tier_rects(figure.tiers, canvas, margin, params):
        tx, ty, tw, th = rect

        # Band chrome: background / border / top divider (all style-driven).
        tstyle = tier.style or {}
        if any(k in tstyle for k in ("band_fill", "band_stroke", "divider")):
            entries.append(LayoutEntry(
                (lambda r=rect, s=tstyle, p=params: _band_chrome(r, s, p)),
                (), {}, (0.0, 0.0), ir_id=f"tier_{tier.id}_chrome"))

        if tier.role == TierRole.TITLE:
            title_fs = int(params["tier_title_font_size"])
            sub_fs = int(params["tier_subtitle_font_size"])
            cxm = tx + tw / 2.0
            band_cy = ty + th / 2.0
            gap = title_fs * float(params["tier_title_subtitle_em"])
            # Fixed baseline geometry (not band fractions): a one- or two-line
            # block centred in the band with a separation guaranteed to clear the
            # legibility overlap heuristic even when the band is thin.
            if tier.label and tier.subtitle:
                title_y, sub_y = band_cy - gap * 0.4, band_cy - gap * 0.4 + gap
            elif tier.label:
                title_y, sub_y = band_cy + title_fs * 0.35, None
            else:
                title_y, sub_y = None, band_cy + sub_fs * 0.35
            if tier.label:
                entries.append(LayoutEntry(
                    (lambda t=tier.label, x=cxm, y=title_y, fs=title_fs,
                            p=params: _text_group(t, (x, y), fs,
                                            str(p["tier_text_color"]),
                                            str(p["tier_font_family"]),
                                            anchor="middle", weight="bold")),
                    (), {}, (0.0, 0.0), ir_id=f"tier_{tier.id}_title"))
            if tier.subtitle:
                entries.append(LayoutEntry(
                    (lambda t=tier.subtitle, x=cxm, y=sub_y, fs=sub_fs,
                            p=params: _text_group(t, (x, y), fs,
                                            str(p["tier_text_color"]),
                                            str(p["tier_font_family"]),
                                            anchor="middle", italic=True)),
                    (), {}, (0.0, 0.0), ir_id=f"tier_{tier.id}_subtitle"))
            continue

        if tier.role == TierRole.SCENE_ROW:
            if tier.step_sequence is not None:
                raise NotImplementedError(
                    f"Tier '{tier.id}' uses step_sequence; step expansion is "
                    "Step 6 (not in the Step-3 slice)")
            cols = _column_rects(rect, len(tier.scenes), gutter)
            for scene, cell in zip(tier.scenes, cols):
                entries.extend(_layout_scene(scene, cell, registry, params))

            # Rails: resolve a fraction of the tier extent to an absolute scalar.
            for rail in tier.rails:
                if rail.axis == RailAxis.Y:
                    registry.publish_rail(rail.name, "y", ty + rail.at * th)
                else:
                    registry.publish_rail(rail.name, "x", tx + rail.at * tw)

            # Cross-cell transition arrows.
            for te in tier.transitions:
                if te.from_ref.startswith("rail:") or te.to_ref.startswith("rail:"):
                    raise NotImplementedError(
                        f"Tier '{tier.id}' transition uses a 'rail:' endpoint; "
                        "bare-rail endpoints are not in the Step-3 slice "
                        "(use a scene/slot anchor with on_rail to ride a rail)")
                p0, p1 = registry.resolve_edge(
                    _ref_to_key(te.from_ref), _ref_to_key(te.to_ref),
                    from_standoff=float(params["tier_edge_standoff"]),
                    to_standoff=float(params["tier_edge_standoff"]),
                    on_rail=te.on_rail,
                )
                entries.append(LayoutEntry(
                    (lambda a=p0, b=p1, t=te.type, s=te.style: _edge_group(a, b, t, s)),
                    (), {}, (0.0, 0.0), ir_id=te.ir_id))
            continue

        # SUMMARY_BAR / BAND: band background only in the slice (inner content
        # arrives with the full tier compositor in Step 4).

    return entries
