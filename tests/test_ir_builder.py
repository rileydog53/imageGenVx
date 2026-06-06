from imageGen.ir.builder import build, entity, relation, compartment
from imageGen.ir.schema import Figure, Archetype, EntityType, RelationType, CompartmentType
from pydantic import ValidationError
import pytest
import json
from pathlib import Path

# Define the path to the fixtures directory
FIXTURES_DIR = Path(__file__).parent / "fixtures"

@pytest.fixture
def mapk_cascade_json_data():
    """Loads the MAPK cascade fixture JSON data."""
    with open(FIXTURES_DIR / "mapk_cascade.json", "r") as f:
        return json.load(f)

@pytest.fixture
def minimal_entities_and_relations():
    """Provides a set of minimal entities and relations for testing."""
    ents = [
        ('a', 'protein', 'Protein A'),
        ('b', 'protein', 'Protein B'),
        ('c', 'protein', 'Protein C')
    ]
    rels = [
        ('a', 'activates', 'b'),
        ('b', 'inhibits', 'c')
    ]
    return ents, rels


def test_build_minimal_pathway():
    """Builds a minimal pathway and asserts its archetype and empty lists."""
    fig = build('pathway')
    assert fig.archetype == Archetype.PATHWAY
    assert len(fig.entities) == 0
    assert len(fig.relations) == 0
    assert len(fig.compartments) == 0


def test_build_simple_pathway_3_entities_2_relations():
    """Builds a simple pathway with 3 entities and 2 relations, then asserts counts."""
    # Docstring example: Ras/Raf/Mek chain
    ents = [
        ('ras', 'protein', 'Ras'),
        ('raf', 'protein', 'Raf'),
        ('mek', 'protein', 'Mek')
    ]
    rels = [
        ('ras', 'activates', 'raf'),
        ('raf', 'activates', 'mek')
    ]
    fig = build('pathway', entities=ents, relations=rels)
    assert len(fig.entities) == 3
    assert len(fig.relations) == 2


def test_build_with_style_kwarg():
    """Builds a pathway with a style preset and asserts it's set."""
    fig = build('pathway', style='nature')
    assert fig.style_preset == 'nature'


def test_build_with_title_and_caption():
    """Builds a pathway with a title and caption, then asserts they are set."""
    fig = build('pathway', title='My Test Title', caption='A descriptive caption.')
    assert fig.title == 'My Test Title'
    assert fig.caption == 'A descriptive caption.'


def test_entity_tuple_3_arity():
    """Tests a 3-element entity tuple results in location being None."""
    fig = build('pathway', entities=[('a', 'protein', 'A')])
    assert fig.entities[0].location is None


def test_entity_tuple_4_arity():
    """Tests a 4-element entity tuple correctly sets the location."""
    fig = build(
        'pathway',
        entities=[('a', 'protein', 'A', 'cyto')],
        compartments=[('cyto', 'cytoplasm', 'Cytoplasm')]
    )
    assert fig.entities[0].location == 'cyto'


def test_entity_tuple_5_arity_sets_primitive_override():
    """FR7: a 5th tuple element wires a primitive override via style.primitive."""
    fig = build(
        'pathway',
        entities=[('igg', 'protein', 'IgG', None, 'antibody')],
    )
    e = fig.entities[0]
    assert e.location is None
    assert e.style == {'primitive': 'antibody'}


def test_entity_tuple_5_arity_with_location_and_primitive():
    """FR7: location and primitive override coexist in a 5-tuple."""
    fig = build(
        'pathway',
        entities=[('gpcr', 'receptor', 'GPCR', 'mem', 'gpcr')],
        compartments=[('mem', 'membrane', 'Plasma membrane')],
    )
    e = fig.entities[0]
    assert e.location == 'mem'
    assert e.style == {'primitive': 'gpcr'}


def test_entity_tuple_bad_arity_rejected():
    """A 6-element entity tuple is rejected with a helpful message."""
    import pytest
    with pytest.raises(ValueError, match="3 to 5 elements"):
        build('pathway', entities=[('a', 'protein', 'A', 'c', 'gpcr', 'x')])


def test_relation_tuple_3_arity():
    """Tests a 3-element relation tuple correctly sets source, target, type, with no label."""
    fig = build(
        'pathway',
        entities=[('a', 'protein', 'A'), ('b', 'protein', 'B')],
        relations=[('a', 'activates', 'b')]
    )
    assert fig.relations[0].source == 'a'
    assert fig.relations[0].target == 'b'
    assert fig.relations[0].type == RelationType.ACTIVATES
    assert fig.relations[0].label is None


def test_relation_tuple_4_arity():
    """Tests a 4-element relation tuple correctly sets the label."""
    fig = build(
        'pathway',
        entities=[('a', 'protein', 'A'), ('b', 'protein', 'B')],
        relations=[('a', 'activates', 'b', 'My Activation Label')]
    )
    assert fig.relations[0].label == 'My Activation Label'


