import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from imageGen.ir import (
    Annotation,
    AnnotationType,
    Archetype,
    Compartment,
    CompartmentType,
    Entity,
    EntityType,
    Figure,
    NamedSlot,
    Panel,
    ReactionConditions,
    Relation,
    RelationType,
)


FIXTURES_DIR = Path(__file__).parent / "fixtures"
FIXTURES = sorted(FIXTURES_DIR.glob("*.json"))


def test_fixtures_directory_populated():
    assert len(FIXTURES) >= 10, f"expected >=10 fixtures, found {len(FIXTURES)}"


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: p.name)
def test_fixture_loads_validates_and_roundtrips(path: Path):
    data = json.loads(path.read_text())
    fig = Figure.from_dict(data)
    assert isinstance(fig, Figure)
    serialized = json.loads(fig.to_json())
    fig2 = Figure.from_dict(serialized)
    assert fig.model_dump(mode="json") == fig2.model_dump(mode="json")


def test_relation_label_side_roundtrips():
    """FR8: the optional label_side enum survives JSON round-trip; default None."""
    from imageGen.ir import RelationLabelSide

    plain = Relation(source="a", target="b", type=RelationType.ACTIVATES)
    assert plain.label_side is None

    rel = Relation(source="a", target="b", type=RelationType.ACTIVATES,
                   label="x", label_side=RelationLabelSide.LEFT)
    back = Relation.from_dict(json.loads(rel.to_json()))
    assert back.label_side is RelationLabelSide.LEFT


def test_relation_label_side_rejects_unknown_value():
    with pytest.raises(ValidationError):
        Relation(source="a", target="b", type=RelationType.ACTIVATES,
                 label_side="sideways")


def test_relation_unknown_target_rejected():
    with pytest.raises(ValidationError, match="unknown target entity"):
        Figure(
            archetype=Archetype.PATHWAY,
            entities=[Entity(id="a", type=EntityType.PROTEIN, label="A")],
            relations=[
                Relation(source="a", target="missing", type=RelationType.ACTIVATES)
            ],
        )


def test_relation_unknown_source_rejected():
    with pytest.raises(ValidationError, match="unknown source entity"):
        Figure(
            archetype=Archetype.PATHWAY,
            entities=[Entity(id="b", type=EntityType.PROTEIN, label="B")],
            relations=[
                Relation(source="missing", target="b", type=RelationType.ACTIVATES)
            ],
        )


def test_entity_location_must_exist():
    with pytest.raises(ValidationError, match="unknown compartment"):
        Figure(
            archetype=Archetype.PATHWAY,
            compartments=[
                Compartment(id="cyto", type=CompartmentType.CYTOPLASM, label="Cyto")
            ],
            entities=[
                Entity(
                    id="x",
                    type=EntityType.PROTEIN,
                    label="X",
                    location="nope",
                )
            ],
        )


def test_duplicate_entity_ids_rejected():
    with pytest.raises(ValidationError, match="Entity ids must be unique"):
        Figure(
            archetype=Archetype.PATHWAY,
            entities=[
                Entity(id="a", type=EntityType.PROTEIN, label="A"),
                Entity(id="a", type=EntityType.PROTEIN, label="A2"),
            ],
        )


def test_overlapping_panel_grids_rejected():
    leaf = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="a", type=EntityType.PROTEIN, label="A")],
    )
    with pytest.raises(ValidationError, match="overlaps"):
        Figure(
            archetype=Archetype.WORKFLOW,
            panels=[
                Panel(id="p1", grid=(0, 0, 1, 2), content=leaf),
                Panel(id="p2", grid=(0, 1, 1, 1), content=leaf),
            ],
        )


def test_panels_and_entities_mutually_exclusive():
    leaf = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="a", type=EntityType.PROTEIN, label="A")],
    )
    with pytest.raises(ValidationError, match="not both"):
        Figure(
            archetype=Archetype.WORKFLOW,
            entities=[Entity(id="z", type=EntityType.PROTEIN, label="Z")],
            panels=[Panel(id="p1", grid=(0, 0, 1, 1), content=leaf)],
        )


def test_entity_type_must_be_enum_value():
    with pytest.raises(ValidationError):
        Entity(id="x", type="not-a-real-type", label="X")


def test_panel_grid_span_must_be_positive():
    leaf = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="a", type=EntityType.PROTEIN, label="A")],
    )
    with pytest.raises(ValidationError, match=">= 1"):
        Panel(id="p", grid=(0, 0, 0, 1), content=leaf)


def test_reaction_conditions_yield_range():
    with pytest.raises(ValidationError, match="between 0 and 100"):
        ReactionConditions(yield_pct=120.0)


def test_annotation_position_accepts_coords_and_slots():
    a1 = Annotation(type=AnnotationType.LABEL, text="x", position=(1.0, 2.5))
    assert a1.position == (1.0, 2.5)
    a2 = Annotation(type=AnnotationType.LABEL, text="y", position="top-left")
    assert a2.position is NamedSlot.TOP_LEFT


def test_extra_fields_forbidden():
    with pytest.raises(ValidationError):
        Entity(id="x", type=EntityType.PROTEIN, label="X", bogus_field=True)


def test_reaction_relation_keeps_typed_conditions_after_roundtrip():
    rel = Relation(
        source="a",
        target="b",
        type=RelationType.GENERIC,
        conditions=ReactionConditions(reagents=["AcOH"], yield_pct=50.0),
    )
    payload = rel.model_dump(mode="json")
    rel2 = Relation.from_dict(payload)
    assert isinstance(rel2.conditions, ReactionConditions)
    assert rel2.conditions.reagents == ["AcOH"]
