"""Port-based arrow routing, fan-out branching + compartment-border drawing.

Phase R1.d, extracted from ``pathway_layout`` — the largest pathway sub-module.
Owns how relation arrows leave/enter entities without stacking: per-side ports,
shared-trunk Y-fork fan-out, same-band arch routing over intervening nodes, and
orthogonal membrane-corridor lifting; plus the compartment band chrome
(``_compartment_band`` and the bilayer / nuclear-envelope borders it draws).

Imports the bbox/endpoint helpers from ``_pathway_bands`` and the shared
receptor font from ``_pathway_common``; references no sibling rings/labels
symbol. The orchestrator re-exports the routing entry points it calls.
"""
from __future__ import annotations

import warnings

import svgwrite.container
import svgwrite.path
import svgwrite.shapes
import svgwrite.text

from imageGen.ir.schema import CompartmentType
from imageGen.layout._pathway_bands import (
    _arrow_bbox_for_entity,
    _arrow_endpoints,
    _bbox_exit_point,
)
from imageGen.layout._pathway_common import _RECEPTOR_FONT_SIZE


_HIT_TEST_MARGIN = 8.0         # px — expanded half-extent for arch hit-test (Bug 4)


# ---------------------------------------------------------------------------
# Port-based arrow routing + fan-out branching.
#
# Center-to-center routing exits every arrow at the same edge midpoint, so two
# arrows leaving one entity toward the same side stack on top of each other and
# 1→{A,B} is indistinguishable from the chain 1→A→B. Ports spread co-sided
# arrows to distinct edge points; fan-out draws one shared trunk that branches
# at a Y-junction so a single source driving N targets reads as one fork.
# ---------------------------------------------------------------------------

_FANOUT_DIRS = {"right": (1.0, 0.0), "left": (-1.0, 0.0),
                "bottom": (0.0, 1.0), "top": (0.0, -1.0)}


def _natural_side(
    src_center: tuple[float, float], tgt_center: tuple[float, float]
) -> str:
    """Which bbox side the vector src→tgt exits, by dominant axis.

    Ties (``|dx| == |dy|``) break to the horizontal axis, the more common case
    in left-to-right band layouts. Coincident points return ``'right'`` (the
    self-loop default), so the caller's elbow code routes the loop normally.
    """
    dx = tgt_center[0] - src_center[0]
    dy = tgt_center[1] - src_center[1]
    if abs(dx) >= abs(dy):
        return "right" if dx >= 0 else "left"
    return "bottom" if dy >= 0 else "top"


def _diverging_fanouts(
    relations: list,
    positions: dict[str, tuple[float, float]],
    effective_bbox: dict,
    entity_by_id: dict,
    location_map: dict[str, str],
) -> dict[tuple[str, str], list[int]]:
    """Map ``(source_id, side)`` → relation indices that form a true fan-out.

    A source driving several targets on one side is only a fork when those
    targets actually diverge *perpendicular* to the exit direction. Co-sided
    targets strung out along the exit axis (same row → a chain with a skip
    link) are excluded — they keep their straight/arch routing. Only groups of
    size ≥ 2 that clear the divergence test are returned.

    Cross-band relations are excluded: they route through the inter-band
    corridor (a vertical exit), so a perpendicular-side trunk doesn't apply.
    """
    groups: dict[tuple[str, str], list[int]] = {}
    for idx, r in enumerate(relations):
        if location_map[r.source] != location_map[r.target]:
            continue
        side = _natural_side(positions[r.source], positions[r.target])
        groups.setdefault((r.source, side), []).append(idx)

    forks: dict[tuple[str, str], list[int]] = {}
    for (eid, side), group in groups.items():
        if len(group) < 2:
            continue
        perp_axis = 1 if side in ("left", "right") else 0
        perp = [positions[relations[i].target][perp_axis] for i in group]
        tgt_extent = min(
            effective_bbox[entity_by_id[relations[i].target].type][perp_axis]
            for i in group
        )
        if max(perp) - min(perp) >= tgt_extent:
            forks[(eid, side)] = group
    return forks


