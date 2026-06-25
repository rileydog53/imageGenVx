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

import math
import re
import xml.etree.ElementTree as ET
from typing import Literal

MoleculeStyle = Literal["skeletal", "ball_stick"]

import svgwrite
import svgwrite.base
import svgwrite.container
import svgwrite.text

from rdkit import Chem
from rdkit.Chem import rdDepictor
from rdkit.Chem.Draw import rdMolDraw2D
from rdkit.Geometry import Point3D

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

# Heteroatoms that carry a lone pair an arrow-pushing curly can originate from.
_LONE_PAIR_ELEMENTS = {7, 8, 16}  # N, O, S


def _bond_and_lone_pair_anchors(
    mol: "Chem.Mol",
    atom_coords: dict[int, tuple[float, float]],
    map_to_idx: dict[int, int],
    anchor_names: dict[int, str] | None,
) -> dict[str, tuple[float, float]]:
    """Bond-midpoint and lone-pair anchors for arrow-pushing (P7.2 / MF-2).

    An arrow-pushing curly arrow originates at a *bond* (a C=O π bond) or a *lone
    pair*, not only an atom centre. This publishes, in the same local frame as the
    atom anchors:

    * ``bond{lo}_{hi}`` — the midpoint of every bond, keyed by its sorted atom
      indices (always available, the bond analogue of ``atom{idx}``); plus
      ``bond_a{m1}_a{m2}`` / ``bond_{name1}_{name2}`` aliases (both orderings) for
      bonds whose endpoints are atom-mapped / human-named.
    * ``lp{idx}`` — one representative lone-pair point per N/O/S, offset outward
      from the atom along the direction away from its bonded neighbours (where a
      lone pair sits); plus ``lp_a{map}`` / ``lp_{name}`` aliases.

    Args:
        mol: the RDKit molecule (post-render; bonds + atomic numbers intact).
        atom_coords: ``{atom_idx: (x, y)}`` already in the placed local frame.
        map_to_idx: ``{atom_map_number: atom_idx}`` captured before map-clearing.
        anchor_names: optional ``{map_number: human_name}`` alias map.

    Returns:
        ``{anchor_name: (x, y)}`` to merge into the molecule's anchor dict.
    """
    idx_to_map = {idx: m for m, idx in map_to_idx.items()}
    idx_to_name: dict[int, str] = {}
    if anchor_names:
        for m, nm in anchor_names.items():
            if m in map_to_idx:
                idx_to_name[map_to_idx[m]] = nm
    out: dict[str, tuple[float, float]] = {}

    for bond in mol.GetBonds():
        i, j = bond.GetBeginAtomIdx(), bond.GetEndAtomIdx()
        (xi, yi), (xj, yj) = atom_coords[i], atom_coords[j]
        mid = ((xi + xj) / 2.0, (yi + yj) / 2.0)
        lo, hi = sorted((i, j))
        out[f"bond{lo}_{hi}"] = mid
        for a, b in ((i, j), (j, i)):  # both orderings so either is addressable
            if a in idx_to_map and b in idx_to_map:
                out[f"bond_a{idx_to_map[a]}_a{idx_to_map[b]}"] = mid
            if a in idx_to_name and b in idx_to_name:
                out[f"bond_{idx_to_name[a]}_{idx_to_name[b]}"] = mid

    for atom in mol.GetAtoms():
        if atom.GetAtomicNum() not in _LONE_PAIR_ELEMENTS:
            continue
        idx = atom.GetIdx()
        ax, ay = atom_coords[idx]
        nbrs = [atom_coords[n.GetIdx()] for n in atom.GetNeighbors()]
        if nbrs:
            sx = sum(nx - ax for nx, _ny in nbrs)
            sy = sum(ny - ay for _nx, ny in nbrs)
            mag = math.hypot(sx, sy) or 1.0
            ux, uy = -sx / mag, -sy / mag  # outward: away from the neighbours
            off = 0.5 * (min(math.hypot(nx - ax, ny - ay) for nx, ny in nbrs) or 12.0)
        else:
            ux, uy, off = 0.0, -1.0, 12.0
        lp = (ax + ux * off, ay + uy * off)
        out[f"lp{idx}"] = lp
        if idx in idx_to_map:
            out[f"lp_a{idx_to_map[idx]}"] = lp
        if idx in idx_to_name:
            out[f"lp_{idx_to_name[idx]}"] = lp
    return out


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
    fixed_bond_px: float | None = None,
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
    if fixed_bond_px is not None:
        # P-sizing: pin the drawn bond length so every molecule shares one scale
        # (content-aware sizing — the box is derived from the molecule, not the
        # molecule squeezed into a fixed box). Default None keeps the historic
        # fill-the-box behaviour for leaf/panel callers byte-identical.
        opts.fixedBondLength = float(fixed_bond_px)

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
    fixed_bond_px: float | None = None,
) -> tuple[svgwrite.container.Group, dict[int, tuple[float, float]]]:
    """Like :func:`_inline_molecule`, but also return ``{atom_idx: (x, y)}``.

    The atom coords are shifted by *translate* so they describe positions in the
    frame of whatever places this Group's origin — matching how the Group's own
    ``translate(...)`` transform shifts the rendered atoms. Keeps the SVG-build
    body in one place: same restyle + width/height/viewBox handling as
    ``_inline_molecule``.
    """
    raw_svg, atom_coords = _rdkit_mol_to_svg_and_coords(
        mol, size, style_name, style, fixed_bond_px=fixed_bond_px)
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


