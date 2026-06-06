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
