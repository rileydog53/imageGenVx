"""Convention verification — Phase 6 Step 3.

Re-parses a rendered SVG and verifies that scientific drawing conventions
hold. A figure can pass ``semantic_check`` (every element present) and
``legibility_check`` (text readable) yet still mislead a reader by drawing
an element with the wrong glyph — ``convention_check`` is that audit.

Conventions enforced:
  * Inhibition arrows use a T-bar terminus, never a triangular arrowhead.
    A T-bar and an arrowhead carry different biological meanings
    (repression vs. activation), so the two must never be swapped.
  * Every entity renders with its resolved primitive's conventional shape.
    The expected primitive comes from ``layout/_geom.resolve_entity_primitive``
    — the single source of truth shared with ``pathway_layout`` dispatch
    (explicit ``style.primitive`` override → EW4 label inference → the
    ``EntityType`` default) — so this catches both an inconsistency *and* a
    whole type rendered with the wrong shape, and never disagrees with what
    layout actually drew.

Scope:
  Mirrors ``semantic_check``'s dispatch — REACTION_SCHEME (sub-)figures
  render as one composite ``reaction_0`` group with no per-entity or
  per-relation ids, so they are skipped. A missing element is
  ``semantic_check``'s responsibility; ``convention_check`` assumes the
  figure already passed Step 1 and silently skips any id it cannot find.

Failure mode:
  Raises ``ConventionCheckError`` on the first violation, matching the
  fail-loud precedent of ``SemanticCheckError`` / ``LegibilityCheckError``.

Limitations:
  The entity-shape signature is the SVG geometry *tag* of the shape, so it
  distinguishes the rect-family from the polygon-family but not a kinase
  hexagon from a receptor hourglass — both are 6-point ``<polygon>``s.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterator, Literal

from imageGen.ir.schema import Archetype, Figure, RelationType
from imageGen.layout._geom import resolve_entity_primitive
# P0c.1: the primitive → shape-tag map and the composite skip-set are derived
# from the single PRIMITIVE_SPECS list. Aliased to the historical private names
# so this module's consumers (and tests importing them) are unchanged.
from imageGen.primitives.primitive_specs import (
    PRIMITIVE_SHAPE as _PRIMITIVE_SHAPE,
    SKIP_SHAPE_PRIMITIVES as _SKIP_SHAPE_PRIMITIVES,
)
from imageGen.render.compositor import scoped_id

_Kind = Literal["inhibition_arrow", "entity_shape"]

# SVG tags that count as an entity's primary shape, matched in the order
# the primitives emit children — the shape glyph is always drawn before
# any badge (e.g. a phosphorylated-kinase ``<circle>``) or ``<text>`` label.
_SHAPE_TAGS = ("rect", "polygon", "ellipse", "circle", "path", "polyline")

# `_PRIMITIVE_SHAPE` (primitive callable → SVG shape tag) and
# `_SKIP_SHAPE_PRIMITIVES` (composite primitives with no conventional glyph) are
# imported above from `primitives/primitive_specs.py` — `_geom` owns the
# `EntityType → primitive` mapping, the spec list owns `primitive → shape tag`.


class ConventionCheckError(RuntimeError):
    """Raised when a rendered figure violates a visual convention.

    Attributes:
        kind: ``"inhibition_arrow"`` (an inhibition drawn with an
            arrowhead or missing its T-bar) or ``"entity_shape"`` (an
            entity rendered with the wrong shape for its type).
        ir_id: The IR id of the offending element — an entity id, or a
            relation's synthetic ``Relation.ir_id``.
        detail: Human-readable specifics.
    """

    def __init__(self, kind: _Kind, ir_id: str, detail: str) -> None:
        self.kind = kind
        self.ir_id = ir_id
        self.detail = detail
        super().__init__(f"Convention violation ({kind}): {detail}")


def _tag(el: ET.Element) -> str:
    """Local tag name, stripped of the ``{namespace}`` prefix."""
    return el.tag.split("}")[-1]


def _figures(
    figure: Figure, panel_chain: tuple[str, ...]
) -> Iterator[tuple[Figure, tuple[str, ...]]]:
    """Yield ``(figure, panel_chain)`` for ``figure`` and every nested panel.

    The panel chain is extended by each panel id so callers can build the
    same scoped ids the compositor applies (D1).
    """
    yield figure, panel_chain
    for panel in figure.panels:
        yield from _figures(panel.content, (*panel_chain, panel.id))


def _check_inhibition_arrows(
    figure: Figure, panel_chain: tuple[str, ...], groups: dict[str, ET.Element]
) -> None:
    """Verify every INHIBITS relation in ``figure`` is drawn with a T-bar."""
    for relation in figure.relations:
        if relation.type != RelationType.INHIBITS:
            continue
        group = groups.get(scoped_id(relation.ir_id, panel_chain))
        if group is None:
            continue  # missing element — semantic_check's responsibility
        has_polygon = has_t_bar = False
        for el in group.iter():
            tag = _tag(el)
            if tag == "polygon":
                has_polygon = True
            elif tag == "line" and el.get("stroke-linecap") == "square":
                has_t_bar = True
        if has_polygon:
            raise ConventionCheckError(
                "inhibition_arrow",
                relation.ir_id,
                f"inhibition relation {relation.ir_id!r} is drawn with an "
                f"arrowhead (<polygon>) instead of a T-bar",
            )
        if not has_t_bar:
            raise ConventionCheckError(
                "inhibition_arrow",
                relation.ir_id,
                f"inhibition relation {relation.ir_id!r} has no T-bar "
                f"(square-capped <line>) terminus",
            )


def _check_entity_shapes(
    figure: Figure, panel_chain: tuple[str, ...], groups: dict[str, ET.Element]
) -> None:
    """Verify every entity renders with its type's conventional shape."""
    for entity in figure.entities:
        group = groups.get(scoped_id(entity.id, panel_chain))
        if group is None:
            continue  # missing element — semantic_check's responsibility
        # Resolve the primitive exactly as pathway_layout does — explicit
        # override, then EW4 label inference, then the type default — via the
        # shared resolver, so the expected shape always matches what was drawn.
        prim = resolve_entity_primitive(entity)
        if prim in _SKIP_SHAPE_PRIMITIVES:
            continue  # composite structure (e.g. a molecule) — no conventional shape
        expected = _PRIMITIVE_SHAPE[prim]
        actual = next(
            (_tag(el) for el in group.iter() if _tag(el) in _SHAPE_TAGS), None
        )
        if actual is None:
            raise ConventionCheckError(
                "entity_shape",
                entity.id,
                f"entity {entity.id!r} renders no shape element",
            )
        if actual != expected:
            raise ConventionCheckError(
                "entity_shape",
                entity.id,
                f"entity {entity.id!r} (type {entity.type.value}) renders as "
                f"<{actual}> but the {entity.type.value} convention is "
                f"<{expected}>",
            )


def convention_check(ir: Figure, svg_path: str | Path) -> None:
    """Verify visual conventions hold in a rendered SVG.

    Args:
        ir: The IR Figure that was rendered.
        svg_path: Path to the SVG produced by ``render_figure``.

    Raises:
        ConventionCheckError: On the first convention violation — an
            inhibition arrow without a T-bar, or an entity rendered with
            the wrong shape for its type.
    """
    root = ET.parse(str(svg_path)).getroot()
    groups = {el.get("id"): el for el in root.iter() if el.get("id") is not None}

    for figure, panel_chain in _figures(ir, ()):
        if figure.archetype == Archetype.REACTION_SCHEME:
            continue  # composite reaction_0 group — no per-element ids
        _check_inhibition_arrows(figure, panel_chain, groups)
        _check_entity_shapes(figure, panel_chain, groups)