def _assign_ports(
    relations: list,
    positions: dict[str, tuple[float, float]],
    effective_bbox: dict,
    entity_by_id: dict,
    location_map: dict[str, str],
    arrow_gap: float,
    corner_inset: float,
) -> tuple[dict, set, list]:
    """Assign an exit/entry point to every relation endpoint.

    Returns ``(ports, reassigned, fanout_groups)``:

    * ``ports`` maps every ``(rel_idx, 'src')`` / ``(rel_idx, 'tgt')`` to
      ``(x, y)``.
    * ``reassigned`` is the subset of keys whose port was moved off the default
      exit, so the caller knows when to pull an elbow path's terminal waypoint
      onto the port.
    * ``fanout_groups`` is a list of ``(group_indices, side, src_port)`` for
      each true fan-out, so the caller can build the shared Y-trunk.

    **Port exclusivity.** Endpoints are bucketed per ``(entity, side)`` —
    *both* exits and entries on the same side share a bucket, plus one slot per
    fan-out trunk. A bucket with a single occupant keeps the exact
    ``_arrow_endpoints`` exit (single arrows stay byte-identical). A bucket with
    several occupants spreads them to evenly-spaced ports inset ``corner_inset``
    px from each corner, ordered by the perpendicular coordinate of their far
    endpoint to minimise crossing. This covers fan-in (many entries), the
    bidirectional pair (one exit + one entry colliding on a side), and any
    mixed case — not just fan-out, which the trunk routing also distinguishes.

    Only **same-band** endpoints are bucketed. Cross-band arrows route through
    the inter-band corridor (vertical exit/entry), so their ``natural_side`` is
    not a real edge — reassigning them to a perpendicular port would fight the
    corridor. They keep their default exits untouched.
    """
    forks = _diverging_fanouts(
        relations, positions, effective_bbox, entity_by_id, location_map
    )
    fork_members = {i for group in forks.values() for i in group}

    ports: dict[tuple[int, str], tuple[float, float]] = {}
    # Default every endpoint to its center-to-center exit.
    for idx, r in enumerate(relations):
        s_center = positions[r.source]
        t_center = positions[r.target]
        src = entity_by_id[r.source]
        tgt = entity_by_id[r.target]
        s_bbox = _arrow_bbox_for_entity(src, effective_bbox[src.type])
        t_bbox = _arrow_bbox_for_entity(tgt, effective_bbox[tgt.type])
        ports[(idx, "src")] = _bbox_exit_point(
            s_center, s_bbox[0] / 2.0, s_bbox[1] / 2.0, t_center, arrow_gap
        )
        ports[(idx, "tgt")] = _bbox_exit_point(
            t_center, t_bbox[0] / 2.0, t_bbox[1] / 2.0, s_center, arrow_gap
        )

    # Bucket occupants per (entity, side). An occupant is a fan-out trunk, a
    # single source exit, or a target entry. ``anchor`` is the perpendicular
    # coordinate used to order the bucket so arrows don't cross.
    buckets: dict[tuple[str, str], list[dict]] = {}

    def _perp(side: str, pt: tuple[float, float]) -> float:
        return pt[1] if side in ("left", "right") else pt[0]

    for (eid, side), group in forks.items():
        anchor = sum(_perp(side, positions[relations[i].target]) for i in group) / len(group)
        buckets.setdefault((eid, side), []).append(
            {"kind": "fanout", "group": group, "anchor": anchor}
        )
    for idx, r in enumerate(relations):
        if location_map[r.source] != location_map[r.target]:
            continue  # cross-band: keep corridor routing, no port reassignment
        if idx not in fork_members:
            s_side = _natural_side(positions[r.source], positions[r.target])
            buckets.setdefault((r.source, s_side), []).append(
                {"kind": "src", "idx": idx,
                 "anchor": _perp(s_side, positions[r.target])}
            )
        t_side = _natural_side(positions[r.target], positions[r.source])
        buckets.setdefault((r.target, t_side), []).append(
            {"kind": "tgt", "idx": idx,
             "anchor": _perp(t_side, positions[r.source])}
        )

    reassigned: set[tuple[int, str]] = set()
    fanout_groups: list[tuple[list[int], str, tuple[float, float]]] = []

    for (eid, side), occ in buckets.items():
        entity = entity_by_id[eid]
        bw, bh = _arrow_bbox_for_entity(entity, effective_bbox[entity.type])
        hw, hh = bw / 2.0, bh / 2.0
        cx, cy = positions[eid]
        horizontal_edge = side in ("left", "right")
        occ.sort(key=lambda o: o["anchor"])
        m = len(occ)
        has_entry = any(o["kind"] == "tgt" for o in occ)

        # Spread only when an entry shares the side — this covers fan-in (many
        # entries) and the bidirectional collision (one exit + one entry). A
        # pure-exit bucket (a chain's straight link plus its skip links) is left
        # to arch routing, which separates the skips vertically; spreading those
        # exits horizontally would fight the arch geometry.
        if m == 1 or not has_entry:
            for o in occ:
                if o["kind"] == "fanout":
                    src_port = _edge_point(cx, cy, hw, hh, side, 0.5, arrow_gap)
                    for i in o["group"]:
                        ports[(i, "src")] = src_port
                    fanout_groups.append((o["group"], side, src_port))
            # Lone / pure-exit occupants keep their default exits.
            continue

        span = (2.0 * hh if horizontal_edge else 2.0 * hw) - 2.0 * corner_inset
        if span <= 0 or span / (m - 1) < corner_inset:
            warnings.warn(
                f"pathway port routing: {m} arrows on the {side} side of "
                f"'{eid}' exceed edge capacity; ports cluster near the corners.",
                UserWarning,
                stacklevel=2,
            )
        for k, o in enumerate(occ):
            pos = _edge_point(cx, cy, hw, hh, side, k / (m - 1), arrow_gap,
                              inset=corner_inset)
            if o["kind"] == "fanout":
                for i in o["group"]:
                    ports[(i, "src")] = pos
                fanout_groups.append((o["group"], side, pos))
            else:
                key = (o["idx"], "src" if o["kind"] == "src" else "tgt")
                ports[key] = pos
                reassigned.add(key)

    return ports, reassigned, fanout_groups


