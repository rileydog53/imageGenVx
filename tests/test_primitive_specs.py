"""Structural tests for the single-site primitive registry (P0c.1).

Registering a primitive used to require synchronized edits across ``_geom``
(registry + bbox), ``convention_check`` (shape map + skip set) and
``entity_adapters`` (icon assets). Those four tables are now *derived* from the
one ``PRIMITIVE_SPECS`` list, so the coverage guard is structural: it iterates
the spec list rather than re-asserting hand-kept parallel dicts.
"""
from __future__ import annotations

import pytest

from imageGen.primitives.primitive_specs import (
    PRIMITIVE_REGISTRY,
    PRIMITIVE_SHAPE,
    PRIMITIVE_SPECS,
    PRIMITIVE_TO_BBOX,
    SKIP,
    SKIP_SHAPE_PRIMITIVES,
    ICON_ASSETS,
    PrimitiveSpec,
)
from imageGen.primitives import entity_adapters

# Tags convention_check accepts as an entity's primary shape — a spec's shape
# tag must be one of these (or SKIP). Mirrors convention_check._SHAPE_TAGS.
_VALID_SHAPE_TAGS = {"rect", "polygon", "ellipse", "circle", "path", "polyline"}


def test_every_spec_is_well_formed():
    """Each spec carries a name, a callable, a 2-tuple bbox, and a shape that is
    either a valid SVG tag or the SKIP sentinel."""
    for s in PRIMITIVE_SPECS:
        assert isinstance(s, PrimitiveSpec)
        assert s.name and isinstance(s.name, str)
        assert callable(s.render), f"{s.name!r} render is not callable"
        assert (
            isinstance(s.bbox, tuple) and len(s.bbox) == 2
            and all(isinstance(v, float) for v in s.bbox)
        ), f"{s.name!r} bbox malformed: {s.bbox!r}"
        assert s.shape is SKIP or s.shape in _VALID_SHAPE_TAGS, (
            f"{s.name!r} shape {s.shape!r} is neither SKIP nor a valid tag"
        )


def test_names_and_callables_are_unique():
    """The registry keys on both name and callable; neither may collide."""
    names = [s.name for s in PRIMITIVE_SPECS]
    assert len(names) == len(set(names)), "duplicate spec name(s)"
    renders = [s.render for s in PRIMITIVE_SPECS]
    assert len(renders) == len(set(renders)), "duplicate spec callable(s)"


def test_derived_tables_cover_exactly_the_registry():
    """Every registered primitive has a bbox and is classified once as either a
    shape-checked glyph or a skipped composite — never both, never neither."""
    registry_callables = set(PRIMITIVE_REGISTRY.values())
    assert set(PRIMITIVE_TO_BBOX) == registry_callables
    shaped = set(PRIMITIVE_SHAPE)
    skipped = set(SKIP_SHAPE_PRIMITIVES)
    assert shaped.isdisjoint(skipped)
    assert shaped | skipped == registry_callables


def test_derived_tables_match_the_spec_list():
    """The four derived dicts are exactly the projection of the spec list."""
    assert PRIMITIVE_REGISTRY == {s.name: s.render for s in PRIMITIVE_SPECS}
    assert PRIMITIVE_TO_BBOX == {s.render: s.bbox for s in PRIMITIVE_SPECS}
    assert PRIMITIVE_SHAPE == {
        s.render: s.shape for s in PRIMITIVE_SPECS if s.shape is not SKIP
    }
    assert SKIP_SHAPE_PRIMITIVES == frozenset(
        s.render for s in PRIMITIVE_SPECS if s.shape is SKIP
    )


def test_icon_assets_only_on_skip_specs():
    """An ``icon_asset`` is the asset stem of an embedded composite, so any spec
    carrying one must be SKIP-shaped (a faithful multi-path illustration)."""
    for s in PRIMITIVE_SPECS:
        if s.icon_asset is not None:
            assert s.shape is SKIP, f"{s.name!r} has an icon_asset but is not SKIP"
    assert ICON_ASSETS == {
        s.render: s.icon_asset for s in PRIMITIVE_SPECS if s.icon_asset is not None
    }


def test_registry_resolves_through_geom_and_convention():
    """The historical import sites still expose the same derived objects, so the
    collapse is transparent to every existing consumer."""
    from imageGen.layout import _geom
    from imageGen.verify import convention_check as cc
    from imageGen.render import credits

    assert _geom.PRIMITIVE_REGISTRY is PRIMITIVE_REGISTRY
    assert _geom.PRIMITIVE_TO_BBOX is PRIMITIVE_TO_BBOX
    assert cc._PRIMITIVE_SHAPE is PRIMITIVE_SHAPE
    assert cc._SKIP_SHAPE_PRIMITIVES is SKIP_SHAPE_PRIMITIVES
    assert credits.ICON_ASSETS is ICON_ASSETS


def test_duplicate_name_fails_loud():
    """The import-time uniqueness guard rejects a colliding registration."""
    from imageGen.primitives import primitive_specs as ps

    bad = [*ps.PRIMITIVE_SPECS, ps.PRIMITIVE_SPECS[0]]
    saved = ps.PRIMITIVE_SPECS
    ps.PRIMITIVE_SPECS = bad
    try:
        with pytest.raises(ValueError, match="Duplicate PrimitiveSpec"):
            ps._check_unique()
    finally:
        ps.PRIMITIVE_SPECS = saved
