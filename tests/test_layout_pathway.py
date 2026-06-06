"""Phase 3 Step 2 tests for layout/pathway_layout.py."""
from __future__ import annotations

import pytest
import svgwrite
import svgwrite.container

from tests._helpers import load_fixture, render_entries_to_png
from imageGen.ir.schema import (
    Archetype, Compartment, CompartmentType, Entity, EntityType,
    Figure, Relation, RelationLabelSide, RelationType,
)
from imageGen.layout._geom import ENTITY_BBOX, ENTITY_TO_PRIMITIVE
from imageGen.layout.pathway_layout import (
    PATHWAY_DEFAULT_PARAMS,
    RELATION_TO_ARROW,
    _BAND_BASELINE,
    _LABEL_MARGIN,
    _bbox_exit_point,
    _compartment_band,
    _midpoint_of_path,
    _phosphorylation_arrow,
    _relation_glyph,
    _route_same_band_arrows,
    _segment_hits_rect,
    compute_pathway_canvas,
    layout_pathway,
)
from imageGen.layout.types import LayoutEntry
from imageGen.primitives import arrows, proteins


def _entity_entries(entries: list[LayoutEntry]) -> list[LayoutEntry]:
    return [e for e in entries if e.primitive in ENTITY_TO_PRIMITIVE.values()]


def _arrow_entries(entries: list[LayoutEntry]) -> list[LayoutEntry]:
    return [e for e in entries if e.primitive in RELATION_TO_ARROW.values()]


def _band_entries(entries: list[LayoutEntry]) -> list[LayoutEntry]:
    return [e for e in entries if e.primitive is _compartment_band]


def _band_geom(entry: LayoutEntry) -> tuple[str, float, float, float, float]:
    """(label, x, y, w, h) for a _compartment_band LayoutEntry."""
    label, x, y, w, h = entry.args
    return label, x, y, w, h


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_wrong_archetype_raises():
    """REACTION_SCHEME has its own engine; layout_pathway must reject it."""
    fig = Figure(
        archetype=Archetype.REACTION_SCHEME,
        entities=[Entity(id="x", type=EntityType.GENERIC, label="X")],
    )
    with pytest.raises(ValueError, match="archetype"):
        layout_pathway(fig)


def test_workflow_archetype_accepted():
    """WORKFLOW / CELLULAR_SCHEMATIC / MECHANISM_CARTOON share the
    pathway entity-graph shape and route through layout_pathway too."""
    fig = Figure(
        archetype=Archetype.WORKFLOW,
        entities=[Entity(id="x", type=EntityType.GENERIC, label="X")],
    )
    entries = layout_pathway(fig)
    assert entries


def test_empty_entities_raises():
    fig = Figure(archetype=Archetype.PATHWAY)
    with pytest.raises(ValueError, match="entities"):
        layout_pathway(fig)


# ---------------------------------------------------------------------------
# Compartment ordering and bands
# ---------------------------------------------------------------------------

def test_no_compartments_uses_implicit_band():
    fig = load_fixture("mapk_cascade.json")
    entries = layout_pathway(fig)
    bands = _band_entries(entries)
    assert len(bands) == 1
    label, *_ = _band_geom(bands[0])
    assert label == ""


def test_compartments_use_ir_declaration_order():
    fig = load_fixture("gpcr_signaling.json")
    bands = [_band_geom(b) for b in _band_entries(layout_pathway(fig))]
    assert [label for label, *_ in bands] == [
        "Extracellular", "Plasma membrane", "Cytoplasm"
    ]
    ys = [y for _, _, y, _, _ in bands]
    assert ys == sorted(ys)


def test_compartment_bands_partition_canvas():
    fig = load_fixture("gpcr_signaling.json")
    canvas_h = 600.0
    entries = layout_pathway(fig, layout_params={"pathway_canvas": (800.0, canvas_h)})
    bands = [_band_geom(b) for b in _band_entries(entries)]
    for (_, _, prev_y, _, prev_h), (_, _, nxt_y, _, _) in zip(bands, bands[1:]):
        assert prev_y + prev_h == pytest.approx(nxt_y)
    assert sum(h for _, _, _, _, h in bands) == pytest.approx(canvas_h)


# ---------------------------------------------------------------------------
# Entity placement
# ---------------------------------------------------------------------------

def test_entities_snap_into_their_compartment_band():
    fig = load_fixture("gpcr_signaling.json")
    entries = layout_pathway(fig)
    bands_by_label: dict[str, tuple[float, float]] = {
        label: (y, y + h) for label, _, y, _, h in map(_band_geom, _band_entries(entries))
    }
    location_to_label = {c.id: c.label for c in fig.compartments}
    for ent in fig.entities:
        match = next(
            e for e in _entity_entries(entries) if e.args[0] == ent.label
        )
        _, (_, y) = match.args
        top, bottom = bands_by_label[location_to_label[ent.location]]
        assert top <= y <= bottom


def test_isolated_entity_still_placed():
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="solo", type=EntityType.PROTEIN, label="Solo"),
        ],
    )
    entries = layout_pathway(fig)
    ents = _entity_entries(entries)
    assert len(ents) == 1
    label, (x, y) = ents[0].args
    assert label == "Solo"
    # placed somewhere on the canvas
    assert 0 <= x <= 800
    assert 0 <= y <= 600


def test_layout_is_deterministic():
    fig = load_fixture("gpcr_signaling.json")
    a = layout_pathway(fig)
    b = layout_pathway(fig)
    a_pos = [e.args for e in _entity_entries(a)]
    b_pos = [e.args for e in _entity_entries(b)]
    assert a_pos == b_pos


