"""Tests for primitives/entity_adapters.py and its wiring into _geom.py.

These adapters bridge the ``cells`` and ``lab_equipment`` modules into the
entity-dispatch convention so the documented ``cell`` / ``organelle`` /
``equipment`` / ``sample`` entity types (and a set of ``primitive=`` overrides
for the richer lab-equipment icons) render as real domain glyphs rather than a
generic protein box.
"""
from __future__ import annotations

import pytest

from imageGen.ir.schema import Archetype, Entity, EntityType, Figure, Relation, RelationType
from imageGen.layout._geom import (
    ENTITY_TO_PRIMITIVE,
    PRIMITIVE_REGISTRY,
    infer_primitive,
    resolve_entity_primitive,
)
from imageGen.layout.pathway_layout import layout_pathway
from imageGen.primitives import entity_adapters
from imageGen.render.compositor import render_figure
from imageGen.verify.convention_check import (
    _PRIMITIVE_SHAPE,
    _SKIP_SHAPE_PRIMITIVES,
    convention_check,
)
from imageGen.verify.legibility_check import LegibilityResult, legibility_check
from imageGen.verify.semantic_check import semantic_check


# ---------------------------------------------------------------------------
# Dispatch wiring — the cellular-schematic entity types render as adapters
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "etype, expected",
    [
        (EntityType.CELL, entity_adapters.cell),
        (EntityType.ORGANELLE, entity_adapters.mitochondrion),
        (EntityType.EQUIPMENT, entity_adapters.microscope),
        (EntityType.SAMPLE, entity_adapters.tube),
    ],
)
def test_entity_type_dispatches_to_adapter(etype, expected):
    """CELL/ORGANELLE/EQUIPMENT/SAMPLE no longer fall back to a generic box."""
    assert ENTITY_TO_PRIMITIVE[etype] is expected
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="e1", label="X", type=etype)],
    )
    entry = next(e for e in layout_pathway(fig) if e.ir_id == "e1")
    assert entry.primitive is expected


@pytest.mark.parametrize(
    "name",
    [
        "cell", "cell_neuron", "cell_epithelial", "cell_immune",
        "mitochondrion", "nucleus", "endoplasmic_reticulum", "golgi", "lysosome",
        "microscope", "well_plate", "tube", "pipette", "gel", "western_blot",
        "mouse", "human_figure", "flask", "centrifuge",
        "molecule", "functional_group", "liposome",
    ],
)
def test_new_primitive_overrides_are_registered(name):
    """Each new primitive is reachable via the ``primitive=`` override path."""
    assert name in PRIMITIVE_REGISTRY
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(
            id="e1", label="X", type=EntityType.GENERIC,
            style={"primitive": name},
        )],
    )
    entry = next(e for e in layout_pathway(fig) if e.ir_id == "e1")
    assert entry.primitive is PRIMITIVE_REGISTRY[name]


# ---------------------------------------------------------------------------
# Completeness guard — convention_check must know every registry primitive
# ---------------------------------------------------------------------------

def test_primitive_shape_covers_registry():
    """Every PRIMITIVE_REGISTRY entry needs a _PRIMITIVE_SHAPE tag (or be an
    explicitly skipped composite), else convention_check raises KeyError at
    runtime instead of failing loudly here."""
    missing = [
        n for n, p in PRIMITIVE_REGISTRY.items()
        if p not in _PRIMITIVE_SHAPE and p not in _SKIP_SHAPE_PRIMITIVES
    ]
    assert not missing, f"_PRIMITIVE_SHAPE missing tags for: {missing}"


def test_default_dispatch_shapes_covered():
    """Every ENTITY_TO_PRIMITIVE target must be known to convention_check —
    either a shape tag or an explicitly skipped composite (EQUIPMENT/SAMPLE now
    default to embedded Bioicons, which are skip-shape)."""
    missing = [
        t for t, p in ENTITY_TO_PRIMITIVE.items()
        if p not in _PRIMITIVE_SHAPE and p not in _SKIP_SHAPE_PRIMITIVES
    ]
    assert not missing, f"convention_check missing tags for entity types: {missing}"


# ---------------------------------------------------------------------------
# End-to-end — a figure of wired entities renders and passes every verifier
# ---------------------------------------------------------------------------

