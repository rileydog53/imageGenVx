"""Unified info box: legend + abbreviations + credits in one box.

Pins:
  1. info_box_size is (0,0) when every section is empty and grows as sections
     and rows are added.
  2. info_box renders only the sections with content, each with its subtitle.
  3. The legend and abbreviations sub-groups keep data-ir-id tags so existing
     semantic checks still find them.
  4. Credit lines render as their own section.
"""
from __future__ import annotations

import re

from imageGen.ir.schema import GlossaryEntry
from imageGen.render.info_box import info_box, info_box_size

_KEYS = ["activation", "inhibition"]
_ABBR = [
    GlossaryEntry(term="PI3K", definition="phosphoinositide 3-kinase"),
    GlossaryEntry(term="AKT", definition="protein kinase B"),
]
_CREDITS = ["Western blot — Pooja (CC-BY 4.0, modified)"]


def _texts(group) -> list[str]:
    return re.findall(r">([^<]+)</text>", group.tostring())


def test_size_zero_when_all_empty():
    assert info_box_size([], [], []) == (0.0, 0.0)


def test_size_grows_with_sections_and_rows():
    one = info_box_size(_KEYS, [], [])
    two = info_box_size(_KEYS, _ABBR, [])
    three = info_box_size(_KEYS, _ABBR, _CREDITS)
    assert two[1] > one[1] > 0          # adding a section grows height
    assert three[1] > two[1]
    # more abbreviation rows → taller
    more = info_box_size(_KEYS, _ABBR + [GlossaryEntry(term="X", definition="y")], [])
    assert more[1] > two[1]


def test_renders_all_three_sections():
    g = info_box((0.0, 0.0), legend_keys=_KEYS, glossary_entries=_ABBR,
                 credit_lines=_CREDITS)
    texts = _texts(g)
    xml = g.tostring()
    # subtitles
    assert "Key" in texts and "Abbreviations" in texts and "Credits" in texts
    # legend captions + credit line render as plain <text>
    assert "Activation" in texts and "Inhibition" in texts
    assert _CREDITS[0] in texts
    # abbreviation term/definition render inside <tspan>s
    assert "PI3K" in xml and "protein kinase B" in xml


def test_empty_sections_omitted():
    g = info_box((0.0, 0.0), glossary_entries=_ABBR)  # only abbreviations
    texts = _texts(g)
    assert "Abbreviations" in texts
    assert "Key" not in texts and "Credits" not in texts


def test_subgroups_tagged_for_semantic_check():
    xml = info_box((0.0, 0.0), legend_keys=_KEYS, glossary_entries=_ABBR).tostring()
    assert 'data-ir-id="legend"' in xml
    assert 'data-ir-id="glossary"' in xml


def test_credits_only_box_renders():
    g = info_box((0.0, 0.0), credit_lines=_CREDITS)
    texts = _texts(g)
    assert "Credits" in texts and _CREDITS[0] in texts
    assert "Key" not in texts and "Abbreviations" not in texts