# ---------------------------------------------------------------------------
# Dispatch tables
# ---------------------------------------------------------------------------

def test_entity_dispatch_covers_all_entity_types():
    missing = set(EntityType) - set(ENTITY_TO_PRIMITIVE.keys())
    assert not missing, f"Unmapped EntityTypes: {missing}"


def test_relation_dispatch_covers_all_relation_types():
    missing = set(RelationType) - set(RELATION_TO_ARROW.keys())
    assert not missing, f"Unmapped RelationTypes: {missing}"


def test_phosphorylates_uses_phosphorylation_arrow():
    """V2/L4: PHOSPHORYLATES maps to the annotated wrapper, not the bare activation_arrow."""
    assert RELATION_TO_ARROW[RelationType.PHOSPHORYLATES] is _phosphorylation_arrow


def test_phospho_badge_occupied_bbox_brackets_the_midpoint():
    """LT3: the reserved badge bbox is a square centered on the shaft midpoint."""
    from imageGen.layout.pathway_layout import phospho_badge_occupied_bbox

    entry = LayoutEntry(
        primitive=_phosphorylation_arrow,
        args=((0.0, 100.0), (200.0, 100.0)),
        kwargs={"waypoints": None},
        position=(0.0, 0.0),
    )
    bbox = phospho_badge_occupied_bbox(entry)
    assert bbox is not None
    x0, y0, x1, y1 = bbox
    # Square centered on the midpoint (100, 100), side = 2 * radius (>= 14).
    assert (x0 + x1) / 2 == pytest.approx(100.0)
    assert (y0 + y1) / 2 == pytest.approx(100.0)
    assert (x1 - x0) == pytest.approx(y1 - y0)
    assert (x1 - x0) >= 14.0


def test_phospho_badge_occupied_bbox_none_for_other_arrows():
    """LT3: the badge reservation only applies to phosphorylation arrows."""
    from imageGen.layout.pathway_layout import phospho_badge_occupied_bbox

    entry = LayoutEntry(
        primitive=arrows.activation_arrow,
        args=((0.0, 0.0), (10.0, 0.0)),
        kwargs={},
        position=(0.0, 0.0),
    )
    assert phospho_badge_occupied_bbox(entry) is None


# ---------------------------------------------------------------------------
# LT4 — label-aware horizontal clamp
# ---------------------------------------------------------------------------


def test_clamp_center_x_respects_label_extent():
    """LT4: a center is pulled inward so a wide footprint stays in bounds."""
    from imageGen.layout.pathway_layout import _clamp_center_x

    # x wants the right edge (190) but a 100px-wide footprint (half 50) must
    # keep 50px clear of the bound at 200 → clamped to 150.
    assert _clamp_center_x(190.0, 0.0, 200.0, 50.0) == pytest.approx(150.0)
    # Already-inside x is untouched.
    assert _clamp_center_x(100.0, 0.0, 200.0, 50.0) == pytest.approx(100.0)


def test_clamp_center_x_centers_when_footprint_wider_than_slot():
    """LT4: a label wider than the whole slot is centered, not pinned to an edge."""
    from imageGen.layout.pathway_layout import _clamp_center_x

    # half_extent 120 > slot half-width (100) → bounds invert → center at 100.
    assert _clamp_center_x(10.0, 0.0, 200.0, 120.0) == pytest.approx(100.0)


def test_wide_label_entity_box_stays_within_narrow_canvas():
    """A wide-label entity's BOX stays inside a narrow canvas.

    The old LT4 behavior clamped the entity center by the *centered-label*
    extent. That is retired: the fit ladder fits a label to its box or
    externalizes it (placed by the bounds-aware label engine), so position is
    clamped by box width only. We therefore assert the entity *box* (not its
    label) stays within the canvas, and that the two entities do not overlap.
    """
    from imageGen.ir.schema import (
        Archetype, Entity, EntityType, Figure, Relation, RelationType,
    )
    from imageGen.layout._geom import ENTITY_BBOX

    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="enz", type=EntityType.METABOLITE, label="Enzymatic digestion"),
            Entity(id="x", type=EntityType.METABOLITE, label="X"),
        ],
        relations=[
            Relation(source="enz", target="x", type=RelationType.ACTIVATES),
        ],
    )
    canvas_w = 220.0
    entries = layout_pathway(fig, layout_params={"pathway_canvas": (canvas_w, 200.0)})

    centers = {
        e.ir_id: e.args[1]
        for e in _entity_entries(entries)
    }
    bw, _bh = ENTITY_BBOX[EntityType.METABOLITE]
    for irid, (cx, _cy) in centers.items():
        assert cx - bw / 2 >= 0.0, f"{irid} box crosses left canvas edge"
        assert cx + bw / 2 <= canvas_w, f"{irid} box crosses right canvas edge"
    # The two boxes must not overlap horizontally.
    xs = sorted(cx for cx, _ in centers.values())
    assert xs[1] - xs[0] >= bw, "entity boxes overlap"


def test_entity_type_routes_to_specific_primitive():
    assert ENTITY_TO_PRIMITIVE[EntityType.KINASE] is proteins.kinase
    assert ENTITY_TO_PRIMITIVE[EntityType.RECEPTOR] is proteins.receptor
    assert ENTITY_TO_PRIMITIVE[EntityType.LIGAND] is proteins.generic_protein
    assert ENTITY_TO_PRIMITIVE[EntityType.COMPLEX] is proteins.protein_complex


