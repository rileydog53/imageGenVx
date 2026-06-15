"""Chemistry primitives for scientific figure generation.

Visual conventions followed here:
- Molecules are 2D depictions produced by RDKit's MolDraw2DSVG renderer, then
  re-styled to match the active preset's atom palette and bond stroke. Two
  styles are supported: 'skeletal' (the standard line-angle representation) and
  'ball_stick' (still 2D -- larger atom labels and wider bonds; true 3D
  ball-and-stick is out of scope for v1).
- Reactions read left-to-right: reactants joined by "+" glyphs, then a
  reaction arrow with optional `conditions={"above": ..., "below": ...}` text,
  then products. Per-block width is fixed so layout is predictable; auto-bbox
  packing is deferred to Phase 6.
- Functional groups (carboxyl, amine, phosphate, ...) render as small molecule
  callouts with the group name labeled below.

Overlay composability:
  Every public function returns an svgwrite.container.Group whose underlying
  SVG has a transparent background and overflow="visible". This means the
  caller can drop the Group on top of any other primitive (e.g. a ligand
  Group placed at a receptor()'s binding site for a docking schematic) and
  the underlying primitive remains visible at non-atom pixels. Z-order is
  the caller's responsibility -- Groups added later to a Drawing render on top:

      dwg.add(receptor_group)
      dwg.add(render_molecule("CCO", center=binding_site_xy))

Phase 3 coupling:
  Layout code positions a molecule by either passing `center=(x,y)` to
  render_molecule (the molecule's bounding-box center is anchored there), or
  by wrapping the returned Group in a translate transform. No anchor protocol
  is needed -- chemistry primitives are point-anchored, not curve-anchored.

Phase 4 assumption:
  DEFAULT_STYLE uses flat namespaced keys (chem_*, label_*) so the master
  preset can union all primitive modules without collision.

RDKit re-styling strategy:
  Two layers of style enforcement, in order. (1) Pre-render via drawOptions:
  updateAtomPalette() sets per-element atom colors, bondLineWidth sets stroke
  width, clearBackground=False makes the SVG transparent. (2) Post-pass
  _restyle_rdkit_svg() walks the parsed SVG and rewrites the stroke color of
  any element with a "bond-" CSS class to chem_bond_stroke -- RDKit derives
  bond color from atom-endpoint colors and has no direct bond-color option,
  so this defensive pass is required for bonds to honor the preset.

Module layout (R3 decomposition — pure re-export shim):
  The implementation lives in two `_`-prefixed sibling modules. This module
  re-exports their full surface so every name historically importable from
  ``imageGen.primitives.chemistry`` stays importable here unchanged.
    - ``_mol_render`` — RDKit ingest/style + molecule callouts
      (`render_molecule`, `render_molecule_anchored`, `render_functional_group`).
    - ``_reaction_render`` — reaction arrows/conditions + scheme layout
      (`render_reaction`, `render_multistep_reaction`).
"""
from __future__ import annotations

from imageGen.primitives._mol_render import (
    DEFAULT_STYLE,
    MoleculeStyle,
    _ELEMENT_TO_ATOMIC_NUM,
    _FUNCTIONAL_GROUPS,
    _RESIDUE_SMILES,
    _RawSVGElement,
    _STROKE_IN_STYLE_RE,
    _XMLNS_RE,
    _hex_to_rgb01,
    _inline_molecule,
    _inline_molecule_anchored,
    _rdkit_mol_to_svg,
    _rdkit_mol_to_svg_and_coords,
    _restyle_rdkit_svg,
    _smiles_to_mol,
    molecule_natural_size,
    render_functional_group,
    render_molecule,
    render_molecule_anchored,
    render_residue_anchored,
)
from imageGen.primitives._reaction_render import (
    _arrow,
    _emit_conditions,
    _reversible_arrow,
    _wrap_conditions,
    render_multistep_reaction,
    render_reaction,
)

__all__ = [
    "DEFAULT_STYLE",
    "MoleculeStyle",
    "render_molecule",
    "render_molecule_anchored",
    "render_residue_anchored",
    "molecule_natural_size",
    "render_reaction",
    "render_multistep_reaction",
    "render_functional_group",
]
