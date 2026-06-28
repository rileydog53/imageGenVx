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
    Relation,
    RelationType,
)
from imageGen.layout._geom import (
    ENTITY_BBOX,
    ENTITY_TO_PRIMITIVE,
    PRIMITIVE_REGISTRY,
    PRIMITIVE_TO_BBOX,
    max_entity_bbox,
    resolve_entity_primitive,
)
from imageGen.layout._layered import order_within_ranks, rank_nodes, tighten_ranks
from imageGen.layout._pathway_common import (
    _IMPLICIT_COMPARTMENT_ID,
    _LABEL_MARGIN,
    _RECEPTOR_FONT_SIZE,
    RELATION_TO_ARROW,
)
from imageGen.layout._pathway_glyphs import (
    _PHOSPHO_BADGE_DEFAULTS,
    _midpoint_of_path,
    _phospho_badge_geom,
    _phosphorylation_arrow,
    _relation_glyph,
    phospho_badge_occupied_bbox,
)
from imageGen.layout._pathway_rings import (
    _BAND_BASELINE,
    _MAX_CYCLE_SCAN,
    _clamp_center_x,
    _compute_band_heights,
    _feedback_arc_dag,
    _hamiltonian_cycle_order,
    _is_pure_single_cycle,
    _max_topo_siblings,
    _ranked_ring_order,
    _ring_geometry,
    _ring_order,
    _ring_positions,
    _split_dangling,
)
from imageGen.layout._pathway_bands import (
    _arrow_bbox_for_entity,
    _arrow_endpoints,
    _bbox_exit_point,
    _compute_bands,
    _graph_positions,
    _layered_grid_shape,
    _left_label_extent,
    _RECEPTOR_LABEL_GAP,
    _resolve_compartments,
    _snap_membrane_entities_to_bilayer,
)
from imageGen.layout._pathway_routing import (
    _FANOUT_DIRS,
    _HIT_TEST_MARGIN,
    _arch_waypoints,
    _assign_ports,
    _compartment_band,
    _diverging_fanouts,
    _draw_bilayer_border,
    _draw_nuclear_border,
    _edge_point,
    _lift_corridor_off_membrane,
    _natural_side,
    _orthogonal_waypoints,
    _route_fanout,
    _route_same_band_arrows,
    _segment_hits_rect,
)
from imageGen.layout._pathway_labels import (
    _LEADER_DASH,
    _LEADER_STROKE_WIDTH,
    _RELATION_LEADER_MIN_GAP,
    _RING_DIVERGE_PUSH,
    _RING_DIVERGE_THRESHOLD,
    _RING_RADIAL_NUDGE,
    _SIDE_PRIORITY,
    _fan_apart_ring_labels,
    _leader_line,
    _nearest_point_on_polyline,
    _relation_label_priority,
    pathway_extlabel_leaders,
    pathway_label_requests,
)
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
    # Port-based arrow routing. When one entity drives several targets in the
    # same general direction the arrows share a single trunk before forking at a
    # Y-junction (`fanout_trunk_length` px from the source edge). When several
    # arrows enter/leave the same entity side they are spread to distinct ports
    # inset `port_corner_inset` px from each bbox corner so they never stack.
    "pathway_fanout_trunk_length": 28.0,  # px — shared trunk before Y-fork
    "pathway_port_corner_inset":    8.0,  # px — min port distance from bbox corner
}


# ---------------------------------------------------------------------------
# Ring/cycle detection, ring geometry + band-height math live in
# ``_pathway_rings`` (Phase R1.b); imported above and re-exported from this
# module so the names the test suite pulls stay importable from pathway_layout.
# ---------------------------------------------------------------------------


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

    # #2: a compartment-free DAG is placed by topological rank — a column per
    # rank, with at most ``layered_rows`` nodes stacked in any one rank. The
    # band-wrap model (rows of ``max_per_row``) disagrees with that on both axes,
    # so size from the real layered grid for the implicit-single-band case.
    implicit_single = (len(compartments) == 1
                       and compartments[0].id == _IMPLICIT_COMPARTMENT_ID)
    layered_cols, _layered_rows = (
        _layered_grid_shape(figure) if implicit_single else (0, 0))

    heights = _compute_band_heights(
        compartments, by_band,
        max_per_row=max_per_row,
        row_v_gap=row_v_gap,
        max_entity_h=max_entity_h,
    )

    # L20: for single-implicit-band figures, ensure the band is tall enough
    # to vertically spread the widest sibling group without overlap.
    if implicit_single:
        max_sibs = _max_topo_siblings(figure)
        if max_sibs > 1:
            l20_h = max_sibs * (max_entity_h + row_v_gap) + _LABEL_MARGIN + 2 * edge_margin
            heights = [max(heights[0], l20_h)]
        # #2: a deep single-file chain (one node per rank) needs ONE row, not the
        # ``ceil(N/max_per_row)`` rows the band-wrap height assumed — that padded
        # the figure with dead vertical space. Shrink to one row for that case
        # only (cols > max_per_row AND every rank a singleton), so hubs and small
        # figures are untouched.
        elif layered_cols > max_per_row and _layered_rows == 1:
            chain_h = (max_entity_h + row_v_gap) + _LABEL_MARGIN + 2 * edge_margin
            heights = [max(_BAND_BASELINE, min(heights[0], chain_h))]

    # L21: required width = widest row across all bands.
    # Each row of n_cols entities needs: 2*padding + n_cols*entity_w
    # + (n_cols-1)*inter_gap.  inter_gap = 2*edge_margin so the spacing
    # scales with the same knob that clamps entity bboxes to the canvas edge.
    inter_gap = max(2.0 * edge_margin, 20.0)
    required_w = float(min_w)
    for ents in by_band.values():
        n_cols = min(len(ents), max_per_row)
        if layered_cols > n_cols:
            n_cols = layered_cols
        if n_cols < 1:
            continue
        row_w = 2.0 * padding + n_cols * max_entity_w + (n_cols - 1) * inter_gap
        required_w = max(required_w, row_w)

    return (required_w, max(len(heights) * _BAND_BASELINE, sum(heights)))


