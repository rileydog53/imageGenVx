"""Pathway layout engine.

Translates an IR `Figure` whose `archetype == PATHWAY` into a list of
`LayoutEntry` tuples that the Phase 5 renderer consumes. Pathway figures
group entities into horizontal compartment bands (extracellular →
membrane → cytoplasm → nucleus per biological convention), place
entities within bands using a seeded NetworkX spring layout, and connect
them with arrows whose primitive is selected by `RelationType`.

LayoutEntry is reused from `layout.reaction_layout` for renderer
uniformity. When more layout engines need it, promote LayoutEntry to
`layout/__init__.py`.

Compartment ordering:
  Reads the declaration order from `figure.compartments`. If empty
  (e.g., a cascade with no spatial context like the MAPK fixture), a
  single implicit band is synthesized so downstream code is uniform.

Entity → primitive dispatch:
  `ENTITY_TO_PRIMITIVE[entity.type]`. Layout owns this policy so
  `entity.style` stays reserved for visual presets.

Relation → arrow dispatch:
  `RELATION_TO_ARROW[relation.type]`. PHOSPHORYLATES, TRANSCRIBES, and
  GENERIC all currently route to `activation_arrow`; the per-arrow
  annotation glyph (e.g. a "P" badge for phosphorylation) is deferred
  to Step 4 (`label_placement.py`).

v1 limitations (explicit gaps; not oversights):
  - Arrows are always straight lines from entity-center to entity-center.
    No crossing detection, no curving heuristic, no edge-anchored
    endpoints. Force-directed routing is a Phase 3+ stretch.
  - Entities within a band are ordered by their spring_layout x and
    then evenly spaced horizontally; the y is fixed to the band center
    rather than using spring_layout y (compartment containment).
  - Per-entity primitive sizing uses primitive defaults; pathway
    layout does not forward a `size` kwarg. Wire this up alongside
    Phase 4 style presets.
  - GENE entities map to `generic_protein` rather than a nucleic_acids
    helix; can be lifted to nucleic_acids primitives in a v2.
  - Compartment bands are simple coloured rects + a label. Dedicated
    organelle outlines (membrane, nuclear envelope) belong in archetype
    code, not the layout engine.

Phase 5 coupling:
  All emitted LayoutEntry items use `position=(0.0, 0.0)` because
  primitives are called with absolute SVG coordinates already baked in
  via the `position` arg (entities) or the `start`/`end` args (arrows).
  The renderer's translate(LayoutEntry.position) is therefore a no-op
  here; it stays in the contract for future engines that emit relative
  primitives.
"""
from __future__ import annotations

from typing import Any, Callable

import math
import warnings

import networkx as nx
import svgwrite.container
import svgwrite.path
import svgwrite.shapes
import svgwrite.text

from imageGen.ir.schema import (
    Archetype,
    Compartment,
    CompartmentType,
    Entity,
    EntityType,
    Figure,
    RelationType,
)
from imageGen.layout._geom import (
    ENTITY_BBOX,
    ENTITY_TO_PRIMITIVE,
    PRIMITIVE_REGISTRY,
    PRIMITIVE_TO_BBOX,
    max_entity_bbox,
)
from imageGen.layout._layered import order_within_ranks, rank_nodes, tighten_ranks
from imageGen.layout.types import LayoutEntry
from imageGen.primitives import arrows, proteins
from imageGen.primitives._text import centered_label as _centered_label, fit_label


# ---------------------------------------------------------------------------
# Layout knobs (Phase 4 master preset will union these alongside primitive
# DEFAULT_STYLE dicts; flat namespaced keys for predictable union).
# ---------------------------------------------------------------------------

PATHWAY_DEFAULT_PARAMS: dict[str, Any] = {
    "pathway_canvas":            (800.0, 600.0),    # (w, h) — also the min-size floor
    "pathway_origin":            (0.0, 0.0),        # top-left of canvas
    "pathway_band_padding":      40.0,              # horizontal padding inside band
    "pathway_seed":              42,                # NetworkX RNG seed
    "pathway_arrow_gap":         4.0,               # px between bbox edge and arrow tip
    "pathway_band_fill":         "#F7F9FB",
    "pathway_band_stroke":       "#C8D4DD",
    "pathway_band_stroke_width": 0.5,
    "pathway_band_label_color":  "#4A5C68",
    "pathway_band_label_size":   11,
    "pathway_band_label_family": "Helvetica, Arial, sans-serif",
    # Band-wrap knobs (V2). When a band has more entities than fit on one
    # row, _graph_positions wraps them onto additional rows. The compositor
    # reads these to grow the canvas accordingly.
    "pathway_max_per_row":       6,                 # entities per band row before wrap
    "pathway_row_v_gap":         16.0,              # px between wrapped rows in a band
    # V2 / L9: uniform scale factor applied to every entity's (w, h) at
    # render time. Scales bboxes used for arrow routing and row-height
    # calculation in lock-step with visual size, so figures stay consistent.
    # Default 1.0 → primitive defaults (byte-identical to V1 output).
    "pathway_entity_scale":      1.0,
    # V2 / L15: minimum clearance (px) between an entity's bbox edge and the
    # SVG canvas boundary. Centers are clamped after even-spacing so entities
    # near the canvas perimeter never render partially outside the viewport.
    "pathway_edge_margin":       8.0,
    # V2 / L1: same-band arrow routing. Adjacent same-band entities get a
    # straight arrow; a "skip" arrow whose straight shaft would cross an
    # intervening entity arches over (or under) the row instead. Overlapping
    # arches are stacked into distinct lanes so their corridors never collapse
    # onto one another. `arch_clearance` is the gap between the entity row and
    # the first lane; `arch_lane_gap` is the spacing between successive lanes.
    "pathway_arch_clearance":    12.0,
    "pathway_arch_lane_gap":     14.0,
    # LT1: ring (circular) layout for cyclic pathways. `ring_node_gap` is the
    # minimum clear gap between adjacent node bboxes along the ring; the radius
    # grows so N nodes fit without touching. `ring_min_radius` is a floor for
    # very small cycles. `ring_label_margin` reserves room outside the ring for
    # edge labels (pushed radially outward).
    "pathway_ring_node_gap":     28.0,
    "pathway_ring_min_radius":   120.0,
    "pathway_ring_label_margin": 72.0,
}


# ---------------------------------------------------------------------------
# V2 / L3: dynamic band height helpers
# ---------------------------------------------------------------------------

_BAND_BASELINE = 100.0   # px — matches v1: 600 / 6 bands = 100 px/band
_LABEL_MARGIN  =  40.0   # px — headroom for band label + top/bottom breathing room
_ENTITY_LABEL_FONT = 11.0  # px — default entity-label font (mirrors label_placement)


def _label_extent_w(label: str, font_size: float = _ENTITY_LABEL_FONT) -> float:
    """Estimated rendered width of a centered entity label.

    Mirrors ``label_placement._estimate_text_bbox`` (≈0.6 em/char) so the
    layout's idea of how wide a label draws matches what the legibility
    audit measures. Used to keep an entity's label inside the canvas / panel
    cell, not just its box (LT4).
    """
    return max(1, len(label)) * font_size * 0.6


def _clamp_center_x(
    x: float, lo_bound: float, hi_bound: float, half_extent: float
) -> float:
    """Clamp an entity center x so a ``half_extent``-wide footprint stays in bounds.

    ``lo_bound`` / ``hi_bound`` are the usable left/right edges (canvas inset by
    ``edge_margin``). When the footprint is wider than the slot (label wider than
    the whole cell), the bounds invert; we center it as the least-bad option
    rather than pinning it to one edge (LT4).
    """
    lo = lo_bound + half_extent
    hi = hi_bound - half_extent
    if lo > hi:
        return (lo_bound + hi_bound) / 2
    return max(lo, min(x, hi))


def _feedback_arc_dag(dg: nx.DiGraph) -> nx.DiGraph:
    """Return a DAG derived from *dg* by removing back-edges (DFS cycles).

    When *dg* is already a DAG this returns the same object unchanged (no
    copy). For cyclic graphs — feedback loops like ERK⊣RAF in a MAPK cascade
    — back-edges are stripped one at a time (the last edge of each detected
    cycle) until the graph is acyclic. The result is used only for
    topological seeding and sibling-spread; all original edges remain in
    `figure.relations` for arrow routing so feedback arrows are still drawn.
    """
    if nx.is_directed_acyclic_graph(dg):
        return dg
    dag = dg.copy()
    while not nx.is_directed_acyclic_graph(dag):
        try:
            cycle = nx.find_cycle(dag)
            dag.remove_edge(*cycle[-1][:2])
        except nx.NetworkXNoCycle:
            break
    return dag