# ---------------------------------------------------------------------------
# LayoutEntry shape
# ---------------------------------------------------------------------------

def test_layout_returns_layout_entries():
    fig = load_fixture("mapk_cascade.json")
    entries = layout_pathway(fig)
    assert entries
    assert all(isinstance(e, LayoutEntry) for e in entries)


def test_one_entity_entry_per_entity():
    fig = load_fixture("gpcr_signaling.json")
    entries = layout_pathway(fig)
    assert len(_entity_entries(entries)) == len(fig.entities)


def test_relations_emit_layout_entries():
    fig = load_fixture("mapk_cascade.json")
    entries = layout_pathway(fig)
    assert len(_arrow_entries(entries)) == len(fig.relations)


def test_layout_entries_are_executable():
    fig = load_fixture("gpcr_signaling.json")
    entries = layout_pathway(fig)
    for entry in entries:
        g = entry.primitive(*entry.args, **entry.kwargs)
        assert isinstance(g, svgwrite.container.Group)


# ---------------------------------------------------------------------------
# Param + style overrides
# ---------------------------------------------------------------------------

def test_layout_params_override_seed_and_canvas():
    fig = load_fixture("mapk_cascade.json")
    # MAPK is a strict linear DAG (Ras→Raf→MEK→ERK). With DAG-aware init
    # (L16) the topological rank dominates spring relaxation, so entities land
    # in left-to-right topological order regardless of seed.
    entries = layout_pathway(fig, layout_params={"pathway_seed": 42})
    ent_map = {e.ir_id: e.args[1][0] for e in _entity_entries(entries)}
    assert ent_map["ras"] < ent_map["raf"] < ent_map["mek"] < ent_map["erk"]

    # Seed parameter is still accepted (no error) with either value.
    layout_pathway(fig, layout_params={"pathway_seed": 1})
    layout_pathway(fig, layout_params={"pathway_seed": 2})

    big = layout_pathway(fig, layout_params={"pathway_canvas": (1600.0, 1200.0)})
    _, _, _, w, _ = _band_geom(_band_entries(big)[0])
    assert w == 1600.0


def test_style_dict_forwarded_to_entity_and_arrow_primitives():
    fig = load_fixture("gpcr_signaling.json")
    style = {"protein_fill": "#FF0000"}
    entries = layout_pathway(fig, style_dict=style)
    for e in _entity_entries(entries) + _arrow_entries(entries):
        assert e.kwargs.get("style_dict") == style


def test_band_visual_overrides_via_layout_params():
    """Band visuals (fill/stroke/label) live in layout_params, not style_dict —
    layout_params overrides must reach _compartment_band."""
    fig = load_fixture("mapk_cascade.json")
    entries = layout_pathway(fig, layout_params={"pathway_band_fill": "#ABCDEF"})
    band = _band_entries(entries)[0]
    assert band.kwargs["params"]["pathway_band_fill"] == "#ABCDEF"


def test_default_style_dict_not_forwarded_when_none():
    fig = load_fixture("mapk_cascade.json")
    entries = layout_pathway(fig)
    for e in _entity_entries(entries) + _arrow_entries(entries):
        assert "style_dict" not in e.kwargs


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_cycle_does_not_crash():
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="a", type=EntityType.PROTEIN, label="A"),
            Entity(id="b", type=EntityType.PROTEIN, label="B"),
        ],
        relations=[
            Relation(source="a", target="b", type=RelationType.ACTIVATES),
            Relation(source="b", target="a", type=RelationType.ACTIVATES),
        ],
    )
    entries = layout_pathway(fig)
    assert len(_arrow_entries(entries)) == 2


# ---------------------------------------------------------------------------
# V2 / L9: entity size forwarding
# ---------------------------------------------------------------------------

def test_entity_entries_carry_size_kwarg():
    """Every entity LayoutEntry must carry an explicit `size` kwarg (L9)."""
    fig = load_fixture("mapk_cascade.json")
    entries = layout_pathway(fig)
    for e in _entity_entries(entries):
        assert "size" in e.kwargs, f"Entity entry {e.ir_id!r} missing size kwarg"
        w, h = e.kwargs["size"]
        assert w > 0 and h > 0


def test_entity_size_matches_entity_bbox_at_default_scale():
    """At scale=1.0 (default), size kwarg must equal ENTITY_BBOX for that type."""
    fig = load_fixture("gpcr_signaling.json")
    entries = layout_pathway(fig)
    entity_by_id = {e.id: e for e in fig.entities}
    for entry in _entity_entries(entries):
        entity = entity_by_id[entry.ir_id]
        expected = ENTITY_BBOX[entity.type]
        actual = entry.kwargs["size"]
        assert actual == pytest.approx(expected), (
            f"Entity {entry.ir_id!r} (type={entity.type}) size mismatch: "
            f"expected {expected}, got {actual}"
        )


def test_pathway_entity_scale_doubles_rendered_size():
    """pathway_entity_scale=2.0 must double every entity's size kwarg."""
    fig = load_fixture("mapk_cascade.json")
    entries_1x = layout_pathway(fig, layout_params={"pathway_entity_scale": 1.0})
    entries_2x = layout_pathway(fig, layout_params={"pathway_entity_scale": 2.0})

    sizes_1x = {e.ir_id: e.kwargs["size"] for e in _entity_entries(entries_1x)}
    sizes_2x = {e.ir_id: e.kwargs["size"] for e in _entity_entries(entries_2x)}

    assert sizes_1x.keys() == sizes_2x.keys()
    for ir_id, (w1, h1) in sizes_1x.items():
        w2, h2 = sizes_2x[ir_id]
        assert w2 == pytest.approx(w1 * 2.0), f"{ir_id}: width not doubled"
        assert h2 == pytest.approx(h1 * 2.0), f"{ir_id}: height not doubled"