def _edge_point(
    cx: float,
    cy: float,
    hw: float,
    hh: float,
    side: str,
    frac: float,
    gap: float,
    inset: float = 0.0,
) -> tuple[float, float]:
    """A point on a bbox side, ``frac`` (0→1) of the way along the usable edge.

    The edge runs corner-to-corner; ``inset`` trims that span symmetrically so
    ports keep clear of the corners. ``gap`` pushes the point perpendicularly
    off the edge (matching the arrow-tip gap used elsewhere). ``frac == 0.5``
    with ``inset == 0`` is the plain edge midpoint.
    """
    if side in ("left", "right"):
        lo, hi = cy - hh + inset, cy + hh - inset
        y = lo + frac * (hi - lo)
        x = cx + (hw + gap) * (1.0 if side == "right" else -1.0)
        return (x, y)
    lo, hi = cx - hw + inset, cx + hw - inset
    x = lo + frac * (hi - lo)
    y = cy + (hh + gap) * (1.0 if side == "bottom" else -1.0)
    return (x, y)


def _route_fanout(
    src_port: tuple[float, float],
    exit_side: str,
    branch_entries: list[tuple[tuple[float, float], Any]],
    trunk_length: float,
) -> list[list[tuple[float, float]]]:
    """Y-fork waypoints for a fan-out group sharing ``src_port``.

    ``branch_entries`` is ``[(tgt_port, _unused), ...]``. Every branch shares
    the trunk ``src_port → trunk_end`` (``trunk_length`` px along ``exit_side``)
    then turns orthogonally to its target. Returns one waypoint list
    ``[src_port, trunk_end, turn_corner, tgt_port]`` per branch, in input order.
    """
    dx, dy = _FANOUT_DIRS[exit_side]
    trunk_end = (src_port[0] + dx * trunk_length, src_port[1] + dy * trunk_length)
    branches: list[list[tuple[float, float]]] = []
    for tgt_port, _ in branch_entries:
        if exit_side in ("left", "right"):
            turn_corner = (trunk_end[0], tgt_port[1])
        else:
            turn_corner = (tgt_port[0], trunk_end[1])
        branches.append([src_port, trunk_end, turn_corner, tgt_port])
    return branches


