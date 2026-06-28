import pytest
import xml.etree.ElementTree as ET
from collections import Counter

from imageGen.ir.builder import build
from imageGen.render.compositor import _canvas_size, _compute_pathway_canvas, render_figure
from imageGen.layout.pathway_layout import _graph_positions, PATHWAY_DEFAULT_PARAMS
from imageGen.layout._geom import max_entity_bbox, entities_per_band, ENTITY_BBOX
from imageGen.ir.schema import EntityType, Figure

# Helper to parse SVG dimensions
def _get_svg_dimensions(svg_content):
    """Extracts width and height from an SVG string."""
    root = ET.fromstring(svg_content)
    width = float(root.attrib.get('width', '0').replace('px', ''))
    height = float(root.attrib.get('height', '0').replace('px', ''))
    return width, height


@pytest.fixture
def simple_figure_4_entities():
    """A simple figure with 4 protein entities."""
    return build('pathway', entities=[
        ('e1', 'protein', 'Entity 1'),
        ('e2', 'protein', 'Entity 2'),
        ('e3', 'protein', 'Entity 3'),
        ('e4', 'protein', 'Entity 4'),
    ])


@pytest.fixture
def simple_figure_15_entities():
    """A simple figure with 15 protein entities."""
    entities = [(f'e{i}', 'protein', f'Entity {i}') for i in range(15)]
    return build('pathway', entities=entities)


@pytest.fixture
def mapk_cascade_figure():
    """A minimal figure resembling the MAPK cascade for canvas testing."""
    return build(
        'pathway',
        entities=[
            ('raf', 'protein', 'Raf'),
            ('mek', 'protein', 'Mek'),
            ('erk', 'protein', 'Erk'),
        ],
        relations=[
            ('raf', 'activates', 'mek'),
            ('mek', 'activates', 'erk'),
        ],
    )


def test_small_figure_canvas_is_floor(simple_figure_4_entities):
    """4-entity pathway (1 implicit band) -> height = _BAND_BASELINE (L19 floor)."""
    canvas_w, canvas_h = _compute_pathway_canvas(simple_figure_4_entities)
    assert canvas_w == 800.0
    # L19: floor is n_bands * _BAND_BASELINE (1 * 100) not the old hardcoded 600.
    assert canvas_h == 100.0


def test_two_entity_no_relations_canvas_is_floor():
    """Build 2 entities (1 implicit band) -> height = _BAND_BASELINE (L19 floor)."""
    figure = build('pathway', entities=[('a', 'protein', 'A'), ('b', 'protein', 'B')])
    canvas_w, canvas_h = _compute_pathway_canvas(figure)
    assert canvas_w == 800.0
    # L19: floor is 1 * 100 not 600.
    assert canvas_h == 100.0


def test_empty_figure_canvas_is_floor():
    """Empty pathway -> _canvas_size returns exactly (800.0, 600.0)."""
    figure = build('pathway')
    canvas_w, canvas_h = _compute_pathway_canvas(figure)
    assert (canvas_w, canvas_h) == (800.0, 600.0)


def test_many_compartments_grows_height():
    """Pathway with 10 compartments and 1 entity each -> canvas height > 600."""
    compartments = [(f'c{i}', 'custom', f'Compartment {i}') for i in range(10)]
    entities = [(f'e{i}', 'protein', f'Entity {i}', f'c{i}') for i in range(10)]
    figure = build('pathway', entities=entities, compartments=compartments)
    _, canvas_h = _compute_pathway_canvas(figure)
    assert canvas_h > 600.0


def test_max_entity_bbox_empty_figure():
    """Empty figure -> max_entity_bbox returns default protein bbox."""
    figure = build('pathway')
    bbox_w, bbox_h = max_entity_bbox(figure)
    assert (bbox_w, bbox_h) == ENTITY_BBOX[EntityType.PROTEIN]


def test_max_entity_bbox_mixed():
    """Figure with protein (60,30) and receptor (28,60) -> returns (60, 60).

    max_entity_bbox looks up each entity's bbox from ENTITY_BBOX by type —
    no per-entity bbox field is required.
    """
    figure = build(
        'pathway',
        entities=[
            ('p1', 'protein', 'Protein 1'),
            ('r1', 'receptor', 'Receptor 1'),
        ],
    )
    bbox_w, bbox_h = max_entity_bbox(figure)
    assert (bbox_w, bbox_h) == (60.0, 60.0)


