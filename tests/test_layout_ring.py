"""LT1 — ring (circular) layout for cyclic compartment-free pathways."""
import math
import warnings

import pytest

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
from imageGen.layout._geom import ENTITY_TO_PRIMITIVE
from imageGen.layout.pathway_layout import (
    RELATION_TO_ARROW,
    _ring_order,
    compute_pathway_canvas,
    layout_pathway,
    pathway_label_requests,
)

from tests._helpers import load_fixture


def _cycle_figure(n: int, *, hint: str | None = None, compartments=None) -> Figure:
    ents = [Entity(id=f"e{i}", type=EntityType.METABOLITE, label=f"E{i}") for i in range(n)]
    rels = [
        Relation(source=f"e{i}", target=f"e{(i + 1) % n}", type=RelationType.GENERIC)
        for i in range(n)
    ]
    return Figure(
        archetype=Archetype.PATHWAY,
        entities=ents,
        relations=rels,
        layout_hint=hint,
        compartments=compartments or [],
    )


def _chain_figure(n: int, *, hint: str | None = None) -> Figure:
    ents = [Entity(id=f"e{i}", type=EntityType.METABOLITE, label=f"E{i}") for i in range(n)]
    rels = [
        Relation(source=f"e{i}", target=f"e{i + 1}", type=RelationType.GENERIC)
        for i in range(n - 1)
    ]
    return Figure(
        archetype=Archetype.PATHWAY, entities=ents, relations=rels, layout_hint=hint
    )


def _entity_pos(entries):
    prims = set(ENTITY_TO_PRIMITIVE.values())
    return {e.ir_id: e.args[1] for e in entries if e.primitive in prims and e.ir_id}


def _centroid(pos):
    xs = [p[0] for p in pos.values()]
    ys = [p[1] for p in pos.values()]
    return sum(xs) / len(xs), sum(ys) / len(ys)


# --- detection --------------------------------------------------------------

def test_pure_single_cycle_auto_rings():
    assert _ring_order(_cycle_figure(6)) is not None


def test_two_node_cycle_does_not_ring():
    assert _ring_order(_cycle_figure(2)) is None


def test_linear_chain_does_not_ring():
    assert _ring_order(_chain_figure(5)) is None


def test_layout_hint_requires_cycle_subgraph():
    # layout_hint="circular" still requires a valid cycle after stripping dandling
    # entry nodes. A pure linear chain has no cycle subgraph → must return None.
    assert _ring_order(_chain_figure(4, hint="circular")) is None


def test_layout_hint_forces_ring_on_cycle_with_entry():
    # layout_hint="circular" on a cycle + one dangling entry node → ring mode.
    assert _ring_order(_cycle_with_entry(4, 1)) is not None


def test_ring_order_follows_cycle_adjacency():
    order, _dangling = _ring_order(_cycle_figure(5))
    # Consecutive ring slots must be adjacent in the cycle e0→e1→…→e4→e0.
    idx = {n: i for i, n in enumerate(order)}
    for i in range(5):
        assert abs(idx[f"e{i}"] - idx[f"e{(i + 1) % 5}"]) in (1, 4)


def test_layout_hint_ignored_with_compartments_warns():
    fig = _cycle_figure(
        4,
        hint="circular",
        compartments=[Compartment(id="c0", type=CompartmentType.CYTOPLASM, label="Cyto")],
    )
    for e in fig.entities:
        e.location = "c0"
    with pytest.warns(UserWarning, match="compartment-free"):
        assert _ring_order(fig) is None


# --- geometry ---------------------------------------------------------------

def test_ring_nodes_are_equidistant_from_centre():
    fig = load_fixture("krebs_cycle.json")
    entries = layout_pathway(fig)
    pos = _entity_pos(entries)
    assert len(pos) == 8
    cx, cy = _centroid(pos)
    radii = [math.hypot(x - cx, y - cy) for x, y in pos.values()]
    assert max(radii) - min(radii) < 1e-6  # exact ring


def test_ring_canvas_is_square():
    fig = load_fixture("krebs_cycle.json")
    w, h = compute_pathway_canvas(fig)
    assert w == h
    # compute_pathway_canvas and layout_pathway must agree on the envelope.
    entries = layout_pathway(fig)
    pos = _entity_pos(entries)
    for x, y in pos.values():
        assert 0 <= x <= w and 0 <= y <= h


