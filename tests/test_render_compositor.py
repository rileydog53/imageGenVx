"""Tests for render/compositor.py — Phase 5 Steps 1–2.

Covers: render_figure return value, SVG file validity, style resolution,
format inference/rejection, archetype dispatch (PATHWAY + REACTION_SCHEME),
IR-id tagging (D1), label auto-invoke (D3), and
golden-SVG structure checks for mapk_cascade and oxidation_reaction.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
from PIL import Image

from imageGen.ir.schema import (
    Archetype,
    Entity,
    EntityType,
    Figure,
    Relation,
    RelationType,
)
from imageGen.render.compositor import (
    _build_panel_styles,
    _is_multistep_reaction,
    _resolve_format,
    _resolve_style,
    render_figure,
    scoped_id,
)
from tests._helpers import load_fixture

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MAPK = "mapk_cascade.json"
TRANSLOCATION = "multi_compartment_translocation.json"
OXIDATION = "oxidation_reaction.json"
WORKFLOW_FIXTURE = "three_panel_workflow.json"

# Ethanol -> Acetaldehyde for the oxidation_reaction fixture.
OXIDATION_SMILES = {"alcohol": "CCO", "aldehyde": "CC=O"}


# ---------------------------------------------------------------------------
# Return value and file output
# ---------------------------------------------------------------------------


def test_render_figure_returns_path(tmp_path):
    ir = load_fixture(MAPK)
    out = render_figure(ir, tmp_path / "fig.svg")
    assert isinstance(out, Path)


def test_output_file_exists(tmp_path):
    ir = load_fixture(MAPK)
    out = render_figure(ir, tmp_path / "fig.svg")
    assert out.exists()


def test_output_is_valid_xml(tmp_path):
    ir = load_fixture(MAPK)
    out = render_figure(ir, tmp_path / "fig.svg")
    ET.parse(str(out))  # raises if not valid XML


def test_output_root_is_svg(tmp_path):
    ir = load_fixture(MAPK)
    out = render_figure(ir, tmp_path / "fig.svg")
    tree = ET.parse(str(out))
    root = tree.getroot()
    assert root.tag.endswith("svg")


# ---------------------------------------------------------------------------
# Style resolution
# ---------------------------------------------------------------------------


def test_style_kwarg_overrides_ir_preset(tmp_path):
    ir = load_fixture(MAPK)
    # Should not raise even when style_name differs from any ir.style_preset
    out = render_figure(ir, tmp_path / "fig.svg", style_name="nature")
    assert out.exists()


def test_style_falls_back_to_cell_press_when_neither_set(tmp_path):
    # _resolve_style with no kwarg and no ir.style_preset should use DEFAULT_PRESET
    from imageGen.ir.schema import Figure, Archetype
    from imageGen.render.compositor import _resolve_style
    from imageGen.styles.loader import DEFAULT_PRESET, load_style
    ir = load_fixture(MAPK)
    ir_no_preset = ir.model_copy(update={"style_preset": None})
    assert ir_no_preset.style_preset is None
    d = _resolve_style(ir_no_preset, None)
    assert d == load_style(DEFAULT_PRESET)


def test_resolve_style_prefers_kwarg_over_ir():
    ir = load_fixture(MAPK)
    d = _resolve_style(ir, "nature")
    from imageGen.styles.loader import load_style
    assert d == load_style("nature")


def test_resolve_style_falls_back_to_default():
    ir = load_fixture(MAPK)
    from imageGen.styles.loader import DEFAULT_PRESET, load_style
    d = _resolve_style(ir, None)
    assert d == load_style(DEFAULT_PRESET)


# ---------------------------------------------------------------------------
# Format resolution
# ---------------------------------------------------------------------------


def test_format_inferred_from_svg_suffix(tmp_path):
    assert _resolve_format(tmp_path / "x.svg", None) == "svg"


def test_unknown_suffix_raises_value_error(tmp_path):
    with pytest.raises(ValueError, match="Cannot infer"):
        _resolve_format(tmp_path / "x.tiff", None)


def test_explicit_svg_format_accepted(tmp_path):
    assert _resolve_format(tmp_path / "x.svg", "svg") == "svg"


def test_explicit_png_format_accepted(tmp_path):
    assert _resolve_format(tmp_path / "x.png", "png") == "png"


def test_explicit_pdf_format_accepted(tmp_path):
    assert _resolve_format(tmp_path / "x.pdf", "pdf") == "pdf"


# ---------------------------------------------------------------------------
# Non-SVG output (Step 4: PNG + PDF via render/export.py)
# ---------------------------------------------------------------------------


def test_render_figure_png_end_to_end(tmp_path):
    """`format='png'` writes a Pillow-readable PNG plus a sibling SVG."""
    ir = load_fixture(MAPK)
    out = render_figure(ir, tmp_path / "fig.png")
    assert out == tmp_path / "fig.png"
    assert out.exists()
    assert (tmp_path / "fig.svg").exists(), "sibling SVG should be persisted"
    with Image.open(out) as img:
        assert img.format == "PNG"


def test_render_figure_pdf_end_to_end(tmp_path):
    """`format='pdf'` writes a real PDF plus a sibling SVG."""
    ir = load_fixture(MAPK)
    out = render_figure(ir, tmp_path / "fig.pdf")
    assert out == tmp_path / "fig.pdf"
    assert out.exists()
    assert out.read_bytes().startswith(b"%PDF-")
    assert (tmp_path / "fig.svg").exists(), "sibling SVG should be persisted"


def test_render_figure_png_forwards_dpi(tmp_path):
    """Higher `dpi` yields a larger PNG — proves the kwarg threads through."""
    ir = load_fixture(MAPK)
    lo = render_figure(ir, tmp_path / "lo.png", dpi=96)
    hi = render_figure(ir, tmp_path / "hi.png", dpi=300)
    with Image.open(lo) as a, Image.open(hi) as b:
        assert b.width > a.width


def test_render_figure_format_kwarg_overrides_suffix(tmp_path):
    """Explicit `format='png'` on a non-png suffix still produces a PNG."""
    ir = load_fixture(MAPK)
    out = render_figure(ir, tmp_path / "fig.out", format="png")
    assert out.exists()
    with Image.open(out) as img:
        assert img.format == "PNG"


# ---------------------------------------------------------------------------
# Archetype dispatch
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "fixture",
    [
        "western_blot_schematic.json",  # WORKFLOW
        "cellular_schematic.json",  # CELLULAR_SCHEMATIC
        "mechanism_cartoon.json",  # MECHANISM_CARTOON
    ],
)
def test_pathway_compatible_leaf_archetype_renders(fixture, tmp_path):
    """Leaf WORKFLOW / CELLULAR_SCHEMATIC / MECHANISM_CARTOON figures route
    through layout_pathway — wired in Phase 7 (previously NotImplementedError).

    Rendered with labels off: this isolates the dispatch fix from the greedy
    label engine, which overflows on some of these fixtures (BACKLOG L2/L14).
    """
    ir = load_fixture(fixture)
    assert not ir.panels
    out = render_figure(ir, tmp_path / f"{Path(fixture).stem}.svg", labels=False)
    assert out.exists() and out.stat().st_size > 0
    ET.parse(str(out))  # well-formed SVG


def test_pathway_archetype_does_not_raise(tmp_path):
    ir = load_fixture(MAPK)
    render_figure(ir, tmp_path / "fig.svg")  # no exception


def test_pathway_archetype_ignores_smiles_map(tmp_path):
    """Regression: smiles_map=None on a PATHWAY must not raise (smiles_map
    is REACTION_SCHEME-only)."""
    ir = load_fixture(MAPK)
    render_figure(ir, tmp_path / "fig.svg", smiles_map=None)  # no exception


# ---------------------------------------------------------------------------
# REACTION_SCHEME dispatch (Step 2)
# ---------------------------------------------------------------------------


def test_reaction_scheme_renders_with_smiles_map(tmp_path):
    ir = load_fixture(OXIDATION)
    out = render_figure(ir, tmp_path / "fig.svg", smiles_map=OXIDATION_SMILES)
    assert out.exists()


def test_reaction_scheme_output_is_valid_xml(tmp_path):
    ir = load_fixture(OXIDATION)
    out = render_figure(ir, tmp_path / "fig.svg", smiles_map=OXIDATION_SMILES)
    ET.parse(str(out))  # raises if not valid XML


def test_reaction_scheme_missing_smiles_map_raises(tmp_path):
    """ValueError must list every entity id when smiles_map is None."""
    ir = load_fixture(OXIDATION)
    with pytest.raises(ValueError, match="smiles_map required for REACTION_SCHEME") as exc:
        render_figure(ir, tmp_path / "fig.svg")  # smiles_map omitted
    for eid in ("alcohol", "aldehyde"):
        assert eid in str(exc.value), f"entity id {eid!r} not in error message"


def test_reaction_scheme_tagged_with_data_ir_id(tmp_path):
    """D1: the reaction_0 entry's group must carry data-ir-id.

    Guards the debug=False path in _tag_group / _write_svg — svgwrite's
    strict validator rejects data-* attrs by default.
    """
    ir = load_fixture(OXIDATION)
    out = render_figure(ir, tmp_path / "fig.svg", smiles_map=OXIDATION_SMILES)
    tagged = _svg_elements_with_attr(out, "data-ir-id")
    assert "reaction_0" in tagged


def test_reaction_scheme_style_kwarg_accepted(tmp_path):
    ir = load_fixture(OXIDATION)
    out = render_figure(
        ir, tmp_path / "fig.svg", style_name="nature", smiles_map=OXIDATION_SMILES
    )
    assert out.exists()


def test_golden_svg_oxidation_reaction(tmp_path):
    """Render oxidation_reaction and verify the reaction_0 group is tagged."""
    ir = load_fixture(OXIDATION)
    out = render_figure(
        ir, tmp_path / "oxidation_reaction.svg", smiles_map=OXIDATION_SMILES
    )

    tagged = _svg_elements_with_attr(out, "data-ir-id")
    assert "reaction_0" in tagged

    # Produce a fixture PNG for visual inspection (mirrors mapk_cascade).
    from tests._helpers import FIGURES_DIR
    import cairosvg
    FIGURES_DIR.mkdir(exist_ok=True)
    png_path = FIGURES_DIR / "compositor_oxidation_reaction.png"
    png_path.write_bytes(cairosvg.svg2png(url=str(out)))
    assert png_path.exists()


# ---------------------------------------------------------------------------
# Multi-step reaction routing (R3): A→B→C is rendered as a pathway, not a
# single reactant→product reaction row.
# ---------------------------------------------------------------------------


def _multistep_reaction(n_steps: int = 2) -> Figure:
    """A REACTION_SCHEME chain e0→e1→…→e{n} (every middle entity an intermediate)."""
    entities = [
        Entity(id=f"e{i}", type=EntityType.METABOLITE, label=f"M{i}")
        for i in range(n_steps + 1)
    ]
    relations = [
        Relation(source=f"e{i}", target=f"e{i + 1}", type=RelationType.GENERIC)
        for i in range(n_steps)
    ]
    return Figure(
        archetype=Archetype.REACTION_SCHEME, entities=entities, relations=relations
    )


def test_is_multistep_reaction_predicate():
    """The predicate is True only for a REACTION_SCHEME with an intermediate."""
    assert _is_multistep_reaction(_multistep_reaction(2)) is True
    # Single-step: distinct source and target sets, no intermediate.
    single = Figure(
        archetype=Archetype.REACTION_SCHEME,
        entities=[
            Entity(id="a", type=EntityType.METABOLITE, label="A"),
            Entity(id="p", type=EntityType.METABOLITE, label="P"),
        ],
        relations=[Relation(source="a", target="p", type=RelationType.GENERIC)],
    )
    assert _is_multistep_reaction(single) is False
    # A genuine pathway is never treated as a multi-step reaction.
    assert _is_multistep_reaction(load_fixture(MAPK)) is False


def test_linear_multistep_reaction_requires_smiles_map(tmp_path):
    """R6: a linear multi-step chain now renders real structures, so it needs a
    smiles_map just like a single-step scheme — omitting it raises."""
    ir = _multistep_reaction(2)
    with pytest.raises(ValueError, match="smiles_map required"):
        render_figure(ir, tmp_path / "fig.svg")  # no smiles_map


def test_linear_multistep_reaction_uses_reaction_path(tmp_path):
    """R6: the chain renders as a molecule sequence (reaction_0 group present),
    NOT per-entity pathway boxes."""
    ir = _multistep_reaction(2)
    smiles = {e.id: "C" * (i + 1) for i, e in enumerate(ir.entities)}
    out = render_figure(ir, tmp_path / "fig.svg", smiles_map=smiles)
    tagged = _svg_elements_with_attr(out, "data-ir-id")
    assert "reaction_0" in tagged, "reaction_0 absent — did not route to layout_reaction"
    # Per-entity ids are NOT tagged: the chain is a single composite group.
    for e in ir.entities:
        assert e.id not in tagged, f"entity {e.id!r} tagged — routed to pathway, not reaction"


def _convergent_multistep_reaction() -> Figure:
    """A convergent (non-linear) multi-step REACTION_SCHEME: e0,e1 → e2 → e3."""
    entities = [
        Entity(id=f"e{i}", type=EntityType.METABOLITE, label=f"M{i}") for i in range(4)
    ]
    relations = [
        Relation(source="e0", target="e2", type=RelationType.GENERIC),
        Relation(source="e1", target="e2", type=RelationType.GENERIC),
        Relation(source="e2", target="e3", type=RelationType.GENERIC),
    ]
    return Figure(archetype=Archetype.REACTION_SCHEME, entities=entities, relations=relations)


def test_nonlinear_multistep_reaction_falls_back_to_pathway(tmp_path):
    """PH.1: with the explicit opt-in (pathway_fallback=True), a convergent
    multi-step graph coerces to the pathway engine: per-entity boxes, no
    reaction_0, and a SMILES-drop warning."""
    ir = _convergent_multistep_reaction()
    smiles = {e.id: "C" for e in ir.entities}
    with pytest.warns(UserWarning, match="SMILES structures will not be drawn"):
        out = render_figure(ir, tmp_path / "fig.svg", smiles_map=smiles,
                            pathway_fallback=True)
    tagged = _svg_elements_with_attr(out, "data-ir-id")
    assert "reaction_0" not in tagged
    for e in ir.entities:
        assert e.id in tagged, f"entity {e.id!r} not tagged — did not route to pathway"


def test_nonlinear_multistep_reaction_fails_loud_by_default(tmp_path):
    """PH.1: a non-linear multi-step reaction fails loud by default — the
    previously-silent no-smiles downgrade path now raises instead of quietly
    rendering as a pathway."""
    ir = _convergent_multistep_reaction()
    # No smiles_map, no fallback: previously a SILENT downgrade — now fail-loud.
    with pytest.raises(NotImplementedError, match="non-linear multi-step"):
        render_figure(ir, tmp_path / "fig.svg")
    # Even with a smiles_map, default behaviour is fail-loud (no silent coercion).
    with pytest.raises(NotImplementedError, match="non-linear multi-step"):
        render_figure(ir, tmp_path / "fig2.svg",
                      smiles_map={e.id: "C" for e in ir.entities})


def test_cyclic_multistep_reaction_fails_loud(tmp_path):
    """PH.1: an A→B→C→A cycle is a non-linear multi-step reaction; it fails loud
    by default and renders (with a warning) only under the explicit opt-in."""
    entities = [
        Entity(id=x, type=EntityType.METABOLITE, label=x.upper())
        for x in ("a", "b", "c")
    ]
    relations = [
        Relation(source="a", target="b", type=RelationType.GENERIC),
        Relation(source="b", target="c", type=RelationType.GENERIC),
        Relation(source="c", target="a", type=RelationType.GENERIC),
    ]
    ir = Figure(archetype=Archetype.REACTION_SCHEME, entities=entities, relations=relations)
    smiles = {e.id: "C" for e in ir.entities}
    with pytest.raises(NotImplementedError, match="non-linear multi-step"):
        render_figure(ir, tmp_path / "cyc.svg", smiles_map=smiles)
    with pytest.warns(UserWarning, match="SMILES structures will not be drawn"):
        render_figure(ir, tmp_path / "cyc2.svg", smiles_map=smiles,
                      pathway_fallback=True)


# ---------------------------------------------------------------------------
# IR-id tagging (D1)
# ---------------------------------------------------------------------------


def _svg_elements_with_attr(svg_path: Path, attr: str) -> list[str]:
    """Return all values of `attr` found on any element in the SVG."""
    tree = ET.parse(str(svg_path))
    return [el.get(attr) for el in tree.iter() if el.get(attr) is not None]


def test_entity_ids_tagged_as_data_ir_id(tmp_path):
    ir = load_fixture(MAPK)
    out = render_figure(ir, tmp_path / "fig.svg")
    tagged = _svg_elements_with_attr(out, "data-ir-id")
    entity_ids = {e.id for e in ir.entities}
    for eid in entity_ids:
        assert eid in tagged, f"entity id {eid!r} not found in data-ir-id attrs"


def test_compartment_ids_tagged_as_data_ir_id(tmp_path):
    ir = load_fixture(TRANSLOCATION)
    assert ir.compartments, "fixture must have compartments"
    out = render_figure(ir, tmp_path / "fig.svg")
    tagged = _svg_elements_with_attr(out, "data-ir-id")
    for c in ir.compartments:
        assert c.id in tagged, f"compartment id {c.id!r} not found in data-ir-id attrs"


def test_relation_synthetic_ids_tagged(tmp_path):
    ir = load_fixture(MAPK)
    out = render_figure(ir, tmp_path / "fig.svg")
    tagged = _svg_elements_with_attr(out, "data-ir-id")
    for r in ir.relations:
        assert r.ir_id in tagged, f"relation id {r.ir_id!r} not found in data-ir-id attrs"


def test_scoped_id_at_depth_zero_equals_raw_id():
    assert scoped_id("ras", ()) == "ras"


def test_scoped_id_with_panel_chain():
    assert scoped_id("ras", ("panel_a",)) == "panel_a__ras"
    assert scoped_id("ras", ("panel_a", "panel_b")) == "panel_a__panel_b__ras"


def test_svg_id_equals_data_ir_id_at_depth_zero(tmp_path):
    """At depth 0 (no panel nesting) the SVG id and data-ir-id must match."""
    ir = load_fixture(MAPK)
    out = render_figure(ir, tmp_path / "fig.svg")
    tree = ET.parse(str(out))
    for el in tree.iter():
        if el.get("data-ir-id") is not None:
            assert el.get("id") == el.get("data-ir-id"), (
                f"id {el.get('id')!r} != data-ir-id {el.get('data-ir-id')!r}"
            )


# ---------------------------------------------------------------------------
# Label auto-invoke (D3)
# ---------------------------------------------------------------------------


def test_labels_true_produces_label_elements(tmp_path):
    ir = load_fixture(TRANSLOCATION)
    labeled_rels = [r for r in ir.relations if r.label]
    assert labeled_rels, "fixture must have labeled relations"
    out = render_figure(ir, tmp_path / "fig.svg", labels=True)
    tagged = _svg_elements_with_attr(out, "data-ir-id")
    label_tags = [t for t in tagged if t.startswith("label_")]
    assert label_tags, "expected label_ data-ir-id entries with labels=True"


def test_labels_false_suppresses_label_elements(tmp_path):
    ir = load_fixture(TRANSLOCATION)
    out = render_figure(ir, tmp_path / "fig.svg", labels=False)
    tagged = _svg_elements_with_attr(out, "data-ir-id")
    label_tags = [t for t in tagged if t.startswith("label_")]
    assert not label_tags, "expected no label_ data-ir-id entries with labels=False"


# ---------------------------------------------------------------------------
# Golden SVG — structure check (not pixel-level)
# ---------------------------------------------------------------------------


def test_golden_svg_mapk_cascade(tmp_path):
    """Render mapk_cascade and verify structure: all 4 entities + 3 relations tagged."""
    ir = load_fixture(MAPK)
    out = render_figure(ir, tmp_path / "mapk_cascade.svg")

    tagged = _svg_elements_with_attr(out, "data-ir-id")
    # 4 entities
    for eid in ("ras", "raf", "mek", "erk"):
        assert eid in tagged
    # 3 relations
    assert "rel_ras_activates_raf" in tagged
    assert "rel_raf_phosphorylates_mek" in tagged
    assert "rel_mek_phosphorylates_erk" in tagged

    # Produce a fixture PNG for visual inspection
    from tests._helpers import FIGURES_DIR
    import cairosvg
    FIGURES_DIR.mkdir(exist_ok=True)
    png_path = FIGURES_DIR / "compositor_mapk_cascade.png"
    png_path.write_bytes(cairosvg.svg2png(url=str(out)))
    assert png_path.exists()


# ---------------------------------------------------------------------------
# PANEL dispatch (Step 3)
# ---------------------------------------------------------------------------


def _svg_id_pairs(svg_path: Path) -> list[tuple[str | None, str | None]]:
    """Return (id, data-ir-id) for every element carrying data-ir-id."""
    tree = ET.parse(str(svg_path))
    return [
        (el.get("id"), el.get("data-ir-id"))
        for el in tree.iter()
        if el.get("data-ir-id") is not None
    ]


def test_panel_figure_renders(tmp_path):
    ir = load_fixture(WORKFLOW_FIXTURE)
    assert ir.panels, "fixture must have panels"
    out = render_figure(ir, tmp_path / "fig.svg")
    assert out.exists()


def test_panel_figure_output_is_valid_xml(tmp_path):
    ir = load_fixture(WORKFLOW_FIXTURE)
    out = render_figure(ir, tmp_path / "fig.svg")
    ET.parse(str(out))  # raises if not valid XML


def test_panel_entity_ids_have_scoped_svg_ids(tmp_path):
    """Each entity from each panel.content has id=<panel.id>__<entity.id>
    and data-ir-id=<entity.id> (D1)."""
    ir = load_fixture(WORKFLOW_FIXTURE)
    out = render_figure(ir, tmp_path / "fig.svg")
    pairs = _svg_id_pairs(out)
    by_data: dict[str, set[str | None]] = {}
    for svg_id, data_id in pairs:
        by_data.setdefault(data_id, set()).add(svg_id)

    for panel in ir.panels:
        for entity in panel.content.entities:
            scoped = f"{panel.id}__{entity.id}"
            assert entity.id in by_data, (
                f"data-ir-id {entity.id!r} not found in SVG"
            )
            assert scoped in by_data[entity.id], (
                f"expected svg id {scoped!r} for entity {entity.id!r}, "
                f"got {by_data[entity.id]!r}"
            )


def test_panel_chrome_tagged_with_unprefixed_ids(tmp_path):
    """Chrome entries' ir_id is already panel-scoped (`p1_chrome`);
    panel_chain is empty so SVG id == data-ir-id."""
    ir = load_fixture(WORKFLOW_FIXTURE)
    out = render_figure(ir, tmp_path / "fig.svg")
    pairs = _svg_id_pairs(out)
    for panel in ir.panels:
        chrome_id = f"{panel.id}_chrome"
        match = [(s, d) for s, d in pairs if d == chrome_id]
        assert match, f"chrome data-ir-id {chrome_id!r} not found"
        assert all(s == chrome_id for s, _ in match), (
            f"chrome svg id should equal data-ir-id {chrome_id!r}, "
            f"got {match!r}"
        )


def test_panel_labels_placed_per_panel(tmp_path):
    """Relation labels (e.g. `treat`, `lyse`) render and carry
    panel-scoped svg ids."""
    ir = load_fixture(WORKFLOW_FIXTURE)
    out = render_figure(ir, tmp_path / "fig.svg", labels=True)
    pairs = _svg_id_pairs(out)
    label_pairs = [(s, d) for s, d in pairs if d and d.startswith("label_")]
    assert label_pairs, "expected at least one label_* data-ir-id"
    # At least one label's svg id should be panel-scoped.
    scoped = [
        (s, d) for s, d in label_pairs
        if s and "__" in s and s.split("__", 1)[1] == d
    ]
    assert scoped, (
        f"expected at least one label with panel-scoped svg id, "
        f"got {label_pairs!r}"
    )


def test_panel_figure_with_reaction_inside(tmp_path):
    """Flat smiles_map broadcasts to all panels; one REACTION_SCHEME
    panel renders without error."""
    ir = Figure(
        archetype=Archetype.WORKFLOW,
        title="reaction-in-panel",
        panels=[
            {
                "id": "p1",
                "title": "Step 1",
                "grid": [0, 0, 1, 1],
                "content": {
                    "archetype": "workflow",
                    "entities": [
                        {"id": "cells", "type": "sample", "label": "Cells"},
                        {"id": "drug", "type": "ligand", "label": "Drug"},
                    ],
                    "relations": [
                        {"source": "drug", "target": "cells", "type": "generic"}
                    ],
                },
            },
            {
                "id": "p2",
                "title": "Step 2",
                "grid": [0, 1, 1, 1],
                "content": {
                    "archetype": "reaction_scheme",
                    "entities": [
                        {"id": "alcohol", "type": "metabolite", "label": "EtOH"},
                        {"id": "aldehyde", "type": "metabolite", "label": "AcH"},
                    ],
                    "relations": [
                        {"source": "alcohol", "target": "aldehyde", "type": "generic"}
                    ],
                },
            },
        ],
    )
    smiles_map = {"alcohol": "CCO", "aldehyde": "CC=O"}
    out = render_figure(ir, tmp_path / "fig.svg", smiles_map=smiles_map)
    assert out.exists()
    pairs = _svg_id_pairs(out)
    data_ids = {d for _, d in pairs}
    assert "reaction_0" in data_ids
    assert "cells" in data_ids


def test_panel_figure_missing_smiles_map_raises_for_reaction_panel(tmp_path):
    """Omitting smiles_map when a panel contains a REACTION_SCHEME
    raises ValueError naming the reaction panel id."""
    ir = Figure(
        archetype=Archetype.WORKFLOW,
        panels=[
            {
                "id": "rxn_panel",
                "title": "Rxn",
                "grid": [0, 0, 1, 1],
                "content": {
                    "archetype": "reaction_scheme",
                    "entities": [
                        {"id": "alcohol", "type": "metabolite", "label": "EtOH"},
                        {"id": "aldehyde", "type": "metabolite", "label": "AcH"},
                    ],
                    "relations": [
                        {"source": "alcohol", "target": "aldehyde", "type": "generic"}
                    ],
                },
            },
        ],
    )
    with pytest.raises(ValueError, match="rxn_panel"):
        render_figure(ir, tmp_path / "fig.svg")


# ---------------------------------------------------------------------------
# V2 / ST4: per-panel preset switching
# ---------------------------------------------------------------------------

def test_build_panel_styles_empty_when_all_same():
    """_build_panel_styles returns {} when all panels share the top-level preset."""
    ir = load_fixture(WORKFLOW_FIXTURE)
    # all panels default to cell_press; top-level style_name is also cell_press
    result = _build_panel_styles(ir, "cell_press")
    assert result == {}


def test_build_panel_styles_returns_entry_for_different_preset():
    """_build_panel_styles includes a panel whose content uses a different preset."""
    from imageGen.ir.schema import Panel, Figure, Archetype, Entity, EntityType
    # Build a minimal 2-panel figure; p2 uses "nature" instead of the top-level "acs"
    sub_fig_a = Figure(
        archetype=Archetype.PATHWAY,
        style_preset="acs",
        entities=[Entity(id="e1", label="A", type=EntityType.PROTEIN)],
    )
    sub_fig_b = Figure(
        archetype=Archetype.PATHWAY,
        style_preset="nature",
        entities=[Entity(id="e2", label="B", type=EntityType.PROTEIN)],
    )
    ir = Figure(
        archetype=Archetype.PATHWAY,
        panels=[
            Panel(id="p1", content=sub_fig_a, grid=(0, 0, 1, 1)),
            Panel(id="p2", content=sub_fig_b, grid=(0, 1, 1, 1)),
        ],
    )
    result = _build_panel_styles(ir, "acs")
    assert "p1" not in result          # p1 matches top-level "acs"
    assert "p2" in result              # p2 differs → entry built
    # Spot-check: nature has a different protein_fill from acs
    from imageGen.styles.loader import load_style
    assert result["p2"]["protein_fill"] == load_style("nature")["protein_fill"]


def test_per_panel_preset_renders_without_error(tmp_path):
    """render_figure must succeed when panel content has a different style_preset."""
    from imageGen.ir.schema import Panel, Figure, Archetype, Entity, EntityType
    sub_fig_a = Figure(
        archetype=Archetype.PATHWAY,
        style_preset="cell_press",
        entities=[Entity(id="e1", label="Protein A", type=EntityType.PROTEIN)],
    )
    sub_fig_b = Figure(
        archetype=Archetype.PATHWAY,
        style_preset="nature",
        entities=[Entity(id="e2", label="Protein B", type=EntityType.PROTEIN)],
    )
    ir = Figure(
        archetype=Archetype.PATHWAY,
        panels=[
            Panel(id="p1", content=sub_fig_a, grid=(0, 0, 1, 1)),
            Panel(id="p2", content=sub_fig_b, grid=(0, 1, 1, 1)),
        ],
    )
    out = render_figure(ir, tmp_path / "mixed_preset.svg")
    assert out.exists()
    ET.parse(str(out))  # valid XML


def test_golden_svg_three_panel_workflow(tmp_path):
    """End-to-end golden: render three_panel_workflow, verify per-panel
    entity tagging, and emit the PNG for visual review."""
    ir = load_fixture(WORKFLOW_FIXTURE)
    out = render_figure(ir, tmp_path / "three_panel_workflow.svg")
    pairs = _svg_id_pairs(out)
    data_ids = {d for _, d in pairs}

    for panel in ir.panels:
        assert f"{panel.id}_chrome" in data_ids
        for entity in panel.content.entities:
            assert entity.id in data_ids

    from tests._helpers import FIGURES_DIR
    import cairosvg
    FIGURES_DIR.mkdir(exist_ok=True)
    png_path = FIGURES_DIR / "compositor_three_panel_workflow.png"
    png_path.write_bytes(cairosvg.svg2png(url=str(out)))
    assert png_path.exists()


# ---------------------------------------------------------------------------
# V2 / L22: autocrop consumes needs_crop
# ---------------------------------------------------------------------------

import re as _re

_SVG_SIZE = _re.compile(r'<svg\b[^>]*\swidth="([\d.]+)"[^>]*\sheight="([\d.]+)"', _re.I)
_VIEWBOX = _re.compile(r'viewBox="([\d.\- ]+)"', _re.I)


def _svg_dims(svg_path) -> tuple[float, float]:
    """Parse (width, height) from the opening <svg> tag."""
    tag = _re.search(r"<svg\b[^>]*>", svg_path.read_text(), _re.I).group(0)
    w = float(_re.search(r'width="([\d.]+)"', tag).group(1))
    h = float(_re.search(r'height="([\d.]+)"', tag).group(1))
    return w, h


def test_autocrop_false_preserves_canvas(tmp_path):
    """Default autocrop=False leaves SVG dimensions at the computed canvas size."""
    fig = load_fixture(MAPK)
    out = tmp_path / "fig.svg"
    render_figure(fig, out, autocrop=False)
    w, h = _svg_dims(out)
    # 4-entity pathway, single implicit band: L21 width ≥ 800, L19 height = 100.
    assert w >= 800.0
    assert h == 100.0


def test_autocrop_true_trims_excess_whitespace(tmp_path):
    """autocrop=True shrinks the SVG height when the content leaves dead bottom margin."""
    fig = load_fixture(MAPK)
    out_crop = tmp_path / "cropped.svg"
    out_full = tmp_path / "full.svg"
    render_figure(fig, out_full, autocrop=False)
    render_figure(fig, out_crop, autocrop=True)
    _, h_full = _svg_dims(out_full)
    _, h_crop = _svg_dims(out_crop)
    # The crop must be strictly smaller or equal (content fits in the same height
    # only when there was no dead margin — in practice the 100px band floor leaves
    # whitespace above/below the entity row, so the crop should be tighter).
    assert h_crop <= h_full


def test_autocrop_true_adds_viewbox(tmp_path):
    """autocrop=True rewrites the SVG to have a viewBox attribute."""
    fig = load_fixture(MAPK)
    out = tmp_path / "fig.svg"
    render_figure(fig, out, autocrop=True)
    text = out.read_text()
    assert _VIEWBOX.search(text) is not None


# ---------------------------------------------------------------------------
# Page background — figures must ship opaque, not on a transparent canvas that
# composites to black in a viewer.
# ---------------------------------------------------------------------------

def _first_drawable_tag(root) -> str:
    """Local tag name of the first non-<defs> child of the <svg> root."""
    for child in root:
        tag = child.tag.split("}")[-1]
        if tag != "defs":
            return tag
    return ""


def test_background_rect_is_painted_behind_content(tmp_path):
    """A full-frame data-role=background rect is the first drawable element."""
    fig = load_fixture(MAPK)
    out = tmp_path / "fig.svg"
    render_figure(fig, out)
    root = ET.parse(out).getroot()
    # The background must paint first (behind everything else).
    assert _first_drawable_tag(root) == "rect"
    bg = next(c for c in root if c.tag.split("}")[-1] == "rect")
    assert bg.get("data-role") == "background"
    # It covers the whole frame (origin 0,0 here — no crop applied).
    w, h = _svg_dims(out)
    assert float(bg.get("width")) == pytest.approx(w)
    assert float(bg.get("height")) == pytest.approx(h)


def test_background_covers_cropped_viewbox(tmp_path):
    """After autocrop the background still matches the (rewritten) viewBox."""
    fig = load_fixture(MAPK)
    out = tmp_path / "fig.svg"
    render_figure(fig, out, autocrop=True)
    root = ET.parse(out).getroot()
    vb = [float(v) for v in root.get("viewBox").split()]
    bg = next(c for c in root if c.tag.split("}")[-1] == "rect")
    assert bg.get("data-role") == "background"
    assert float(bg.get("x")) == pytest.approx(vb[0])
    assert float(bg.get("y")) == pytest.approx(vb[1])
    assert float(bg.get("width")) == pytest.approx(vb[2])
    assert float(bg.get("height")) == pytest.approx(vb[3])


def test_rendered_png_corners_are_opaque(tmp_path):
    """The shipped PNG has no transparent pixels (the 'void' regression)."""
    fig = load_fixture("gpcr_signaling.json")  # banded figure with empty regions
    out = tmp_path / "fig.png"
    render_figure(fig, out, legend=True, dpi=96)
    with Image.open(out) as img:
        rgba = img.convert("RGBA")
        w, h = rgba.size
        for x, y in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (w // 2, h - 1)]:
            assert rgba.getpixel((x, y))[3] == 255, f"transparent pixel at {(x, y)}"


# ---------------------------------------------------------------------------
# Figure title heading — mechanism_cartoon / workflow ship the spec title.
# ---------------------------------------------------------------------------

def _titled_fig(archetype, title="My Title"):
    return Figure(
        archetype=archetype,
        title=title,
        entities=[
            Entity(id="a", type=EntityType.METABOLITE, label="A"),
            Entity(id="b", type=EntityType.METABOLITE, label="B"),
        ],
        relations=[Relation(source="a", target="b", type=RelationType.GENERIC)],
    )


def _title_text_nodes(svg_path):
    root = ET.parse(svg_path).getroot()
    out = []
    for g in root.iter():
        if g.get("data-ir-id") == "figure_title":
            out.append("".join(g.itertext()).strip())
    return out


def test_mechanism_cartoon_renders_spec_title(tmp_path):
    out = tmp_path / "fig.svg"
    render_figure(_titled_fig(Archetype.MECHANISM_CARTOON, "SN2 mechanism"), out)
    assert _title_text_nodes(out) == ["SN2 mechanism"]
    # The frame grew upward to include the heading above the content (y=0).
    vb = [float(v) for v in ET.parse(out).getroot().get("viewBox").split()]
    assert vb[1] < 0.0


def test_workflow_renders_spec_title(tmp_path):
    out = tmp_path / "fig.svg"
    render_figure(_titled_fig(Archetype.WORKFLOW, "Western blot workflow"), out)
    assert _title_text_nodes(out) == ["Western blot workflow"]


def test_pathway_figure_is_not_titled_this_batch(tmp_path):
    # Title rendering is scoped to mechanism_cartoon / workflow for now.
    out = tmp_path / "fig.svg"
    render_figure(_titled_fig(Archetype.PATHWAY, "Some pathway"), out)
    assert _title_text_nodes(out) == []


def test_titled_archetype_without_title_emits_no_heading(tmp_path):
    out = tmp_path / "fig.svg"
    fig = _titled_fig(Archetype.WORKFLOW, "x")
    fig = fig.model_copy(update={"title": None})
    render_figure(fig, out)
    assert _title_text_nodes(out) == []
