"""Tests for the v2.x expansion entity-glyph set.

Covers the glyphs in ``primitives/glyphs.py`` plus the two nucleic-acid add-ons
(``mrna_helix``, ``primer_helix``) that are part of the same expansion. Tests
are registry-driven so a newly-registered glyph is automatically exercised.

Each glyph must:
  * return an ``svgwrite.container.Group``;
  * render its registered convention shape as the FIRST shape element
    (``convention_check`` keys off the first shape tag);
  * include its label text.

An end-to-end test renders a pathway whose entities opt into glyphs via
``style["primitive"]`` and asserts all three verifiers pass.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
import svgwrite
import svgwrite.container

from imageGen.ir.schema import Entity, EntityType, Figure, Relation, RelationType
from imageGen.layout._geom import PRIMITIVE_REGISTRY, PRIMITIVE_TO_BBOX
from imageGen.primitives import glyphs
from imageGen.render.compositor import render_figure
from imageGen.verify.convention_check import (
    _PRIMITIVE_SHAPE,
    _SHAPE_TAGS,
    convention_check,
)
from imageGen.verify.semantic_check import semantic_check

# The glyphs introduced by the v2.x expansion (names in PRIMITIVE_REGISTRY).
# NOTE: flask and centrifuge were re-pointed to embedded Bioicons (DECISIONS D9)
# and are now covered by tests/test_entity_adapters.py + test_icon_loader.py, so
# they are no longer in this glyph-registry-driven list.
EXPANSION_GLYPHS = [
    "antibody", "ion_channel", "transporter", "pump", "phosphatase",
    "ribosome", "vesicle",
    "flow_cytometer", "sequencer", "petri_dish",
    "syringe",
    "mrna_helix", "primer_helix",
]


def _first_shape_tag(group: svgwrite.container.Group) -> str | None:
    d = svgwrite.Drawing(size=(240, 240))
    d.add(group)
    root = ET.fromstring(d.tostring())
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        if tag in _SHAPE_TAGS:
            return tag
    return None


def _all_text(group: svgwrite.container.Group) -> str:
    d = svgwrite.Drawing(size=(240, 240))
    d.add(group)
    root = ET.fromstring(d.tostring())
    return " ".join(el.text or "" for el in root.iter() if el.text)


# ---------------------------------------------------------------------------
# Registry wiring
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", EXPANSION_GLYPHS)
def test_glyph_is_registered_and_covered(name):
    assert name in PRIMITIVE_REGISTRY, f"{name} not in PRIMITIVE_REGISTRY"
    prim = PRIMITIVE_REGISTRY[name]
    assert prim in _PRIMITIVE_SHAPE, f"{name} missing from _PRIMITIVE_SHAPE"
    assert prim in PRIMITIVE_TO_BBOX, f"{name} missing from PRIMITIVE_TO_BBOX"


def test_glyphs_default_style_has_label_keys():
    for k in ("label_font_family", "label_font_size", "label_font_color"):
        assert k in glyphs.DEFAULT_STYLE


# ---------------------------------------------------------------------------
# Per-glyph rendering
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", EXPANSION_GLYPHS)
def test_glyph_returns_group(name):
    prim = PRIMITIVE_REGISTRY[name]
    g = prim(name, (120, 120), size=PRIMITIVE_TO_BBOX[prim])
    assert isinstance(g, svgwrite.container.Group)


@pytest.mark.parametrize("name", EXPANSION_GLYPHS)
def test_glyph_first_shape_matches_convention(name):
    """The first shape element must equal the registered convention shape, or
    convention_check will reject an entity that opts into the glyph."""
    prim = PRIMITIVE_REGISTRY[name]
    g = prim(name, (120, 120), size=PRIMITIVE_TO_BBOX[prim])
    assert _first_shape_tag(g) == _PRIMITIVE_SHAPE[prim]


@pytest.mark.parametrize("name", EXPANSION_GLYPHS)
def test_glyph_includes_label(name):
    prim = PRIMITIVE_REGISTRY[name]
    g = prim("MyLabel", (120, 120), size=PRIMITIVE_TO_BBOX[prim])
    assert "MyLabel" in _all_text(g)


# ---------------------------------------------------------------------------
# End-to-end: overrides render and pass the verifiers
# ---------------------------------------------------------------------------

def test_overrides_render_and_pass_verifiers(tmp_path):
    figure = Figure(
        archetype="pathway",
        title="glyph override e2e",
        entities=[
            Entity(id="ab", type=EntityType.PROTEIN, label="IgG",
                   style={"primitive": "antibody"}),
            Entity(id="pp", type=EntityType.PROTEIN, label="PP2A",
                   style={"primitive": "phosphatase"}),
            Entity(id="mr", type=EntityType.RNA, label="mRNA",
                   style={"primitive": "mrna_helix"}),
            Entity(id="fl", type=EntityType.EQUIPMENT, label="Flask",
                   style={"primitive": "flask"}),
        ],
        relations=[
            Relation(source="ab", target="pp", type=RelationType.BINDS),
            Relation(source="pp", target="mr", type=RelationType.GENERIC),
            Relation(source="mr", target="fl", type=RelationType.GENERIC),
        ],
    )
    out = tmp_path / "glyphs.png"
    render_figure(figure, str(out))
    svg = tmp_path / "glyphs.svg"
    assert svg.exists()
    # Both must pass without raising.
    semantic_check(figure, str(svg))
    convention_check(figure, str(svg))


def test_unknown_override_falls_back_without_convention_error(tmp_path):
    """An unknown primitive name warns + falls back to the type default; the
    rendered shape must then satisfy the type's convention, not raise."""
    figure = Figure(
        archetype="pathway",
        entities=[
            Entity(id="x", type=EntityType.PROTEIN, label="X",
                   style={"primitive": "does_not_exist"}),
            Entity(id="y", type=EntityType.PROTEIN, label="Y"),
        ],
        relations=[Relation(source="x", target="y", type=RelationType.ACTIVATES)],
    )
    out = tmp_path / "fallback.png"
    with pytest.warns(UserWarning):
        render_figure(figure, str(out))
    convention_check(figure, str(tmp_path / "fallback.svg"))
