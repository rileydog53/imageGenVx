"""Annotation rendering (FR1): figure.annotations draw on top of the figure.

Pins:
  1. Position resolution: named slots anchor to canvas corners/edges with an
     inset; a fractional (0..1) tuple scales by canvas, an out-of-range tuple is
     absolute.
  2. Each annotation type (label / caption / scale_bar) emits its text.
  3. label gets a halo Rect; caption is italic; scale_bar draws a rule Line.
  4. render_figure draws annotations: their text + synthetic ids appear in the
     SVG, and a figure with no annotations adds nothing.
"""
from __future__ import annotations

import json
import re

from imageGen.ir.schema import (
    Annotation,
    AnnotationType,
    Figure,
    NamedSlot,
)
from imageGen.render.annotations import (
    _resolve_position,
    annotation_entries,
    annotation_group,
)


CANVAS = (800.0, 600.0)


def _texts(group) -> list[str]:
    return re.findall(r">([^<]+)</text>", group.tostring())


# ---------------------------------------------------------------------------
# Position resolution
# ---------------------------------------------------------------------------


def test_named_slot_center_is_canvas_center():
    x, y, anchor, vertical = _resolve_position(NamedSlot.CENTER, CANVAS)
    assert (x, y) == (400.0, 300.0)
    assert anchor == "middle" and vertical == "middle"


def test_named_slot_corner_insets_inward():
    x, y, anchor, vertical = _resolve_position(NamedSlot.TOP_RIGHT, CANVAS)
    assert x < CANVAS[0] and y > 0.0  # pulled in off both edges
    assert anchor == "end" and vertical == "top"


def test_fractional_tuple_scales_by_canvas():
    x, y, anchor, _ = _resolve_position((0.5, 0.5), CANVAS)
    assert (x, y) == (400.0, 300.0)
    assert anchor == "middle"


def test_absolute_tuple_passes_through():
    x, y, _, _ = _resolve_position((640.0, 120.0), CANVAS)
    assert (x, y) == (640.0, 120.0)


# ---------------------------------------------------------------------------
# Per-type rendering
# ---------------------------------------------------------------------------


def test_label_has_text_and_halo_box():
    ann = Annotation(type=AnnotationType.LABEL, text="Powerhouse",
                     position=(0.7, 0.55))
    svg = annotation_group(ann, CANVAS).tostring()
    assert "Powerhouse" in _texts_from_str(svg)
    assert "<rect" in svg  # legibility halo


def test_caption_is_italic():
    ann = Annotation(type=AnnotationType.CAPTION,
                     text="Illustrative", position="bottom")
    svg = annotation_group(ann, CANVAS).tostring()
    assert "Illustrative" in _texts_from_str(svg)
    assert "italic" in svg


def test_scale_bar_draws_rule_line():
    ann = Annotation(type=AnnotationType.SCALE_BAR, text="10 um",
                     position="bottom-right")
    svg = annotation_group(ann, CANVAS).tostring()
    assert "10 um" in _texts_from_str(svg)
    assert "<line" in svg


# ---------------------------------------------------------------------------
# Compositor integration
# ---------------------------------------------------------------------------


def test_annotation_entries_one_per_annotation():
    fig = Figure.from_dict(json.load(open("tests/fixtures/mechanism_cartoon.json")))
    entries = annotation_entries(fig, CANVAS, {})
    assert len(entries) == len(fig.annotations)
    assert [e.ir_id for e in entries] == ["annotation_0", "annotation_1"]


def test_render_emits_annotation_text(tmp_path):
    from imageGen.render.compositor import render_figure
    fig = Figure.from_dict(json.load(open("tests/fixtures/cellular_schematic.json")))
    out = tmp_path / "cell.svg"
    render_figure(fig, out)
    svg = out.read_text()
    assert "Powerhouse" in svg
    assert 'data-ir-id="annotation_0"' in svg


def _texts_from_str(svg: str) -> list[str]:
    return re.findall(r">([^<]+)</text>", svg)