def _max_topo_siblings(figure: Figure) -> int:
    """Return the max number of nodes sharing a topological rank in `figure`.

    Used by L20 to size the implicit-band height so vertically-spread siblings
    never clip each other. Returns 1 for non-DAGs or figures without edges
    (falls back to the normal BAND_BASELINE height in those cases).
    """
    if not figure.relations:
        return 1
    DG = nx.DiGraph()
    for e in figure.entities:
        DG.add_node(e.id)
    for r in figure.relations:
        DG.add_edge(r.source, r.target)
    dag = _feedback_arc_dag(DG)
    return max((len(list(gen)) for gen in nx.topological_generations(dag)), default=1)


# ---------------------------------------------------------------------------
# LT1: ring (circular) layout for cyclic pathways
# ---------------------------------------------------------------------------

def _is_pure_single_cycle(dg: nx.DiGraph) -> bool:
    """True if `dg` is one simple directed cycle through every node.

    A pure cycle has N nodes, N edges, every node in/out-degree exactly 1, and
    is strongly connected (Krebs: cit→iso→…→oaa→cit). This is the unambiguous
    case we ring automatically; branchy or convergent graphs do not qualify.
    """
    n = dg.number_of_nodes()
    if n < 3 or dg.number_of_edges() != n:
        return False
    if any(dg.in_degree(v) != 1 or dg.out_degree(v) != 1 for v in dg):
        return False
    return nx.is_strongly_connected(dg)


def _split_dangling(dg: nx.DiGraph) -> tuple[nx.DiGraph, list[str]]:
    """Partition `dg` into a cycle subgraph and dangling entry nodes.

    Dangling nodes are those with in-degree 0 (pure entry points — they feed
    into the cycle but receive no edges from it). Removal is iterated until
    stable, so chains of entry nodes (A→B→Citrate where A and B are both
    external) are fully stripped. Returns (cycle_subgraph, dangling_list).
    The cycle_subgraph is a copy; `dg` is not mutated.
    """
    working = dg.copy()
    dangling: list[str] = []
    while True:
        leaves = [v for v in working if working.in_degree(v) == 0]
        if not leaves:
            break
        dangling.extend(leaves)
        working.remove_nodes_from(leaves)
    return working, dangling


def _ring_order(figure: Figure) -> tuple[list[str], list[str]] | None:
    """Return (ring_order, dangling_nodes) if this figure should use ring layout.

    Ring layout applies to compartment-free pathways when either:
    - The full relation graph is a pure single cycle (auto-detected). All nodes
      must have in/out-degree exactly 1 — no dandling entry nodes. This is the
      strict unambiguous case (e.g. an 8-node Krebs cycle with no inputs shown).
    - `layout_hint == "circular"` forces ring mode. In this case dangling entry
      nodes (in-degree 0) are stripped from the cycle graph and placed outside
      the ring near their ring target. Use this mode when you need to show
      metabolic inputs (e.g. Acetyl-CoA feeding into Citrate).

    Returns None if ring layout does not apply or the cycle has <3 nodes.
    """
    if figure.compartments:  # real compartments → keep band layout
        if figure.layout_hint == "circular":
            warnings.warn(
                "layout_hint='circular' ignored: ring layout requires a "
                "compartment-free figure.",
                UserWarning,
                stacklevel=2,
            )
        return None

    DG = nx.DiGraph()
    for e in figure.entities:
        DG.add_node(e.id)
    for r in figure.relations:
        DG.add_edge(r.source, r.target)

    forced = figure.layout_hint == "circular"

    if forced:
        # Strip dangling entry nodes so the cycle subgraph can be detected.
        cycle_dg, dangling = _split_dangling(DG)
        if not _is_pure_single_cycle(cycle_dg):
            return None
        if cycle_dg.number_of_nodes() < 3:
            return None
        dag = _feedback_arc_dag(cycle_dg)
    else:
        # Strict auto-detect: all nodes must be on the cycle.
        if not _is_pure_single_cycle(DG):
            return None
        if DG.number_of_nodes() < 3:
            return None
        dangling = []
        dag = _feedback_arc_dag(DG)

    ranks = rank_nodes(dag)
    order_idx = order_within_ranks(dag, ranks)
    order = sorted(ranks, key=lambda n: (ranks[n], order_idx.get(n, 0), n))
    return order, dangling


def _ring_geometry(
    n: int,
    max_entity_w: float,
    max_entity_h: float,
    params: dict,
    origin: tuple[float, float],
) -> tuple[tuple[float, float], tuple[float, float], float]:
    """Return ((canvas_w, canvas_h), (center_x, center_y), radius) for an
    n-node ring. Radius is chosen so adjacent node bboxes keep at least
    `ring_node_gap` clear; the canvas is square with room for outward labels.
    """
    node_span = max(max_entity_w, max_entity_h)
    node_gap = float(params["pathway_ring_node_gap"])
    min_radius = float(params["pathway_ring_min_radius"])
    label_margin = float(params["pathway_ring_label_margin"])
    edge_margin = float(params["pathway_edge_margin"])

    # Chord between adjacent nodes is 2*R*sin(pi/n); require it to clear the
    # node span plus the gap. Solve for R.
    chord_min = node_span + node_gap
    radius = max(min_radius, chord_min / (2.0 * math.sin(math.pi / n)))

    side = 2.0 * (radius + node_span / 2.0 + edge_margin + label_margin)
    ox, oy = origin
    center = (ox + side / 2.0, oy + side / 2.0)
    return (side, side), center, radius


def _ring_positions(
    order: list[str],
    dangling: list[str],
    entity_by_id: dict,
    entity_sizes: dict,
    params: dict,
    origin: tuple[float, float],
    relations: list,
) -> tuple[dict[str, tuple[float, float]], tuple[float, float], tuple[float, float]]:
    """Place ring nodes evenly on a circle; place dangling entry nodes outside.

    Ring nodes sit at angle `-pi/2 + 2*pi*i/n` (first node at top, clockwise).
    Dangling nodes (in-degree 0) are positioned radially outside the ring,
    offset from their first ring target at 1.6× the ring radius from center.
    Multiple dangling nodes targeting the same ring node are fanned ±30°.
    Returns (positions, canvas, center).
    """
    n = len(order)
    all_nodes = list(order) + list(dangling)
    max_w = max(entity_sizes[entity_by_id[i].type][0] for i in all_nodes)
    max_h = max(entity_sizes[entity_by_id[i].type][1] for i in all_nodes)
    canvas, center, radius = _ring_geometry(n, max_w, max_h, params, origin)
    cx, cy = center

    # Place ring nodes on circle
    ring_theta: dict[str, float] = {}
    positions: dict[str, tuple[float, float]] = {}
    for i, node in enumerate(order):
        theta = -math.pi / 2.0 + 2.0 * math.pi * i / n
        ring_theta[node] = theta
        positions[node] = (cx + radius * math.cos(theta), cy + radius * math.sin(theta))

    if dangling:
        # Build map: ring_target → list of dangling nodes pointing to it
        target_map: dict[str, list[str]] = {}
        for d in dangling:
            targets = [r.target for r in relations if r.source == d and r.target in positions]
            ring_target = targets[0] if targets else order[0]
            target_map.setdefault(ring_target, []).append(d)

        outer_radius = radius * 1.6
        fan_step = math.radians(30)
        for ring_target, dlist in target_map.items():
            base_theta = ring_theta.get(ring_target, -math.pi / 2.0)
            offsets = [0.0] if len(dlist) == 1 else [
                fan_step * (i - (len(dlist) - 1) / 2.0) for i in range(len(dlist))
            ]
            for d, offset in zip(dlist, offsets):
                theta = base_theta + offset
                positions[d] = (cx + outer_radius * math.cos(theta),
                                cy + outer_radius * math.sin(theta))

    return positions, canvas, center


