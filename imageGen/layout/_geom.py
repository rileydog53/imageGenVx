"""Shared geometry and primitive-dispatch tables for the layout package.

These tables are keyed by `EntityType` and consumed by multiple layout
engines, so they live here rather than inside any one engine. Keep
`ENTITY_BBOX` in sync if a primitive's default size changes; Phase 4's
master preset will eventually centralise this so the bbox can come from
style instead of a hard-coded table.
"""
from __future__ import annotations

from typing import Callable

import svgwrite.container

from imageGen.ir.schema import EntityType, Figure
from imageGen.primitives import glyphs, nucleic_acids, proteins

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
    EntityType.CELL:       (60.0, 30.0),
    EntityType.ORGANELLE:  (60.0, 30.0),
    EntityType.EQUIPMENT:  (60.0, 30.0),
    EntityType.SAMPLE:     (60.0, 30.0),
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
    EntityType.CELL:       proteins.generic_protein,
    EntityType.ORGANELLE:  proteins.generic_protein,
    EntityType.EQUIPMENT:  proteins.generic_protein,
    EntityType.SAMPLE:     proteins.generic_protein,
    EntityType.GENERIC:    proteins.generic_protein,
}


# ---------------------------------------------------------------------------
# V2 / L6: primitive override registry.
# Maps string name → primitive callable. IR authors can set
# entity.style["primitive"] = "<name>" to render that entity with a
# non-default primitive regardless of its EntityType. Unknown names trigger
# a UserWarning in pathway_layout and fall back to the type default.
# Add new entity-appropriate primitives here when introduced.
# ---------------------------------------------------------------------------

PRIMITIVE_REGISTRY: dict[str, Callable[..., svgwrite.container.Group]] = {
    "generic_protein":       proteins.generic_protein,
    "protein_complex":       proteins.protein_complex,
    "kinase":                proteins.kinase,
    "receptor":              proteins.receptor,
    "gpcr":                  proteins.gpcr,
    "transcription_factor":  proteins.transcription_factor,
    "gene_helix":            nucleic_acids.gene_helix,
    "rna_helix":             nucleic_acids.rna_helix,
    # v2.x expansion glyphs — cell / signalling
    "antibody":              glyphs.antibody,
    "ion_channel":           glyphs.ion_channel,
    "transporter":           glyphs.transporter,
    "pump":                  glyphs.pump,
    "phosphatase":           glyphs.phosphatase,
    "ribosome":              glyphs.ribosome,
    "vesicle":               glyphs.vesicle,
    # v2.x expansion glyphs — lab equipment
    "flask":                 glyphs.flask,
    "centrifuge":            glyphs.centrifuge,
    "flow_cytometer":        glyphs.flow_cytometer,
    "sequencer":             glyphs.sequencer,
    "petri_dish":            glyphs.petri_dish,
    "syringe":               glyphs.syringe,
    # v2.x expansion glyphs — nucleic acids
    "mrna_helix":            nucleic_acids.mrna_helix,
    "primer_helix":          nucleic_acids.primer_helix,
    # domain-canonical idioms (FR10)
    "voltage_trace":         glyphs.voltage_trace,
}

# Explicit (w, h) for registry primitives that have no ENTITY_TO_PRIMITIVE
# entry to inherit a bbox from. Keeps arrow insets and collision bboxes sane
# for the expansion glyphs (which don't map 1:1 to an EntityType).
_PRIMITIVE_BBOX_OVERRIDE: dict[Callable[..., svgwrite.container.Group], tuple[float, float]] = {
    glyphs.antibody:        (50.0, 50.0),
    glyphs.ion_channel:     (40.0, 50.0),
    glyphs.transporter:     (40.0, 50.0),
    glyphs.pump:            (44.0, 52.0),
    glyphs.phosphatase:     (70.0, 32.0),
    glyphs.ribosome:        (50.0, 50.0),
    glyphs.vesicle:         (44.0, 44.0),
    glyphs.flask:           (44.0, 56.0),
    glyphs.centrifuge:      (54.0, 54.0),
    glyphs.flow_cytometer:  (64.0, 50.0),
    glyphs.sequencer:       (64.0, 48.0),
    glyphs.petri_dish:      (60.0, 40.0),
    glyphs.syringe:         (76.0, 30.0),
    nucleic_acids.mrna_helix:   (90.0, 40.0),
    nucleic_acids.primer_helix: (60.0, 36.0),
    glyphs.voltage_trace:       (150.0, 90.0),
}

# Canonical (w, h) for each registered primitive — used when a primitive
# override is applied so arrow insets and collision bboxes stay correct.
# An explicit override wins; otherwise inherit from ENTITY_BBOX for the first
# EntityType that maps to the primitive; otherwise the generic-protein size.
PRIMITIVE_TO_BBOX: dict[Callable[..., svgwrite.container.Group], tuple[float, float]] = {
    prim: _PRIMITIVE_BBOX_OVERRIDE.get(
        prim,
        next(
            (ENTITY_BBOX[et] for et, p in ENTITY_TO_PRIMITIVE.items() if p is prim),
            (60.0, 30.0),
        ),
    )
    for prim in PRIMITIVE_REGISTRY.values()
}


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