def test_ring_arrows_are_straight_chords():
    fig = load_fixture("krebs_cycle.json")
    entries = layout_pathway(fig)
    arrows = [e for e in entries if e.primitive in set(RELATION_TO_ARROW.values())]
    assert len(arrows) == 8
    # No arch / corridor waypoints — every ring arrow is a straight chord.
    assert all(not a.kwargs.get("waypoints") for a in arrows)


def test_ring_emits_no_compartment_band():
    fig = load_fixture("krebs_cycle.json")
    entries = layout_pathway(fig)
    from imageGen.layout.pathway_layout import _compartment_band
    assert not any(e.primitive is _compartment_band for e in entries)


def test_ring_edge_labels_pushed_outside_node_radius():
    fig = load_fixture("krebs_cycle.json")
    entries = layout_pathway(fig)
    pos = _entity_pos(entries)
    cx, cy = _centroid(pos)
    node_r = math.hypot(next(iter(pos.values()))[0] - cx,
                        next(iter(pos.values()))[1] - cy)
    reqs = pathway_label_requests(fig, entries)
    assert len(reqs) == 8
    # Chord midpoints sit at node_r*cos(pi/8); the outward push must move the
    # label anchor strictly farther from centre than that midpoint.
    chord_mid_r = node_r * math.cos(math.pi / 8)
    for r in reqs:
        d = math.hypot(r.anchor[0] - cx, r.anchor[1] - cy)
        assert d > chord_mid_r


def test_linear_fixture_layout_unchanged_by_lt1():
    # A real-compartment pathway must not be touched by ring detection.
    fig = load_fixture("mapk_cascade.json")
    assert _ring_order(fig) is None


# --- dangling entry nodes (LT1 extension) -----------------------------------

def _cycle_with_entry(n_cycle: int, n_entry: int, *, hint: str = "circular") -> Figure:
    """n_cycle-node pure cycle plus n_entry dangling entry nodes feeding node 0."""
    ents = [
        Entity(id=f"e{i}", type=EntityType.METABOLITE, label=f"E{i}")
        for i in range(n_cycle)
    ]
    ents += [
        Entity(id=f"d{i}", type=EntityType.LIGAND, label=f"D{i}")
        for i in range(n_entry)
    ]
    rels = [
        Relation(source=f"e{i}", target=f"e{(i + 1) % n_cycle}", type=RelationType.GENERIC)
        for i in range(n_cycle)
    ]
    rels += [
        Relation(source=f"d{i}", target="e0", type=RelationType.GENERIC)
        for i in range(n_entry)
    ]
    return Figure(archetype=Archetype.PATHWAY, entities=ents, relations=rels, layout_hint=hint)


def test_ring_forced_with_single_dangling_entry():
    """layout_hint=circular + one dangling entry: cycle on ring, dangling off-ring."""
    fig = _cycle_with_entry(4, 1)
    result = _ring_order(fig)
    assert result is not None
    order, dangling = result
    assert set(order) == {"e0", "e1", "e2", "e3"}
    assert dangling == ["d0"]


def test_ring_no_autodetect_with_dangling_entry():
    """Without layout_hint, a cycle+dangling graph must NOT auto-detect as ring."""
    fig = _cycle_with_entry(4, 1, hint=None)
    assert _ring_order(fig) is None


def test_ring_forced_with_dangling_chain():
    """layout_hint=circular + chain of entry nodes: only cycle nodes on ring."""
    ents = [Entity(id=f"e{i}", type=EntityType.METABOLITE, label=f"E{i}") for i in range(4)]
    ents += [Entity(id="d0", type=EntityType.LIGAND, label="D0"),
             Entity(id="d1", type=EntityType.LIGAND, label="D1")]
    rels = [
        Relation(source=f"e{i}", target=f"e{(i + 1) % 4}", type=RelationType.GENERIC)
        for i in range(4)
    ]
    rels += [
        Relation(source="d0", target="d1", type=RelationType.GENERIC),
        Relation(source="d1", target="e0", type=RelationType.GENERIC),
    ]
    fig = Figure(archetype=Archetype.PATHWAY, entities=ents, relations=rels, layout_hint="circular")
    result = _ring_order(fig)
    assert result is not None
    order, dangling = result
    assert set(order) == {"e0", "e1", "e2", "e3"}
    assert set(dangling) == {"d0", "d1"}


