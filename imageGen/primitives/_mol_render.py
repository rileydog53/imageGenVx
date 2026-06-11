"""Molecule rendering: RDKit ingest, preset re-styling, and molecule callouts.

Internals of :mod:`imageGen.primitives.chemistry` (R3 split). Holds the RDKit
depiction pipeline (`_rdkit_mol_to_svg*`, `_restyle_rdkit_svg`, `_inline_molecule*`)
and the molecule-level public API (`render_molecule`, `render_molecule_anchored`,
`render_functional_group`). The reaction-scheme layer lives in the sibling
``_reaction_render`` module, which imports `DEFAULT_STYLE`, `_smiles_to_mol`, and
`_inline_molecule` from here.

RDKit re-styling strategy:
  Two layers of style enforcement, in order. (1) Pre-render via drawOptions:
  updateAtomPalette() sets per-element atom colors, bondLineWidth sets stroke
  width, clearBackground=False makes the SVG transparent. (2) Post-pass
  _restyle_rdkit_svg() walks the parsed SVG and rewrites the stroke color of
  any element with a "bond-" CSS class to chem_bond_stroke -- RDKit derives
  bond color from atom-endpoint colors and has no direct bond-color option,
  so this defensive pass is required for bonds to honor the preset.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Literal

MoleculeStyle = Literal["skeletal", "ball_stick"]

import svgwrite
import svgwrite.base
import svgwrite.container
import svgwrite.text

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

from imageGen.primitives._anchors import AnchoredGroup


# ---------------------------------------------------------------------------
# Style defaults -- flat namespaced keys for Phase 4 preset union
# ---------------------------------------------------------------------------

DEFAULT_STYLE: dict[str, object] = {
    # Atom label colors (per element). Keys map to atomic numbers in
    # _rdkit_mol_to_svg via _ELEMENT_TO_ATOMIC_NUM.
    "chem_atom_C":                  "#1A1A1A",   # carbon: near-black
    "chem_atom_N":                  "#1565C0",   # nitrogen: blue
    "chem_atom_O":                  "#C62828",   # oxygen: red
    "chem_atom_P":                  "#EF6C00",   # phosphorus: orange
    "chem_atom_S":                  "#F9A825",   # sulfur: yellow
    "chem_atom_font_scale":          1.0,        # multiplier on RDKit's baseFontSize
    # Bonds
    "chem_bond_stroke":             "#1A1A1A",   # bond line color (post-pass restyle)
    "chem_bond_stroke_width":        2.0,
    # Reaction layout
    "chem_reaction_arrow_length":   60.0,
    "chem_reaction_arrow_stroke":   "#1A1A1A",
    "chem_reaction_arrow_stroke_width": 1.5,
    "chem_reaction_arrow_head_size": 8.0,
    "chem_reaction_gap":            12.0,        # px gap between blocks and arrow
    "chem_reaction_plus_font_size":  18,
    "chem_reaction_plus_color":     "#1A1A1A",
    "chem_conditions_font_size":     11,
    "chem_conditions_color":        "#1A1A1A",
    "chem_conditions_offset":        6.0,        # vertical offset above/below arrow
    "chem_reaction_reversible_gap":  5.0,        # V2/R2: px between forward/backward half-arrows
    # Functional group callouts
    "chem_fg_label_font_size":       10,
    "chem_fg_label_color":          "#37474F",
    "chem_fg_label_offset":          6.0,        # px below molecule bbox
    # Shared label
    "label_font_family":            "Helvetica, Arial, sans-serif",
    "label_font_size":               11,
    "label_font_color":             "#1A1A1A",
}


# Element symbol → atomic number, for updateAtomPalette
_ELEMENT_TO_ATOMIC_NUM: dict[str, int] = {
    "C": 6, "N": 7, "O": 8, "P": 15, "S": 16,
}


# Common functional groups by name → SMILES. Extend by adding entries here;
# public API surfaces are unchanged.
_FUNCTIONAL_GROUPS: dict[str, str] = {
    "carboxyl":  "C(=O)O",
    "amine":     "N",
    "phosphate": "OP(=O)(O)O",
    "hydroxyl":  "O",
    "methyl":    "C",
    "aldehyde":  "C=O",
    "ester":     "C(=O)OC",
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

class _RawSVGElement(svgwrite.base.BaseElement):
    """svgwrite element adapter that emits a pre-built ElementTree node verbatim.

    svgwrite serializes children by calling get_xml(); returning a parsed XML
    node directly inlines an externally-rendered SVG fragment (here: RDKit's
    output) inside an svgwrite Group without a string round-trip.
    """

    elementname = "svg"

    def __init__(self, etree_node: ET.Element, **kwargs):
        super().__init__(**kwargs)
        self._etree_node = etree_node

    def get_xml(self) -> ET.Element:  # type: ignore[override]
        return self._etree_node


def _hex_to_rgb01(hex_color: str) -> tuple[float, float, float]:
    """Convert '#RRGGBB' to (r, g, b) in 0..1 -- the form RDKit expects."""
    h = hex_color.lstrip("#")
    return (int(h[0:2], 16) / 255.0, int(h[2:4], 16) / 255.0, int(h[4:6], 16) / 255.0)


def _smiles_to_mol(smiles: str) -> Chem.Mol:
    """Parse SMILES; raise ValueError with the offending input on failure."""
    mol = Chem.MolFromSmiles(smiles)
    if mol is None:
        raise ValueError(f"Invalid SMILES: {smiles!r}")
    return mol


def _rdkit_mol_to_svg_and_coords(
    mol: Chem.Mol,
    size: tuple[int, int],
    style_name: str,
    style: dict,
) -> tuple[str, dict[int, tuple[float, float]]]:
    """Render *mol* via MolDraw2DSVG; return (raw SVG, {atom_idx: (x, y)}).

    The coords are each atom's post-layout pixel position from
    ``drawer.GetDrawCoords(i)``. MolDraw2DSVG emits ``viewBox='0 0 W H'`` matching
    *size*, so those pixels map 1:1 onto the inlined ``<svg>``'s local frame —
    they are exactly where each atom renders inside the returned Group's local
    space. This is the source of truth for the V3 anchor protocol; the plain
    ``_rdkit_mol_to_svg`` below discards the coords for existing callers.

    style_name='ball_stick' uses larger labels and thicker bonds; both styles
    produce 2D depictions (MolDraw2DSVG is inherently 2D).
    """
    width, height = size
    drawer = rdMolDraw2D.MolDraw2DSVG(width, height)
    opts = drawer.drawOptions()
    opts.clearBackground = False  # transparent background -- enables overlay use

    bond_width = float(style["chem_bond_stroke_width"])
    if style_name == "ball_stick":
        bond_width *= 1.6
        opts.baseFontSize = 0.9 * float(style["chem_atom_font_scale"])
    else:
        opts.baseFontSize = 0.6 * float(style["chem_atom_font_scale"])
    opts.bondLineWidth = bond_width

    palette: dict[int, tuple[float, float, float]] = {}
    for symbol, atomic_num in _ELEMENT_TO_ATOMIC_NUM.items():
        palette[atomic_num] = _hex_to_rgb01(str(style[f"chem_atom_{symbol}"]))
    opts.updateAtomPalette(palette)

    drawer.DrawMolecule(mol)
    drawer.FinishDrawing()
    coords: dict[int, tuple[float, float]] = {}
    for i in range(mol.GetNumAtoms()):
        p = drawer.GetDrawCoords(i)
        coords[i] = (float(p.x), float(p.y))
    return drawer.GetDrawingText(), coords


def _rdkit_mol_to_svg(
    mol: Chem.Mol,
    size: tuple[int, int],
    style_name: str,
    style: dict,
) -> str:
    """Render *mol* via MolDraw2DSVG with preset-aware drawOptions. Returns raw SVG.

    Thin wrapper over :func:`_rdkit_mol_to_svg_and_coords` for the existing
    point-anchored callers that don't need atom coordinates.
    """
    return _rdkit_mol_to_svg_and_coords(mol, size, style_name, style)[0]


# Match `stroke:#xxxxxx` inside a style attribute (RDKit emits bond color this way)
_STROKE_IN_STYLE_RE = re.compile(r"stroke:#[0-9A-Fa-f]{6}")
_XMLNS_RE = re.compile(r"\sxmlns(:\w+)?='[^']*'")


def _restyle_rdkit_svg(svg_text: str, style: dict) -> ET.Element:
    """Parse RDKit's SVG; rewrite bond strokes to chem_bond_stroke; return root.

    RDKit has no direct bond-color option (bonds inherit from atom endpoints),
    so this post-pass walks all <path> elements whose `class` attribute marks
    them as bonds and rewrites the stroke color in their inline `style`.
    overflow='visible' is set on the root so atoms near the edge of *size*
    aren't clipped when the Group is composed against another primitive.
    """
    # RDKit declares xmlns by default; strip so element tags compare cleanly
    # without {http://...}path prefixes.
    svg_text = _XMLNS_RE.sub("", svg_text)
    root = ET.fromstring(svg_text)
    bond_replacement = f"stroke:{style['chem_bond_stroke']}"
    for elem in root.iter("path"):
        if "bond-" not in elem.get("class", ""):
            continue
        s = elem.get("style", "")
        if s:
            elem.set("style", _STROKE_IN_STYLE_RE.sub(bond_replacement, s))
    root.set("overflow", "visible")
    return root


def _inline_molecule(
    mol: Chem.Mol,
    size: tuple[int, int],
    style_name: str,
    style: dict,
    translate: tuple[float, float] = (0.0, 0.0),
) -> svgwrite.container.Group:
    """Render *mol* and wrap the SVG in a Group translated to *translate*."""
    raw_svg = _rdkit_mol_to_svg(mol, size, style_name, style)
    svg_root = _restyle_rdkit_svg(raw_svg, style)
    width, height = size
    # Set explicit width/height on the inlined <svg> so it positions as a
    # block at our local origin; viewBox is preserved from RDKit's output.
    svg_root.set("width", str(width))
    svg_root.set("height", str(height))
    svg_root.set("x", "0")
    svg_root.set("y", "0")
    tx, ty = translate
    group = svgwrite.container.Group(transform=f"translate({tx},{ty})")
    group.add(_RawSVGElement(svg_root))
    return group


def _inline_molecule_anchored(
    mol: Chem.Mol,
    size: tuple[int, int],
    style_name: str,
    style: dict,
    translate: tuple[float, float] = (0.0, 0.0),
) -> tuple[svgwrite.container.Group, dict[int, tuple[float, float]]]:
    """Like :func:`_inline_molecule`, but also return ``{atom_idx: (x, y)}``.

    The atom coords are shifted by *translate* so they describe positions in the
    frame of whatever places this Group's origin — matching how the Group's own
    ``translate(...)`` transform shifts the rendered atoms. Keeps the SVG-build
    body in one place: same restyle + width/height/viewBox handling as
    ``_inline_molecule``.
    """
    raw_svg, atom_coords = _rdkit_mol_to_svg_and_coords(mol, size, style_name, style)
    svg_root = _restyle_rdkit_svg(raw_svg, style)
    width, height = size
    svg_root.set("width", str(width))
    svg_root.set("height", str(height))
    svg_root.set("x", "0")
    svg_root.set("y", "0")
    tx, ty = translate
    group = svgwrite.container.Group(transform=f"translate({tx},{ty})")
    group.add(_RawSVGElement(svg_root))
    shifted = {i: (x + tx, y + ty) for i, (x, y) in atom_coords.items()}
    return group, shifted


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def render_molecule(
    smiles: str,
    size: tuple[int, int] = (200, 150),
    style: MoleculeStyle = "skeletal",
    style_dict: dict | None = None,
    center: tuple[float, float] | None = None,
) -> svgwrite.container.Group:
    """Render a 2D molecular structure from SMILES.

    Args:
        smiles: SMILES string (e.g. 'CN1C=NC2=C1C(=O)N(C(=O)N2C)C' for caffeine).
        size: (width, height) of the molecule's bounding box in pixels.
        style: 'skeletal' (line-angle, default) or 'ball_stick' (larger labels,
            thicker bonds; still 2D).
        style_dict: Optional preset overlay; merged onto DEFAULT_STYLE.
        center: Optional (x, y) at which the molecule's bbox center is placed.
            If None, the molecule's top-left sits at the Group's local origin.
            Provide a center to drop a ligand on top of a known anchor (e.g. a
            receptor binding site) without doing bbox math at the call site.

    Returns:
        An svgwrite.container.Group with a transparent background, suitable
        for overlay on any other primitive in the same Drawing.

    Raises:
        ValueError: SMILES does not parse, or *style* is unsupported.
    """
    if style not in ("skeletal", "ball_stick"):
        raise ValueError(f"Unknown style {style!r} (expected 'skeletal' or 'ball_stick')")
    merged_style = {**DEFAULT_STYLE, **(style_dict or {})}
    mol = _smiles_to_mol(smiles)
    width, height = size
    if center is not None:
        cx, cy = center
        translate = (cx - width / 2.0, cy - height / 2.0)
    else:
        translate = (0.0, 0.0)
    return _inline_molecule(mol, size, style, merged_style, translate=translate)


def render_molecule_anchored(
    smiles: str,
    size: tuple[int, int] = (200, 150),
    style: MoleculeStyle = "skeletal",
    style_dict: dict | None = None,
    center: tuple[float, float] | None = None,
    anchor_names: dict[int, str] | None = None,
) -> AnchoredGroup:
    """Render a molecule AND publish per-atom anchor points (V3 scene chassis).

    Same depiction as :func:`render_molecule`, but returns an
    :class:`~imageGen.primitives._anchors.AnchoredGroup` so the scene layer can
    draw bonds/curly-arrows that terminate on specific atoms (e.g. the carbonyl
    carbon a Ser530 hydroxyl attacks).

    Anchor naming, every atom gets:
        - ``"atom{idx}"`` — always, the RDKit atom index (debug / fallback).
        - ``"a{map}"`` — when the SMILES carries an atom-map number (``[O:1]`` →
          ``"a1"``); this is how an author addresses a specific atom.
        - the human name from *anchor_names* ``{map_num: name}`` — when given,
          an additional alias (``{1: "carbonyl_C"}`` → anchor ``"carbonyl_C"``).

    Args:
        smiles: SMILES; may carry atom-map numbers to name anchors.
        size: (width, height) bbox in pixels.
        style: 'skeletal' (default) or 'ball_stick'.
        style_dict: Optional preset overlay; merged onto DEFAULT_STYLE.
        center: Optional (x, y) bbox-center placement, as in render_molecule; the
            returned anchors include the same translate so they stay correct.
        anchor_names: Optional ``{atom_map_number: human_name}`` alias map.

    Returns:
        AnchoredGroup(group, anchors) — anchors in the Group's local frame.

    Raises:
        ValueError: SMILES does not parse, *style* is unsupported, or an
            *anchor_names* key has no matching atom-map number in the SMILES.
    """
    if style not in ("skeletal", "ball_stick"):
        raise ValueError(f"Unknown style {style!r} (expected 'skeletal' or 'ball_stick')")
    merged_style = {**DEFAULT_STYLE, **(style_dict or {})}
    mol = _smiles_to_mol(smiles)
    width, height = size
    if center is not None:
        cx, cy = center
        translate = (cx - width / 2.0, cy - height / 2.0)
    else:
        translate = (0.0, 0.0)

    # Capture the atom-map -> index mapping, then clear the map numbers so they
    # don't render as "C:1" labels. Indices are unaffected by clearing, so the
    # coords (keyed by index) stay atom-precise.
    map_to_idx = {
        a.GetAtomMapNum(): a.GetIdx()
        for a in mol.GetAtoms()
        if a.GetAtomMapNum()
    }
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)

    group, atom_coords = _inline_molecule_anchored(
        mol, size, style, merged_style, translate=translate
    )
    anchors: dict[str, tuple[float, float]] = {}
    for idx, xy in atom_coords.items():
        anchors[f"atom{idx}"] = xy
    for map_num, idx in map_to_idx.items():
        anchors[f"a{map_num}"] = atom_coords[idx]
    if anchor_names:
        for map_num, name in anchor_names.items():
            if map_num not in map_to_idx:
                raise ValueError(
                    f"anchor_names key {map_num} has no matching atom-map number "
                    f"in SMILES {smiles!r} (mapped numbers: {sorted(map_to_idx)})"
                )
            anchors[name] = atom_coords[map_to_idx[map_num]]
    return AnchoredGroup(group=group, anchors=anchors)


def render_functional_group(
    name: str,
    style_dict: dict | None = None,
    size: tuple[int, int] = (120, 90),
) -> svgwrite.container.Group:
    """Render a named functional group as a callout: molecule + label below.

    Args:
        name: Group name. Must be a key in _FUNCTIONAL_GROUPS (e.g. 'carboxyl',
            'amine', 'phosphate', 'hydroxyl', 'methyl', 'aldehyde', 'ester').
        style_dict: Optional preset overlay; merged onto DEFAULT_STYLE.
        size: (width, height) of the molecule portion of the callout.

    Returns:
        An svgwrite.container.Group with the molecule rendered at local origin
        and the group name labeled below.

    Raises:
        ValueError: *name* is not a known functional group.
    """
    if name not in _FUNCTIONAL_GROUPS:
        valid = ", ".join(sorted(_FUNCTIONAL_GROUPS))
        raise ValueError(f"Unknown functional group {name!r} (valid: {valid})")
    style = {**DEFAULT_STYLE, **(style_dict or {})}
    mol = _smiles_to_mol(_FUNCTIONAL_GROUPS[name])

    group = svgwrite.container.Group()
    group.add(_inline_molecule(mol, size, "skeletal", style, translate=(0.0, 0.0)))

    label_size = int(style["chem_fg_label_font_size"])
    width, height = size
    group.add(svgwrite.text.Text(
        name,
        insert=(width / 2.0, height + float(style["chem_fg_label_offset"]) + label_size),
        font_size=label_size, fill=str(style["chem_fg_label_color"]),
        font_family=str(style["label_font_family"]),
        text_anchor="middle",
    ))
    return group