def _segment_hits_rect(
    p0: tuple[float, float],
    p1: tuple[float, float],
    cx: float,
    cy: float,
    hw: float,
    hh: float,
) -> bool:
    """True if segment p0→p1 intersects the axis-aligned rect centred at
    (cx, cy) with half-extents (hw, hh). Liang–Barsky slab clipping."""
    x0, y0 = p0
    x1, y1 = p1
    dx, dy = x1 - x0, y1 - y0
    left, right = cx - hw, cx + hw
    bottom, top = cy - hh, cy + hh
    t_enter, t_exit = 0.0, 1.0
    for p, q in (
        (-dx, x0 - left),    # left slab
        (dx, right - x0),    # right slab
        (-dy, y0 - bottom),  # bottom slab
        (dy, top - y0),      # top slab
    ):
        if p == 0:
            # Segment parallel to this slab: outside if origin is outside.
            if q < 0:
                return False
            continue
        t = q / p
        if p < 0:
            if t > t_exit:
                return False
            if t > t_enter:
                t_enter = t
        else:
            if t < t_enter:
                return False
            if t < t_exit:
                t_exit = t
    return t_enter <= t_exit


def _arch_waypoints(
    src_center: tuple[float, float],
    src_bbox: tuple[float, float],
    tgt_center: tuple[float, float],
    tgt_bbox: tuple[float, float],
    band: tuple[float, float],
    gap: float,
    lane: int,
    *,
    above: bool,
    clearance: float,
    lane_gap: float,
) -> list[tuple[float, float]]:
    """4-point elbow that arches a same-band skip arrow over (or under) the
    intervening entities. `lane` (0-based) stacks successive arches into
    distinct corridors so overlapping arches never share a shaft line. The
    corridor is clamped to stay inside the band interior."""
    sx, sy = src_center
    tx, ty = tgt_center
    shh = src_bbox[1] / 2
    thh = tgt_bbox[1] / 2
    band_top, band_bottom = band
    if above:
        base = min(sy - shh, ty - thh) - clearance
        corridor_y = base - lane * lane_gap
        corridor_y = max(corridor_y, band_top + clearance)
        tail = (sx, sy - shh - gap)
        head = (tx, ty - thh - gap)
    else:
        base = max(sy + shh, ty + thh) + clearance
        corridor_y = base + lane * lane_gap
        corridor_y = min(corridor_y, band_bottom - clearance)
        tail = (sx, sy + shh + gap)
        head = (tx, ty + thh + gap)
    return [tail, (sx, corridor_y), (tx, corridor_y), head]