def test_tca_8node_with_acetylcoa():
    """Krebs fixture + Acetyl-CoA: layout_hint=circular puts AcCoA off-ring."""
    fig = load_fixture("krebs_cycle.json")
    fig.entities.append(Entity(id="acoa", type=EntityType.LIGAND, label="Acetyl-CoA"))
    fig.relations.append(Relation(source="acoa", target="cit", type=RelationType.GENERIC))
    fig.layout_hint = "circular"

    result = _ring_order(fig)
    assert result is not None, "ring should activate with layout_hint=circular"
    order, dangling = result
    assert len(order) == 8
    assert "acoa" not in order
    assert "acoa" in dangling

    # Acetyl-CoA must sit outside the ring (farther from center than ring nodes)
    entries = layout_pathway(fig)
    pos = _entity_pos(entries)
    cx = sum(x for x, y in pos.values()) / len(pos)
    cy = sum(y for x, y in pos.values()) / len(pos)
    ring_radii = [math.hypot(pos[n][0] - cx, pos[n][1] - cy) for n in order if n in pos]
    avg_ring_r = sum(ring_radii) / len(ring_radii)
    acoa_r = math.hypot(pos["acoa"][0] - cx, pos["acoa"][1] - cy)
    assert acoa_r > avg_ring_r * 1.1, "Acetyl-CoA should sit outside the ring"


# ---------------------------------------------------------------------------
# FR5 — cross-link (chord) cycles auto-detect as rings
# ---------------------------------------------------------------------------


def test_ring_autodetect_cycle_with_cross_link_chord():
    """A covering cycle with an extra cross-link chord still auto-rings (FR5).

    Previously the strict degree-1 check rejected any cycle with an extra edge,
    so a real cyclic pathway with cross-links flattened to an L→R DAG."""
    ents = [Entity(id=f"e{i}", type=EntityType.METABOLITE, label=f"E{i}") for i in range(4)]
    rels = [
        Relation(source=f"e{i}", target=f"e{(i + 1) % 4}", type=RelationType.GENERIC)
        for i in range(4)
    ]
    # cross-link chord between two non-adjacent ring nodes
    rels.append(Relation(source="e1", target="e3", type=RelationType.GENERIC))
    fig = Figure(archetype=Archetype.PATHWAY, entities=ents, relations=rels)

    result = _ring_order(fig)
    assert result is not None, "cross-link cycle should auto-ring"
    order, dangling = result
    assert set(order) == {"e0", "e1", "e2", "e3"}
    assert dangling == []


def test_ring_no_autodetect_for_acyclic_cascade():
    """A linear cascade (no covering cycle) must NOT ring."""
    ents = [Entity(id=f"e{i}", type=EntityType.PROTEIN, label=f"E{i}") for i in range(4)]
    rels = [
        Relation(source=f"e{i}", target=f"e{i + 1}", type=RelationType.ACTIVATES)
        for i in range(3)
    ]
    fig = Figure(archetype=Archetype.PATHWAY, entities=ents, relations=rels)
    assert _ring_order(fig) is None


def test_ring_no_autodetect_when_cycle_misses_a_node():
    """A 3-cycle plus a dead-end branch node has no covering cycle → no ring."""
    ents = [Entity(id=f"e{i}", type=EntityType.METABOLITE, label=f"E{i}") for i in range(3)]
    ents.append(Entity(id="side", type=EntityType.METABOLITE, label="Side"))
    rels = [
        Relation(source=f"e{i}", target=f"e{(i + 1) % 3}", type=RelationType.GENERIC)
        for i in range(3)
    ]
    rels.append(Relation(source="e0", target="side", type=RelationType.GENERIC))
    rels.append(Relation(source="side", target="e1", type=RelationType.GENERIC))
    fig = Figure(archetype=Archetype.PATHWAY, entities=ents, relations=rels)
    # 'side' lies on a cycle e0->side->e1->e2->e0 — that IS a covering cycle, so
    # this should ring. Assert the broadened detector finds it.
    result = _ring_order(fig)
    assert result is not None
    assert set(result[0]) == {"e0", "e1", "e2", "side"}