def test_entities_per_band_no_compartments_returns_total():
    """5 entities, no compartments -> entities_per_band returns [5]."""
    figure = build(
        'pathway',
        entities=[
            ('e1', 'protein', 'E1'), ('e2', 'protein', 'E2'), ('e3', 'protein', 'E3'),
            ('e4', 'protein', 'E4'), ('e5', 'protein', 'E5')
        ]
    )
    # For figures with no explicit compartments, an '__implicit__' band is assumed.
    # The function should correctly identify this.
    band_counts = entities_per_band(figure)
    assert band_counts == [5]


def test_entities_per_band_distributes_correctly():
    """Figure with 3 compartments (2/1/4 entities) -> entities_per_band returns [2,1,4]."""
    figure = build(
        'pathway',
        compartments=[
            ('c1', 'custom', 'Compartment 1'),
            ('c2', 'custom', 'Compartment 2'),
            ('c3', 'custom', 'Compartment 3'),
        ],
        entities=[
            ('e1', 'protein', 'E1', 'c1'),
            ('e2', 'protein', 'E2', 'c1'),
            ('e3', 'protein', 'E3', 'c2'),
            ('e4', 'protein', 'E4', 'c3'),
            ('e5', 'protein', 'E5', 'c3'),
            ('e6', 'protein', 'E6', 'c3'),
            ('e7', 'protein', 'E7', 'c3'),
        ],
    )
    band_counts = entities_per_band(figure)
    assert band_counts == [2, 1, 4]


def test_entities_per_band_fallback_to_first():
    """Entity without location goes to first compartment."""
    figure = build(
        'pathway',
        compartments=[
            ('c1', 'custom', 'First Compartment'),
            ('c2', 'custom', 'Second Compartment'),
        ],
        entities=[
            ('e1', 'protein', 'E1', 'c2'),  # In c2
            ('e2', 'protein', 'E2'),         # No location → falls back to c1
            ('e3', 'protein', 'E3', 'c1'),  # In c1
        ],
    )
    # e2 (no location) + e3 → c1; e1 → c2.
    band_counts = entities_per_band(figure)
    assert band_counts == [2, 1]


def test_graph_positions_single_row_when_n_le_max_per_row(simple_figure_4_entities: Figure):
    """4 entities -> all share one y (single row preserved for backwards compat)."""
    fig = simple_figure_4_entities
    bands = {'__implicit__': (0.0, 600.0)}
    location_map = {e.id: '__implicit__' for e in fig.entities}
    canvas = (800.0, 600.0)
    origin = (0.0, 0.0)
    padding = 40.0
    seed = 42
    max_per_row = 6
    row_v_gap = 16.0

    positions = _graph_positions(fig, bands, location_map, canvas, origin, padding, seed, max_per_row, row_v_gap)

    # All y coordinates should be the same for a single row
    y_coords = {pos[1] for pos in positions.values()}
    assert len(y_coords) == 1, "All entities should be on a single row (same y-coordinate)"


def test_graph_positions_wraps_to_multiple_rows(simple_figure_15_entities: Figure):
    """15 entities with max_per_row=6 -> at least 3 distinct y values among entity positions."""
    fig = simple_figure_15_entities
    bands = {'__implicit__': (0.0, 600.0)}
    location_map = {e.id: '__implicit__' for e in fig.entities}
    canvas = (800.0, 600.0)
    origin = (0.0, 0.0)
    padding = 40.0
    seed = 42
    max_per_row = 6
    row_v_gap = 16.0

    positions = _graph_positions(fig, bands, location_map, canvas, origin, padding, seed, max_per_row, row_v_gap)

    # Extract all y coordinates
    y_coords = [pos[1] for pos in positions.values()]
    distinct_y_coords = set(y_coords)

    # With 15 entities and max_per_row=6, we expect at least ceil(15/6) = 3 rows.
    assert len(distinct_y_coords) >= 3, "Expected at least 3 distinct y-coordinates for wrapped layout."


