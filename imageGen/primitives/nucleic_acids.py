"""Nucleic acid primitives for scientific figure generation.

Visual conventions followed here:
- DNA double helix: two sine waves with 180° phase offset projected perpendicularly
  onto the helix axis. Crossover depth is conveyed by alternating z-order at each
  half-period -- even segments show strand 1 in front (drawn last), odd segments
  show strand 2 in front. Base pair rungs are drawn at the half-period midpoints;
  when a sequence string is provided, rungs are color-coded (A-T red, G-C blue)
  and labeled with both bases ("A-T", "G-C").
- RNA: a single sine wave in orange (convention: RNA is orange, DNA is blue in
  most cell-biology pathway figures). double-stranded RNA uses the same crossover
  z-order logic as DNA.
- Chromatin: beads-on-string at condensation_level=0 (nucleosome circles on a thin
  backbone), condensed fiber at condensation_level=1. Intermediate values interpolate:
  nucleosome radius shrinks and fiber opacity rises linearly.

Phase 3 coupling:
  dna_segment and rna_segment accept start/end axis coordinates directly. Composability
  is by caller convention -- a transcription schematic places rna_segment(start=tx_site)
  at a coordinate derived from a dna_segment call without importing this module twice.
  No anchor protocol needed here (contrast: membranes.py MembraneCurve, which exists
  because membrane proteins must anchor to an arbitrary closed curve).

Phase 4 assumption:
  DEFAULT_STYLE uses flat namespaced keys (dna_*, rna_*, chromatin_*, label_*)
  so the Phase 4 master preset JSON can union all primitive modules without collision.

Future extensibility:
  - Methylation marks: extend the rung-drawing section of dna_segment with an
    optional methyl marker at CpG positions -- no changes to the public signature.
  - New RNA colors: change rna_stroke in the preset, not this module.
  - Supercoiled accuracy: _supercoiled_axis() currently uses a secondary sine wave.
    Replace it with a true plectonemic algorithm in Phase 6 without changing the
    dna_segment() public API.
  - Chromatin detail: add histone tail glyphs by extending the bead loop in
    chromatin() without changing its signature.

Module layout (R4 decomposition — pure re-export shim):
  The implementation lives in two `_`-prefixed sibling modules. This module
  re-exports their full surface so every name historically importable from
  ``imageGen.primitives.nucleic_acids`` stays importable here unchanged.
    - ``_dna`` — shared `DEFAULT_STYLE` + helix geometry helpers, plus
      `dna_segment`, `gene_helix`, and the `_broken_dna_segment` helper.
    - ``_rna`` — `rna_segment`, `rna_helix`, `mrna_helix`, `primer_helix`,
      `chromatin`.
"""
from __future__ import annotations

from imageGen.primitives._dna import (
    DEFAULT_STYLE,
    _add_strand_polyline,
    _axis_frame,
    _broken_dna_segment,
    _complement,
    _rung_color,
    _sample_strand_on_path,
    _supercoiled_axis,
    dna_segment,
    gene_helix,
)
from imageGen.primitives._rna import (
    chromatin,
    mrna_helix,
    primer_helix,
    rna_helix,
    rna_segment,
)

__all__ = [
    "DEFAULT_STYLE",
    "dna_segment",
    "rna_segment",
    "gene_helix",
    "rna_helix",
    "mrna_helix",
    "primer_helix",
    "chromatin",
]
