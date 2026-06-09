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
    "tier_canvas": (600.0, 300.0),
    "tier_margin": 20.0,
    "tier_gutter": 24.0,
    "tier_slot_size": (180.0, 140.0),
    "tier_edge_standoff": 8.0,
    "tier_title_font_size": 18,
    "tier_subtitle_font_size": 13,
    "tier_text_font_size": 12,
    "tier_text_color": "#1A1A1A",
    "tier_font_family": "Helvetica, Arial, sans-serif",
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

def _tier_rects(
    tiers: list[Tier], canvas: tuple[float, float], margin: float
) -> list[tuple[Tier, tuple[float, float, float, float]]]:
    """Stack tiers vertically. Heights use ``height_frac`` (normalised over the
    content height) when every tier declares one, else an equal split."""
    w, h = canvas
    inner_w = w - 2 * margin
    inner_h = h - 2 * margin
    fracs = [t.height_frac for t in tiers]
    if tiers and all(f is not None for f in fracs):
        total = sum(fracs)  # normalise so they fill the content height
        heights = [inner_h * (f / total) for f in fracs]
    else:
        heights = [inner_h / len(tiers)] * len(tiers) if tiers else []
    rects: list[tuple[Tier, tuple[float, float, float, float]]] = []
    y = margin
    for tier, th in zip(tiers, heights):
        rects.append((tier, (margin, y, inner_w, th)))
        y += th
    return rects


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
    """Render a scene's slots into ``rect``, publish anchors, emit connect edges."""
    sw, sh = params["tier_slot_size"]
    standoff = float(params["tier_edge_standoff"])
    cx, cy, cw, ch = rect
    entries: list[LayoutEntry] = []

    # Scene-frame anchors (for cross-cell "scene@edge" TierEdge refs).
    registry.publish(scene.id, {
        "left": (0.0, ch / 2.0), "right": (cw, ch / 2.0),
        "top": (cw / 2.0, 0.0), "bottom": (cw / 2.0, ch),
        "center": (cw / 2.0, ch / 2.0),
    }, offset=(cx, cy))

    centers = _solve_slot_centers(scene, rect, (sw, sh))
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


def _band(rect: tuple[float, float, float, float], fill: str) -> svgwrite.container.Group:
    """A rounded band-background rect for a tier."""
    x, y, w, h = rect
    g = svgwrite.container.Group()
    g.add(svgwrite.shapes.Rect(insert=(x, y), size=(w, h), fill=str(fill), rx=4, ry=4))
    return g


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
        layout_params: overrides merged onto ``TIER_DEFAULT_PARAMS`` (notably
            ``tier_canvas``).
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
    canvas = params["tier_canvas"]
    margin = float(params["tier_margin"])
    gutter = float(params["tier_gutter"])
    registry = AnchorRegistry()
    entries: list[LayoutEntry] = []

    for tier, rect in _tier_rects(figure.tiers, canvas, margin):
        tx, ty, tw, th = rect

        # Optional band background (style['band_fill']).
        band_fill = (tier.style or {}).get("band_fill")
        if band_fill:
            entries.append(LayoutEntry(
                (lambda r=rect, f=band_fill: _band(r, f)),
                (), {}, (0.0, 0.0), ir_id=f"tier_{tier.id}_band"))

        if tier.role == TierRole.TITLE:
            if tier.label:
                entries.append(LayoutEntry(
                    (lambda t=tier.label, x=tx + tw / 2.0, y=ty + th * 0.45,
                            p=params: _text_group(t, (x, y), int(p["tier_title_font_size"]),
                                            str(p["tier_text_color"]),
                                            str(p["tier_font_family"]),
                                            anchor="middle", weight="bold")),
                    (), {}, (0.0, 0.0), ir_id=f"tier_{tier.id}_title"))
            if tier.subtitle:
                entries.append(LayoutEntry(
                    (lambda t=tier.subtitle, x=tx + tw / 2.0, y=ty + th * 0.75,
                            p=params: _text_group(t, (x, y), int(p["tier_subtitle_font_size"]),
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
