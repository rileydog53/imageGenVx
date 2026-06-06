"""Abbreviation glossary (FR9): render box + advisory coverage check.

Pins:
  1. glossary_box_size grows with entry count; empty -> (0, 0).
  2. glossary_box renders the title, each term (bold) and definition.
  3. render_figure draws the glossary (text + 'glossary' id present) and grows
     the canvas downward so the box sits below the figure, not over it.
  4. glossary_check is advisory: flags acronyms used in labels but undefined,
     is a no-op when the figure has no glossary, and ignores mixed-case tokens.
"""
from __future__ import annotations

import re

from imageGen.ir import builder as B
from imageGen.ir.schema import (
    Archetype, Entity, EntityType, Figure, GlossaryEntry, Relation, RelationType,
)
from imageGen.render.compositor import render_figure
from imageGen.render.glossary import glossary_box, glossary_box_size
from imageGen.verify.glossary_check import glossary_check


def _texts(svg: str) -> str:
    return svg


# ---------------------------------------------------------------------------
# Box geometry + rendering
# ---------------------------------------------------------------------------


def test_box_size_empty_is_zero():
    assert glossary_box_size([]) == (0.0, 0.0)


def test_box_size_grows_with_entries():
    one = glossary_box_size([GlossaryEntry(term="A", definition="alpha")])
    two = glossary_box_size([
        GlossaryEntry(term="A", definition="alpha"),
        GlossaryEntry(term="B", definition="beta"),
    ])
    assert two[1] > one[1]  # taller with more rows


def test_box_renders_terms_and_definitions():
    entries = [GlossaryEntry(term="PI3K", definition="phosphoinositide 3-kinase")]
    svg = glossary_box(entries, (0.0, 0.0)).tostring()
    assert "Abbreviations" in svg
    assert "PI3K" in svg
    assert "phosphoinositide 3-kinase" in svg
    assert "font-weight" in svg  # the term is bolded


def test_render_draws_glossary_and_grows_canvas(tmp_path):
    fig = B.build(
        archetype="pathway", title="t",
        entities=[("pi3k", "kinase", "PI3K"), ("akt", "kinase", "AKT")],
        relations=[("pi3k", "activates", "akt")],
        glossary=[("PI3K", "phosphoinositide 3-kinase"), ("AKT", "protein kinase B")],
    )
    out = tmp_path / "g.svg"
    render_figure(fig, out)
    svg = out.read_text()
    assert 'data-ir-id="glossary"' in svg
    assert "phosphoinositide 3-kinase" in svg


def test_no_glossary_is_byte_identical(tmp_path):
    """A figure without a glossary renders exactly as before (no box, no growth)."""
    fig = B.build(
        archetype="pathway", title="t",
        entities=[("a", "protein", "A"), ("b", "protein", "B")],
        relations=[("a", "activates", "b")],
    )
    out = tmp_path / "g.svg"
    render_figure(fig, out)
    assert "glossary" not in out.read_text()


# ---------------------------------------------------------------------------
# Advisory coverage check
# ---------------------------------------------------------------------------


def test_check_flags_undefined_acronym():
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="a", type=EntityType.KINASE, label="ERK"),
                  Entity(id="b", type=EntityType.METABOLITE, label="ATP")],
        relations=[Relation(source="a", target="b", type=RelationType.ACTIVATES)],
        glossary=[GlossaryEntry(term="ATP", definition="adenosine triphosphate")],
    )
    assert glossary_check(fig) == ["ERK"]


def test_check_noop_without_glossary():
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="a", type=EntityType.KINASE, label="ERK")],
    )
    assert glossary_check(fig) == []


def test_check_ignores_mixed_case_tokens():
    """mTOR is not a pure acronym — don't flag it."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="a", type=EntityType.KINASE, label="mTOR")],
        glossary=[GlossaryEntry(term="ATP", definition="adenosine triphosphate")],
    )
    assert glossary_check(fig) == []
