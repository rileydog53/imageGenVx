"""Auto-legend (Issue #4): opt-in inset key for a figure's glyph conventions.

Pins:
  1. Glyph-key detection from relations, deduplicated by visual appearance
     (activates / transcribes / generic share the filled-triangle "activation"
     glyph -> one row), in canonical order.
  2. A phosphorylated kinase entity contributes the phosphorylation badge even
     without a PHOSPHORYLATES relation.
  3. legend() draws a bordered box anchored at its top-right corner, with a
     title, one caption per key, and a 'P' badge for phosphorylation.
  4. render_figure(legend=True) appends a single unified 'info_box' entry
     containing the legend section; legend=False (default) appends nothing.
"""
from __future__ import annotations

import re

from imageGen.ir.schema import (
    Archetype,
    Entity,
    EntityType,
    Figure,
    Relation,
    RelationType,
)
from imageGen.render.legend import (
    legend,
    legend_box_size,
    legend_glyph_keys_for_figure,
)


def _texts(group) -> list[str]:
    return re.findall(r">([^<]+)</text>", group.tostring())


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------

def test_keys_dedupe_shared_glyph():
    """activates, transcribes, generic all use the filled-triangle glyph."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id=c, type=EntityType.PROTEIN, label=c) for c in "abcd"],
        relations=[
            Relation(source="a", target="b", type=RelationType.ACTIVATES),
            Relation(source="b", target="c", type=RelationType.TRANSCRIBES),
            Relation(source="c", target="d", type=RelationType.GENERIC),
        ],
    )
    assert legend_glyph_keys_for_figure(fig) == ["activation"]


def test_keys_canonical_order_and_distinct_glyphs():
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id=c, type=EntityType.PROTEIN, label=c) for c in "abcd"],
        relations=[
            Relation(source="a", target="b", type=RelationType.INHIBITS),
            Relation(source="b", target="c", type=RelationType.ACTIVATES),
            Relation(source="c", target="d", type=RelationType.BINDS),
        ],
    )
    # Canonical order is activation, inhibition, binding, ...
    assert legend_glyph_keys_for_figure(fig) == ["activation", "inhibition", "binding"]


def test_phosphorylated_entity_contributes_badge():
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="k", type=EntityType.KINASE, label="ERK",
                   style={"phosphorylated": True}),
            Entity(id="p", type=EntityType.PROTEIN, label="SUB"),
        ],
        relations=[Relation(source="k", target="p", type=RelationType.ACTIVATES)],
    )
    keys = legend_glyph_keys_for_figure(fig)
    assert "phosphorylation" in keys
    assert keys == ["activation", "phosphorylation"]


def test_no_relations_no_keys():
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="a", type=EntityType.PROTEIN, label="a")],
        relations=[],
    )
    assert legend_glyph_keys_for_figure(fig) == []


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def test_legend_renders_title_captions_and_badge():
    keys = ["activation", "phosphorylation"]
    g = legend(keys, (500.0, 12.0))
    texts = _texts(g)
    assert texts[0] == "Key"
    assert "Activation" in texts
    assert "Phosphorylation" in texts
    assert "P" in texts, "phosphorylation row must include the 'P' badge"


def test_legend_box_anchored_top_right():
    keys = ["activation", "inhibition"]
    box_w, box_h = legend_box_size(keys)
    top_right = (500.0, 12.0)
    g = legend(keys, top_right)
    xml = g.tostring()
    m = re.search(r'<rect[^>]*\bx="([\d.]+)"[^>]*\by="([\d.]+)"', xml)
    assert m, "legend must draw a bounding rect"
    rx, ry = float(m.group(1)), float(m.group(2))
    # Right edge of the box sits at the anchor x; top edge at the anchor y.
    assert abs((rx + box_w) - top_right[0]) < 0.01
    assert abs(ry - top_right[1]) < 0.01


def test_legend_box_grows_with_row_count():
    one = legend_box_size(["activation"])
    three = legend_box_size(["activation", "inhibition", "binding"])
    assert three[1] > one[1]


# ---------------------------------------------------------------------------
# Compositor integration
# ---------------------------------------------------------------------------

def _fig() -> Figure:
    return Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="a", type=EntityType.PROTEIN, label="A"),
            Entity(id="b", type=EntityType.PROTEIN, label="B"),
        ],
        relations=[Relation(source="a", target="b", type=RelationType.INHIBITS)],
    )


def test_render_figure_legend_flag_adds_info_box(tmp_path, monkeypatch):
    import imageGen.render.compositor as C

    captured: dict[str, list] = {}
    orig = C._write_svg

    def spy(entries, canvas, path):
        captured["entries"] = list(entries)
        return orig(entries, canvas, path)

    monkeypatch.setattr(C, "_write_svg", spy)

    # legend=True now rides in the single unified info box (which carries a
    # `legend` sub-group with the glyph rows).
    with_path = tmp_path / "with.svg"
    C.render_figure(_fig(), with_path, legend=True)
    ids_with = [e.ir_id for e in captured["entries"]]
    assert ids_with.count("info_box") == 1
    svg = with_path.read_text()
    assert 'data-ir-id="legend"' in svg      # legend section present inside the box
    assert "Inhibition" in svg               # the figure's INHIBITS glyph caption

    # legend=False with no glossary/credits → no info box at all.
    C.render_figure(_fig(), tmp_path / "without.svg", legend=False)
    ids_without = [e.ir_id for e in captured["entries"]]
    assert "info_box" not in ids_without