def _compute_band_heights(
    compartments: list[Compartment],
    by_band: dict[str, list],
    max_per_row: int,
    row_v_gap: float,
    max_entity_h: float,
) -> list[float]:
    """Return minimum pixel height for each compartment band (in declaration order).

    Each band receives enough vertical room for its wrapped entity rows plus a
    fixed label/margin allowance. Bands with no entities get the BAND_BASELINE
    floor so they don't collapse to zero. The BAND_BASELINE (100 px) matches
    the implicit per-band allocation in v1 (600 px ÷ 6 bands), so single-row
    figures produce the same geometry as before.
    """
    heights = []
    for c in compartments:
        ents = by_band.get(c.id, [])
        n_rows = max(1, (len(ents) + max_per_row - 1) // max_per_row)
        h = max(_BAND_BASELINE, n_rows * (max_entity_h + row_v_gap) + _LABEL_MARGIN)
        heights.append(h)
    return heights


def compute_pathway_canvas(
    figure: Figure,
    layout_params: dict | None = None,
) -> tuple[float, float]:
    """Return the SVG (width, height) needed to contain this pathway figure.

    Takes entity scale, max-per-row, and row-gap into account. Both
    ``layout_pathway`` (for band geometry) and the compositor (for SVG
    viewport sizing) call this so they always agree on the canvas size.

    Width is always the floor (default 800 px); height grows when any band
    needs more than one entity row or when there are many compartments.

    Args:
        figure: The pathway IR Figure.
        layout_params: Optional overlay onto PATHWAY_DEFAULT_PARAMS. Pass
            the same dict you would pass to ``layout_pathway`` so the canvas
            is computed with the same knobs.

    Returns:
        ``(width, height)`` tuple. Both dimensions are at least the
        ``pathway_canvas`` floor from PATHWAY_DEFAULT_PARAMS.
    """
    params = {**PATHWAY_DEFAULT_PARAMS, **(layout_params or {})}
    min_w, min_h = params["pathway_canvas"]

    if not figure.entities:
        return (float(min_w), float(min_h))

    max_per_row = int(params["pathway_max_per_row"])
    row_v_gap   = float(params["pathway_row_v_gap"])
    scale       = float(params["pathway_entity_scale"])

    raw_max_w, raw_max_h = max_entity_bbox(figure)
    max_entity_w = raw_max_w * scale
    max_entity_h = raw_max_h * scale
    padding     = float(params["pathway_band_padding"])
    edge_margin = float(params["pathway_edge_margin"])

    # LT1: ring layout → square canvas sized from the ring geometry.
    _ring_result = _ring_order(figure)
    if _ring_result is not None:
        _ring_nodes, _ring_dangling = _ring_result
        canvas, _center, _radius = _ring_geometry(
            len(_ring_nodes), max_entity_w, max_entity_h, params,
            params["pathway_origin"],
        )
        return canvas

    compartments, location_map = _resolve_compartments(figure)
    by_band: dict[str, list] = {}
    for e in figure.entities:
        by_band.setdefault(location_map[e.id], []).append(e)

    heights = _compute_band_heights(
        compartments, by_band,
        max_per_row=max_per_row,
        row_v_gap=row_v_gap,
        max_entity_h=max_entity_h,
    )

    # L20: for single-implicit-band figures, ensure the band is tall enough
    # to vertically spread the widest sibling group without overlap.
    if len(compartments) == 1 and compartments[0].id == _IMPLICIT_COMPARTMENT_ID:
        max_sibs = _max_topo_siblings(figure)
        if max_sibs > 1:
            edge_margin = float(params["pathway_edge_margin"])
            l20_h = max_sibs * (max_entity_h + row_v_gap) + _LABEL_MARGIN + 2 * edge_margin
            heights = [max(heights[0], l20_h)]

    # L21: required width = widest row across all bands.
    # Each row of n_cols entities needs: 2*padding + n_cols*entity_w
    # + (n_cols-1)*inter_gap.  inter_gap = 2*edge_margin so the spacing
    # scales with the same knob that clamps entity bboxes to the canvas edge.
    inter_gap = max(2.0 * edge_margin, 20.0)
    required_w = float(min_w)
    for ents in by_band.values():
        n_cols = min(len(ents), max_per_row)
        if n_cols < 1:
            continue
        row_w = 2.0 * padding + n_cols * max_entity_w + (n_cols - 1) * inter_gap
        required_w = max(required_w, row_w)

    return (required_w, max(len(heights) * _BAND_BASELINE, sum(heights)))


# ---------------------------------------------------------------------------
# V2 / L4: per-arrow annotation glyph helpers
# (defined before RELATION_TO_ARROW so _phosphorylation_arrow is resolvable
#  at module load time)
# ---------------------------------------------------------------------------

# Style fallbacks for the phosphorylation badge.  These keys are present in
# proteins.DEFAULT_STYLE; replicated here so pathway_layout stays independent
# of the proteins module.
_PHOSPHO_BADGE_DEFAULTS: dict = {
    "kinase_badge_fill":       "#D32F2F",
    "kinase_badge_text_color": "#FFFFFF",
    "label_font_size":          11,
    "label_font_family":       "Helvetica, Arial, sans-serif",
    "label_font_color":        "#1A1A1A",
    "protein_stroke":          "#1F4E79",
    "protein_stroke_width":     0.5,
}


def _midpoint_of_path(
    waypoints: list[tuple[float, float]],
) -> tuple[float, float]:
    """Return the geometric midpoint of a polyline (list of ≥ 2 points).

    For a two-point path this is the exact midpoint of the segment. For a
    multi-waypoint elbow path it returns the midpoint of the middle segment
    so the badge sits on the longest visible shaft rather than at a corner.
    """
    if len(waypoints) < 2:
        return waypoints[0]
    if len(waypoints) == 2:
        (x1, y1), (x2, y2) = waypoints
        return ((x1 + x2) / 2, (y1 + y2) / 2)
    mid_i = len(waypoints) // 2
    (x1, y1) = waypoints[mid_i - 1]
    (x2, y2) = waypoints[mid_i]
    return ((x1 + x2) / 2, (y1 + y2) / 2)


def _relation_glyph(
    group: svgwrite.container.Group,
    cx: float,
    cy: float,
    text: str,
    style: dict,
) -> None:
    """Append a small circular badge carrying ``text`` to ``group`` at (cx, cy).

    The badge uses ``kinase_badge_fill`` / ``kinase_badge_text_color`` style
    keys so it picks up preset overrides automatically. Badge radius scales
    with ``label_font_size`` so it stays proportional across presets.
    """
    font_size = float(style.get("label_font_size", 11))
    r = max(7.0, font_size * 0.75)
    badge = svgwrite.shapes.Circle(
        center=(cx, cy), r=r,
        fill=style.get("kinase_badge_fill", "#D32F2F"),
        stroke=style.get("protein_stroke", "#1F4E79"),
    )
    badge["stroke-width"] = float(style.get("protein_stroke_width", 0.5))
    group.add(badge)
    group.add(_centered_label(
        text, cx, cy, style,
        weight="bold",
        color=style.get("kinase_badge_text_color", "#FFFFFF"),
        size_override=font_size * 0.9,
    ))


def _phospho_badge_geom(
    pts: list[tuple[float, float]],
    style: dict,
) -> tuple[tuple[float, float], float]:
    """Return the ('P' badge center, radius) for a phosphorylation shaft.

    Single source of truth for the badge placement: both
    ``_phosphorylation_arrow`` (which draws it) and
    ``phospho_badge_occupied_bbox`` (which reserves its footprint in the
    label engine) call this, so the rendered glyph and the collision box
    can never drift apart. Radius mirrors ``_relation_glyph``.
    """
    cx, cy = _midpoint_of_path(pts)
    font_size = float(style.get("label_font_size", 11))
    r = max(7.0, font_size * 0.75)
    return (cx, cy), r


def _phosphorylation_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    *,
    style_dict: dict | None = None,
    waypoints: list[tuple[float, float]] | None = None,
) -> svgwrite.container.Group:
    """Activation arrow annotated with a 'P' badge at the shaft midpoint.

    V2 / L4. Calls ``arrows.activation_arrow`` for the shaft/head, then
    overlays a phosphorylation badge so the PHOSPHORYLATES relation type is
    visually distinct from a plain ACTIVATES arrow.
    """
    g = arrows.activation_arrow(start, end, style_dict=style_dict, waypoints=waypoints)
    s = {**_PHOSPHO_BADGE_DEFAULTS, **(style_dict or {})}
    pts = waypoints if waypoints else [start, end]
    (cx, cy), _r = _phospho_badge_geom(pts, s)
    _relation_glyph(g, cx, cy, "P", s)
    return g


def phospho_badge_occupied_bbox(entry) -> tuple[float, float, float, float] | None:
    """Bbox of the 'P' badge for a phosphorylation-arrow ``LayoutEntry``.

    LT3. The badge carries a ``<text>`` 'P' that the legibility audit treats
    as a label; without reserving its footprint, a relation label anchored at
    the same shaft midpoint renders on top of it. ``label_placement._entry_bbox``
    calls this so the badge joins the placement ``occupied`` set and labels are
    steered clear. Returns ``None`` for any non-phosphorylation entry.
    """
    if entry.primitive is not _phosphorylation_arrow:
        return None
    start, end = entry.args
    waypoints = entry.kwargs.get("waypoints")
    style = {**_PHOSPHO_BADGE_DEFAULTS, **(entry.kwargs.get("style_dict") or {})}
    pts = waypoints if waypoints else [start, end]
    (cx, cy), r = _phospho_badge_geom(pts, style)
    return (cx - r, cy - r, cx + r, cy + r)


# ---------------------------------------------------------------------------
# Dispatch tables (public so tests + future archetypes can introspect them).
# ---------------------------------------------------------------------------

