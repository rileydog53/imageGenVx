"""Tests for verify/semantic_check.py — Phase 6 Step 1.

Covers the happy path for all three dispatch families (flat PATHWAY,
REACTION_SCHEME, multi-panel), and the failure modes: a missing entity,
a missing relation, a missing reaction anchor, and a panel-scope
mismatch. Failures are simulated by rendering a correct SVG and then
surgically editing an `id` attribute so the rendered output no longer
matches the IR — the regression `semantic_check` is meant to catch.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from imageGen.ir import Figure
from imageGen.ir.schema import Relation, RelationType
from imageGen.render.compositor import render_figure
from imageGen.verify.semantic_check import SemanticCheckError, semantic_check
from tests._helpers import load_fixture

MAPK = "mapk_cascade.json"
OXIDATION = "oxidation_reaction.json"
WORKFLOW = "three_panel_workflow.json"

OXIDATION_SMILES = {"alcohol": "CCO", "aldehyde": "CC=O"}


def _render(fixture, dest, smiles_map=None):
    """Render a fixture to `dest`; return the parsed IR Figure."""
    ir = load_fixture(fixture)
    render_figure(ir, dest, smiles_map=smiles_map)
    return ir


def _break_id(svg_path: Path, old: str, new: str) -> None:
    """Rewrite one `id="..."` attribute in a rendered SVG in place."""
    text = svg_path.read_text()
    marker = f'id="{old}"'
    assert marker in text, f"{marker!r} not in rendered SVG — test setup is stale"
    svg_path.write_text(text.replace(marker, f'id="{new}"'))


# ---------------------------------------------------------------------------
# Happy path — one per dispatch family
# ---------------------------------------------------------------------------


def test_pathway_figure_passes(tmp_path):
    svg = tmp_path / "fig.svg"
    ir = _render(MAPK, svg)
    semantic_check(ir, svg)  # no exception


def test_reaction_scheme_figure_passes(tmp_path):
    svg = tmp_path / "fig.svg"
    ir = _render(OXIDATION, svg, smiles_map=OXIDATION_SMILES)
    semantic_check(ir, svg)  # no exception


def test_panel_figure_passes(tmp_path):
    svg = tmp_path / "fig.svg"
    ir = _render(WORKFLOW, svg)
    semantic_check(ir, svg)  # no exception


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_missing_entity_raises(tmp_path):
    svg = tmp_path / "fig.svg"
    ir = _render(MAPK, svg)
    _break_id(svg, "ras", "ras_GONE")
    with pytest.raises(SemanticCheckError) as excinfo:
        semantic_check(ir, svg)
    assert excinfo.value.ir_id == "ras"
    assert excinfo.value.kind == "entity"


def test_missing_relation_raises(tmp_path):
    svg = tmp_path / "fig.svg"
    ir = _render(MAPK, svg)
    _break_id(svg, "rel_ras_activates_raf", "rel_BROKEN")
    with pytest.raises(SemanticCheckError) as excinfo:
        semantic_check(ir, svg)
    assert excinfo.value.ir_id == "rel_ras_activates_raf"
    assert excinfo.value.kind == "relation"


def test_missing_reaction_anchor_raises(tmp_path):
    svg = tmp_path / "fig.svg"
    ir = _render(OXIDATION, svg, smiles_map=OXIDATION_SMILES)
    _break_id(svg, "reaction_0", "reaction_GONE")
    with pytest.raises(SemanticCheckError) as excinfo:
        semantic_check(ir, svg)
    assert excinfo.value.kind == "reaction"


def test_reaction_molecule_present_passes(tmp_path):
    # #6: each reaction molecule is tagged with its entity id, so semantic_check
    # now verifies every molecule of a top-level reaction is rendered (not only
    # the composite reaction_0 anchor).
    svg = tmp_path / "fig.svg"
    ir = _render(OXIDATION, svg, smiles_map=OXIDATION_SMILES)
    present = svg.read_text()
    for e in ir.entities:
        assert f'id="{e.id}"' in present, f"molecule {e.id!r} not tagged"
    semantic_check(ir, svg)  # no exception


def test_missing_reaction_molecule_raises(tmp_path):
    # #6: dropping a single molecule's id now fails the check — previously a
    # reaction was audited only at reaction_0 and a missing molecule slipped by.
    svg = tmp_path / "fig.svg"
    ir = _render(OXIDATION, svg, smiles_map=OXIDATION_SMILES)
    _break_id(svg, "aldehyde", "aldehyde_GONE")
    with pytest.raises(SemanticCheckError) as excinfo:
        semantic_check(ir, svg)
    assert excinfo.value.ir_id == "aldehyde"
    assert excinfo.value.kind == "entity"


def test_panel_scope_mismatch_raises(tmp_path):
    """A mis-prefixed panel child must surface as the *expected* scoped id."""
    svg = tmp_path / "fig.svg"
    ir = _render(WORKFLOW, svg)
    _break_id(svg, "p1__cells", "wrongprefix__cells")
    with pytest.raises(SemanticCheckError) as excinfo:
        semantic_check(ir, svg)
    assert excinfo.value.scoped_id == "p1__cells"
    assert excinfo.value.ir_id == "cells"


def test_exception_attributes_are_consistent(tmp_path):
    svg = tmp_path / "fig.svg"
    ir = _render(MAPK, svg)
    _break_id(svg, "mek", "mek_GONE")
    with pytest.raises(SemanticCheckError) as excinfo:
        semantic_check(ir, svg)
    exc = excinfo.value
    assert exc.ir_id == "mek"
    assert exc.kind == "entity"
    assert exc.scoped_id == "mek"  # depth 0 → scoped id equals raw id
    assert exc.ir_id in str(exc) and exc.kind in str(exc)


def test_relation_ir_id_format():
    """Pins the synthetic relation-id format that layout + verify share."""
    r = Relation(source="a", target="b", type=RelationType.ACTIVATES)
    assert r.ir_id == "rel_a_activates_b"


# ---------------------------------------------------------------------------
# FR6 — undrawn-annotation guard (the FR1 symptom)
# ---------------------------------------------------------------------------

CELLULAR = "cellular_schematic.json"


def test_annotation_present_passes(tmp_path):
    """A figure whose annotation is drawn passes semantic_check (FR1 fixed)."""
    svg = tmp_path / "fig.svg"
    ir = _render(CELLULAR, svg)
    assert ir.annotations  # fixture really has an annotation
    semantic_check(ir, svg)  # no exception


def test_undrawn_annotation_raises(tmp_path):
    """Simulate the FR1 regression: an annotation that never rendered is caught."""
    svg = tmp_path / "fig.svg"
    ir = _render(CELLULAR, svg)
    _break_id(svg, "annotation_0", "annotation_X")
    with pytest.raises(SemanticCheckError) as ei:
        semantic_check(ir, svg)
    assert ei.value.kind == "annotation"
    assert ei.value.ir_id == "annotation_0"


# ---------------------------------------------------------------------------
# P7.0 — tier figures are audited at the scene-slot level
# ---------------------------------------------------------------------------

ASPIRIN = "C[C:1](=O)[O:3]c1ccccc1C(=O)O"


def _tier_figure() -> Figure:
    """A SCENE_ROW tier with a molecule + a text slot in one scene and a
    molecule in the next — exercising both rendered slot kinds and two scenes."""
    return Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [
            {"id": "title", "role": "title", "label": "T", "subtitle": "s"},
            {"id": "row", "role": "scene_row", "scenes": [
                {"id": "s1", "label": "one", "slots": [
                    {"id": "mol", "kind": "molecule", "style": {"smiles": "CCO"}},
                    {"id": "note", "kind": "text", "label": "hi"}]},
                {"id": "s2", "label": "two", "slots": [
                    {"id": "mol", "kind": "molecule", "style": {"smiles": "CCO"}}]},
            ]},
        ],
    })


def test_tier_figure_slots_pass(tmp_path):
    """A correctly-rendered tier figure passes — its slot ids are present."""
    svg = tmp_path / "fig.svg"
    fig = _tier_figure()
    render_figure(fig, svg)
    # the slots the verifier requires really are in the SVG
    text = svg.read_text()
    for sid in ("s1.mol", "s1.note", "s2.mol"):
        assert f'id="{sid}"' in text
    semantic_check(fig, svg)  # no exception


def test_missing_tier_slot_raises(tmp_path):
    """A tier slot absent from the SVG is caught (the regression P7.0 closes:
    before, a tier figure was silently un-audited)."""
    svg = tmp_path / "fig.svg"
    fig = _tier_figure()
    render_figure(fig, svg)
    _break_id(svg, "s1.note", "s1.GONE")
    with pytest.raises(SemanticCheckError) as ei:
        semantic_check(fig, svg)
    assert ei.value.kind == "slot"
    assert ei.value.ir_id == "s1.note"
    assert ei.value.scoped_id == "s1.note"  # tiers carry no panel chain


def test_step_sequence_tier_slots_audited(tmp_path):
    """Expanded step_sequence scenes (one per step) are audited — a base slot
    present in every step, an added slot only from the step that adds it."""
    fig = Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [{"id": "row", "role": "scene_row", "step_sequence": {
            "id": "q", "base": {"id": "base", "slots": [
                {"id": "m", "kind": "molecule", "style": {"smiles": "CCO"}}]},
            "steps": [
                {"id": "s1"},
                {"id": "s2", "deltas": [{"op": "add", "value": {
                    "id": "b", "kind": "text", "label": "B"}}]}]}}]})
    svg = tmp_path / "fig.svg"
    render_figure(fig, svg)
    semantic_check(fig, svg)  # the expanded s1.m / s2.m / s2.b are all present
    _break_id(svg, "s2.b", "s2.MISSING")
    with pytest.raises(SemanticCheckError) as ei:
        semantic_check(fig, svg)
    assert ei.value.kind == "slot" and ei.value.ir_id == "s2.b"


def test_tier_overlay_slot_audited(tmp_path):
    """An overlay scene's slot is audited too (it renders in the gutter strip)."""
    fig = Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [{"id": "row", "role": "scene_row",
                   "scenes": [{"id": "main", "slots": [
                       {"id": "m", "kind": "molecule", "style": {"smiles": "CCO"}}]}],
                   "overlays": [{"id": "ov", "slots": [
                       {"id": "g", "kind": "text", "label": "G"}]}]}]})
    svg = tmp_path / "fig.svg"
    render_figure(fig, svg)
    semantic_check(fig, svg)
    _break_id(svg, "ov.g", "ov.GONE")
    with pytest.raises(SemanticCheckError) as ei:
        semantic_check(fig, svg)
    assert ei.value.kind == "slot" and ei.value.ir_id == "ov.g"
