"""Tests for verify/legibility_check.py — Phase 6 Step 2.

Happy-path tests render real fixtures (one per dispatch family) and
assert a ``LegibilityResult`` comes back. Failure modes — overlapping
labels and an undersized font — and the crop signal are exercised with
small hand-written SVG fixtures, which are deterministic and far easier
than coaxing a real render into a known-bad state.
"""
from __future__ import annotations

import pytest

from imageGen.render.compositor import render_figure
from imageGen.verify.legibility_check import (
    LegibilityCheckError,
    LegibilityResult,
    legibility_check,
)
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


def _write_svg(path, width, height, body):
    """Write a minimal standalone SVG with `body` as its only content."""
    path.write_text(
        f'<svg xmlns="http://www.w3.org/2000/svg" '
        f'width="{width}" height="{height}">{body}</svg>'
    )
    return path


def _text(x, y, content, font_size=11):
    """A center-anchored <text> element, matching how the renderer emits labels."""
    return (
        f'<text x="{x}" y="{y}" font-size="{font_size}" '
        f'text-anchor="middle" dominant-baseline="central">{content}</text>'
    )


# ---------------------------------------------------------------------------
# Happy path — one per dispatch family
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture,smiles",
    [(MAPK, None), (WORKFLOW, None), (OXIDATION, OXIDATION_SMILES)],
)
def test_real_figure_passes(tmp_path, fixture, smiles):
    svg = tmp_path / "fig.svg"
    _render(fixture, svg, smiles_map=smiles)
    result = legibility_check(svg)
    assert isinstance(result, LegibilityResult)
    assert result.canvas_bbox[2] > 0 and result.canvas_bbox[3] > 0


# ---------------------------------------------------------------------------
# Failure modes
# ---------------------------------------------------------------------------


def test_overlapping_labels_raise(tmp_path):
    svg = _write_svg(
        tmp_path / "fig.svg", 200, 200,
        _text(100, 100, "Alpha") + _text(104, 100, "Beta"),
    )
    with pytest.raises(LegibilityCheckError) as excinfo:
        legibility_check(svg)
    exc = excinfo.value
    assert exc.kind == "overlap"
    assert set(exc.labels) == {"Alpha", "Beta"}
    assert "overlap" in str(exc)


def test_undersized_font_raises(tmp_path):
    svg = _write_svg(
        tmp_path / "fig.svg", 200, 200,
        _text(100, 100, "Tiny", font_size=3),
    )
    with pytest.raises(LegibilityCheckError) as excinfo:
        legibility_check(svg)
    exc = excinfo.value
    assert exc.kind == "font_size"
    assert exc.labels == ("Tiny",)
    assert "Tiny" in str(exc)


def test_undersized_font_threshold_is_configurable(tmp_path):
    """An 8pt label passes by default but fails a stricter floor."""
    svg = _write_svg(tmp_path / "fig.svg", 200, 200, _text(100, 100, "Mid", font_size=8))
    legibility_check(svg)  # 8 >= default 6.0 — no raise
    with pytest.raises(LegibilityCheckError):
        legibility_check(svg, min_font_size=10.0)


# ---------------------------------------------------------------------------
# Crop signal
# ---------------------------------------------------------------------------


def test_sparse_content_needs_crop(tmp_path):
    """A small label alone on a large canvas leaves excess whitespace."""
    svg = _write_svg(tmp_path / "fig.svg", 1000, 1000, _text(60, 60, "Lonely"))
    result = legibility_check(svg)
    assert result.needs_crop is True
    assert result.canvas_bbox == (0.0, 0.0, 1000.0, 1000.0)