RELATION_TO_ARROW: dict[RelationType, Callable[..., svgwrite.container.Group]] = {
    RelationType.ACTIVATES:      arrows.activation_arrow,
    RelationType.INHIBITS:       arrows.inhibition_arrow,
    RelationType.BINDS:          arrows.binding_arrow,
    RelationType.TRANSLOCATES:   arrows.translocation_arrow,
    RelationType.PHOSPHORYLATES: _phosphorylation_arrow,  # V2/L4: annotated with 'P' badge
    RelationType.TRANSCRIBES:    arrows.activation_arrow,
    RelationType.CATALYZES:      arrows.catalysis_arrow,
    RelationType.CLEAVES:        arrows.cleavage_arrow,
    RelationType.TRANSPORTS:     arrows.transport_arrow,
    RelationType.RECRUITS:       arrows.recruitment_arrow,
    RelationType.GENERIC:        arrows.activation_arrow,
}


_IMPLICIT_COMPARTMENT_ID = "__implicit__"


# Archetypes that share the "entity-graph laid out across compartment bands"
# shape. All of these route to layout_pathway; the panel engine relies on
# this for sub-archetype dispatch, and standalone callers can pass any of
# them too. REACTION_SCHEME stays out: it has a dedicated engine and a
# different kwargs contract (smiles_map).
_PATHWAY_COMPATIBLE_ARCHETYPES = {
    Archetype.PATHWAY,
    Archetype.WORKFLOW,
    Archetype.CELLULAR_SCHEMATIC,
    Archetype.MECHANISM_CARTOON,
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _resolve_compartments(
    figure: Figure,
) -> tuple[list[Compartment], dict[str, str]]:
    """Return (ordered_compartments, entity_id → band_id).

    If `figure.compartments` is empty, synthesizes one implicit band so
    every entity has a band. When compartments are declared but an entity
    has `location is None`, the entity is assigned to the first declared
    compartment (deterministic fallback documented in the module
    docstring).
    """
    if not figure.compartments:
        implicit = Compartment(
            id=_IMPLICIT_COMPARTMENT_ID,
            type=CompartmentType.CUSTOM,
            label="",
        )
        return [implicit], {e.id: implicit.id for e in figure.entities}

    compartments = list(figure.compartments)
    fallback = compartments[0].id
    location_map = {e.id: (e.location or fallback) for e in figure.entities}
    return compartments, location_map


def _compute_bands(
    compartments: list[Compartment],
    canvas: tuple[float, float],
    origin: tuple[float, float],
    *,
    band_heights: list[float] | None = None,
) -> dict[str, tuple[float, float]]:
    """Return compartment id → (band_top_y, band_bottom_y).

    When ``band_heights`` is provided (V2/L3 dynamic mode), each band gets
    exactly the height specified (in compartment declaration order). The
    canvas height is ignored in this mode — the caller is responsible for
    setting it to ``sum(band_heights)`` before passing it on.

    When ``band_heights`` is None (v1 fallback / user-supplied canvas), bands
    evenly partition the canvas height in declaration order.
    """
    _, oy = origin
    if band_heights is None:
        _, h = canvas
        bh = h / len(compartments)
        heights: list[float] = [bh] * len(compartments)
    else:
        heights = band_heights

    result: dict[str, tuple[float, float]] = {}
    y = oy
    for c, h in zip(compartments, heights):
        result[c.id] = (y, y + h)
        y += h
    return result


def _graph_positions(
    figure: Figure,
    bands: dict[str, tuple[float, float]],
    location_map: dict[str, str],
    canvas: tuple[float, float],
    origin: tuple[float, float],
    padding: float,
    seed: int,
    max_per_row: int = 6,
    row_v_gap: float = 16.0,
    entity_sizes: dict | None = None,
    edge_margin: float = 8.0,
) -> dict[str, tuple[float, float]]:
    """Compute (x, y) for every entity.

    y is the vertical center of the entity's compartment band (snap-to-band
    enforces compartment containment). x is derived from a seeded
    `nx.spring_layout` to give the relation graph a say in horizontal
    ordering, then evenly spaced inside the band's horizontal extent so
    primitives don't overlap.

    Band wrap (v2): when a band holds more than `max_per_row` entities,
    rows are stacked vertically around the band's center line with
    `row_v_gap` px of vertical breathing room between row centers.
    Backwards-compatible for small bands: `n <= max_per_row` produces a
    single row at the band center, byte-identical to the v1 placement.
    """
    G = nx.Graph()
    DG = nx.DiGraph()
    for e in figure.entities:
        G.add_node(e.id)
        DG.add_node(e.id)
    for r in figure.relations:
        G.add_edge(r.source, r.target)
        DG.add_edge(r.source, r.target)

    # Seed spring_layout with topological-rank x positions so left-to-right
    # order reflects the actual flow direction (A→B→C instead of a U-shape).
    # L23: for cyclic graphs (feedback edges like ERK⊣RAF), _feedback_arc_dag
    # strips back-edges first, so a cycle no longer falls back to unconstrained
    # spring and renders the cascade backwards.
    _dag_for_ranking: nx.DiGraph | None = None
    init_pos: dict | None = None
    if G.number_of_edges():
        _dag_for_ranking = _feedback_arc_dag(DG)
        generations = list(nx.topological_generations(_dag_for_ranking))
        max_rank = max(len(generations) - 1, 1)
        init_pos = {}
        for rank, gen in enumerate(generations):
            for node in gen:
                init_pos[node] = (rank / max_rank, 0.0)

    # spring_layout is only meaningful when there are edges to relax; with no
    # relations the result is rotationally symmetric noise that gets discarded
    # by the even-spacing pass below. Skip it for an isolated-entity figure.
    raw = (
        nx.spring_layout(G, seed=seed, pos=init_pos)
        if G.number_of_edges()
        else {}
    )

    w, _ = canvas
    ox, _ = origin
    inner_w = max(w - 2 * padding, 1.0)
    # Row height for vertical stacking. Use the max entity height in the
    # figure so kinase (32) and receptor (60) entities don't clip rows
    # narrower than themselves. When entity_sizes is provided (V2/L9 scaled
    # bboxes), use that table so row height tracks the rendered entity size.
    _sizes = entity_sizes if entity_sizes is not None else ENTITY_BBOX
    row_h = max(_sizes[e.type][1] for e in figure.entities) if figure.entities else 30.0

    by_band: dict[str, list[Entity]] = {}
    for e in figure.entities:
        by_band.setdefault(location_map[e.id], []).append(e)

    # L20: when the figure has a single implicit compartment (no real spatial
    # context), spread entities vertically by their position among siblings at
    # the same topological rank — hub (N→1), branch (1→N), and convergence
    # topologies otherwise collapse to a flat row because every entity gets
    # the same center_y. When real compartments exist, band-snap is preserved.
    use_topo_y_mode = len(bands) == 1 and _IMPLICIT_COMPARTMENT_ID in bands

    # LT2: layered (Sugiyama-style) layout for compartment-free DAGs. Rank each
    # node by longest-path depth (x column) and order nodes within a rank to
    # minimise edge crossings (y position). This replaces the spring-x ordering
    # + flat sibling spread so convergence reads as columns funnelling into one
    # node and divergence as one column fanning out. Only active when there are
    # no real compartments and the graph has edges to rank; otherwise the
    # band-snap path below is used unchanged.
    use_layered = use_topo_y_mode and _dag_for_ranking is not None
    layered_rank: dict[str, int] = {}
    layered_order: dict[str, int] = {}
    layered_rank_size: dict[int, int] = {}
    layered_max_rank = 0
    if use_layered:
        # LT10: tighten ASAP ranks toward consumers so a no-predecessor cofactor
        # (e.g. coagulation Factor V → Prothrombin) sits beside the node it
        # modifies instead of pinned to column 0 with a long over-arching edge.
        layered_rank = tighten_ranks(_dag_for_ranking, rank_nodes(_dag_for_ranking))
        layered_order = order_within_ranks(_dag_for_ranking, layered_rank)
        layered_max_rank = max(layered_rank.values()) if layered_rank else 0
        for r in layered_rank.values():
            layered_rank_size[r] = layered_rank_size.get(r, 0) + 1

    pos: dict[str, tuple[float, float]] = {}
    for band_id, ents in by_band.items():
        band_top, band_bottom = bands[band_id]
        center_y = (band_top + band_bottom) / 2
        # spring_layout's x decides ordering inside the band; ties broken
        # by id for determinism.
        sorted_ents = sorted(
            ents,
            key=lambda e: (raw.get(e.id, (0.0, 0.0))[0], e.id),
        )
        n = len(sorted_ents)
        n_rows = max(1, (n + max_per_row - 1) // max_per_row)

        for i, e in enumerate(sorted_ents):
            ew, eh = _sizes.get(e.type, (30.0, 30.0))

            # LT2: layered DAG placement — x from longest-path rank column,
            # y from crossing-reduced order within the rank.
            if use_layered and e.id in layered_rank:
                rank = layered_rank[e.id]
                if layered_max_rank > 0:
                    x = ox + padding + inner_w * rank / layered_max_rank
                else:
                    x = ox + w / 2
                # Clamp by box width only. The label-fit ladder keeps a
                # centered label inside the box (rungs 0-3) or externalizes it
                # (rung 4, placed by the bounds-aware label engine), so the old
                # LT4 centered-label-extent clamp is obsolete here — and it
                # forced wide-label neighbours on adjacent ranks to overlap
                # (their boxes were yanked inward until they collided, which in
                # turn made the connecting arrow render backwards inside a box).
                half_x = ew / 2
                # Bug 3 (canvas-side tail): a receptor's label sits LEFT of its
                # body, so push the left bound in by that overhang to keep the
                # label on-canvas when the receptor lands in the first column.
                lo_x = ox + edge_margin + _left_label_extent(e)
                x = _clamp_center_x(x, lo_x, ox + w - edge_margin, half_x)
                k = layered_rank_size.get(rank, 1)
                t = (layered_order.get(e.id, 0) + 0.5) / k
                usable_top    = band_top    + edge_margin + eh / 2
                usable_bottom = band_bottom - edge_margin - eh / 2
                if usable_bottom > usable_top:
                    y = usable_top + t * (usable_bottom - usable_top)
                else:
                    y = center_y
                pos[e.id] = (x, y)
                continue

            row = i // max_per_row
            col = i % max_per_row
            # cols_in_row matters only for the final, possibly-partial row.
            cols_in_row = min(max_per_row, n - row * max_per_row)
            if cols_in_row == 1:
                x = ox + w / 2
            else:
                x = ox + padding + inner_w * col / (cols_in_row - 1)
            # L15: clamp centers so the entity *box* stays inside the canvas.
            # The label is no longer part of this clamp: the fit ladder fits it
            # to the box or externalizes it (placed by the bounds-aware label
            # engine), so the old LT4 label-extent term only forced box overlap.
            half_x = ew / 2
            # Bug 3 (canvas-side tail): keep a left-edge receptor's left-anchored
            # label on-canvas by reserving its overhang in the left clamp bound.
            lo_x = ox + edge_margin + _left_label_extent(e)
            x = _clamp_center_x(x, lo_x, ox + w - edge_margin, half_x)

            # Stack rows vertically, centered around the band center.
            y_offset = (row - (n_rows - 1) / 2) * (row_h + row_v_gap)
            raw_y = center_y + y_offset
            y = max(
                band_top + edge_margin + eh / 2,
                min(raw_y, band_bottom - edge_margin - eh / 2),
            )
            pos[e.id] = (x, y)
    return pos


_RECEPTOR_LABEL_GAP = 6.0      # px — matches the hard-coded gap in receptor() primitive
_RECEPTOR_FONT_SIZE = 11.0     # matches _DEFAULT_LABEL_STYLE in label_placement
_HIT_TEST_MARGIN = 8.0         # px — expanded half-extent for arch hit-test (Bug 4)


def _arrow_bbox_for_entity(
    entity,
    base_bbox: tuple[float, float],
) -> tuple[float, float]:
    """Effective (w, h) for arrow-endpoint routing.

    For receptor entities the label sits LEFT of the body, outside the 28×60
    body bbox.  Inflate the width symmetrically so _bbox_exit_point routes
    the arrow past the label.  The right-side overshoot is harmless because
    no receptor label sits on the right side.
    """
    if entity.type != EntityType.RECEPTOR:
        return base_bbox
    bw, bh = base_bbox
    label_ext = _left_label_extent(entity)
    return (bw + 2.0 * label_ext, bh)


def _left_label_extent(entity) -> float:
    """Px occupied LEFT of a receptor's body bbox by its left-anchored label.

    The receptor primitive draws its label with ``text-anchor="end"`` at
    ``cx - ec_w/2 - 6`` (see ``proteins.receptor``), so the label spills
    ``gap + label_width`` past the body's left edge. Estimate that overhang
    so placement can keep the label on-canvas (Bug 3 canvas-side tail). Mirror
    the same width heuristic used by ``_arrow_bbox_for_entity``. Returns 0 for
    non-receptor entities (no left-side label overhang).
    """
    if entity.type != EntityType.RECEPTOR:
        return 0.0
    label_w = max(1, len(entity.label)) * _RECEPTOR_FONT_SIZE * 0.6
    return _RECEPTOR_LABEL_GAP + label_w


def _bbox_exit_point(
    center: tuple[float, float],
    half_w: float,
    half_h: float,
    target: tuple[float, float],
    gap: float = 0.0,
) -> tuple[float, float]:
    """Where the line `center → target` exits an axis-aligned bbox.

    Returns `center` itself if the two points coincide. The optional `gap`
    pushes the exit point another `gap` px along the direction (so an
    arrow's head visually clears the shape). The gap is clamped to the
    line's actual length to avoid overshooting past `target`.
    """
    cx, cy = center
    tx, ty = target
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return center
    inv_x = half_w / abs(dx) if dx else float("inf")
    inv_y = half_h / abs(dy) if dy else float("inf")
    t_edge = min(inv_x, inv_y)
    length = (dx * dx + dy * dy) ** 0.5
    t_gap = gap / length if length else 0.0
    t = min(t_edge + t_gap, 1.0)
    return (cx + t * dx, cy + t * dy)


def _arrow_endpoints(
    src_center: tuple[float, float],
    src_bbox: tuple[float, float],
    tgt_center: tuple[float, float],
    tgt_bbox: tuple[float, float],
    gap: float,
) -> tuple[tuple[float, float], tuple[float, float]]:
    """Inset both ends of a relation arrow to their entity bbox edges + gap."""
    src_w, src_h = src_bbox
    tgt_w, tgt_h = tgt_bbox
    start = _bbox_exit_point(src_center, src_w / 2, src_h / 2, tgt_center, gap)
    end = _bbox_exit_point(tgt_center, tgt_w / 2, tgt_h / 2, src_center, gap)
    return start, end


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


def _orthogonal_waypoints(
    src_center: tuple[float, float],
    src_bbox: tuple[float, float],
    src_band: tuple[float, float],
    tgt_center: tuple[float, float],
    tgt_bbox: tuple[float, float],
    tgt_band: tuple[float, float],
    gap: float,
) -> list[tuple[float, float]]:
    """Compute a 4-point orthogonal (elbow) path from src to tgt.

    For entities in different bands the path travels through the clear
    corridor between the two bands (no entities occupy that space), so
    it is guaranteed not to pass through any third entity box.

    For entities in the same band the path routes through a corridor
    above the band top (outside the band), which may briefly exit the
    canvas for the top-most band but is still rendered correctly by SVG.

    Returns a 4-element list: [tail_exit, elbow_src, elbow_tgt, head_enter].
    The first and last points land on the bbox perimeters of source and
    target respectively; the middle two define the horizontal corridor leg.
    """
    sx, sy = src_center
    tx, ty = tgt_center
    shw, shh = src_bbox[0] / 2, src_bbox[1] / 2
    thw, thh = tgt_bbox[0] / 2, tgt_bbox[1] / 2
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def layout_pathway(
    figure: Figure,
    layout_params: dict | None = None,
    style_dict: dict | None = None,
) -> list[LayoutEntry]:
    """Lay out an IR PATHWAY Figure as a list of LayoutEntry tuples.

    Args:
        figure: IR Figure with archetype=PATHWAY, non-empty entities.
            Compartments are optional (single implicit band synthesized
            when omitted). Relations are optional (isolated-entity
            pathways still produce a layout).
        layout_params: Optional overlay onto PATHWAY_DEFAULT_PARAMS.
            Notable keys: `pathway_canvas`, `pathway_seed`.
        style_dict: Optional preset overlay forwarded to every primitive
            and to `_compartment_band`.

    Returns:
        A list of LayoutEntry tuples in render order: compartment bands
        (background) → entities → relation arrows.

    Raises:
        ValueError: figure.archetype is not PATHWAY, or entities is empty.
    """
    if figure.archetype not in _PATHWAY_COMPATIBLE_ARCHETYPES:
        raise ValueError(
            f"layout_pathway requires archetype in "
            f"{sorted(a.value for a in _PATHWAY_COMPATIBLE_ARCHETYPES)}, "
            f"got {figure.archetype!r}"
        )
    if not figure.entities:
        raise ValueError("layout_pathway requires a non-empty entities list")

    params = {**PATHWAY_DEFAULT_PARAMS, **(layout_params or {})}
    canvas = params["pathway_canvas"]
    origin = params["pathway_origin"]

    # V2 / L9: build effective per-type bboxes by applying pathway_entity_scale
    # to every ENTITY_BBOX entry. Used for arrow routing, row-height calculation,
    # and the explicit `size=` kwarg forwarded to entity primitives. At the
    # default scale of 1.0 this is byte-identical to the V1 output.
    scale = float(params["pathway_entity_scale"])
    effective_bbox: dict = {
        t: (w * scale, h * scale)
        for t, (w, h) in ENTITY_BBOX.items()
    }

    compartments, location_map = _resolve_compartments(figure)
    entity_by_id = {e.id: e for e in figure.entities}

    # LT1: ring layout for compartment-free cyclic pathways. Nodes are placed
    # on a circle and arrows drawn as straight chords between adjacent nodes,
    # so the cycle reads as a ring instead of a band with a long closing arch.
    _ring_result = _ring_order(figure)
    ring_mode = _ring_result is not None
    ring_order: list[str] = []
    ring_dangling: list[str] = []
    if ring_mode:
        ring_order, ring_dangling = _ring_result  # type: ignore[misc]
        positions, canvas, _ring_center = _ring_positions(
            ring_order, ring_dangling, entity_by_id, effective_bbox, params,
            params["pathway_origin"], figure.relations,
        )
        bands = {}

    # V2 / L3: compute per-band heights dynamically unless the caller
    # explicitly supplied a pathway_canvas override (honour their envelope).
    _user_set_canvas = "pathway_canvas" in (layout_params or {})
    if ring_mode:
        pass  # ring positions/canvas already set above
    elif _user_set_canvas:
        per_band_heights = None  # fall back to equal-split of supplied canvas
    else:
        by_band_for_heights: dict[str, list] = {}
        for e in figure.entities:
            by_band_for_heights.setdefault(location_map[e.id], []).append(e)
        max_entity_h = max(effective_bbox[e.type][1] for e in figure.entities)
        per_band_heights = _compute_band_heights(
            compartments, by_band_for_heights,
            max_per_row=int(params["pathway_max_per_row"]),
            row_v_gap=float(params["pathway_row_v_gap"]),
            max_entity_h=max_entity_h,
        )
        # L20: grow single-implicit-band height for hub/branch topologies.
        if len(compartments) == 1 and compartments[0].id == _IMPLICIT_COMPARTMENT_ID:
            max_sibs = _max_topo_siblings(figure)
            if max_sibs > 1:
                l20_h = (max_sibs * (max_entity_h + float(params["pathway_row_v_gap"]))
                         + _LABEL_MARGIN + 2.0 * float(params["pathway_edge_margin"]))
                per_band_heights = [max(per_band_heights[0], l20_h)]
        total_h = max(canvas[1], sum(per_band_heights))
        # L21: grow width to fit the widest entity row (mirrors compute_pathway_canvas).
        max_entity_w = max(effective_bbox[e.type][0] for e in figure.entities)
        inter_gap = max(2.0 * float(params["pathway_edge_margin"]), 20.0)
        required_w = canvas[0]
        for ents_list in by_band_for_heights.values():
            n_cols = min(len(ents_list), int(params["pathway_max_per_row"]))
            if n_cols < 1:
                continue
            row_w = (2.0 * float(params["pathway_band_padding"])
                     + n_cols * max_entity_w
                     + (n_cols - 1) * inter_gap)
            required_w = max(required_w, row_w)
        canvas = (required_w, total_h)

    if not ring_mode:
        bands = _compute_bands(compartments, canvas, origin, band_heights=per_band_heights)
        positions = _graph_positions(
            figure, bands, location_map, canvas, origin,
            padding=float(params["pathway_band_padding"]),
            seed=int(params["pathway_seed"]),
            max_per_row=int(params["pathway_max_per_row"]),
            row_v_gap=float(params["pathway_row_v_gap"]),
            entity_sizes=effective_bbox,
            edge_margin=float(params["pathway_edge_margin"]),
        )

    style_kwargs: dict = {"style_dict": style_dict} if style_dict is not None else {}
    cw, _ = canvas
    ox, _ = origin
    arrow_gap = float(params["pathway_arrow_gap"])

    def _entry(
        primitive: Callable, args: tuple, kwargs: dict, ir_id: str | None = None
    ) -> LayoutEntry:
        return LayoutEntry(primitive, args, kwargs, position=(0.0, 0.0), ir_id=ir_id)

    entries: list[LayoutEntry] = []

    # Bands take the full merged params so band-visual overrides via
    # layout_params land here; entity/arrow primitives take only style_dict.
    # V2/L8: pass compartment_type + style_dict for organelle border decorations.
    # LT1: ring layout draws no compartment band (the figure is compartment-free).
    for c in compartments if not ring_mode else []:
        top, bottom = bands[c.id]
        band_kwargs: dict = {
            "params": params,
            "compartment_type": c.type,
        }
        if style_dict is not None:
            band_kwargs["style_dict"] = style_dict
        entries.append(_entry(
            _compartment_band,
            (c.label, ox, top, cw, bottom - top),
            band_kwargs,
            ir_id=c.id,
        ))

    for e in figure.entities:
        # V2 / L6: per-entity primitive override via entity.style["primitive"].
        prim_override_name = (e.style or {}).get("primitive")
        if prim_override_name is not None:
            override_prim = PRIMITIVE_REGISTRY.get(prim_override_name)
            if override_prim is None:
                warnings.warn(
                    f"Entity {e.id!r}: unknown primitive override "
                    f"{prim_override_name!r}; using default for type "
                    f"{e.type.value!r}. Known primitives: "
                    f"{sorted(PRIMITIVE_REGISTRY)}.",
                    UserWarning,
                    stacklevel=2,
                )
                override_prim = ENTITY_TO_PRIMITIVE[e.type]
        else:
            override_prim = ENTITY_TO_PRIMITIVE[e.type]

        # Size: use the override primitive's canonical bbox when overriding,
        # otherwise use the entity-type bbox (already scaled by L9 factor).
        if prim_override_name is not None and override_prim is not ENTITY_TO_PRIMITIVE[e.type]:
            size = PRIMITIVE_TO_BBOX.get(override_prim, effective_bbox[e.type])
        else:
            # V2 / L9: forward effective size explicitly so primitives render at
            # the scaled dimensions. Merged after style_kwargs so the size kwarg
            # is always present regardless of whether a style_dict was supplied.
            size = effective_bbox[e.type]

        # Forward per-entity visual style (e.g. LT7's dna_break) into the
        # primitive's style_dict, dropping the control keys consumed above
        # (primitive override name, sublabel). Figure-level style is the base;
        # the entity's own keys win.
        entity_style = {
            k: v for k, v in (e.style or {}).items()
            if k not in ("primitive", "sublabel")
        }
        entity_kwargs = {**style_kwargs, "size": size}
        if entity_style:
            base_style = entity_kwargs.get("style_dict") or {}
            entity_kwargs["style_dict"] = {**base_style, **entity_style}
        entries.append(_entry(
            override_prim,
            (e.label, positions[e.id]),
            entity_kwargs,
            ir_id=e.id,
        ))

    # V2 / L1: same-band arrows route straight when clear, or arch over an
    # intervening entity in a distinct lane when not. Cross-band arrows keep
    # the inter-band corridor routing. Same-band routes are decided together
    # so overlapping arches can be assigned separate lanes.
    # LT1: ring arrows are straight chords between adjacent ring nodes — no
    # arch routing (which is what produced the long over-arching closing edge).
    same_band_routes = {} if ring_mode else _route_same_band_arrows(
        figure.relations, positions, entity_by_id, bands, location_map,
        effective_bbox, arrow_gap,
        clearance=float(params["pathway_arch_clearance"]),
        lane_gap=float(params["pathway_arch_lane_gap"]),
    )

    for idx, r in enumerate(figure.relations):
        src = entity_by_id[r.source]
        tgt = entity_by_id[r.target]
        start, end = _arrow_endpoints(
            positions[r.source], _arrow_bbox_for_entity(src, effective_bbox[src.type]),
            positions[r.target], _arrow_bbox_for_entity(tgt, effective_bbox[tgt.type]),
            arrow_gap,
        )
        if location_map[r.source] != location_map[r.target]:
            wps = _orthogonal_waypoints(
                positions[r.source], effective_bbox[src.type], bands[location_map[r.source]],
                positions[r.target], effective_bbox[tgt.type], bands[location_map[r.target]],
                arrow_gap,
            )
        else:
            wps = same_band_routes.get(idx)  # None → straight arrow
        arrow_kwargs: dict = {**style_kwargs, "waypoints": wps}
        entries.append(_entry(
            RELATION_TO_ARROW[r.type],
            (start, end),
            arrow_kwargs,
            ir_id=r.ir_id,
        ))

    return entries


# ---------------------------------------------------------------------------
# Bug 6: ring edge-label decluttering knobs.
# ---------------------------------------------------------------------------

_RING_RADIAL_NUDGE = 24.0        # px — outward push of an edge label off the ring
_RING_DIVERGE_THRESHOLD = 20.0   # px — pairs closer than this get fanned apart
_RING_DIVERGE_PUSH = 12.0        # px — tangential push applied to each of the pair


def _fan_apart_ring_labels(ring_label_data: list[tuple]) -> list[tuple]:
    """Push co-located ring edge labels apart along their tangents.

    Each item is ``(anchor, (ux, uy), priority, text, ir_id)`` where ``(ux, uy)``
    is the outward radial unit vector at the label's anchor. When two labels'
    anchors fall within ``_RING_DIVERGE_THRESHOLD`` px, each is shifted by
    ``_RING_DIVERGE_PUSH`` px along its own tangent (perpendicular to its
    radial), in the direction that increases their separation, so the pair fans
    apart instead of stacking. Order is preserved; a label is pushed at most
    once (by its nearest close neighbour). Returns a new list.
    """
    n = len(ring_label_data)
    if n < 2:
        return ring_label_data

    anchors = [item[0] for item in ring_label_data]
    out = list(ring_label_data)
    for i in range(n):
        ax, ay = anchors[i]
        # Find the nearest other label within the divergence threshold.
        nearest_j = -1
        nearest_d = _RING_DIVERGE_THRESHOLD
        for j in range(n):
            if j == i:
                continue
            d = math.hypot(anchors[j][0] - ax, anchors[j][1] - ay)
            if d < nearest_d:
                nearest_d = d
                nearest_j = j
        if nearest_j < 0:
            continue
        # Tangent = perpendicular to this label's radial unit vector.
        ux, uy = ring_label_data[i][1]
        tx, ty = -uy, ux
        # Push along the tangent in whichever direction moves away from the
        # neighbour (positive dot with the neighbour→self vector).
        away_x, away_y = ax - anchors[nearest_j][0], ay - anchors[nearest_j][1]
        sign = 1.0 if (tx * away_x + ty * away_y) >= 0 else -1.0
        new_anchor = (ax + tx * _RING_DIVERGE_PUSH * sign,
                      ay + ty * _RING_DIVERGE_PUSH * sign)
        item = out[i]
        out[i] = (new_anchor, item[1], item[2], item[3], item[4])
    return out


def pathway_label_requests(
    figure: Figure,
    entries: list[LayoutEntry],
    layout_params: dict | None = None,
) -> list:
    """Emit one `LabelRequest` per labeled relation in a pathway figure.

    Walks `figure.relations`; for each relation whose `label` is a
    non-empty string, anchors a request at the midpoint of the
    corresponding arrow's start/end (read back from the matching arrow
    LayoutEntry). The anchor bbox is small (a thin shaft point), so
    label_placement's offset gap dominates the spacing.

    Imported lazily by `label_placement.py` callers; declared here so
    the IR-shape walk lives next to its archetype's other concerns.
    Returns `list[label_placement.LabelRequest]` (typed as `list` to
    avoid an import cycle in this module).

    Args:
        figure: The same IR Figure passed to `layout_pathway`.
        entries: The exact list returned from `layout_pathway(figure)`.
            Used to recover the bbox-inset arrow endpoints (so labels
            anchor at the rendered arrow midpoint, not the raw entity
            centers).
        layout_params: Optional overlay; reserved for future use
            (currently no params are read).

    Returns:
        A list of LabelRequest items, one per `Relation.label` that is
        truthy. Empty when no relations carry labels.
    """
    from imageGen.layout.label_placement import LabelRequest  # noqa: PLC0415 — break import cycle

    arrow_entries = [e for e in entries if e.primitive in RELATION_TO_ARROW.values()]
    if len(arrow_entries) != len(figure.relations):
        raise ValueError(
            "pathway_label_requests requires the entries list returned by "
            "layout_pathway(figure); arrow count does not match relations"
        )

    # LT1: in ring mode, push edge labels radially outward from the ring centre
    # so enzyme/reaction names sit outside the ring instead of inside it. The
    # centre is the mean of the entity centres (exact for an evenly-spaced ring).
    ring_mode = _ring_order(figure) is not None
    ring_center: tuple[float, float] | None = None
    if ring_mode:
        _ent_prims = frozenset(PRIMITIVE_REGISTRY.values())
        ent_pts = [e.args[1] for e in entries if e.primitive in _ent_prims]
        if ent_pts:
            ring_center = (
                sum(p[0] for p in ent_pts) / len(ent_pts),
                sum(p[1] for p in ent_pts) / len(ent_pts),
            )

    # Bug 5: entity-anchored labels (external rung-4 labels + sublabels) are
    # collected separately from relation labels so they can be submitted to
    # place_labels FIRST. A relation label can roam the whole canvas, but an
    # external entity label has only one sensible home — beside its own box.
    # Submitting it first lets it claim that slot before a relation label takes
    # it (which is what made "Fluorescence-activated cell sorting" land on top
    # of "load onto sorter" in stress3).
    relation_requests: list[LabelRequest] = []
    sublabel_requests: list[LabelRequest] = []
    extlabel_requests: list[LabelRequest] = []
    # Bug 6: ring edge labels are collected here (anchor, radial unit vector,
    # priority, text, ir_id) and emitted after the loop so a divergence pass can
    # fan apart any co-located pair before requests are built.
    ring_label_data: list[tuple] = []
    for relation, arrow in zip(figure.relations, arrow_entries):
        text = relation.label
        if not text:
            continue
        (sx, sy), (ex, ey) = arrow.args
        midpoint = ((sx + ex) / 2, (sy + ey) / 2)
        anchor = midpoint

        if ring_center is not None:
            # Radial outward direction from ring centre through the chord
            # midpoint; bias the label off the ring and try the outward
            # side first. Bug 6: nudge further out (was 14px) so edge labels
            # clear their adjacent ring node instead of jamming against it
            # (e.g. "SDH"/"SCS" beside "Succinate" at the bottom of the ring).
            rx, ry = midpoint[0] - ring_center[0], midpoint[1] - ring_center[1]
            norm = math.hypot(rx, ry) or 1.0
            ux, uy = rx / norm, ry / norm
            anchor = (midpoint[0] + ux * _RING_RADIAL_NUDGE,
                      midpoint[1] + uy * _RING_RADIAL_NUDGE)
            if abs(ux) >= abs(uy):
                priority = (("right", "above", "below", "left", "center")
                            if ux > 0 else
                            ("left", "above", "below", "right", "center"))
            else:
                priority = (("below", "right", "left", "above", "center")
                            if uy > 0 else
                            ("above", "right", "left", "below", "center"))
            ring_label_data.append(
                (anchor, (ux, uy), priority, text, relation.ir_id)
            )
            continue
        else:
            # Place the label perpendicular to the arrow shaft so it doesn't
            # render directly on top of the line. For a mostly-horizontal arrow
            # try above/below first; for a mostly-vertical arrow try right/left
            # first. The default priority ("right", "below", ...) would put a
            # horizontal-arrow label at the same y as the arrow itself.
            dx, dy = ex - sx, ey - sy
            if abs(dx) >= abs(dy):
                priority = ("above", "below", "right", "left", "center")
            else:
                priority = ("right", "left", "above", "below", "center")
        # Anchor is a notional point on the arrow shaft; small bbox so
        # label_placement's gap dominates spacing.
        relation_requests.append(LabelRequest(
            text=text,
            anchor=anchor,
            anchor_size=(2.0, 2.0),
            priority=priority,
            ir_id=relation.ir_id,
        ))

    # Bug 6: ring edge labels were deferred above so co-located pairs can be
    # fanned apart along the tangent before their requests are built. Two
    # adjacent chords can share nearly the same radial angle (a tight ring),
    # placing their outward-nudged anchors on top of each other; push each
    # along its tangent away from the other so the labels diverge.
    fanned = _fan_apart_ring_labels(ring_label_data)
    for anchor, _radial, priority, text, ir_id in fanned:
        relation_requests.append(LabelRequest(
            text=text,
            anchor=anchor,
            anchor_size=(2.0, 2.0),
            priority=priority,
            ir_id=ir_id,
        ))

    # V2 / L5: entity sublabels — text anchored to entity bbox, placed below
    # first (avoids arrow shafts which run beside / above most entities).
    _entity_prim_set = frozenset(PRIMITIVE_REGISTRY.values())
    entity_entry_by_id = {
        e.ir_id: e for e in entries if e.primitive in _entity_prim_set
    }
    for entity in figure.entities:
        sublabel = (entity.style or {}).get("sublabel")
        if not sublabel:
            continue
        entry = entity_entry_by_id.get(entity.id)
        if entry is None:
            continue
        cx, cy = entry.args[1]
        size = entry.kwargs.get("size", ENTITY_BBOX.get(entity.type, (60.0, 30.0)))
        sublabel_requests.append(LabelRequest(
            text=sublabel,
            anchor=(cx, cy),
            anchor_size=size,
            priority=("below", "above", "right", "left", "center"),
            ir_id=f"{entity.id}_sublabel",
        ))

    # LABEL_FIT rung 4: a fit-aware entity whose label can't fit even at the
    # font floor renders an empty box (see proteins.FIT_AWARE_PRIMITIVES). The
    # primitive and this walk both call _text.fit_label with the same box size
    # and style, so they agree on which entities are external; here we re-place
    # the full label just outside the box via the standard placement machinery.
    for entity in figure.entities:
        entry = entity_entry_by_id.get(entity.id)
        if entry is None or entry.primitive not in proteins.FIT_AWARE_PRIMITIVES:
            continue
        cx, cy = entry.args[1]
        size = entry.kwargs.get("size", ENTITY_BBOX.get(entity.type, (60.0, 30.0)))
        style = entry.kwargs.get("style_dict") or proteins.DEFAULT_STYLE
        fit = fit_label(entity.label, size[0], size[1], style)
        if not fit.external:
            continue
        extlabel_requests.append(LabelRequest(
            text=entity.label,
            anchor=(cx, cy),
            anchor_size=size,
            priority=("below", "above", "right", "left", "center"),
            ir_id=f"{entity.id}_extlabel",
        ))

    # External entity labels first (claim their box-adjacent slot), then
    # relation labels (free to roam), then sublabels.
    return extlabel_requests + relation_requests + sublabel_requests


# ---------------------------------------------------------------------------
# Bug 5: leader lines for externalized (rung-4) entity labels.
# A fit-aware entity whose label can't fit even at the font floor renders an
# empty box; its label is re-placed outside the box by place_labels. Without a
# connector, the floating text reads as unrelated to the box. After placement
# we walk the entries, pair each placed `_extlabel` with its entity box, and
# draw a thin dashed edge-to-edge connector.
# ---------------------------------------------------------------------------

_LEADER_DASH = "3,2"            # dash pattern for the external-label connector
_LEADER_STROKE_WIDTH = 0.5      # px — deliberately hairline so it never competes
# A relation label normally sits ~15-19 px off its arrow shaft (offset gap +
# half its own height). When collision avoidance pushes it further than this,
# the association with its arrow is lost (e.g. "Thr24" floating ~40 px away,
# beside an unrelated box) — tether it back to the shaft with a hairline leader.
_RELATION_LEADER_MIN_GAP = 28.0


def _nearest_point_on_polyline(
    p: tuple[float, float],
    pts: list[tuple[float, float]],
) -> tuple[tuple[float, float], float]:
    """Closest point on a polyline to ``p`` and its distance.

    Walks each segment, projecting ``p`` onto it (clamped to the segment), and
    returns the nearest projection found. ``pts`` must hold at least one point;
    a single point degenerates to that point.
    """
    if len(pts) == 1:
        q = pts[0]
        return q, math.hypot(p[0] - q[0], p[1] - q[1])
    best_q = pts[0]
    best_d = math.inf
    px, py = p
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        if L == 0.0:
            qx, qy = ax, ay
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
            qx, qy = ax + t * dx, ay + t * dy
        d = math.hypot(px - qx, py - qy)
        if d < best_d:
            best_d, best_q = d, (qx, qy)
    return best_q, best_d


def _leader_line(
    start: tuple[float, float],
    end: tuple[float, float],
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """A hairline dashed connector from an external label to its entity box."""
    s = {**proteins.DEFAULT_STYLE, **(style_dict or {})}
    color = s.get("label_font_color", "#1A1A1A")
    g = svgwrite.container.Group()
    line = svgwrite.shapes.Line(start=start, end=end, stroke=color)
    line["stroke-width"] = _LEADER_STROKE_WIDTH
    line["stroke-dasharray"] = _LEADER_DASH
    g.add(line)
    return g


def pathway_extlabel_leaders(
    entries: list[LayoutEntry],
    style_dict: dict | None = None,
) -> list[LayoutEntry]:
    """Insert dashed leader lines that re-associate drifted labels with their owner.

    Operates on the post-`place_labels` entry list. Two kinds of leader are emitted:

    * **External entity label** (`label_{id}_extlabel`): a fit-aware entity whose
      label can't fit renders an empty box and the label is placed outside it;
      connect label edge to box edge (edge-to-edge).
    * **Relation label** (`label_{relation_id}`): when collision avoidance has
      pushed the label further than ``_RELATION_LEADER_MIN_GAP`` from its arrow
      shaft, tether the label edge to the nearest point on the shaft. Labels that
      sit comfortably beside their shaft get no leader (no clutter).

    Returns the entries with leader-line LayoutEntry items inserted immediately
    before the first placed label (so leaders draw over content but under label
    text). A no-op (returns the input unchanged) when no leaders are needed, so it
    is safe to call for every archetype.

    The split point — the index of the first label entry — equals the count of
    pre-label entries, so a caller that slices ``result[:n]`` / ``result[n:]``
    (e.g. the per-panel label path) keeps leaders grouped with the labels.
    """
    from imageGen.layout.label_placement import (  # noqa: PLC0415 — break cycle
        _DEFAULT_LABEL_STYLE,
        _estimate_text_bbox,
        _label_primitive,
    )

    ent_prims = frozenset(PRIMITIVE_REGISTRY.values())
    entity_geom: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
    for e in entries:
        if e.primitive in ent_prims and e.ir_id is not None and len(e.args) >= 2:
            size = e.kwargs.get("size", (60.0, 30.0))
            entity_geom[e.ir_id] = (e.args[1], size)

    # Relation-label leaders need the rendered shaft of each arrow (start, any
    # waypoints, end) keyed by the relation's ir_id (which the placed label
    # carries as `label_{relation_id}`).
    arrow_prims = frozenset(RELATION_TO_ARROW.values())
    arrow_geom: dict[str, list[tuple[float, float]]] = {}
    for e in entries:
        if e.primitive in arrow_prims and e.ir_id is not None and len(e.args) >= 2:
            start, end = e.args
            wps = e.kwargs.get("waypoints") or []
            arrow_geom[e.ir_id] = [start, *wps, end]

    def _font_size(e: LayoutEntry) -> float:
        return float(
            (e.kwargs.get("style_dict") or _DEFAULT_LABEL_STYLE)["label_font_size"]
        )

    leaders: list[LayoutEntry] = []
    first_label_idx = len(entries)
    for i, e in enumerate(entries):
        if e.primitive is not _label_primitive:
            continue
        first_label_idx = min(first_label_idx, i)
        ir_id = e.ir_id or ""
        if not ir_id.startswith("label_"):
            continue
        key = ir_id[len("label_"):]
        label_center = e.args[1]

        # (a) Externalized entity label -> connect to its box (edge-to-edge).
        if key.endswith("_extlabel"):
            entity_id = key[: -len("_extlabel")]
            geom = entity_geom.get(entity_id)
            if geom is None:
                continue
            box_center, box_size = geom
            lw, lh = _estimate_text_bbox(str(e.args[0]), _font_size(e))
            label_exit = _bbox_exit_point(label_center, lw / 2, lh / 2, box_center, 0.0)
            box_exit = _bbox_exit_point(
                box_center, box_size[0] / 2, box_size[1] / 2, label_center, 0.0
            )
            leaders.append(LayoutEntry(
                primitive=_leader_line,
                args=(label_exit, box_exit),
                kwargs={"style_dict": style_dict} if style_dict else {},
                position=(0.0, 0.0),
                ir_id=f"leader_{entity_id}",
            ))
            continue

        # (b) Relation label that drifted far from its shaft -> tether to shaft.
        shaft = arrow_geom.get(key)
        if shaft is None:
            continue
        nearest_pt, dist = _nearest_point_on_polyline(label_center, shaft)
        if dist <= _RELATION_LEADER_MIN_GAP:
            continue
        lw, lh = _estimate_text_bbox(str(e.args[0]), _font_size(e))
        label_exit = _bbox_exit_point(label_center, lw / 2, lh / 2, nearest_pt, 0.0)
        leaders.append(LayoutEntry(
            primitive=_leader_line,
            args=(label_exit, nearest_pt),
            kwargs={"style_dict": style_dict} if style_dict else {},
            position=(0.0, 0.0),
            ir_id=f"leader_{key}",
        ))

    if not leaders:
        return entries
    return entries[:first_label_idx] + leaders + entries[first_label_idx:]