def test_wired_entities_render_and_pass_verifiers(tmp_path):
    """A figure exercising the new entity types + overrides survives the full
    render + semantic/convention/legibility verification pipeline."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="cellA", label="T cell", type=EntityType.CELL),
            Entity(id="mito", label="Mito", type=EntityType.ORGANELLE),
            Entity(id="scope", label="Imaging", type=EntityType.EQUIPMENT),
            Entity(id="samp", label="Sample", type=EntityType.SAMPLE),
            Entity(id="plate", label="Plate", type=EntityType.GENERIC,
                   style={"primitive": "well_plate"}),
        ],
        relations=[
            Relation(source="cellA", target="mito", type=RelationType.GENERIC),
            Relation(source="scope", target="samp", type=RelationType.GENERIC),
        ],
    )
    out = tmp_path / "wired.svg"
    render_figure(fig, out)
    semantic_check(fig, out)            # every entity id present
    convention_check(fig, out)          # each renders with its mapped shape
    assert isinstance(legibility_check(out), LegibilityResult)


# ---------------------------------------------------------------------------
# EW1 — molecule entities (chemical structure from SMILES)
# ---------------------------------------------------------------------------

def test_molecule_entity_renders_structure_and_passes_verifiers(tmp_path):
    """A metabolite with style.smiles draws an inline RDKit structure and
    survives the full verification pipeline (convention_check skips it)."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="glc", label="Glucose", type=EntityType.METABOLITE,
                   style={"primitive": "molecule",
                          "smiles": "C(C1C(C(C(C(O1)O)O)O)O)O"}),
            Entity(id="enz", label="Hexokinase", type=EntityType.KINASE),
        ],
        relations=[Relation(source="enz", target="glc", type=RelationType.CATALYZES)],
    )
    out = tmp_path / "mol.svg"
    render_figure(fig, out)
    # The molecule group is present (semantic) and the structure drew paths.
    semantic_check(fig, out)
    convention_check(fig, out)          # molecule is skipped, kinase still checked
    assert isinstance(legibility_check(out), LegibilityResult)
    assert "glc" in out.read_text()     # scoped id for the molecule entity


def test_molecule_without_smiles_warns_but_still_renders(tmp_path):
    """primitive='molecule' with no SMILES warns and falls back to label-only
    rather than crashing the render."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="m", label="Mystery", type=EntityType.GENERIC,
                         style={"primitive": "molecule"})],
    )
    out = tmp_path / "nosmiles.svg"
    with pytest.warns(UserWarning, match="requires style\\['smiles'\\]"):
        render_figure(fig, out)
    semantic_check(fig, out)
    convention_check(fig, out)


# ---------------------------------------------------------------------------
# EW2 — functional-group entities
# ---------------------------------------------------------------------------

def test_functional_group_via_style_key_renders(tmp_path):
    """An entity with style.functional_group draws the named callout and passes
    verification (convention_check skips it)."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="acid", label="Acid", type=EntityType.METABOLITE,
                   style={"primitive": "functional_group", "functional_group": "carboxyl"}),
            Entity(id="enz", label="Esterase", type=EntityType.KINASE),
        ],
        relations=[Relation(source="enz", target="acid", type=RelationType.CATALYZES)],
    )
    out = tmp_path / "fg.svg"
    render_figure(fig, out)
    semantic_check(fig, out)
    convention_check(fig, out)
    assert isinstance(legibility_check(out), LegibilityResult)


def test_functional_group_falls_back_to_label_as_name(tmp_path):
    """With no functional_group key, the entity label names the group."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="g", label="amine", type=EntityType.GENERIC,
                         style={"primitive": "functional_group"})],
    )
    out = tmp_path / "fg2.svg"
    render_figure(fig, out)            # no warning — label 'amine' is a valid group
    semantic_check(fig, out)
    convention_check(fig, out)


def test_functional_group_unknown_name_warns_but_renders(tmp_path):
    """An unknown group name warns and falls back to a label-only render."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="g", label="Whatsit", type=EntityType.GENERIC,
                         style={"primitive": "functional_group",
                                "functional_group": "notagroup"})],
    )
    out = tmp_path / "fg3.svg"
    with pytest.warns(UserWarning, match="did not render"):
        render_figure(fig, out)
    semantic_check(fig, out)
    convention_check(fig, out)


# ---------------------------------------------------------------------------
# EW3 — liposome entity (closed lipid-bilayer vesicle)
# ---------------------------------------------------------------------------

