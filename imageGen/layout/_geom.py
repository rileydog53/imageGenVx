"""Shared geometry and primitive-dispatch tables for the layout package.

These tables are keyed by `EntityType` and consumed by multiple layout
engines, so they live here rather than inside any one engine. Keep
`ENTITY_BBOX` in sync if a primitive's default size changes; Phase 4's
master preset will eventually centralise this so the bbox can come from
style instead of a hard-coded table.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Callable

import svgwrite.container

from imageGen.ir.schema import Entity, EntityType, Figure
from imageGen.primitives import entity_adapters, nucleic_acids, proteins
# P0c.1: the primitive override registry + its bbox table are now *derived* from
# the single PRIMITIVE_SPECS list. Re-exported here so the historical import
# sites (``from imageGen.layout._geom import PRIMITIVE_REGISTRY, PRIMITIVE_TO_BBOX``)
# keep resolving unchanged.
from imageGen.primitives.primitive_specs import (  # noqa: F401  (re-export)
    PRIMITIVE_REGISTRY,
    PRIMITIVE_TO_BBOX,
)

# Per-EntityType bounding boxes (w, h), tracking each primitive's default
# size in `primitives/proteins.py`. Used to inset arrow endpoints to the
# entity's perimeter so shafts/heads never overlap entity labels, and
# (in label_placement) to compute the bbox of an entity LayoutEntry for
# collision-aware label anchoring.
ENTITY_BBOX: dict[EntityType, tuple[float, float]] = {
    EntityType.PROTEIN:    (60.0, 30.0),
    EntityType.COMPLEX:    (72.0, 38.0),
    EntityType.LIGAND:     (60.0, 30.0),
    EntityType.RECEPTOR:   (28.0, 60.0),
    EntityType.KINASE:     (70.0, 32.0),
    EntityType.GENE:       (80.0, 40.0),
    EntityType.RNA:        (80.0, 40.0),
    EntityType.METABOLITE: (60.0, 30.0),
    EntityType.CELL:       (72.0, 56.0),
    EntityType.ORGANELLE:  (56.0, 46.0),
    EntityType.EQUIPMENT:  (60.0, 64.0),
    EntityType.SAMPLE:     (40.0, 58.0),
    EntityType.GENERIC:    (60.0, 30.0),
}

# EntityType → primitive callable. Pathway layout uses this to render
# entities; label_placement uses the reverse lookup (primitive → bbox)
# when anchoring labels to entity LayoutEntries.
ENTITY_TO_PRIMITIVE: dict[EntityType, Callable[..., svgwrite.container.Group]] = {
    EntityType.PROTEIN:    proteins.generic_protein,
    EntityType.COMPLEX:    proteins.protein_complex,
    EntityType.LIGAND:     proteins.generic_protein,
    EntityType.RECEPTOR:   proteins.receptor,
    EntityType.KINASE:     proteins.kinase,
    EntityType.GENE:       nucleic_acids.gene_helix,
    EntityType.RNA:        nucleic_acids.rna_helix,
    EntityType.METABOLITE: proteins.generic_protein,
    EntityType.CELL:       entity_adapters.cell,
    EntityType.ORGANELLE:  entity_adapters.mitochondrion,
    EntityType.EQUIPMENT:  entity_adapters.microscope,
    EntityType.SAMPLE:     entity_adapters.tube,
    EntityType.GENERIC:    proteins.generic_protein,
}


# ---------------------------------------------------------------------------
# V2 / L6: primitive override registry — now defined as a single PRIMITIVE_SPECS
# list (P0c.1, ``primitives/primitive_specs.py``). ``PRIMITIVE_REGISTRY`` (name →
# callable; an IR author sets ``entity.style["primitive"] = "<name>"`` to override
# the EntityType default) and ``PRIMITIVE_TO_BBOX`` (callable → canonical (w, h)
# for arrow insets / collision boxes) are re-exported above. Add a new primitive
# by appending one ``PrimitiveSpec`` there — no edit needed here.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# EW4 / PH.5: label-keyword → glyph inference for the coarse, label-agnostic types.
#
# CELL / ORGANELLE / EQUIPMENT / SAMPLE each have a single ``ENTITY_TO_PRIMITIVE``
# default (a generic cell / mitochondrion / microscope / tube) that ignores the
# label — so a ``"Western blot"`` equipment drew as a microscope. These rules
# map a label keyword to a *more specific* registered primitive; the first
# matching keyword wins, and a no-match falls through to the type default.
#
# Only NON-default glyphs are listed (the default already covers everything
# else), which keeps the blast radius small: a figure's rendering changes only
# when a label actually names a specific glyph. Keywords are matched at a
# word-start boundary so stems work (``"epitheli"`` → *epithelial*) without
# false friends mid-word (``\bplate`` does not fire inside *template*).
#
# PH.5: the table is now checked-in declarative data (``inference_rules.json``,
# this directory) so it is diffable and unit-testable. It is loaded here into the
# same in-memory shape the hardcoded table used, so ``infer_primitive`` and every
# caller are unchanged. ``infer_primitive_explained`` / ``explain_entity_primitive``
# expose *why* an entity drew as a given glyph for the CLI ``--explain`` pass.
# ---------------------------------------------------------------------------

_INFERENCE_RULES_PATH = Path(__file__).parent / "inference_rules.json"


def _load_inference_rules() -> dict[EntityType, tuple[tuple[tuple[str, ...], str], ...]]:
    """Load ``inference_rules.json`` into ``{EntityType: ((keywords, primitive), …)}``.

    Order is preserved (it is significant — e.g. EQUIPMENT 'blot' precedes 'gel').
    ``_``-prefixed keys (the file's ``_comment``) are skipped. Returns the same
    shape the hardcoded table used so ``infer_primitive`` is behaviour-identical.
    """
    raw = json.loads(_INFERENCE_RULES_PATH.read_text())
    return {
        EntityType(entity_type): tuple(
            (tuple(keywords), primitive) for keywords, primitive in rules
        )
        for entity_type, rules in raw.items()
        if not entity_type.startswith("_")
    }


_INFERENCE_RULES: dict[EntityType, tuple[tuple[tuple[str, ...], str], ...]] = (
    _load_inference_rules()
)


def infer_primitive_explained(
    entity_type: EntityType, label: str | None
) -> tuple[str | None, str | None]:
    """Like :func:`infer_primitive`, but also return the keyword that matched.

    Returns ``(primitive, keyword)`` when a rule fires (the first matching
    keyword, top-to-bottom), else ``(None, None)``. The single source of the
    matching logic — :func:`infer_primitive` delegates to it. Powers the
    ``--explain`` pass so an author can see *why* an entity drew as a glyph.
    """
    rules = _INFERENCE_RULES.get(entity_type)
    if not rules or not label:
        return None, None
    text = label.lower()
    for keywords, primitive in rules:
        for kw in keywords:
            if re.search(r"\b" + re.escape(kw), text):
                return primitive, kw
    return None, None


def infer_primitive(entity_type: EntityType, label: str | None) -> str | None:
    """Return a registry primitive name inferred from ``label``, or ``None``.

    Consulted only for the coarse types in ``_INFERENCE_RULES``; every other
    type (and any unmatched label) returns ``None`` so the caller uses the
    ``ENTITY_TO_PRIMITIVE`` default. See the table comment for the rationale.
    """
    return infer_primitive_explained(entity_type, label)[0]


def resolve_entity_primitive(
    entity: Entity,
) -> Callable[..., svgwrite.container.Group]:
    """Resolve the primitive an entity renders with: explicit override →
    label inference → entity-type default.

    The single source of truth shared by ``pathway_layout`` (dispatch) and
    ``convention_check`` (shape verification) so the two never disagree about
    which glyph an entity is drawn as. An unknown override name falls through to
    inference/default here; ``pathway_layout`` separately emits the warning.
    """
    name = (entity.style or {}).get("primitive")
    if name is not None and name in PRIMITIVE_REGISTRY:
        return PRIMITIVE_REGISTRY[name]
    inferred = infer_primitive(entity.type, entity.label)
    if inferred is not None:
        return PRIMITIVE_REGISTRY[inferred]
    return ENTITY_TO_PRIMITIVE[entity.type]


def explain_entity_primitive(entity: Entity) -> tuple[str | None, str]:
    """Return ``(primitive_name, basis)`` describing how *entity*'s glyph is
    chosen — the observable counterpart to :func:`resolve_entity_primitive`,
    which it mirrors branch-for-branch.

    ``basis`` is one of:
      - ``"override: style['primitive']=<name>"`` — an explicit, registered override.
      - ``"inferred: keyword '<kw>' -> <primitive>"`` — a label-keyword match.
      - ``"default: entity type <type>"`` — the ``ENTITY_TO_PRIMITIVE`` fallback.

    ``primitive_name`` is the registered name when known (``None`` only for a
    default callable that isn't in ``PRIMITIVE_REGISTRY``). This adds
    observability for the CLI ``--explain`` pass (PH.5); the *control* over the
    choice already exists via ``entity.style['primitive']``.
    """
    name = (entity.style or {}).get("primitive")
    if name is not None and name in PRIMITIVE_REGISTRY:
        return name, f"override: style['primitive']={name!r}"
    inferred, keyword = infer_primitive_explained(entity.type, entity.label)
    if inferred is not None:
        return inferred, f"inferred: keyword {keyword!r} -> {inferred}"
    default_cb = ENTITY_TO_PRIMITIVE[entity.type]
    default_name = next(
        (n for n, cb in PRIMITIVE_REGISTRY.items() if cb is default_cb), None
    )
    return default_name, f"default: entity type {entity.type.value!r}"


def max_entity_bbox(figure: Figure) -> tuple[float, float]:
    """Return (max_w, max_h) of all entity bboxes in `figure`.

    Falls back to the PROTEIN default for an entity-less figure so callers
    that pre-size a canvas always get a sensible answer. Used by the
    compositor to compute a content-aware canvas size.
    """
    if not figure.entities:
        return ENTITY_BBOX[EntityType.PROTEIN]
    widths = [ENTITY_BBOX[e.type][0] for e in figure.entities]
    heights = [ENTITY_BBOX[e.type][1] for e in figure.entities]
    return (max(widths), max(heights))


def entities_per_band(figure: Figure) -> list[int]:
    """Return entity count per compartment in declaration order.

    When a figure has no declared compartments, returns a single-element
    list with the total entity count (matches the implicit-band synthesis
    that pathway_layout does). Entities with `location=None` fall back to
    the first declared compartment — same rule the layout engine uses.
    """
    if not figure.compartments:
        return [len(figure.entities)]
    fallback = figure.compartments[0].id
    counts: list[int] = []
    for c in figure.compartments:
        counts.append(sum(
            1 for e in figure.entities
            if (e.location or fallback) == c.id
        ))
    return counts