def _route_same_band_arrows(
    relations: list,
    positions: dict[str, tuple[float, float]],
    entity_by_id: dict,
    bands: dict[str, tuple[float, float]],
    location_map: dict[str, str],
    effective_bbox: dict,
    gap: float,
    clearance: float,
    lane_gap: float,
) -> dict[int, list[tuple[float, float]] | None]:
    """Decide waypoints for every same-band relation.

    Returns a map from `relations` index → waypoint list, or ``None`` for a
    straight arrow. An arrow arches when its straight shaft would cross an
    intervening entity in the same band; arches are assigned to lanes via a
    left-edge sweep so overlapping spans never collapse onto one corridor,
    alternating above/below the row to use both sides of the band.
    """
    # Entities grouped per band, for the intervening-entity test.
    band_members: dict[str, list[str]] = {}
    for eid in positions:
        band_members.setdefault(location_map[eid], []).append(eid)

    routes: dict[int, list[tuple[float, float]] | None] = {}
    arching: list[tuple[float, float, int]] = []  # (x_left, x_right, rel_index)

    for idx, r in enumerate(relations):
        if location_map[r.source] != location_map[r.target]:
            continue  # cross-band handled elsewhere
        src = entity_by_id[r.source]
        tgt = entity_by_id[r.target]
        s_center = positions[r.source]
        t_center = positions[r.target]
        s_bbox = _arrow_bbox_for_entity(src, effective_bbox[src.type])
        t_bbox = _arrow_bbox_for_entity(tgt, effective_bbox[tgt.type])
        start, end = _arrow_endpoints(s_center, s_bbox, t_center, t_bbox, gap)

        hit = False
        for oid in band_members[location_map[r.source]]:
            if oid in (r.source, r.target):
                continue
            ocx, ocy = positions[oid]
            ow, oh = effective_bbox[entity_by_id[oid].type]
            # Bug 4: broaden the hit-test half-extents by _HIT_TEST_MARGIN so
            # shafts that visually graze an entity bbox but miss it by a few px
            # (due to vertical spread from the layered-DAG topo-y logic) still
            # trigger an arch.  Also include the entity's label footprint: a
            # shaft that passes through a long centered label arches even if it
            # clears the body box.  The width estimate uses the same formula as
            # label_placement._estimate_text_bbox so the two are consistent.
            obs_label = entity_by_id[oid].label
            obs_lw = max(1, len(obs_label)) * _RECEPTOR_FONT_SIZE * 0.6
            hw = max(ow / 2, obs_lw / 2) + _HIT_TEST_MARGIN
            hh = oh / 2 + _HIT_TEST_MARGIN
            if _segment_hits_rect(start, end, ocx, ocy, hw, hh):
                hit = True
                break

        if not hit:
            routes[idx] = None  # straight
        else:
            arching.append((min(s_center[0], t_center[0]),
                            max(s_center[0], t_center[0]), idx))

    # Left-edge lane assignment: sort by left x, place each span in the
    # lowest lane whose last span ends before this one starts.
    arching.sort(key=lambda s: (s[0], s[1]))
    lane_right_edge: list[float] = []  # rightmost x occupied per lane
    lane_of: dict[int, int] = {}
    for x_left, x_right, idx in arching:
        placed = False
        for lane, redge in enumerate(lane_right_edge):
            if x_left >= redge:
                lane_right_edge[lane] = x_right
                lane_of[idx] = lane
                placed = True
                break
        if not placed:
            lane_of[idx] = len(lane_right_edge)
            lane_right_edge.append(x_right)

    for x_left, x_right, idx in arching:
        r = relations[idx]
        src = entity_by_id[r.source]
        tgt = entity_by_id[r.target]
        lane = lane_of[idx]
        # Alternate sides: even lanes arch above, odd lanes arch below, so a
        # band uses both halves and fits roughly twice as many arches.
        side_lane = lane // 2
        above = (lane % 2 == 0)
        routes[idx] = _arch_waypoints(
            positions[r.source], effective_bbox[src.type],
            positions[r.target], effective_bbox[tgt.type],
            bands[location_map[r.source]],
            gap, side_lane,
            above=above, clearance=clearance, lane_gap=lane_gap,
        )
    return routes


def _lift_corridor_off_membrane(
    corridor_y: float,
    membrane_keepouts: list[tuple[float, float]] | None,
) -> float:
    """Nudge a horizontal corridor out of any membrane bilayer keep-out zone.

    A cross-band corridor placed at the boundary between two contiguous bands
    can land exactly on a lipid-bilayer stripe (drawn at the membrane band's
    top edge), so the horizontal leg of the elbow visually rides along the
    membrane. When ``corridor_y`` falls inside a keep-out interval, lift it to
    just above the stripe (the interval's top), so the corridor runs in the
    band above the membrane and only the vertical legs cross the bilayer —
    perpendicular, as a membrane crossing should read. No-op when there are no
    membranes or the corridor already clears them.
    """
    if not membrane_keepouts:
        return corridor_y
    for lo, hi in membrane_keepouts:
        if lo < corridor_y < hi:
            corridor_y = lo
    return corridor_y


