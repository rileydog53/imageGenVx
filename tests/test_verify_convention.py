"""Tests for verify/convention_check.py — Phase 6 Step 3.

Covers the happy path on real fixtures (a flat PATHWAY with an inhibition
relation, a multi-panel figure, a skipped REACTION_SCHEME) and the failure
modes: an inhibition drawn with an arrowhead, an inhibition missing its
T-bar, and an entity rendered with the wrong shape for its type.

Happy paths render real fixtures so the actual renderer's output is
exercised. Failure modes pair a hand-built minimal ``Figure`` with a
hand-written SVG — the convention violation `convention_check` is meant to
catch cannot be produced by the (correct) renderer.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from imageGen.ir.schema import (
    Archetype,
    Entity,
    EntityType,
    Figure,
    Relation,
    RelationType,
)
from imageGen.render.compositor import render_figure
from imageGen.verify.convention_check import ConventionCheckError, convention_check
from tests._helpers import load_fixture

DRUG_INHIBITION = "drug_inhibition.json"
WORKFLOW = "three_panel_workflow.json"
OXIDATION = "oxidation_reaction.json"

OXIDATION_SMILES = {"alcohol": "CCO", "aldehyde": "CC=O"}


def _render(fixture, dest, smiles_map=None):
    """Render a fixture to `dest`; return the parsed IR Figure."""
    ir = load_fixture(fixture)
    render_figure(ir, dest, smiles_map=smiles_map)
    return ir


def _write_svg(path: Path, body: str) -> Path:
    """Write a minimal standalone SVG whose only content is `body`."""
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">'
        f"{body}</svg>"
    )
    return path


# ---------------------------------------------------------------------------
# Happy path — real fixtures
# ---------------------------------------------------------------------------


def test_pathway_with_inhibition_passes(tmp_path):
    """The real renderer draws inhibitions with T-bars and shapes by type."""
    svg = tmp_path / "fig.svg"
    ir = _render(DRUG_INHIBITION, svg)
    convention_check(ir, svg)  # no exception


def test_panel_figure_passes(tmp_path):
    svg = tmp_path / "fig.svg"
    ir = _render(WORKFLOW, svg)
    convention_check(ir, svg)  # no exception


def test_reaction_scheme_is_skipped(tmp_path):
    """A REACTION_SCHEME has no per-entity ids — it must pass without error."""
    svg = tmp_path / "fig.svg"
    ir = _render(OXIDATION, svg, smiles_map=OXIDATION_SMILES)
    convention_check(ir, svg)  # no exception


def test_complex_entity_renders_and_passes_convention(tmp_path):
    """LT6 ext: a 'complex' entity renders its rect-based glyph and audits clean."""
    ir = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="a", type=EntityType.PROTEIN, label="A"),
            Entity(id="rnp", type=EntityType.COMPLEX, label="RNP"),
        ],
        relations=[Relation(source="a", target="rnp", type=RelationType.BINDS)],
    )
    svg = tmp_path / "fig.svg"
    render_figure(ir, svg)
    convention_check(ir, svg)  # no exception


# ---------------------------------------------------------------------------
# Failure mode — inhibition arrows
# ---------------------------------------------------------------------------


def _inhibition_ir() -> Figure:
    """Minimal PATHWAY figure with a single drug→kinase inhibition."""
    return Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="a", type=EntityType.KINASE, label="A"),
            Entity(id="b", type=EntityType.KINASE, label="B"),
        ],
        relations=[Relation(source="a", target="b", type=RelationType.INHIBITS)],
    )


def test_arrowhead_on_inhibition_raises(tmp_path):
    ir = _inhibition_ir()
    svg = _write_svg(
        tmp_path / "fig.svg",
        '<g id="a"><polygon points="0,0 1,0 1,1" /></g>'
        '<g id="b"><polygon points="0,0 1,0 1,1" /></g>'
        '<g id="rel_a_inhibits_b">'
        '<line x1="0" y1="0" x2="10" y2="0" />'
        '<polygon points="10,0 14,2 14,-2" /></g>',
    )
    with pytest.raises(ConventionCheckError) as excinfo:
        convention_check(ir, svg)
    assert excinfo.value.kind == "inhibition_arrow"
    assert excinfo.value.ir_id == "rel_a_inhibits_b"


def test_inhibition_missing_t_bar_raises(tmp_path):
    ir = _inhibition_ir()
    svg = _write_svg(
        tmp_path / "fig.svg",
        '<g id="a"><polygon points="0,0 1,0 1,1" /></g>'
        '<g id="b"><polygon points="0,0 1,0 1,1" /></g>'
        '<g id="rel_a_inhibits_b"><line x1="0" y1="0" x2="10" y2="0" /></g>',
    )
    with pytest.raises(ConventionCheckError) as excinfo:
        convention_check(ir, svg)
    assert excinfo.value.kind == "inhibition_arrow"
    assert excinfo.value.ir_id == "rel_a_inhibits_b"


# ---------------------------------------------------------------------------
# Failure mode — entity shapes
# ---------------------------------------------------------------------------


def test_wrong_entity_shape_raises(tmp_path):
    """A KINASE rendered as a <rect> violates the polygon convention."""
    ir = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="k1", type=EntityType.KINASE, label="K1"),
            Entity(id="k2", type=EntityType.KINASE, label="K2"),
        ],
    )
    svg = _write_svg(
        tmp_path / "fig.svg",
        '<g id="k1"><polygon points="0,0 1,0 1,1" /></g>'
        '<g id="k2"><rect x="0" y="0" width="10" height="10" /></g>',
    )
    with pytest.raises(ConventionCheckError) as excinfo:
        convention_check(ir, svg)
    assert excinfo.value.kind == "entity_shape"
    assert excinfo.value.ir_id == "k2"


def test_exception_attributes_are_consistent(tmp_path):
    ir = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="k1", type=EntityType.KINASE, label="K1")],
    )
    svg = _write_svg(
        tmp_path / "fig.svg",
        '<g id="k1"><rect x="0" y="0" width="10" height="10" /></g>',
    )
    with pytest.raises(ConventionCheckError) as excinfo:
        convention_check(ir, svg)
    exc = excinfo.value
    assert exc.kind == "entity_shape"
    assert exc.ir_id == "k1"
    assert exc.detail and exc.detail in str(exc)
    assert exc.kind in str(exc)


def test_reaction_scheme_entities_not_audited(tmp_path):
    """REACTION_SCHEME entities have no per-entity ids — shapes aren't checked."""
    ir = Figure(
        archetype=Archetype.REACTION_SCHEME,
        entities=[Entity(id="k1", type=EntityType.KINASE, label="K1")],
    )
    svg = _write_svg(
        tmp_path / "fig.svg",
        '<g id="k1"><rect x="0" y="0" width="10" height="10" /></g>',
    )
    convention_check(ir, svg)  # no exception — figure is skipped