def test_pathway_entity_scale_in_default_params():
    """pathway_entity_scale must be present in PATHWAY_DEFAULT_PARAMS at 1.0."""
    assert "pathway_entity_scale" in PATHWAY_DEFAULT_PARAMS
    assert PATHWAY_DEFAULT_PARAMS["pathway_entity_scale"] == 1.0


def test_scaled_entity_size_renders_without_error():
    """Scaled entities must produce valid SVG groups (primitive accepts the size)."""
    fig = load_fixture("gpcr_signaling.json")
    entries = layout_pathway(fig, layout_params={"pathway_entity_scale": 1.5})
    for entry in _entity_entries(entries):
        result = entry.primitive(*entry.args, **entry.kwargs)
        assert result is not None


def test_default_layout_params_keys_are_namespaced():
    """Mirrors the locked-in 'flat namespaced keys' template."""
    for key in PATHWAY_DEFAULT_PARAMS:
        assert key.startswith("pathway_"), f"non-namespaced key: {key}"


# ---------------------------------------------------------------------------
# Arrow inset to entity bbox edges (so arrows never overlap entity labels)
# ---------------------------------------------------------------------------

def test_bbox_exit_point_horizontal():
    # Center at origin, 60×30 bbox, target far right → exits at (30, 0).
    p = _bbox_exit_point((0.0, 0.0), 30.0, 15.0, (200.0, 0.0), gap=0.0)
    assert p == pytest.approx((30.0, 0.0))


def test_bbox_exit_point_vertical_with_gap():
    # 60×30 bbox, target above; exit at (0, -15) plus 4px gap upward.
    p = _bbox_exit_point((0.0, 0.0), 30.0, 15.0, (0.0, -100.0), gap=4.0)
    assert p == pytest.approx((0.0, -19.0))


def test_bbox_exit_point_returns_center_when_target_coincides():
    p = _bbox_exit_point((10.0, 20.0), 30.0, 15.0, (10.0, 20.0))
    assert p == (10.0, 20.0)


def test_arrow_endpoints_are_outside_entity_bboxes():
    """Arrows must start/end on the bbox perimeter (plus the configured gap),
    never at an entity center where they'd overlap the entity's label.
    Uses the NF-κB fixture, which has two distinct entities sharing the
    label 'NF-κB' — checks must key by entity id, not label."""
    fig = load_fixture("multi_compartment_translocation.json")
    entries = layout_pathway(fig)

    # The order of _entity_entries(entries) matches figure.entities order.
    centers_by_id = {
        ent.id: entry.args[1]
        for ent, entry in zip(fig.entities, _entity_entries(entries))
    }
    type_by_id = {e.id: e.type for e in fig.entities}
    gap = PATHWAY_DEFAULT_PARAMS["pathway_arrow_gap"]

    for arrow, relation in zip(_arrow_entries(entries), fig.relations):
        start, end = arrow.args
        assert start != centers_by_id[relation.source]
        assert end != centers_by_id[relation.target]

        # Endpoint must lie on or outside the bbox edge: at least one axis
        # offset reaches half-extent. The configured gap pushes further along
        # the arrow's *direction*, not axis-aligned, so the perpendicular
        # offset alone need not exceed half + gap.
        for eid, point in ((relation.source, start), (relation.target, end)):
            cx, cy = centers_by_id[eid]
            w, h = ENTITY_BBOX[type_by_id[eid]]
            on_x_edge = abs(point[0] - cx) >= w / 2 - 1e-6
            on_y_edge = abs(point[1] - cy) >= h / 2 - 1e-6
            assert on_x_edge or on_y_edge, (
                f"arrow endpoint {point} sits strictly inside entity "
                f"{eid}'s bbox (center={(cx, cy)}, size=({w}, {h}))"
            )


def test_arrow_gap_is_overridable():
    fig = load_fixture("mapk_cascade.json")
    tight = layout_pathway(fig, layout_params={"pathway_arrow_gap": 0.0})
    loose = layout_pathway(fig, layout_params={"pathway_arrow_gap": 20.0})
    tight_first = _arrow_entries(tight)[0].args
    loose_first = _arrow_entries(loose)[0].args
    assert tight_first != loose_first


# ---------------------------------------------------------------------------
# Render-to-PNG (golden seeds)
# ---------------------------------------------------------------------------

def test_render_mapk_cascade_to_png():
    fig = load_fixture("mapk_cascade.json")
    entries = layout_pathway(fig)
    out = render_entries_to_png(entries, "layout_pathway_mapk.png")
    assert out.exists() and out.stat().st_size > 0


def test_render_gpcr_signaling_to_png():
    fig = load_fixture("gpcr_signaling.json")
    entries = layout_pathway(fig)
    out = render_entries_to_png(entries, "layout_pathway_gpcr.png")
    assert out.exists() and out.stat().st_size > 0


def test_render_nfkb_translocation_to_png():
    fig = load_fixture("multi_compartment_translocation.json")
    entries = layout_pathway(fig)
    out = render_entries_to_png(entries, "layout_pathway_nfkb.png")
    assert out.exists() and out.stat().st_size > 0