def _natural_box(
    mol: "Chem.Mol", target_bond_px: float, pad: float
) -> tuple[int, int]:
    """Pixel ``(w, h)`` that renders *mol* at ~``target_bond_px`` bond length.

    Computes a 2D depiction with RDKit's default algorithm (the same one
    ``DrawMolecule`` would use, so leaf/panel renders are unaffected) and scales
    the conformer bbox by ``target_bond_px / median-bond`` — so the box is sized
    to the MOLECULE rather than the molecule squeezed into a fixed box. This is
    what gives every molecule in a figure one consistent bond scale.
    """
    if mol.GetNumConformers() == 0:
        rdDepictor.Compute2DCoords(mol)
    conf = mol.GetConformer()
    n = mol.GetNumAtoms()
    if n == 0:
        side = max(int(round(2.0 * pad)), 1)
        return side, side
    xs = [conf.GetAtomPosition(i).x for i in range(n)]
    ys = [conf.GetAtomPosition(i).y for i in range(n)]
    bonds = [
        math.hypot(conf.GetAtomPosition(b.GetBeginAtomIdx()).x
                   - conf.GetAtomPosition(b.GetEndAtomIdx()).x,
                   conf.GetAtomPosition(b.GetBeginAtomIdx()).y
                   - conf.GetAtomPosition(b.GetEndAtomIdx()).y)
        for b in mol.GetBonds()
    ]
    median = sorted(bonds)[len(bonds) // 2] if bonds else 1.5
    ppu = target_bond_px / (median or 1.5)
    w = (max(xs) - min(xs)) * ppu + 2.0 * pad
    h = (max(ys) - min(ys)) * ppu + 2.0 * pad
    floor = int(round(2.0 * pad))
    return max(int(round(w)), floor), max(int(round(h)), floor)


def molecule_natural_size(
    smiles: str, target_bond_px: float, pad: float = 16.0,
    *,
    orient_to: str | None = None,
    orient_direction: str | None = None,
    orient_reflect: bool = False,
    orient_deadband_deg: float = 30.0,
    anchor_names: dict[int, str] | None = None,
) -> tuple[int, int]:
    """The ``(w, h)`` pixel box a SMILES occupies rendered at ``target_bond_px``
    bond length — the pre-render size predictor the tier solver needs before it
    places a molecule slot. Matches the box :func:`render_molecule_anchored` uses
    internally for the same ``target_bond_px`` (both call :func:`_natural_box`).

    D6: when the same ``orient_*`` arguments the renderer will use are supplied,
    the predictor orients its (independent, but deterministic and identical) pose
    too, so the predicted box matches the box the rotated molecule will actually
    occupy — otherwise a rotated-to-tall molecule would be sized as if still
    wide. The rotation is deterministic, so predictor and renderer agree."""
    mol = _smiles_to_mol(smiles)
    if orient_to is not None and orient_direction is not None:
        _orient_conformer(
            mol, orient_to, orient_direction, anchor_names,
            reflect=orient_reflect, deadband_deg=orient_deadband_deg,
        )
    return _natural_box(mol, target_bond_px, pad)


# ---------------------------------------------------------------------------
# D6 -- directional orientation (pub-grade dim 3)
# ---------------------------------------------------------------------------
#
# RDKit lays a molecule out in its own canonical pose; nothing aims a chosen
# atom in a chosen direction. For a mechanism to read left-to-right the attacked
# atom (the electrophile a SceneEdge.to_anchor names) should face the partner
# residue (the side a Slot is Attach'd to). ``_orient_conformer`` rigidly rotates
# the shared conformer about its centroid so that atom points the requested way,
# BEFORE the box is measured and the molecule is drawn -- so the drawn depiction
# and every published anchor move together (they all derive from this one
# conformer). The transform is rigid (rotation/reflection only), so bond lengths
# and angles are untouched. Callers gate this to the V3 tier path
# (``target_bond_px`` set); the leaf/panel path never orients, so it stays
# byte-identical. See ``D6_ORIENTATION_SCOPE.md``.

# Desired direction -> angle in the RDKit conformer frame (y points UP). The SVG
# drawer flips y for display, so conf +y renders at the TOP of the image: 'up'
# maps to +pi/2 here and the atom lands at the top of the drawn group.
_DIRECTION_ANGLE: dict[str, float] = {
    "right": 0.0,
    "up": math.pi / 2.0,
    "left": math.pi,
    "down": -math.pi / 2.0,
}


def _resolve_atom_index(
    token: str,
    map_to_idx: dict[int, int],
    anchor_names: dict[int, str] | None,
) -> int | None:
    """Resolve an anchor token (the atom part of a 'slot.anchor' ref) to an RDKit
    atom index, or ``None`` if it does not name a single atom.

    Handles the forms :func:`render_molecule_anchored` publishes: a human name
    from *anchor_names* (e.g. ``'carbonyl_C'``), an atom-map alias (``'a1'``), a
    raw index (``'atom5'``), and the lone-pair / bond aliases (``'lp_a1'``,
    ``'bond_a1_a2'``) by falling back to their first atom -- so an edge that
    targets a bond or lone pair still yields an atom to aim.
    """
    if not token:
        return None
    if anchor_names:
        for mnum, name in anchor_names.items():
            if name == token and mnum in map_to_idx:
                return map_to_idx[mnum]
    if token.startswith("atom") and token[4:].isdigit():
        return int(token[4:])
    if token.startswith("a") and token[1:].isdigit():
        return map_to_idx.get(int(token[1:]))
    if token.startswith("lp_"):
        return _resolve_atom_index(token[3:], map_to_idx, anchor_names)
    if token.startswith("lp") and token[2:].isdigit():
        return int(token[2:])
    if token.startswith("bond_"):
        first = token[len("bond_"):].split("_", 1)[0]
        return _resolve_atom_index(first, map_to_idx, anchor_names)
    return None


def _orient_conformer(
    mol: "Chem.Mol",
    orient_to: str,
    direction: str,
    anchor_names: dict[int, str] | None = None,
    *,
    reflect: bool = False,
    deadband_deg: float = 30.0,
) -> None:
    """Rigidly rotate *mol*'s 2D conformer so atom *orient_to* faces *direction*.

    In-place and no-op-safe: if the molecule is empty, the direction is unknown,
    the target can't be resolved or sits at the centroid, or the needed rotation
    is within *deadband_deg* of the current pose (and no reflection is asked
    for), the conformer is left exactly as RDKit laid it out -- so an
    already-aligned molecule stays byte-stable. Rotation is rigid (about the atom
    centroid) so geometry is preserved. Must run before the bbox is measured and
    before the molecule is drawn.
    """
    if direction not in _DIRECTION_ANGLE:
        return
    n = mol.GetNumAtoms()
    if n == 0:
        return
    map_to_idx = {
        a.GetAtomMapNum(): a.GetIdx() for a in mol.GetAtoms() if a.GetAtomMapNum()
    }
    idx = _resolve_atom_index(orient_to, map_to_idx, anchor_names)
    if idx is None or idx >= n:
        return
    if mol.GetNumConformers() == 0:
        rdDepictor.Compute2DCoords(mol)
    conf = mol.GetConformer()
    cx = sum(conf.GetAtomPosition(i).x for i in range(n)) / n
    cy = sum(conf.GetAtomPosition(i).y for i in range(n)) / n
    # coords relative to centroid, optionally mirrored across the vertical axis
    pts = []
    for i in range(n):
        p = conf.GetAtomPosition(i)
        x = -(p.x - cx) if reflect else (p.x - cx)
        pts.append((x, p.y - cy, p.z))
    tx, ty, _ = pts[idx]
    if math.hypot(tx, ty) < 1e-9:
        return
    theta = _DIRECTION_ANGLE[direction] - math.atan2(ty, tx)
    theta = (theta + math.pi) % (2.0 * math.pi) - math.pi  # normalize to (-pi, pi]
    if not reflect and abs(theta) <= math.radians(deadband_deg):
        return  # already close enough; leave the canonical pose untouched
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    for i, (x, y, z) in enumerate(pts):
        conf.SetAtomPosition(
            i, Point3D(x * cos_t - y * sin_t + cx, x * sin_t + y * cos_t + cy, z)
        )


def render_molecule_anchored(
    smiles: str,
    size: tuple[int, int] = (200, 150),
    style: MoleculeStyle = "skeletal",
    style_dict: dict | None = None,
    center: tuple[float, float] | None = None,
    anchor_names: dict[int, str] | None = None,
    *,
    open_valence: bool = False,
    attach_anchor: str = "attach",
    target_bond_px: float | None = None,
    size_pad: float = 16.0,
    orient_to: str | None = None,
    orient_direction: str | None = None,
    orient_reflect: bool = False,
    orient_deadband_deg: float = 30.0,
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
        - ``attach_anchor`` (default ``"attach"``) — only under *open_valence*,
          the dangling-bond attachment point (see below); ``"{attach_anchor}{n}"``
          when more than one dummy atom is present.
        - ``"bond{lo}_{hi}"`` (atom-index midpoint of every bond) plus
          ``"bond_a{m1}_a{m2}"`` / ``"bond_{name1}_{name2}"`` aliases, and
          ``"lp{idx}"`` / ``"lp_a{map}"`` / ``"lp_{name}"`` lone-pair points on
          N/O/S — so an arrow-pushing curly arrow (P7.2 / MF-2) can originate at a
          bond (a C=O π) or a lone pair, not only an atom centre.

    Args:
        smiles: SMILES; may carry atom-map numbers to name anchors.
        size: (width, height) bbox in pixels.
        style: 'skeletal' (default) or 'ball_stick'.
        style_dict: Optional preset overlay; merged onto DEFAULT_STYLE.
        center: Optional (x, y) bbox-center placement, as in render_molecule; the
            returned anchors include the same translate so they stay correct.
        anchor_names: Optional ``{atom_map_number: human_name}`` alias map.
        open_valence: When True (residue / fragment rendering), each dummy atom
            (``'*'``, atomic number 0) is drawn as an *open valence* — its label
            is blanked so the bond to it renders as a dangling stub instead of a
            literal ``'*'`` glyph — and its position is published as the
            attachment anchor. Default False keeps every existing depiction
            byte-identical.
        attach_anchor: Anchor name for the open-valence attachment point.

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

    # Capture the atom-map -> index mapping, then clear the map numbers so they
    # don't render as "C:1" labels. Indices are unaffected by clearing, so the
    # coords (keyed by index) stay atom-precise.
    map_to_idx = {
        a.GetAtomMapNum(): a.GetIdx()
        for a in mol.GetAtoms()
        if a.GetAtomMapNum()
    }
    # D6: orient so the requested atom faces the requested direction. Runs while
    # the atom-map numbers are still present (they let _orient_conformer resolve
    # an 'a{n}' / named target) and BEFORE _natural_box measures the box, so the
    # rotated bbox, the drawn depiction, and the published anchors all derive from
    # this one transformed conformer. Tier path only -- the target_bond_px=None
    # leaf/panel path skips this and stays byte-identical.
    if (target_bond_px is not None and orient_to is not None
            and orient_direction is not None):
        _orient_conformer(
            mol, orient_to, orient_direction, anchor_names,
            reflect=orient_reflect, deadband_deg=orient_deadband_deg,
        )
    # P7.1: open-valence (residue) rendering. A dummy atom marks where a side
    # chain joins the rest of the protein; blanking its label makes the bond to
    # it render as a dangling stub (an open valence) rather than a '*' glyph —
    # the convention for a residue "entering the frame" — while its draw-coord is
    # still published below as the attachment anchor an H-bond / covalent
    # SceneEdge binds to.
    dummy_indices: list[int] = []
    if open_valence:
        for atom in mol.GetAtoms():
            if atom.GetAtomicNum() == 0:
                atom.SetProp("atomLabel", "")
                dummy_indices.append(atom.GetIdx())
    for atom in mol.GetAtoms():
        atom.SetAtomMapNum(0)

    # Content-aware sizing: when target_bond_px is set, derive the box from the
    # molecule so every structure in a figure renders at one bond scale (the
    # 2D-coord conformer computed here is reused by the draw — no re-layout). When
    # None, keep the caller's fixed box → leaf/panel renders byte-identical.
    if target_bond_px is not None:
        size = _natural_box(mol, target_bond_px, size_pad)
    width, height = size
    if center is not None:
        cx, cy = center
        translate = (cx - width / 2.0, cy - height / 2.0)
    else:
        translate = (0.0, 0.0)

    group, atom_coords = _inline_molecule_anchored(
        mol, size, style, merged_style, translate=translate,
        fixed_bond_px=target_bond_px,
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
    if len(dummy_indices) == 1:
        anchors[attach_anchor] = atom_coords[dummy_indices[0]]
    else:
        for n, idx in enumerate(dummy_indices):
            anchors[f"{attach_anchor}{n}"] = atom_coords[idx]
    # P7.2 (MF-2): bond-midpoint + lone-pair anchors so a curly arrow can
    # originate at a bond or a lone pair, not only an atom centre.
    anchors.update(
        _bond_and_lone_pair_anchors(mol, atom_coords, map_to_idx, anchor_names))
    return AnchoredGroup(group=group, anchors=anchors)


# Common active-site residue side chains by name -> SMILES, each carrying a
# dummy attachment atom ('*', the open valence onto the backbone) and the
# catalytic/reactive atom mapped ':1' (so it resolves to the ``a1`` anchor).
# Extend by adding an entry; the RESIDUE slot path picks it up automatically.
_RESIDUE_SMILES: dict[str, str] = {
    "ser":    "*C[O:1]",            # serine: nucleophilic hydroxyl O
    "ser530": "*C[O:1]",            # COX-1 catalytic serine (aspirin's target)
    "his":    "*Cc1c[nH]c[n:1]1",   # histidine: basic imidazole N
    "his513": "*Cc1c[nH]c[n:1]1",   # COX-1 active-site histidine
    "tyr":    "*Cc1ccc([O:1])cc1",  # tyrosine: phenol O
    "cys":    "*C[S:1]",            # cysteine: thiol S
    "lys":    "*CCCC[N:1]",         # lysine: epsilon-amino N
}


def render_residue_anchored(
    residue: str,
    size: tuple[int, int] = (160, 120),
    style: MoleculeStyle = "skeletal",
    style_dict: dict | None = None,
    center: tuple[float, float] | None = None,
    anchor_names: dict[int, str] | None = None,
    attach_anchor: str = "attach",
    target_bond_px: float | None = None,
    size_pad: float = 16.0,
    orient_to: str | None = None,
    orient_direction: str | None = None,
    orient_reflect: bool = False,
    orient_deadband_deg: float = 30.0,
) -> AnchoredGroup:
    """Render an amino-acid side chain as a real molecular fragment (MF-1).

    A residue is just a molecule with an open valence, so it renders through the
    SAME :func:`render_molecule_anchored` path as any other structure — coloured
    atom *letters*, never bespoke dots — so a figure mixing a ligand and a
    residue reads with one chemistry convention. The fragment "enters the frame"
    with a dangling bond at its backbone attachment (a dummy ``'*'`` atom whose
    glyph is suppressed); that point is published as ``attach_anchor`` and the
    reactive atom (atom-map ``:1``) as ``a1`` / via *anchor_names*, so H-bond or
    covalent ``SceneEdge``s can bind both ends.

    Args:
        residue: a known residue name (``_RESIDUE_SMILES``: ser/his/tyr/cys/lys,
            plus the COX-1 ``ser530``/``his513`` aliases) OR a raw SMILES carrying
            a dummy ``'*'`` attachment atom (e.g. ``"*C[O:1]"``).
        size, style, style_dict, center, anchor_names: as in
            :func:`render_molecule_anchored`.
        attach_anchor: anchor name for the backbone attachment point.

    Returns:
        AnchoredGroup with per-atom anchors, the mapped reactive atom(s), and the
        attachment anchor.

    Raises:
        ValueError: the SMILES (resolved or raw) does not parse, or it carries no
            dummy ``'*'`` attachment atom (a residue must declare where it joins
            the backbone — fail loud rather than render a capped fragment).
    """
    smiles = _RESIDUE_SMILES.get(residue, residue)
    ag = render_molecule_anchored(
        smiles, size=size, style=style, style_dict=style_dict, center=center,
        anchor_names=anchor_names, open_valence=True, attach_anchor=attach_anchor,
        target_bond_px=target_bond_px, size_pad=size_pad,
        orient_to=orient_to, orient_direction=orient_direction,
        orient_reflect=orient_reflect, orient_deadband_deg=orient_deadband_deg,
    )
    if not any(k == attach_anchor or k.startswith(attach_anchor) for k in ag.anchors):
        raise ValueError(
            f"residue {residue!r} has no open-valence attachment atom; include a "
            "dummy '*' atom in the SMILES to mark where it joins the backbone "
            "(e.g. '*C[O:1]')"
        )
    return ag


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