def _orthogonal_waypoints(
    src_center: tuple[float, float],
    src_bbox: tuple[float, float],
    src_band: tuple[float, float],
    tgt_center: tuple[float, float],
    tgt_bbox: tuple[float, float],
    tgt_band: tuple[float, float],
    gap: float,
    membrane_keepouts: list[tuple[float, float]] | None = None,
) -> list[tuple[float, float]]:
    """Compute a 4-point orthogonal (elbow) path from src to tgt.

    For entities in different bands the path travels through the clear
    corridor between the two bands (no entities occupy that space), so
    it is guaranteed not to pass through any third entity box.

    For entities in the same band the path routes through a corridor
    above the band top (outside the band), which may briefly exit the
    canvas for the top-most band but is still rendered correctly by SVG.

    ``membrane_keepouts`` is a list of ``(stripe_top, stripe_bottom)`` y-intervals
    (one per lipid bilayer, already margin-inflated). A cross-band corridor that
    would land on a bilayer is lifted just above it so the horizontal leg never
    rides the membrane.

    Returns a 4-element list: [tail_exit, elbow_src, elbow_tgt, head_enter].
    The first and last points land on the bbox perimeters of source and
    target respectively; the middle two define the horizontal corridor leg.
    """
    sx, sy = src_center
    tx, ty = tgt_center
    shh = src_bbox[1] / 2
    thh = tgt_bbox[1] / 2
    src_top, src_bottom = src_band
    tgt_top, tgt_bottom = tgt_band

    if src_band == tgt_band:
        # Route above both entity tops within the band, not above the band boundary.
        # This keeps the corridor inside the canvas even when the band spans the
        # full height (single implicit band for figures with no compartments).
        clearance = max(gap * 4, 16.0)
        corridor_y = min(sy - shh, ty - thh) - clearance
        tail = (sx, sy - shh - gap)
        head = (tx, ty - thh - gap)
        return [tail, (sx, corridor_y), (tx, corridor_y), head]

    if src_bottom <= tgt_top:
        # src band is above tgt band in the figure (lower y_range in SVG).
        corridor_y = (src_bottom + tgt_top) / 2
        tail = (sx, sy + shh + gap)
        head = (tx, ty - thh - gap)
    else:
        # src band is below tgt band.
        corridor_y = (tgt_bottom + src_top) / 2
        tail = (sx, sy - shh - gap)
        head = (tx, ty + thh + gap)

    corridor_y = _lift_corridor_off_membrane(corridor_y, membrane_keepouts)
    return [tail, (sx, corridor_y), (tx, corridor_y), head]