# ---------------------------------------------------------------------------
# V2 / L3: dynamic band heights
# ---------------------------------------------------------------------------

def test_dynamic_band_height_at_least_baseline():
    """Every band must be at least _BAND_BASELINE tall (even with one entity)."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        compartments=[
            Compartment(id="c1", label="A", type=CompartmentType.CYTOPLASM),
        ],
        entities=[
            Entity(id="e1", type=EntityType.PROTEIN, label="Solo", location="c1"),
        ],
    )
    entries = layout_pathway(fig)
    bands = [_band_geom(b) for b in _band_entries(entries)]
    assert len(bands) == 1
    _, _, _, _, h = bands[0]
    assert h >= _BAND_BASELINE


def test_dynamic_band_expands_for_overflow():
    """When a band contains more entities than fit in one row, its height
    must exceed _BAND_BASELINE so they can stack without overlapping."""
    many_entities = [
        Entity(id=f"p{i}", type=EntityType.PROTEIN, label=f"P{i}", location="c1")
        for i in range(20)
    ]
    fig = Figure(
        archetype=Archetype.PATHWAY,
        compartments=[
            Compartment(id="c1", label="Cytoplasm", type=CompartmentType.CYTOPLASM),
        ],
        entities=many_entities,
    )
    entries = layout_pathway(fig)
    bands = [_band_geom(b) for b in _band_entries(entries)]
    assert len(bands) == 1
    _, _, _, _, h = bands[0]
    assert h > _BAND_BASELINE


def test_dynamic_bands_are_contiguous():
    """Multi-compartment: bands must be stacked without gaps (each band's top
    == previous band's bottom), regardless of whether they fill the canvas."""
    fig = load_fixture("gpcr_signaling.json")
    entries = layout_pathway(fig)
    bands = [_band_geom(b) for b in _band_entries(entries)]
    assert len(bands) >= 2
    for (_, _, y0, _, h0), (_, _, y1, _, _) in zip(bands, bands[1:]):
        assert y0 + h0 == pytest.approx(y1), "bands are not contiguous"


def test_dynamic_band_heights_each_at_least_baseline():
    """Multi-compartment: every band in dynamic mode is at least _BAND_BASELINE."""
    fig = load_fixture("gpcr_signaling.json")
    entries = layout_pathway(fig)
    for entry in _band_entries(entries):
        _, _, _, _, h = _band_geom(entry)
        assert h >= _BAND_BASELINE


def test_explicit_canvas_keeps_equal_split():
    """When caller passes pathway_canvas explicitly, bands revert to equal-height
    partition (L3 dynamic sizing must NOT override an explicit canvas)."""
    fig = load_fixture("gpcr_signaling.json")
    fixed_h = 600.0
    entries = layout_pathway(fig, layout_params={"pathway_canvas": (800.0, fixed_h)})
    bands = [_band_geom(b) for b in _band_entries(entries)]
    heights = [h for _, _, _, _, h in bands]
    # All bands equal-height (within floating-point tolerance).
    assert all(abs(h - heights[0]) < 1e-6 for h in heights)
    assert sum(heights) == pytest.approx(fixed_h)


# ---------------------------------------------------------------------------
# V2 / L8: organelle-outline decorations on MEMBRANE / NUCLEUS bands
# ---------------------------------------------------------------------------

def test_membrane_compartment_band_is_executable():
    """A MEMBRANE-type compartment band must produce a valid SVG group
    (the bilayer decoration must not raise)."""
    from imageGen.ir.schema import CompartmentType
    g = _compartment_band(
        "Plasma membrane", 0.0, 0.0, 800.0, 60.0,
        params=PATHWAY_DEFAULT_PARAMS,
        compartment_type=CompartmentType.MEMBRANE,
    )
    assert isinstance(g, svgwrite.container.Group)
    svg = g.tostring()
    # bilayer decoration adds extra child elements (circles + paths)
    assert svg.count("<") > 3  # more than just the background rect + label


def test_nucleus_compartment_band_is_executable():
    """A NUCLEUS-type compartment band must produce a valid SVG group."""
    from imageGen.ir.schema import CompartmentType
    g = _compartment_band(
        "Nucleus", 0.0, 0.0, 800.0, 100.0,
        params=PATHWAY_DEFAULT_PARAMS,
        compartment_type=CompartmentType.NUCLEUS,
    )
    assert isinstance(g, svgwrite.container.Group)
    svg = g.tostring()
    assert svg.count("<") > 3


def test_non_organelle_band_unchanged_by_l8():
    """CYTOPLASM / CUSTOM compartment types must not add bilayer/nuclear decorations;
    output must be the same as calling without compartment_type."""
    from imageGen.ir.schema import CompartmentType
    base = _compartment_band(
        "Cytoplasm", 0.0, 0.0, 800.0, 100.0,
        params=PATHWAY_DEFAULT_PARAMS,
    )
    typed = _compartment_band(
        "Cytoplasm", 0.0, 0.0, 800.0, 100.0,
        params=PATHWAY_DEFAULT_PARAMS,
        compartment_type=CompartmentType.CYTOPLASM,
    )
    assert base.tostring() == typed.tostring()


def test_gpcr_membrane_band_has_organelle_decoration():
    """End-to-end: gpcr_signaling.json declares a MEMBRANE compartment.
    Its band entry must carry compartment_type=MEMBRANE in kwargs so the
    compositor renders the bilayer decoration."""
    fig = load_fixture("gpcr_signaling.json")
    from imageGen.ir.schema import CompartmentType
    membrane_comps = {c.id for c in fig.compartments if c.type is CompartmentType.MEMBRANE}
    entries = layout_pathway(fig)
    bands = _band_entries(entries)
    membrane_bands = [
        b for b in bands
        if b.kwargs.get("compartment_type") is CompartmentType.MEMBRANE
    ]
    assert len(membrane_bands) == len(membrane_comps), (
        f"Expected {len(membrane_comps)} MEMBRANE band(s), "
        f"got {len(membrane_bands)}"
    )


# ---------------------------------------------------------------------------
# V2 / L4: phosphorylation arrow badge
# ---------------------------------------------------------------------------

def test_midpoint_of_path_two_points():
    """Midpoint of a two-point path is the exact centre."""
    assert _midpoint_of_path([(0.0, 0.0), (10.0, 20.0)]) == pytest.approx((5.0, 10.0))


def test_midpoint_of_path_multi_segment():
    """For odd-length waypoint list, midpoint uses the middle segment."""
    pts = [(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (20.0, 10.0)]
    mx, my = _midpoint_of_path(pts)
    # mid_i = 4//2 = 2 → segment [1]→[2] = (10,0)→(10,10) → mid = (10, 5)
    assert (mx, my) == pytest.approx((10.0, 5.0))


def test_relation_glyph_adds_children():
    """_relation_glyph must append a circle and a text element to the group."""
    import svgwrite
    dwg = svgwrite.Drawing(debug=False)
    g = dwg.g()
    _relation_glyph(g, 50.0, 50.0, "P", {
        "label_font_size": 11,
        "label_font_family": "Helvetica",
        "label_font_color": "#000000",
        "kinase_badge_fill": "#D32F2F",
        "kinase_badge_text_color": "#FFFFFF",
        "protein_stroke": "#1F4E79",
        "protein_stroke_width": 0.5,
    })
    assert len(g.elements) == 2  # circle + text


def test_phosphorylation_arrow_returns_group():
    """_phosphorylation_arrow must return an svgwrite Group."""
    g = _phosphorylation_arrow((0.0, 0.0), (100.0, 0.0))
    assert isinstance(g, svgwrite.container.Group)


def test_phosphorylation_arrow_svg_contains_p_badge():
    """The SVG output of _phosphorylation_arrow must contain a 'P' character."""
    g = _phosphorylation_arrow((0.0, 0.0), (100.0, 0.0))
    svg = g.tostring()
    assert ">P<" in svg


def test_phosphorylation_arrow_respects_style_dict():
    """Custom badge fill must appear in the rendered SVG."""
    custom_fill = "#123456"
    g = _phosphorylation_arrow(
        (0.0, 0.0), (100.0, 0.0),
        style_dict={"kinase_badge_fill": custom_fill},
    )
    assert custom_fill in g.tostring()


def test_phosphorylation_arrow_end_to_end_in_layout():
    """A figure with a PHOSPHORYLATES relation must produce an arrow entry
    whose SVG contains the 'P' badge."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="erk", type=EntityType.KINASE, label="ERK"),
            Entity(id="target", type=EntityType.PROTEIN, label="Target"),
        ],
        relations=[
            Relation(source="erk", target="target", type=RelationType.PHOSPHORYLATES),
        ],
    )
    entries = layout_pathway(fig)
    arrow_entries = _arrow_entries(entries)
    assert len(arrow_entries) == 1
    g = arrow_entries[0].primitive(*arrow_entries[0].args, **arrow_entries[0].kwargs)
    assert ">P<" in g.tostring()


# ---------------------------------------------------------------------------
# V2 / L1: same-band straight vs. arch routing
# ---------------------------------------------------------------------------

def test_segment_hits_rect_through_center():
    # Horizontal segment passing straight through a centred rect.
    assert _segment_hits_rect((0.0, 0.0), (100.0, 0.0), 50.0, 0.0, 10.0, 10.0)


def test_segment_hits_rect_clears_above():
    # Same span but well above the rect → no hit.
    assert not _segment_hits_rect((0.0, -50.0), (100.0, -50.0), 50.0, 0.0, 10.0, 10.0)


def test_segment_hits_rect_stops_short():
    # Segment ends before reaching the rect → no hit.
    assert not _segment_hits_rect((0.0, 0.0), (20.0, 0.0), 50.0, 0.0, 10.0, 10.0)


def test_segment_hits_rect_vertical():
    assert _segment_hits_rect((50.0, -50.0), (50.0, 50.0), 50.0, 0.0, 10.0, 10.0)


def test_segment_hits_rect_parallel_miss():
    # Collinear-with-edge but offset segment never enters the rect.
    assert not _segment_hits_rect((0.0, 100.0), (100.0, 100.0), 50.0, 0.0, 10.0, 10.0)


def _arrows_by_relation(fig, entries):
    """Map (source, target) → arrow LayoutEntry, in figure order."""
    return {
        (r.source, r.target): e
        for r, e in zip(fig.relations, _arrow_entries(entries))
    }


def test_same_band_adjacent_arrow_is_straight():
    """An arrow between two same-band entities with nothing between them is a
    straight line — no elbow waypoints."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="a", type=EntityType.PROTEIN, label="A"),
            Entity(id="b", type=EntityType.PROTEIN, label="B"),
        ],
        relations=[Relation(source="a", target="b", type=RelationType.ACTIVATES)],
    )
    entries = layout_pathway(fig)
    arrow = _arrows_by_relation(fig, entries)[("a", "b")]
    assert arrow.kwargs.get("waypoints") is None


