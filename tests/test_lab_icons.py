"""Re-traced house-style lab glyphs (pipette, human_figure) — DECISIONS D9 / Batch 2.

These are hand-authored (no embedded asset, no license burden) and, unlike the
embedded Bioicons, are themeable via style_dict and shape-tagged for
convention_check (pipette → rect first shape, human_figure → circle).
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import svgwrite

from imageGen.ir.schema import Archetype, Entity, EntityType, Figure, Relation, RelationType
from imageGen.layout._geom import PRIMITIVE_REGISTRY
from imageGen.primitives import lab_icons
from imageGen.render.compositor import render_figure
from imageGen.verify.convention_check import _PRIMITIVE_SHAPE, convention_check
from imageGen.verify.semantic_check import semantic_check

_SHAPE = ("rect", "circle", "ellipse", "polygon", "path", "polyline")


def _first_shape(group) -> str | None:
    d = svgwrite.Drawing(size=(120, 120))
    d.add(group)
    for el in ET.fromstring(d.tostring()).iter():
        tag = el.tag.split("}")[-1]
        if tag in _SHAPE:
            return tag
    return None


def test_pipette_first_shape_is_rect():
    assert _first_shape(lab_icons.pipette()) == "rect"
    assert _PRIMITIVE_SHAPE[PRIMITIVE_REGISTRY["pipette"]] == "rect"


def test_human_first_shape_is_circle():
    assert _first_shape(lab_icons.human_figure()) == "circle"
    assert _PRIMITIVE_SHAPE[PRIMITIVE_REGISTRY["human_figure"]] == "circle"


def test_glyphs_are_themeable():
    """A style_dict color override flows through (unlike embedded Bioicons)."""
    xml = lab_icons.human_figure({"human_fill": "#123456"}).tostring()
    assert "#123456" in xml
    xml2 = lab_icons.pipette({"pipette_accent_fill": "#abcdef"}).tostring()
    assert "#abcdef" in xml2


def test_retraced_glyphs_render_and_pass_verifiers(tmp_path):
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="p", type=EntityType.EQUIPMENT, label="Micropipette"),
            Entity(id="h", type=EntityType.EQUIPMENT, label="Patient"),
        ],
        relations=[Relation(source="p", target="h", type=RelationType.GENERIC)],
    )
    out = tmp_path / "rt.svg"
    render_figure(fig, out)
    semantic_check(fig, out)
    convention_check(fig, out)   # pipette→rect, human→circle (label-inferred)
    # no icon-credit tag (these are not embedded assets)
    assert "data-icon-credit" not in out.read_text()