# ---------------------------------------------------------------------------
# P7.0 — tier-scene slot shapes
# ---------------------------------------------------------------------------


def _box_slot_ir() -> Figure:
    """A SCENE_ROW tier with a single BOX slot — the box convention is <rect>."""
    return Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [{"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [
                {"id": "box", "kind": "box", "label": "callout"}]}]}]})


def test_tier_molecule_text_slots_pass_convention(tmp_path):
    """MOLECULE (composite) and TEXT (text-only) slots have no conventional
    shape → skipped; a real tier render audits clean."""
    ir = Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [{"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [
                {"id": "mol", "kind": "molecule", "style": {"smiles": "CCO"}},
                {"id": "t", "kind": "text", "label": "x"}]}]}]})
    svg = tmp_path / "fig.svg"
    render_figure(ir, svg)
    convention_check(ir, svg)  # no exception


def test_tier_box_slot_wrong_shape_raises(tmp_path):
    """A BOX slot drawn as a <polygon> violates its <rect> convention. (The
    correct renderer can't yet emit a BOX, so the SVG is hand-built — the same
    pattern the entity-shape failure tests use.)"""
    ir = _box_slot_ir()
    svg = _write_svg(tmp_path / "fig.svg",
                     '<g id="s.box"><polygon points="0,0 1,0 1,1" /></g>')
    with pytest.raises(ConventionCheckError) as ei:
        convention_check(ir, svg)
    assert ei.value.kind == "slot_shape"
    assert ei.value.ir_id == "s.box"
    assert ei.value.detail and ei.value.detail in str(ei.value)


def test_tier_box_slot_correct_shape_passes(tmp_path):
    """A BOX slot drawn as a <rect> matches its convention."""
    ir = _box_slot_ir()
    svg = _write_svg(tmp_path / "fig.svg",
                     '<g id="s.box"><rect x="0" y="0" width="10" height="10" /></g>')
    convention_check(ir, svg)  # no exception


def test_tier_blob_slot_no_shape_raises(tmp_path):
    """A BLOB group with no shape element at all is caught (expected <path>)."""
    ir = Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [{"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [{"id": "blob", "kind": "blob"}]}]}]})
    svg = _write_svg(tmp_path / "fig.svg", '<g id="s.blob"><text>nope</text></g>')
    with pytest.raises(ConventionCheckError) as ei:
        convention_check(ir, svg)
    assert ei.value.kind == "slot_shape"
    assert "renders no shape element" in ei.value.detail


def test_tier_missing_slot_group_is_semantic_checks_job(tmp_path):
    """convention_check skips a slot id it can't find — a missing element is
    semantic_check's responsibility, mirroring the entity-shape contract."""
    ir = _box_slot_ir()
    svg = _write_svg(tmp_path / "fig.svg", "<g id='unrelated'></g>")
    convention_check(ir, svg)  # no exception — s.box absent, silently skipped


def _inhibits_tier_ir() -> Figure:
    """A SCENE_ROW tier with an INHIBITS cross-cell transition (a@right→b@left)."""
    return Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "a", "slots": [{"id": "m", "kind": "text", "label": "A"}]},
            {"id": "b", "slots": [{"id": "m", "kind": "text", "label": "B"}]}],
         "transitions": [{"from_ref": "a@right", "to_ref": "b@left",
                          "type": "inhibits"}]}]})


def test_tier_inhibition_with_arrowhead_raises(tmp_path):
    """P7.3c: a tier INHIBITS edge drawn with an arrowhead violates the T-bar
    convention (the bug the inhibits-T-bar fix closes)."""
    ir = _inhibits_tier_ir()
    svg = _write_svg(
        tmp_path / "fig.svg",
        '<g id="tedge_a@right_b@left"><line x1="0" y1="0" x2="10" y2="0" />'
        '<polygon points="10,0 14,2 14,-2" /></g>')
    with pytest.raises(ConventionCheckError) as ei:
        convention_check(ir, svg)
    assert ei.value.kind == "inhibition_arrow"
    assert ei.value.ir_id == "tedge_a@right_b@left"


def test_tier_inhibition_with_tbar_passes(tmp_path):
    """A square-capped T-bar terminus satisfies the convention."""
    ir = _inhibits_tier_ir()
    svg = _write_svg(
        tmp_path / "fig.svg",
        '<g id="tedge_a@right_b@left"><line x1="0" y1="0" x2="10" y2="0" />'
        '<line x1="10" y1="-5" x2="10" y2="5" stroke-linecap="square" /></g>')
    convention_check(ir, svg)  # no exception