def test_same_band_skip_arrow_arches():
    """A skip arrow (A→C over an intervening B) routes as a 4-point arch."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="a", type=EntityType.PROTEIN, label="A"),
            Entity(id="b", type=EntityType.PROTEIN, label="B"),
            Entity(id="c", type=EntityType.PROTEIN, label="C"),
        ],
        relations=[
            Relation(source="a", target="b", type=RelationType.ACTIVATES),
            Relation(source="b", target="c", type=RelationType.ACTIVATES),
            Relation(source="a", target="c", type=RelationType.ACTIVATES),
        ],
    )
    entries = layout_pathway(fig)
    by_rel = _arrows_by_relation(fig, entries)
    # Adjacent links stay straight; the skip link arches.
    assert by_rel[("a", "b")].kwargs.get("waypoints") is None
    assert by_rel[("b", "c")].kwargs.get("waypoints") is None
    skip = by_rel[("a", "c")].kwargs.get("waypoints")
    assert skip is not None and len(skip) == 4


def test_overlapping_arches_get_distinct_lanes():
    """Two skip arrows sharing a source (A→C and A→D) must not collapse onto
    the same corridor — their horizontal legs sit at different y."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="a", type=EntityType.PROTEIN, label="A"),
            Entity(id="b", type=EntityType.PROTEIN, label="B"),
            Entity(id="c", type=EntityType.PROTEIN, label="C"),
            Entity(id="d", type=EntityType.PROTEIN, label="D"),
        ],
        relations=[
            Relation(source="a", target="b", type=RelationType.ACTIVATES),
            Relation(source="b", target="c", type=RelationType.ACTIVATES),
            Relation(source="c", target="d", type=RelationType.ACTIVATES),
            Relation(source="a", target="c", type=RelationType.ACTIVATES),
            Relation(source="a", target="d", type=RelationType.ACTIVATES),
        ],
    )
    entries = layout_pathway(fig)
    by_rel = _arrows_by_relation(fig, entries)
    ac = by_rel[("a", "c")].kwargs["waypoints"]
    ad = by_rel[("a", "d")].kwargs["waypoints"]
    # corridor y is the second waypoint's y; the two arches must differ.
    assert ac[1][1] != ad[1][1]