def test_liposome_entity_renders_bilayer_and_passes_verifiers(tmp_path):
    """primitive='liposome' draws the membrane bilayer (head groups + ring) and
    survives the full render + semantic/convention/legibility pipeline."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="ves", label="Vesicle", type=EntityType.GENERIC,
                         style={"primitive": "liposome"})],
    )
    out = tmp_path / "liposome.svg"
    render_figure(fig, out)
    semantic_check(fig, out)
    convention_check(fig, out)          # first shape is the bilayer <polygon>
    assert isinstance(legibility_check(out), LegibilityResult)
    text = out.read_text()
    assert "ves" in text                # scoped id for the liposome entity
    # head-group circles from lipid_bilayer are present
    assert text.count("<circle") >= 8


# ---------------------------------------------------------------------------
# EW4 — label-keyword glyph inference for the coarse entity-type defaults
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "etype, label, expected_name",
    [
        # EQUIPMENT — default is microscope; a label names the real glyph
        (EntityType.EQUIPMENT, "Western blot", "western_blot"),  # blot → distinct icon
        (EntityType.EQUIPMENT, "Immunoblot", "western_blot"),
        (EntityType.EQUIPMENT, "SDS-PAGE gel", "gel"),
        (EntityType.EQUIPMENT, "Agarose gel", "gel"),
        (EntityType.EQUIPMENT, "Mr ladder", "gel"),
        (EntityType.EQUIPMENT, "96-well plate", "well_plate"),
        (EntityType.EQUIPMENT, "ELISA reader", "well_plate"),
        (EntityType.EQUIPMENT, "Multichannel pipette", "pipette"),
        (EntityType.EQUIPMENT, "Eppendorf tube", "tube"),
        (EntityType.EQUIPMENT, "Mouse model", "mouse"),
        (EntityType.EQUIPMENT, "Benchtop centrifuge", "centrifuge"),
        (EntityType.EQUIPMENT, "Erlenmeyer flask", "flask"),
        (EntityType.EQUIPMENT, "Patient cohort", "human_figure"),
        # ORGANELLE — default is mitochondrion
        (EntityType.ORGANELLE, "Nucleus", "nucleus"),
        (EntityType.ORGANELLE, "Nuclear envelope", "nucleus"),
        (EntityType.ORGANELLE, "Endoplasmic reticulum", "endoplasmic_reticulum"),
        (EntityType.ORGANELLE, "Golgi apparatus", "golgi"),
        (EntityType.ORGANELLE, "Lysosome", "lysosome"),
        # CELL — default is the generic cell
        (EntityType.CELL, "Neuron", "cell_neuron"),
        (EntityType.CELL, "Epithelial cell", "cell_epithelial"),
        (EntityType.CELL, "T cell", "cell_immune"),
        (EntityType.CELL, "Macrophage", "cell_immune"),
        # SAMPLE — default is tube
        (EntityType.SAMPLE, "Western blot membrane", "gel"),
        (EntityType.SAMPLE, "96-well plate", "well_plate"),
    ],
)
def test_infer_primitive_maps_label_to_glyph(etype, label, expected_name):
    """A keyword in the label selects a specific glyph for the coarse types."""
    assert infer_primitive(etype, label) == expected_name


@pytest.mark.parametrize(
    "etype, label",
    [
        (EntityType.EQUIPMENT, "Imaging"),       # → microscope default
        (EntityType.ORGANELLE, "Organelle"),     # → mitochondrion default
        (EntityType.CELL, "Cell"),               # → generic cell default
        (EntityType.SAMPLE, "Lysate"),           # → tube default
        (EntityType.SAMPLE, "Template strand"),  # 'plate' must NOT fire mid-word
        (EntityType.PROTEIN, "Western blot"),    # non-coarse type: never inferred
        (EntityType.EQUIPMENT, ""),              # empty label
        (EntityType.EQUIPMENT, None),            # missing label
    ],
)
def test_infer_primitive_returns_none_when_no_keyword(etype, label):
    """No keyword (or a non-coarse type / empty label) → fall back to default."""
    assert infer_primitive(etype, label) is None


def test_inference_dispatches_specific_glyph_in_layout():
    """layout_pathway routes a labelled coarse entity to the inferred glyph."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="b", label="Western blot", type=EntityType.EQUIPMENT)],
    )
    entry = next(e for e in layout_pathway(fig) if e.ir_id == "b")
    assert entry.primitive is PRIMITIVE_REGISTRY["western_blot"]


def test_explicit_override_beats_inference():
    """An explicit style.primitive wins over a would-be label inference."""
    e = Entity(id="b", label="Western blot", type=EntityType.EQUIPMENT,
               style={"primitive": "microscope"})
    assert resolve_entity_primitive(e) is PRIMITIVE_REGISTRY["microscope"]


def test_inferred_organelle_passes_convention_check(tmp_path):
    """The key consistency guard: inferring a *different-shaped* glyph than the
    type default (nucleus=circle vs mitochondrion=polygon) must still pass
    convention_check, because the check shares resolve_entity_primitive."""
    fig = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="nuc", label="Nucleus", type=EntityType.ORGANELLE),
            Entity(id="tc", label="T cell", type=EntityType.CELL),
        ],
    )
    out = tmp_path / "inferred.svg"
    render_figure(fig, out)
    semantic_check(fig, out)
    convention_check(fig, out)   # nucleus→circle, T cell→cell_immune→polygon