def test_viewbox_offset_is_measured_against_its_own_frame(tmp_path):
    """LT5: a viewBox-cropped SVG is measured against the viewBox, not (0,0,w,h).

    L22 autocrop trims by shifting the viewBox origin rather than translating
    content. A figure whose content lives at y≈30 inside a viewBox starting at
    y=27 fills its frame and must NOT report needs_crop.
    """
    path = tmp_path / "fig.svg"
    path.write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" '
        'width="200" height="146" viewBox="0 27 200 146">'
        '<rect x="10" y="37" width="180" height="126" />'
        + _text(100, 100, "Tight")
        + "</svg>"
    )
    result = legibility_check(path)
    assert result.needs_crop is False
    assert result.canvas_bbox == (0.0, 27.0, 200.0, 173.0)


def test_dense_content_no_crop(tmp_path):
    """Content (a rect) filling the canvas leaves no croppable whitespace."""
    svg = _write_svg(
        tmp_path / "fig.svg", 200, 200,
        '<rect x="0" y="0" width="200" height="200" />' + _text(100, 100, "Full"),
    )
    result = legibility_check(svg)
    assert result.needs_crop is False
    assert result.content_bbox == (0.0, 0.0, 200.0, 200.0)


# ---------------------------------------------------------------------------
# LT3 — phosphorylation 'P' badge must not collide with the relation label
# ---------------------------------------------------------------------------


def test_phospho_badge_does_not_collide_with_relation_label(tmp_path):
    """A labeled phosphorylation edge renders legibly (LT3 regression).

    Before LT3 the 'P' badge text and the relation label both anchored at the
    arrow midpoint and overlapped, failing legibility_check. Feeding the badge
    bbox into the label engine's occupied set steers the label clear.
    """
    svg = tmp_path / "mapk_phospho.svg"
    _render("mapk_phospho_label.json", svg)
    result = legibility_check(svg)  # must not raise on the P/label overlap
    assert isinstance(result, LegibilityResult)


# ---------------------------------------------------------------------------
# LT4 — panel labels must stay inside their cell, not spill into neighbors
# ---------------------------------------------------------------------------


def test_panel_labels_do_not_spill_into_neighbor(tmp_path):
    """A narrow-panel workflow with wide labels renders legibly (LT4 regression).

    Before LT4 a wide entity label in one panel (e.g. 'Enzymatic digestion')
    spilled past its cell edge and overlapped the adjacent panel's label. The
    label-aware x-clamp keeps each entity's label inside its own cell.
    """
    svg = tmp_path / "scrnaseq.svg"
    _render("scrnaseq_workflow.json", svg)
    result = legibility_check(svg)  # must not raise on cross-panel overlap
    assert isinstance(result, LegibilityResult)


# ---------------------------------------------------------------------------
# FR6 — off-canvas text guard (the FR3 symptom)
# ---------------------------------------------------------------------------


def test_off_canvas_text_raises(tmp_path):
    """A label whose box spills past the viewport is flagged (FR6/FR3)."""
    svg = tmp_path / "off.svg"
    _write_svg(svg, 100, 50, '<text x="80" y="25" font-size="12">overflowing label</text>')
    with pytest.raises(LegibilityCheckError) as ei:
        legibility_check(svg)
    assert ei.value.kind == "off_canvas"


def test_text_within_canvas_passes(tmp_path):
    """A label comfortably inside the viewport does not trip the guard."""
    svg = tmp_path / "ok.svg"
    _write_svg(svg, 400, 100, '<text x="20" y="50" font-size="12">fits fine</text>')
    assert isinstance(legibility_check(svg), LegibilityResult)


def test_rendered_annotation_figure_stays_on_canvas(tmp_path):
    """A real figure with an edge annotation expands its frame, so legibility
    sees every label on-canvas (FR3 + FR6 working together)."""
    from imageGen.ir.schema import (
        Annotation, AnnotationType, Archetype, Entity, EntityType, Figure,
    )
    ir = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="a", type=EntityType.METABOLITE, label="A")],
        relations=[],
        annotations=[Annotation(type=AnnotationType.LABEL,
                                text="far right edge label",
                                position=(0.97, 0.5))],
    )
    svg = tmp_path / "ann.svg"
    render_figure(ir, svg)
    assert isinstance(legibility_check(svg), LegibilityResult)