def test_cross_band_arrow_still_uses_corridor():
    """Cross-band arrows keep the inter-band elbow routing (4 waypoints)."""
    fig = load_fixture("multi_compartment_translocation.json")
    entries = layout_pathway(fig)
    fig_relations = fig.relations
    # Find a relation whose endpoints live in different compartments.
    loc = {e.id: e.location for e in fig.entities}
    cross = [
        e for r, e in zip(fig_relations, _arrow_entries(entries))
        if loc[r.source] != loc[r.target]
    ]
    assert cross, "fixture should contain a cross-compartment relation"
    for e in cross:
        wps = e.kwargs.get("waypoints")
        assert wps is not None and len(wps) == 4


# ---------------------------------------------------------------------------
# V2 / L23: cycle-aware DAG ranking (feedback edges no longer break ordering)
# ---------------------------------------------------------------------------

def _make_mapk_with_feedback() -> Figure:
    """MAPK cascade with an ERK⊣RAF feedback inhibition edge (cyclic DiGraph)."""
    return Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="ras", type=EntityType.PROTEIN, label="Ras"),
            Entity(id="raf", type=EntityType.KINASE, label="Raf"),
            Entity(id="mek", type=EntityType.KINASE, label="MEK"),
            Entity(id="erk", type=EntityType.KINASE, label="ERK"),
        ],
        relations=[
            Relation(source="ras", target="raf", type=RelationType.ACTIVATES),
            Relation(source="raf", target="mek", type=RelationType.PHOSPHORYLATES),
            Relation(source="mek", target="erk", type=RelationType.PHOSPHORYLATES),
            Relation(source="erk", target="raf", type=RelationType.INHIBITS),  # feedback
        ],
    )


def test_feedback_edge_does_not_crash():
    """A cyclic graph (feedback loop) must not raise during layout."""
    fig = _make_mapk_with_feedback()
    entries = layout_pathway(fig)
    assert len(_arrow_entries(entries)) == 4


def test_feedback_edge_preserves_forward_order():
    """With a feedback edge (ERK⊣RAF), entities should still appear in
    left-to-right topological order for the forward cascade (L23).
    Without _feedback_arc_dag the cycle fell back to unconstrained spring,
    which often settled right-to-left."""
    fig = _make_mapk_with_feedback()
    entries = layout_pathway(fig)
    ent_x = {e.ir_id: e.args[1][0] for e in _entity_entries(entries)}
    # Forward cascade order must be preserved: Ras→Raf→MEK→ERK (L→R).
    assert ent_x["ras"] < ent_x["raf"], "Ras should be left of Raf"
    assert ent_x["raf"] < ent_x["mek"], "Raf should be left of MEK"
    assert ent_x["mek"] < ent_x["erk"], "MEK should be left of ERK"


def test_feedback_arc_dag_returns_dag():
    """_feedback_arc_dag must produce a DAG regardless of input cycles."""
    import networkx as nx
    from imageGen.layout.pathway_layout import _feedback_arc_dag

    cyclic = nx.DiGraph([("a", "b"), ("b", "c"), ("c", "a")])
    dag = _feedback_arc_dag(cyclic)
    assert nx.is_directed_acyclic_graph(dag)
    # Original graph unchanged.
    assert not nx.is_directed_acyclic_graph(cyclic)