def test_deep_chain_sizes_canvas_to_columns_no_overlap():
    """#2: a deep DAG chain is placed a column per topological rank, so the
    canvas width must fit every column. Previously it was sized for
    ``min(len, max_per_row)=6`` columns, squeezing N boxes into 6-wide and
    overlapping them."""
    n = 20
    ents = [(f"e{i}", "protein", f"N{i}") for i in range(n)]
    rels = [(f"e{i}", "activates", f"e{i+1}") for i in range(n - 1)]
    fig = build("pathway", entities=ents, relations=rels)

    w, h = _compute_pathway_canvas(fig)
    ew, _eh = max_entity_bbox(fig)
    # Width fits a column per node (far beyond the old 6-column envelope)...
    assert w >= n * ew, f"canvas width {w} too small for {n} columns of {ew}px"
    # ...and grows with chain depth.
    short = build("pathway",
                  entities=[(f"e{i}", "protein", f"N{i}") for i in range(5)],
                  relations=[(f"e{i}", "activates", f"e{i+1}") for i in range(4)])
    assert w > _compute_pathway_canvas(short)[0]

    # Placement: consecutive rank columns are separated by at least a box width,
    # so the boxes never overlap.
    bands = {"__implicit__": (0.0, h)}
    location_map = {e.id: "__implicit__" for e in fig.entities}
    positions = _graph_positions(fig, bands, location_map, (w, h), (0.0, 0.0), 40.0, 42)
    xs = sorted(p[0] for p in positions.values())
    min_gap = min(b - a for a, b in zip(xs, xs[1:]))
    assert min_gap >= ew, f"columns overlap: min centre gap {min_gap:.1f} < box width {ew}"


def test_deep_chain_does_not_pad_vertical_whitespace():
    """#2: a single-file chain uses one row, so its band is one row tall — not the
    ``ceil(N/max_per_row)`` rows the band-wrap height assumed (dead whitespace)."""
    n = 20
    chain = build("pathway",
                  entities=[(f"e{i}", "protein", f"N{i}") for i in range(n)],
                  relations=[(f"e{i}", "activates", f"e{i+1}") for i in range(n - 1)])
    # A no-relation set of the same size wraps to ceil(20/6)=4 rows (tall);
    # the chain places one row, so its canvas is much shorter.
    loose = build("pathway",
                  entities=[(f"e{i}", "protein", f"N{i}") for i in range(n)])
    assert _compute_pathway_canvas(chain)[1] < _compute_pathway_canvas(loose)[1]


def test_graph_positions_preserves_old_layout_for_small_n():
    """3 entities, no relations -> positions[0].y == positions[1].y == positions[2].y (single row)."""
    fig = build('pathway', entities=[
        ('e1', 'protein', 'E1'), ('e2', 'protein', 'E2'), ('e3', 'protein', 'E3')
    ])
    bands = {'__implicit__': (0.0, 600.0)}
    location_map = {e.id: '__implicit__' for e in fig.entities}
    canvas = (800.0, 600.0)
    origin = (0.0, 0.0)
    padding = 40.0
    seed = 42
    max_per_row = 6
    row_v_gap = 16.0

    positions = _graph_positions(fig, bands, location_map, canvas, origin, padding, seed, max_per_row, row_v_gap)

    y_coords = {pos[1] for pos in positions.values()}
    assert len(y_coords) == 1, "Expected a single row (same y-coordinate) for small number of entities."


def test_render_pinned_canvas_overrides_compute(tmp_path):
    """Render with canvas=(1500.0, 900.0) kwarg -> resulting SVG has width=1500 and height=900."""
    figure = build('pathway', entities=[('a', 'protein', 'A')])
    output_path = tmp_path / "output.svg"
    
    # Call render_figure with an explicit canvas size
    render_figure(figure, output_path, canvas=(1500.0, 900.0))

    assert output_path.exists()

    # Read the SVG and check dimensions
    svg_content = output_path.read_text()
    width, height = _get_svg_dimensions(svg_content)

    assert width == 1500.0
    assert height == 900.0


def test_render_small_figure_byte_identical_canvas(tmp_path, mapk_cascade_figure: Figure):
    """Render the MAPK cascade figure and check SVG width=800 height=600 (no regression)."""
    output_path = tmp_path / "mapk_cascade.svg"
    
    # Render without explicit canvas, should fall back to compute_pathway_canvas which is 800x600 for small figures.
    render_figure(mapk_cascade_figure, output_path)

    assert output_path.exists()

    # Read the SVG and check dimensions
    svg_content = output_path.read_text()
    width, height = _get_svg_dimensions(svg_content)

    assert width == 800.0
    # L19: 1-band figure floor is _BAND_BASELINE (100), not the old hardcoded 600.
    assert height == 100.0
