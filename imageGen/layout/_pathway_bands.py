"""Compartment/band positioning + entity placement + arrow-endpoint geometry.

Phase R1.c, extracted from ``pathway_layout``. This module turns a figure's
declared (or implicit) compartments into horizontal bands, places every entity
inside its band (seeded spring-x → topological-rank columns → even spacing, with
membrane snap-to-bilayer), and computes the bbox-edge exit points an arrow's
ends inset to.

Sits above ``_pathway_rings`` (uses ``_feedback_arc_dag``/``_clamp_center_x``)
and ``_pathway_common`` (sentinel + receptor font), and is imported by
``_pathway_routing`` (for the bbox/endpoint helpers) and the orchestrator. It
imports no sibling routing/labels symbol, keeping the module graph acyclic.
"""
from __future__ import annotations

import networkx as nx

from imageGen.ir.schema import (
    Compartment,
    CompartmentType,
    Entity,
    EntityType,
    Figure,
)
from imageGen.layout._geom import ENTITY_BBOX
from imageGen.layout._layered import order_within_ranks, rank_nodes, tighten_ranks
from imageGen.layout._pathway_common import _IMPLICIT_COMPARTMENT_ID, _RECEPTOR_FONT_SIZE
from imageGen.layout._pathway_rings import _clamp_center_x, _feedback_arc_dag


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

    _snap_membrane_entities_to_bilayer(figure, location_map, bands, pos)
    return pos


def _snap_membrane_entities_to_bilayer(
    figure: Figure,
    location_map: dict[str, str],
    bands: dict[str, tuple[float, float]],
    pos: dict[str, tuple[float, float]],
) -> None:
    """Snap each entity in a MEMBRANE band onto the lipid-bilayer plane (FR4).

    The bilayer stripe is drawn at the *top* of a MEMBRANE band
    (``band_top`` .. ``band_top + thickness``), but entities are otherwise
    placed at the band's vertical *center* — so a transmembrane glyph
    (receptor / gpcr / ion_channel / transporter / pump) floats well below the
    membrane and pierces neither leaflet. Re-pin each membrane-band entity's
    y to the bilayer center so the glyph straddles the bilayer, its
    extracellular half in the band above and its intracellular half below.

    In-place mutation of ``pos``; x is preserved. Uses the membrane primitive's
    default bilayer thickness, matching ``_draw_bilayer_border``.
    """
    membrane_ids = {
        c.id for c in figure.compartments if c.type is CompartmentType.MEMBRANE
    }
    if not membrane_ids:
        return
    from imageGen.primitives import membranes as _mem  # noqa: PLC0415
    half = float(_mem.DEFAULT_STYLE["bilayer_thickness"]) / 2.0
    for e in figure.entities:
        band_id = location_map.get(e.id)
        if band_id in membrane_ids and e.id in pos:
            x, _y = pos[e.id]
            band_top, _band_bottom = bands[band_id]
            pos[e.id] = (x, band_top + half)


_RECEPTOR_LABEL_GAP = 6.0      # px — matches the hard-coded gap in receptor() primitive


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