def test_feedback_arc_dag_identity_on_dag():
    """_feedback_arc_dag returns the same object for an already-acyclic graph."""
    import networkx as nx
    from imageGen.layout.pathway_layout import _feedback_arc_dag

    acyclic = nx.DiGraph([("a", "b"), ("b", "c")])
    result = _feedback_arc_dag(acyclic)
    assert result is acyclic  # same object — no copy


# ---------------------------------------------------------------------------
# LABEL_FIT rung 4: an unfittable entity label is placed outside on a leader
# ---------------------------------------------------------------------------

def test_unfittable_entity_label_emits_external_request():
    """A label that overflows even at the font floor gets an `_extlabel`
    LabelRequest; a label that fits in its box does not."""
    from imageGen.layout.pathway_layout import pathway_label_requests

    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="big", type=EntityType.PROTEIN,
                   label="Supercalifragilisticexpialidocious"),
            Entity(id="ok", type=EntityType.PROTEIN, label="ATP"),
        ],
        relations=[],
        compartments=[],
    )
    entries = layout_pathway(fig)
    reqs = pathway_label_requests(fig, entries)
    ext_ids = {r.ir_id for r in reqs if r.ir_id and r.ir_id.endswith("_extlabel")}
    assert "big_extlabel" in ext_ids
    assert "ok_extlabel" not in ext_ids
    # The external request carries the full, untruncated label text.
    big_req = next(r for r in reqs if r.ir_id == "big_extlabel")
    assert big_req.text == "Supercalifragilisticexpialidocious"


# ---------------------------------------------------------------------------
# FR4 — transmembrane glyphs snap onto the lipid bilayer
# ---------------------------------------------------------------------------


def test_membrane_entity_snaps_to_bilayer_plane():
    """A receptor in a MEMBRANE band is pinned to the bilayer center, not the
    band center — so the transmembrane glyph straddles both leaflets (FR4)."""
    from imageGen.primitives.membranes import DEFAULT_STYLE as _MEM

    fig = Figure(
        archetype=Archetype.PATHWAY,
        compartments=[
            Compartment(id="ext", type=CompartmentType.EXTRACELLULAR, label="Extracellular"),
            Compartment(id="mem", type=CompartmentType.MEMBRANE, label="Plasma membrane"),
            Compartment(id="cyto", type=CompartmentType.CYTOPLASM, label="Cytoplasm"),
        ],
        entities=[
            Entity(id="lig", type=EntityType.LIGAND, label="L", location="ext"),
            Entity(id="r", type=EntityType.RECEPTOR, label="R", location="mem"),
            Entity(id="g", type=EntityType.PROTEIN, label="G", location="cyto"),
        ],
        relations=[
            Relation(source="lig", target="r", type=RelationType.BINDS),
            Relation(source="r", target="g", type=RelationType.ACTIVATES),
        ],
    )
    entries = layout_pathway(fig)
    bands = {label: (y, h) for label, _, y, _, h in map(_band_geom, _band_entries(entries))}
    mem_top, mem_h = bands["Plasma membrane"]
    expected_y = mem_top + float(_MEM["bilayer_thickness"]) / 2.0

    pos = {e.ir_id: e.args[1] for e in _entity_entries(entries)}
    # Receptor sits on the bilayer plane, NOT the band center.
    assert abs(pos["r"][1] - expected_y) < 0.01
    assert abs(pos["r"][1] - (mem_top + mem_h / 2)) > 1.0


# ---------------------------------------------------------------------------
# FR8 — parallel forward/back edge labels separate onto opposite sides
# ---------------------------------------------------------------------------


def _label_priority_by_id(fig):
    from imageGen.layout.pathway_layout import pathway_label_requests
    entries = layout_pathway(fig)
    return {r.ir_id: r.priority for r in pathway_label_requests(fig, entries)}


def test_fr8_reciprocal_pair_auto_opposite_sides():
    """A labeled A→B + B→A pair auto-assigns perpendicular opposite sides."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="a", type=EntityType.PROTEIN, label="A"),
                  Entity(id="b", type=EntityType.PROTEIN, label="B")],
        relations=[
            Relation(source="a", target="b", type=RelationType.ACTIVATES, label="fwd"),
            Relation(source="b", target="a", type=RelationType.ACTIVATES, label="back"),
        ],
    )
    prio = _label_priority_by_id(fig)
    lead = {k: v[0] for k, v in prio.items()}
    assert {lead["rel_a_activates_b"], lead["rel_b_activates_a"]} == {"above", "below"}


def test_fr8_explicit_label_side_overrides_default():
    """relation.label_side leads the placement priority with that side."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="a", type=EntityType.PROTEIN, label="A"),
                  Entity(id="b", type=EntityType.PROTEIN, label="B")],
        relations=[Relation(source="a", target="b", type=RelationType.ACTIVATES,
                            label="x", label_side=RelationLabelSide.BELOW)],
    )
    prio = _label_priority_by_id(fig)
    assert prio["rel_a_activates_b"][0] == "below"


def test_fr8_single_edge_unchanged_default():
    """A lone horizontal edge keeps the pre-FR8 orientation default (above-first)."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="a", type=EntityType.PROTEIN, label="A"),
                  Entity(id="b", type=EntityType.PROTEIN, label="B")],
        relations=[Relation(source="a", target="b", type=RelationType.ACTIVATES, label="x")],
    )
    prio = _label_priority_by_id(fig)
    assert prio["rel_a_activates_b"][0] == "above"