def test_compartments_tuple():
    """Tests building with a compartment tuple and an entity located within it."""
    comps = [('cyto', 'cytoplasm', 'Cytoplasm')]
    ents = [('e1', 'protein', 'Entity 1', 'cyto')]
    fig = build('pathway', entities=ents, compartments=comps)
    assert fig.compartments[0].id == 'cyto'
    assert fig.entities[0].location == 'cyto'


def test_dict_passthrough():
    """Tests passing dict shapes (from helpers) to build works correctly."""
    e_dict = entity('e1', 'protein', 'Entity 1')
    r_dict = relation('e1', 'activates', 'e1')
    fig = build('pathway', entities=[e_dict], relations=[r_dict])
    assert fig.entities[0].id == 'e1'
    assert fig.relations[0].source == 'e1'


def test_entity_helper_returns_dict():
    """Tests the entity helper returns a dict with correct keys and values."""
    e = entity('e1', 'protein', 'Entity 1')
    assert e == {'id': 'e1', 'type': 'protein', 'label': 'Entity 1'}


def test_relation_helper_returns_dict():
    """Tests the relation helper returns a dict with correct keys and values."""
    r = relation('s1', 'activates', 't1')
    assert r == {'source': 's1', 'type': 'activates', 'target': 't1'}


def test_compartment_helper_returns_dict():
    """Tests the compartment helper returns a dict with correct keys and values."""
    c = compartment('cyto', 'cytoplasm', 'Cytoplasm')
    assert c == {'id': 'cyto', 'type': 'cytoplasm', 'label': 'Cytoplasm'}


def test_bad_entity_tuple_arity_raises():
    """Tests that a 2-element entity tuple raises a ValueError."""
    with pytest.raises(ValueError, match="entity tuple must have 3 to 5 elements"):
        build('pathway', entities=[('e1', 'protein')])


def test_bad_relation_tuple_arity_raises():
    """Tests that a 5-element relation tuple raises a ValueError."""
    with pytest.raises(ValueError, match="relation tuple must have 3 or 4 elements"):
        build(
            'pathway',
            entities=[('s', 'protein', 'S'), ('t', 'protein', 'T')],
            relations=[('s', 'activates', 't', 'lbl', 'extra')],
        )


def test_unknown_entity_type_raises_validation_error():
    """Tests an unknown entity type raises pydantic.ValidationError."""
    # Pydantic's enum error message format varies; just assert the exception type.
    with pytest.raises(ValidationError):
        build('pathway', entities=[('e1', 'not_a_type', 'E1')])


def test_unknown_relation_type_raises_validation_error():
    """Tests an unknown relation type raises pydantic.ValidationError."""
    with pytest.raises(ValidationError):
        build(
            'pathway',
            entities=[('s', 'protein', 'S'), ('t', 'protein', 'T')],
            relations=[('s', 'not_a_type', 't')]
        )


def test_dangling_relation_reference_raises(minimal_entities_and_relations):
    """Tests a relation referencing a non-existent entity raises pydantic.ValidationError."""
    ents, _ = minimal_entities_and_relations
    # Relation references 'x', which is not in ents
    bad_rels = [('a', 'activates', 'x')]
    with pytest.raises(ValidationError, match="unknown target entity"):
        build('pathway', entities=ents, relations=bad_rels)


def test_entity_location_must_match_compartment():
    """Tests an entity with a non-existent location raises pydantic.ValidationError."""
    with pytest.raises(ValidationError, match="unknown compartment 'nope'"):
        build('pathway', entities=[('e1', 'protein', 'E1', 'nope')])


def test_round_trip_mapk_cascade_fixture(mapk_cascade_json_data):
    """Loads a JSON fixture, rebuilds it programmatically, and asserts equivalence.

    Round-trips by parsing the fixture into a Figure, rebuilding the same
    Figure via the builder API, and comparing the two validated objects.
    Comparing Figure objects (not raw dumps) sidesteps default-vs-unset
    field noise.
    """
    original = Figure.model_validate(mapk_cascade_json_data)

    entities_tuples = [
        (e['id'], e['type'], e['label'])
        if e.get('location') is None
        else (e['id'], e['type'], e['label'], e['location'])
        for e in mapk_cascade_json_data['entities']
    ]
    relations_tuples = [
        (r['source'], r['type'], r['target'])
        if r.get('label') is None
        else (r['source'], r['type'], r['target'], r['label'])
        for r in mapk_cascade_json_data['relations']
    ]
    compartments_tuples = [
        (c['id'], c['type'], c['label'])
        for c in mapk_cascade_json_data.get('compartments', [])
    ]

    rebuilt = build(
        archetype=mapk_cascade_json_data['archetype'],
        entities=entities_tuples,
        relations=relations_tuples,
        compartments=compartments_tuples,
        title=mapk_cascade_json_data.get('title'),
        caption=mapk_cascade_json_data.get('caption'),
        style=mapk_cascade_json_data.get('style_preset'),
    )

    assert rebuilt == original
