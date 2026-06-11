"""Ring/cycle detection + ring geometry + band-height math (Phase R1.b).

Extracted from ``pathway_layout``. This module owns:
  * the cyclic-pathway detection ladder (pure single cycle → Hamiltonian
    backbone → dangling-strip) that decides whether a compartment-free figure
    rings (``_ring_order``), plus the ring geometry/placement (``_ring_geometry``,
    ``_ring_positions``);
  * the feedback-arc DAG derivation + topological-rank helpers used to seed
    band placement (``_feedback_arc_dag``, ``_max_topo_siblings``);
  * dynamic per-band height math (``_compute_band_heights``).

Bottom of the placement stack: imports only ``_pathway_common`` (for the shared
``_LABEL_MARGIN``) and external graph/geometry libs. Nothing here imports a
sibling ``_pathway_{bands,routing,labels}`` symbol — that one-directionality is
what keeps the module graph acyclic. ``pathway_layout`` re-exports the names the
test suite pulls (``_feedback_arc_dag``, ``_clamp_center_x``, ``_ring_order``).
"""
from __future__ import annotations

import math
import warnings

import networkx as nx

from imageGen.ir.schema import Compartment, Figure
from imageGen.layout._layered import order_within_ranks, rank_nodes
from imageGen.layout._pathway_common import _LABEL_MARGIN


# ---------------------------------------------------------------------------
# V2 / L3: dynamic band height helpers
# ---------------------------------------------------------------------------

_BAND_BASELINE = 100.0   # px — matches v1: 600 / 6 bands = 100 px/band


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


# FR5: upper bound on the simple-cycle scan used to find a Hamiltonian backbone.
# Bounds the worst case on a dense strongly-connected graph; beyond it the figure
# falls back to the DAG/band layout rather than hanging.
_MAX_CYCLE_SCAN = 20000


def _ranked_ring_order(dag: nx.DiGraph) -> list[str]:
    """Order a (feedback-stripped) cycle DAG into a stable ring sequence."""
    ranks = rank_nodes(dag)
    order_idx = order_within_ranks(dag, ranks)
    return sorted(ranks, key=lambda n: (ranks[n], order_idx.get(n, 0), n))


def _hamiltonian_cycle_order(dg: nx.DiGraph) -> list[str] | None:
    """Return a node order forming a cycle through *every* node, or None (FR5).

    Unlike ``_is_pure_single_cycle`` (which forbids any extra edge), this finds a
    backbone cycle visiting all nodes even when **cross-link chords** exist — the
    case that previously defeated ring detection and flattened a real cyclic
    pathway (carbon cycle, action potential) into an L→R DAG. The chords simply
    render as straight lines across the ring.

    The graph must be strongly connected (a necessary condition for a covering
    cycle). The simple-cycle enumeration is bounded by ``_MAX_CYCLE_SCAN`` so a
    dense graph can't blow up; if no covering cycle is found in the budget the
    caller falls back to the band/DAG layout.
    """
    n = dg.number_of_nodes()
    if n < 3 or not nx.is_strongly_connected(dg):
        return None
    for i, cyc in enumerate(nx.simple_cycles(dg)):
        if len(cyc) == n:
            return cyc  # nodes already in cycle order
        if i >= _MAX_CYCLE_SCAN:
            break
    return None


def _ring_order(figure: Figure) -> tuple[list[str], list[str]] | None:
    """Return (ring_order, dangling_nodes) if this figure should use ring layout.

    Ring layout applies to compartment-free pathways in three cases:
    - **Pure single cycle** (auto): every node has in/out-degree exactly 1 and
      the graph is one strongly-connected cycle (e.g. an 8-node Krebs cycle with
      no inputs shown). Ordered by the canonical rank pass.
    - **Cyclic with cross-links** (auto, FR5): every node lies on a covering
      (Hamiltonian) backbone cycle, but extra **cross-link chords** exist that
      defeated the strict degree-1 check. This rings real cyclic pathways the
      strict check missed; the chords draw as straight lines across the ring.
      Auto mode still requires the cycle to cover *all* nodes — a graph with
      dangling entry/exit nodes needs the explicit hint (avoids false rings).
    - **Forced** (`layout_hint == "circular"`): dangling entry nodes (in-degree
      0) are stripped and placed off-ring, and the remaining core only needs a
      covering cycle — used to show metabolic inputs feeding the ring.

    Returns None if ring layout does not apply or the core cycle has <3 nodes.
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

    if figure.layout_hint == "circular":
        # Forced: strip dangling entry nodes, ring the core on its backbone cycle.
        core, dangling = _split_dangling(DG)
        if core.number_of_nodes() < 3:
            return None
        order = _hamiltonian_cycle_order(core)
        return (order, dangling) if order is not None else None

    # Auto: strict pure single cycle first (preserves the exact Krebs ordering)…
    if _is_pure_single_cycle(DG) and DG.number_of_nodes() >= 3:
        return _ranked_ring_order(_feedback_arc_dag(DG)), []
    # …then the FR5 cross-link case: a covering cycle over *all* nodes, chords
    # allowed. No dangling-strip in auto mode — entry/exit nodes need the hint.
    order = _hamiltonian_cycle_order(DG)
    return (order, []) if order is not None else None


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