# ---------------------------------------------------------------------------
# Dispatch tables (public so tests + future archetypes can introspect them).
# RELATION_TO_ARROW and the per-arrow glyphs live in _pathway_common /
# _pathway_glyphs (Phase R1); imported above and re-exported from this module
# so they stay importable from ``pathway_layout`` for label_placement + tests.
# ---------------------------------------------------------------------------


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

# Compartment/band positioning, entity placement + arrow-endpoint geometry
# live in ``_pathway_bands`` (Phase R1.c); imported above and re-exported.
# ---------------------------------------------------------------------------

# Port-based arrow routing, fan-out branching + compartment-border drawing
# live in ``_pathway_routing`` (Phase R1.d); imported above and re-exported.
# ---------------------------------------------------------------------------


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
        # #2: size from the real layered grid (cols = ranks, rows = max nodes per
        # rank) for the compartment-free case — mirrors compute_pathway_canvas.
        implicit_single = (len(compartments) == 1
                           and compartments[0].id == _IMPLICIT_COMPARTMENT_ID)
        layered_cols, _lrows = (
            _layered_grid_shape(figure) if implicit_single else (0, 0))
        per_band_heights = _compute_band_heights(
            compartments, by_band_for_heights,
            max_per_row=int(params["pathway_max_per_row"]),
            row_v_gap=float(params["pathway_row_v_gap"]),
            max_entity_h=max_entity_h,
        )
        # L20: grow single-implicit-band height for hub/branch topologies.
        if implicit_single:
            max_sibs = _max_topo_siblings(figure)
            if max_sibs > 1:
                l20_h = (max_sibs * (max_entity_h + float(params["pathway_row_v_gap"]))
                         + _LABEL_MARGIN + 2.0 * float(params["pathway_edge_margin"]))
                per_band_heights = [max(per_band_heights[0], l20_h)]
            # #2: a deep single-file chain needs one row, not the band-wrap rows.
            elif layered_cols > int(params["pathway_max_per_row"]) and _lrows == 1:
                chain_h = ((max_entity_h + float(params["pathway_row_v_gap"]))
                           + _LABEL_MARGIN + 2.0 * float(params["pathway_edge_margin"]))
                per_band_heights = [max(_BAND_BASELINE, min(per_band_heights[0], chain_h))]
        total_h = max(canvas[1], sum(per_band_heights))
        # L21: grow width to fit the widest entity row (mirrors compute_pathway_canvas).
        max_entity_w = max(effective_bbox[e.type][0] for e in figure.entities)
        inter_gap = max(2.0 * float(params["pathway_edge_margin"]), 20.0)
        required_w = canvas[0]
        for ents_list in by_band_for_heights.values():
            n_cols = min(len(ents_list), int(params["pathway_max_per_row"]))
            if layered_cols > n_cols:
                n_cols = layered_cols
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

    # Lift cross-band corridors off lipid-bilayer stripes. Each MEMBRANE band
    # draws its bilayer at its top edge, spanning [top - r_head, top + thickness
    # + r_head]; a corridor routed at the band boundary would ride along it.
    # Build margin-inflated keep-out intervals so _orthogonal_waypoints can lift
    # the horizontal leg above the membrane (vertical legs still cross it
    # perpendicularly). Empty in ring mode (no bands) or membrane-free figures.
    membrane_keepouts: list[tuple[float, float]] = []
    if not ring_mode:
        from imageGen.primitives import membranes as _mem  # noqa: PLC0415
        _ms = {**_mem.DEFAULT_STYLE, **(style_dict or {})}
        _thick = float(_ms["bilayer_thickness"])
        _rhead = float(_ms["bilayer_head_radius"])
        _keepout_margin = 8.0
        for c in compartments:
            if c.type is CompartmentType.MEMBRANE and c.id in bands:
                _top = bands[c.id][0]
                membrane_keepouts.append((
                    _top - _rhead - _keepout_margin,
                    _top + _thick + _rhead + _keepout_margin,
                ))

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
        # V2 / L6: per-entity primitive override via entity.style["primitive"];
        # EW4: when absent, infer a specific glyph from the label, else the
        # entity-type default. resolve_entity_primitive owns that policy (and is
        # shared with convention_check); the warning for an unknown explicit
        # override name stays here.
        prim_override_name = (e.style or {}).get("primitive")
        explicit_override = (
            prim_override_name is not None and prim_override_name in PRIMITIVE_REGISTRY
        )
        if prim_override_name is not None and not explicit_override:
            warnings.warn(
                f"Entity {e.id!r}: unknown primitive override "
                f"{prim_override_name!r}; using default for type "
                f"{e.type.value!r}. Known primitives: "
                f"{sorted(PRIMITIVE_REGISTRY)}.",
                UserWarning,
                stacklevel=2,
            )
        override_prim = resolve_entity_primitive(e)

        # Size: an *explicit* override sizes by the chosen glyph's canonical
        # bbox; a default or label-inferred glyph keeps the entity-type bbox
        # (already scaled by L9) so layout positions stay stable.
        if explicit_override and override_prim is not ENTITY_TO_PRIMITIVE[e.type]:
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

    # Port-based exit/entry points so co-sided arrows don't stack, plus
    # Y-fork trunks for fan-out groups. Suppressed in ring mode, where arrows
    # are straight chords between adjacent ring nodes (no trunk insertion).
    ports: dict[tuple[int, str], tuple[float, float]] = {}
    reassigned: set[tuple[int, str]] = set()
    fanout_waypoints: dict[int, list[tuple[float, float]]] = {}
    if not ring_mode:
        ports, reassigned, fanout_groups = _assign_ports(
            figure.relations, positions, effective_bbox, entity_by_id,
            location_map, arrow_gap, float(params["pathway_port_corner_inset"]),
        )
        for group, side, src_port in fanout_groups:
            branch_entries = [(ports[(i, "tgt")], None) for i in group]
            branches = _route_fanout(
                src_port, side, branch_entries,
                float(params["pathway_fanout_trunk_length"]),
            )
            for i, wps in zip(group, branches):
                fanout_waypoints[i] = wps

    for idx, r in enumerate(figure.relations):
        src = entity_by_id[r.source]
        tgt = entity_by_id[r.target]
        start, end = _arrow_endpoints(
            positions[r.source], _arrow_bbox_for_entity(src, effective_bbox[src.type]),
            positions[r.target], _arrow_bbox_for_entity(tgt, effective_bbox[tgt.type]),
            arrow_gap,
        )
        # Override the center-to-center endpoints with the assigned ports.
        start = ports.get((idx, "src"), start)
        end = ports.get((idx, "tgt"), end)
        if idx in fanout_waypoints:
            wps = fanout_waypoints[idx]
        elif location_map[r.source] != location_map[r.target]:
            wps = _orthogonal_waypoints(
                positions[r.source], effective_bbox[src.type], bands[location_map[r.source]],
                positions[r.target], effective_bbox[tgt.type], bands[location_map[r.target]],
                arrow_gap,
                membrane_keepouts=membrane_keepouts,
            )
            # Only pull the elbow's terminals onto the ports when those ports
            # were actually moved (multi-arrow group); single arrows keep the
            # clean vertical exit _orthogonal_waypoints already computed.
            if wps and (idx, "src") in reassigned:
                wps[0] = start
            if wps and (idx, "tgt") in reassigned:
                wps[-1] = end
        else:
            wps = same_band_routes.get(idx)  # None → straight arrow
            if wps and (idx, "src") in reassigned:
                wps[0] = start
            if wps and (idx, "tgt") in reassigned:
                wps[-1] = end
        arrow_kwargs: dict = {**style_kwargs, "waypoints": wps}
        entries.append(_entry(
            RELATION_TO_ARROW[r.type],
            (start, end),
            arrow_kwargs,
            ir_id=r.ir_id,
        ))

    return entries

# ---------------------------------------------------------------------------
# Ring edge-label declutter, label-request emission + leader lines live in
# ``_pathway_labels`` (Phase R1.e); imported above and re-exported so
# ``pathway_label_requests`` / ``pathway_extlabel_leaders`` stay importable
# from ``pathway_layout`` for the compositor + tests.
# ---------------------------------------------------------------------------