def _compartment_band(
    label: str,
    x: float,
    y: float,
    w: float,
    h: float,
    params: dict,
    *,
    compartment_type: CompartmentType | None = None,
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """Background rectangle + top-left label for one compartment band.

    ``params`` is the already-merged layout-params dict from ``layout_pathway``,
    so caller overrides via ``layout_params={"pathway_band_fill": ...}`` reach
    here.

    V2 / L8: when ``compartment_type`` is ``MEMBRANE`` a horizontal lipid-bilayer
    stripe is drawn along the band's top border; when it is ``NUCLEUS`` a
    double-line nuclear-envelope border is drawn instead. Both use the
    membrane primitive's ``DEFAULT_STYLE`` keys merged with ``style_dict`` so
    preset overrides (e.g. ACS monochrome nuclear strokes) flow through.
    """
    g = svgwrite.container.Group()
    # Mark the band group as decorative chrome (not figure content). The crop
    # / whitespace logic excludes data-role="band" subtrees so a full-canvas
    # background band doesn't defeat content-bbox detection. debug=False lets
    # svgwrite emit the non-allowlisted data-* attribute.
    g._parameter.debug = False
    g.attribs["data-role"] = "band"
    rect = svgwrite.shapes.Rect(
        insert=(x, y),
        size=(w, h),
        fill=params["pathway_band_fill"],
        stroke=params["pathway_band_stroke"],
    )
    rect["stroke-width"] = float(params["pathway_band_stroke_width"])
    g.add(rect)
    if label:
        size = float(params["pathway_band_label_size"])
        g.add(svgwrite.text.Text(
            label,
            insert=(x + 8, y + size + 4),
            font_family=params["pathway_band_label_family"],
            font_size=size,
            fill=params["pathway_band_label_color"],
        ))

    # V2 / L8: organelle-specific border decorations
    if compartment_type in (CompartmentType.MEMBRANE, CompartmentType.NUCLEUS):
        from imageGen.primitives import membranes as _mem  # noqa: PLC0415
        ms: dict = {**_mem.DEFAULT_STYLE, **(style_dict or {})}

        if compartment_type is CompartmentType.MEMBRANE:
            _draw_bilayer_border(g, x, y, w, ms)
        else:  # NUCLEUS
            _draw_nuclear_border(g, x, y, w, ms)

    return g


def _draw_bilayer_border(
    group: svgwrite.container.Group,
    x: float, y: float, w: float,
    ms: dict,
) -> None:
    """Draw a horizontal lipid-bilayer stripe at the top edge of a band.

    Renders: a filled tail-region rectangle, two boundary strokes (outer
    and inner leaflet), and evenly-spaced phospholipid head-group circles
    on both leaflets — the standard textbook membrane representation,
    flattened into a horizontal stripe.
    """
    thickness = float(ms["bilayer_thickness"])
    inner_y = y + thickness

    # Hydrophobic tail fill
    group.add(svgwrite.shapes.Rect(
        insert=(x, y), size=(w, thickness),
        fill=str(ms["bilayer_tail_fill"]), stroke="none",
    ))
    # Outer leaflet boundary stroke
    outer = svgwrite.path.Path(
        d=f"M {x:.2f},{y:.2f} L {x + w:.2f},{y:.2f}",
        fill="none", stroke=str(ms["bilayer_outer_stroke"]),
    )
    outer["stroke-width"] = float(ms["bilayer_outer_stroke_width"])
    group.add(outer)
    # Inner leaflet boundary stroke
    inner = svgwrite.path.Path(
        d=f"M {x:.2f},{inner_y:.2f} L {x + w:.2f},{inner_y:.2f}",
        fill="none", stroke=str(ms["bilayer_inner_stroke"]),
    )
    inner["stroke-width"] = float(ms["bilayer_inner_stroke_width"])
    group.add(inner)
    # Head-group circles on both leaflets
    spacing = float(ms["bilayer_head_spacing"])
    r_head  = float(ms["bilayer_head_radius"])
    fill    = str(ms["bilayer_head_fill"])
    hx = x + spacing
    while hx < x + w - spacing * 0.5:
        group.add(svgwrite.shapes.Circle(center=(hx, y),       r=r_head, fill=fill))
        group.add(svgwrite.shapes.Circle(center=(hx, inner_y), r=r_head, fill=fill))
        hx += spacing


def _draw_nuclear_border(
    group: svgwrite.container.Group,
    x: float, y: float, w: float,
    ms: dict,
) -> None:
    """Draw a horizontal double-line nuclear-envelope border at the top of a band.

    Renders: outer nuclear-membrane stroke, inner nuclear-membrane stroke
    (separated by ``nuclear_gap`` px), and evenly-spaced nuclear-pore-complex
    accent circles between the two lines.
    """
    gap    = float(ms["nuclear_gap"])
    inner_y = y + gap
    pore_r = float(ms["nuclear_pore_radius"])
    pore_n = int(ms["nuclear_pore_count"])

    # Outer nuclear membrane
    outer = svgwrite.path.Path(
        d=f"M {x:.2f},{y:.2f} L {x + w:.2f},{y:.2f}",
        fill="none", stroke=str(ms["nuclear_outer_stroke"]),
    )
    outer["stroke-width"] = float(ms["nuclear_outer_stroke_width"])
    group.add(outer)
    # Inner nuclear membrane
    inner = svgwrite.path.Path(
        d=f"M {x:.2f},{inner_y:.2f} L {x + w:.2f},{inner_y:.2f}",
        fill="none", stroke=str(ms["nuclear_inner_stroke"]),
    )
    inner["stroke-width"] = float(ms["nuclear_inner_stroke_width"])
    group.add(inner)
    # Nuclear pore complex accents at midline between the two strokes
    if pore_n > 0:
        pore_y = y + gap / 2
        spacing = w / (pore_n + 1)
        for i in range(1, pore_n + 1):
            group.add(svgwrite.shapes.Circle(
                center=(x + i * spacing, pore_y),
                r=pore_r,
                fill=str(ms["nuclear_pore_fill"]),
            ))

