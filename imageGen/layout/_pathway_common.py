"""Shared constants + dispatch tables for the pathway engine (Phase R1).

The bottom leaf of the pathway-engine module DAG: holds the handful of symbols
referenced by more than one ``_pathway_*`` sub-module, so those modules import
*down* into here rather than sideways into each other (which would cycle).

Depends only on ``_pathway_glyphs`` (for the phospho arrow primitive) and the
external ``arrows`` module. ``pathway_layout`` re-exports ``RELATION_TO_ARROW``
so it stays importable from ``pathway_layout`` for ``label_placement`` + tests.
"""
from __future__ import annotations

from typing import Callable

import svgwrite.container

from imageGen.ir.schema import RelationType
from imageGen.layout._pathway_glyphs import _phosphorylation_arrow
from imageGen.primitives import arrows


# px — headroom for band label + top/bottom breathing room. Used by
# _compute_band_heights (_pathway_rings) and layout_pathway's implicit-band
# height grow (orchestrator).
_LABEL_MARGIN = 40.0

# matches _DEFAULT_LABEL_STYLE in label_placement. Used by _left_label_extent
# (_pathway_bands) and _route_same_band_arrows (_pathway_routing).
_RECEPTOR_FONT_SIZE = 11.0

# Sentinel compartment id for figures with no declared spatial context. Used by
# the band engine (_pathway_bands) and the orchestrator (compute_pathway_canvas,
# layout_pathway).
_IMPLICIT_COMPARTMENT_ID = "__implicit__"


# ---------------------------------------------------------------------------
# Relation → arrow dispatch (public so tests + future archetypes introspect it).
# ---------------------------------------------------------------------------

RELATION_TO_ARROW: dict[RelationType, Callable[..., svgwrite.container.Group]] = {
    RelationType.ACTIVATES:      arrows.activation_arrow,
    RelationType.INHIBITS:       arrows.inhibition_arrow,
    RelationType.BINDS:          arrows.binding_arrow,
    RelationType.TRANSLOCATES:   arrows.translocation_arrow,
    RelationType.PHOSPHORYLATES: _phosphorylation_arrow,  # V2/L4: annotated with 'P' badge
    RelationType.TRANSCRIBES:    arrows.activation_arrow,
    RelationType.CATALYZES:      arrows.catalysis_arrow,
    RelationType.CLEAVES:        arrows.cleavage_arrow,
    RelationType.TRANSPORTS:     arrows.transport_arrow,
    RelationType.RECRUITS:       arrows.recruitment_arrow,
    RelationType.GENERIC:        arrows.activation_arrow,
}
