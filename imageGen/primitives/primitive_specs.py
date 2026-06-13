"""Single-site primitive registry (P0c.1).

Registering a primitive used to mean synchronized edits across three files:
the ``_geom.PRIMITIVE_REGISTRY`` name→callable map *and* its bbox tables, the
``convention_check._PRIMITIVE_SHAPE`` / ``_SKIP_SHAPE_PRIMITIVES`` shape map,
and (for embedded Bioicons) ``entity_adapters.ICON_ASSETS`` — kept in lock-step
only by one coverage test. This module collapses all of that into a single list
of :class:`PrimitiveSpec` records; every downstream table is *derived* from it,
so adding a primitive is a one-line append here.

Each spec carries:

* ``name``        — the ``style.primitive`` override token + registry key.
* ``render``      — the primitive callable (uniform entity signature).
* ``bbox``        — canonical ``(w, h)`` for arrow insets / collision boxes.
* ``shape``       — the SVG tag of its first shape element (for
  ``convention_check``), or :data:`SKIP` for a composite drawing (RDKit
  structure or an embedded multi-path Bioicons illustration) that has no single
  type-conventional glyph and is shape-checked the same way reactions are: not
  at all.
* ``icon_asset``  — for embedded Bioicons only, the ``assets/icons/<name>.svg``
  stem so ``render/credits`` can collect attribution; ``None`` otherwise.

Layering note: this is the lowest layer — it imports only ``primitives``
sub-modules (no ``layout`` / ``verify`` / ``render`` imports), so it can be
imported by all three without a cycle. The ``EntityType`` → primitive *default*
mapping (``ENTITY_TO_PRIMITIVE``) and the per-``EntityType`` ``ENTITY_BBOX`` stay
in ``layout/_geom`` — they are an orthogonal axis (which glyph a *type* defaults
to), not part of registering a primitive. The bbox here is explicit per spec
rather than inherited through ``ENTITY_TO_PRIMITIVE``; the values match what the
old inheritance resolved to, just stated once at the single source.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import svgwrite.container

from imageGen.primitives import entity_adapters, glyphs, nucleic_acids, proteins


class _Skip:
    """Sentinel for a composite primitive with no conventional shape tag."""

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debug aid only
        return "SKIP"


#: Marks a primitive whose drawing is a composite (RDKit structure or an
#: embedded Bioicons illustration), so ``convention_check`` skips its shape.
SKIP = _Skip()


@dataclass(frozen=True)
class PrimitiveSpec:
    """One registered primitive and everything the pipeline needs to know about
    it. See the module docstring for field semantics."""

    name: str
    render: Callable[..., svgwrite.container.Group]
    bbox: tuple[float, float]
    shape: str | _Skip
    icon_asset: str | None = None


# ---------------------------------------------------------------------------
# The single registry. Append one PrimitiveSpec to add a primitive.
# Order mirrors the old PRIMITIVE_REGISTRY for an easy diff.
# ---------------------------------------------------------------------------

PRIMITIVE_SPECS: list[PrimitiveSpec] = [
    # core proteins
    PrimitiveSpec("generic_protein",      proteins.generic_protein,      (60.0, 30.0),  "rect"),
    PrimitiveSpec("protein_complex",      proteins.protein_complex,      (72.0, 38.0),  "rect"),
    PrimitiveSpec("kinase",               proteins.kinase,               (70.0, 32.0),  "polygon"),
    PrimitiveSpec("receptor",             proteins.receptor,             (28.0, 60.0),  "polygon"),
    PrimitiveSpec("gpcr",                 proteins.gpcr,                 (60.0, 30.0),  "rect"),
    PrimitiveSpec("transcription_factor", proteins.transcription_factor, (60.0, 30.0),  "rect"),
    PrimitiveSpec("gene_helix",           nucleic_acids.gene_helix,      (80.0, 40.0),  "polyline"),
    PrimitiveSpec("rna_helix",            nucleic_acids.rna_helix,       (80.0, 40.0),  "polyline"),
    # v2.x expansion glyphs — cell / signalling
    PrimitiveSpec("antibody",             glyphs.antibody,               (50.0, 50.0),  "path"),
    PrimitiveSpec("ion_channel",          glyphs.ion_channel,            (40.0, 50.0),  "polygon"),
    PrimitiveSpec("transporter",          glyphs.transporter,            (40.0, 50.0),  "polygon"),
    PrimitiveSpec("pump",                 glyphs.pump,                   (44.0, 52.0),  "polygon"),
    PrimitiveSpec("phosphatase",          glyphs.phosphatase,            (70.0, 32.0),  "polygon"),
    PrimitiveSpec("ribosome",             glyphs.ribosome,               (50.0, 50.0),  "ellipse"),
    PrimitiveSpec("vesicle",              glyphs.vesicle,                (44.0, 44.0),  "circle"),
    # v2.x expansion glyphs — lab equipment (flask/centrifuge now embedded Bioicons, D9)
    PrimitiveSpec("flask",                entity_adapters.flask,         (44.0, 60.0),  SKIP, "flask"),
    PrimitiveSpec("centrifuge",           entity_adapters.centrifuge,    (64.0, 56.0),  SKIP, "centrifuge"),
    PrimitiveSpec("flow_cytometer",       glyphs.flow_cytometer,         (64.0, 50.0),  "rect"),
    PrimitiveSpec("sequencer",            glyphs.sequencer,              (64.0, 48.0),  "rect"),
    PrimitiveSpec("petri_dish",           glyphs.petri_dish,             (60.0, 40.0),  "ellipse"),
    PrimitiveSpec("syringe",              glyphs.syringe,                (76.0, 30.0),  "rect"),
    # v2.x expansion glyphs — nucleic acids
    PrimitiveSpec("mrna_helix",           nucleic_acids.mrna_helix,      (90.0, 40.0),  "polyline"),
    PrimitiveSpec("primer_helix",         nucleic_acids.primer_helix,    (60.0, 36.0),  "polyline"),
    # domain-canonical idioms (FR10)
    PrimitiveSpec("voltage_trace",        glyphs.voltage_trace,          (150.0, 90.0), "path"),
    # cellular-schematic primitives — cell boundaries & organelles
    PrimitiveSpec("cell",                 entity_adapters.cell,            (72.0, 56.0), "polygon"),
    PrimitiveSpec("cell_neuron",          entity_adapters.cell_neuron,     (84.0, 52.0), "polygon"),
    PrimitiveSpec("cell_epithelial",      entity_adapters.cell_epithelial, (56.0, 72.0), "polygon"),
    PrimitiveSpec("cell_immune",          entity_adapters.cell_immune,     (64.0, 64.0), "polygon"),
    PrimitiveSpec("mitochondrion",        entity_adapters.mitochondrion,   (56.0, 46.0), "polygon"),
    PrimitiveSpec("nucleus",              entity_adapters.nucleus,         (56.0, 52.0), "circle"),
    PrimitiveSpec("endoplasmic_reticulum", entity_adapters.endoplasmic_reticulum, (60.0, 46.0), "polyline"),
    PrimitiveSpec("golgi",                entity_adapters.golgi,           (56.0, 46.0), "polygon"),
    PrimitiveSpec("lysosome",             entity_adapters.lysosome,        (44.0, 44.0), "circle"),
    # method-figure lab equipment (richer than the flask/centrifuge glyphs)
    PrimitiveSpec("microscope",           entity_adapters.microscope,      (60.0, 64.0), SKIP, "microscope"),
    PrimitiveSpec("well_plate",           entity_adapters.well_plate,      (96.0, 70.0), SKIP, "well_plate"),
    PrimitiveSpec("tube",                 entity_adapters.tube,            (40.0, 58.0), SKIP, "tube"),
    PrimitiveSpec("pipette",              entity_adapters.pipette,         (28.0, 74.0), "rect"),
    PrimitiveSpec("gel",                  entity_adapters.gel,             (40.0, 74.0), SKIP, "agarose_gel"),
    PrimitiveSpec("western_blot",         entity_adapters.western_blot,    (60.0, 64.0), SKIP, "western_blot"),
    PrimitiveSpec("mouse",                entity_adapters.mouse,           (84.0, 46.0), SKIP, "mouse"),
    PrimitiveSpec("human_figure",         entity_adapters.human_figure,    (44.0, 60.0), "circle"),
    # chemical structure from SMILES (EW1) — entity with style.smiles
    PrimitiveSpec("molecule",             entity_adapters.molecule,        (120.0, 96.0), SKIP),
    # named functional-group callout (EW2) — entity with style.functional_group
    PrimitiveSpec("functional_group",     entity_adapters.functional_group, (110.0, 96.0), SKIP),
    # closed lipid-bilayer vesicle (EW3) — distinct from glyphs.vesicle
    PrimitiveSpec("liposome",             entity_adapters.liposome,        (96.0, 96.0), "polygon"),
]


def _check_unique() -> None:
    """Fail loud at import if two specs share a name or callable — the registry
    is keyed on both, so a collision would silently shadow one entry."""
    names = [s.name for s in PRIMITIVE_SPECS]
    if len(names) != len(set(names)):
        dupes = sorted({n for n in names if names.count(n) > 1})
        raise ValueError(f"Duplicate PrimitiveSpec name(s): {dupes}")
    renders = [s.render for s in PRIMITIVE_SPECS]
    if len(renders) != len(set(renders)):
        dupes = sorted(
            {r.__name__ for r in renders if renders.count(r) > 1}
        )
        raise ValueError(f"Duplicate PrimitiveSpec callable(s): {dupes}")


_check_unique()


# ---------------------------------------------------------------------------
# Derived tables — every former hand-maintained map now falls out of the list.
# ---------------------------------------------------------------------------

#: name → primitive callable (the override registry).
PRIMITIVE_REGISTRY: dict[str, Callable[..., svgwrite.container.Group]] = {
    s.name: s.render for s in PRIMITIVE_SPECS
}

#: primitive callable → canonical (w, h) bbox.
PRIMITIVE_TO_BBOX: dict[Callable[..., svgwrite.container.Group], tuple[float, float]] = {
    s.render: s.bbox for s in PRIMITIVE_SPECS
}

#: primitive callable → SVG shape tag (composites excluded; see SKIP_SHAPE_PRIMITIVES).
PRIMITIVE_SHAPE: dict[Callable[..., svgwrite.container.Group], str] = {
    s.render: s.shape for s in PRIMITIVE_SPECS if not isinstance(s.shape, _Skip)
}

#: primitive callables whose drawing is a composite — convention_check skips them.
SKIP_SHAPE_PRIMITIVES: frozenset[Callable[..., svgwrite.container.Group]] = frozenset(
    s.render for s in PRIMITIVE_SPECS if isinstance(s.shape, _Skip)
)

#: embedded-Bioicons primitive callable → asset stem (for render/credits).
ICON_ASSETS: dict[Callable[..., svgwrite.container.Group], str] = {
    s.render: s.icon_asset for s in PRIMITIVE_SPECS if s.icon_asset is not None
}
