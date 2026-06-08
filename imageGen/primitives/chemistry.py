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
import svgwrite.shapes
import svgwrite.text

from rdkit import Chem
from rdkit.Chem.Draw import rdMolDraw2D

from imageGen.primitives._text import formula_text as _formula_text


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


def _rdkit_mol_to_svg(
    mol: Chem.Mol,
    size: tuple[int, int],
    style_name: str,
    style: dict,
) -> str:
    """Render *mol* via MolDraw2DSVG with preset-aware drawOptions. Returns raw SVG.

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
    return drawer.GetDrawingText()


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


def _arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    style: dict,
) -> list:
    """Return [line, head_polygon] svg elements for a reaction arrow start→end."""
    stroke = str(style["chem_reaction_arrow_stroke"])
    stroke_w = float(style["chem_reaction_arrow_stroke_width"])
    head_size = float(style["chem_reaction_arrow_head_size"])
    x0, y0 = start
    x1, y1 = end
    line = svgwrite.shapes.Line(
        start=(x0, y0), end=(x1, y1),
        stroke=stroke, stroke_width=stroke_w,
    )
    angle = math.atan2(y1 - y0, x1 - x0)
    base_x = x1 - head_size * math.cos(angle)
    base_y = y1 - head_size * math.sin(angle)
    perp_x = -math.sin(angle) * (head_size * 0.5)
    perp_y = math.cos(angle) * (head_size * 0.5)
    head = svgwrite.shapes.Polygon(
        points=[
            (round(x1, 2), round(y1, 2)),
            (round(base_x + perp_x, 2), round(base_y + perp_y, 2)),
            (round(base_x - perp_x, 2), round(base_y - perp_y, 2)),
        ],
        fill=stroke, stroke="none",
    )
    return [line, head]


def _reversible_arrow(
    start: tuple[float, float],
    end: tuple[float, float],
    style: dict,
) -> list:
    """Return svg elements for a reversible reaction: → on top, ← on bottom.

    The two half-arrows are displaced vertically by
    ``chem_reaction_reversible_gap`` (split evenly above/below the midline)
    so they read as a paired equilibrium symbol without overlapping.

    V2 / R2.
    """
    half = float(style.get("chem_reaction_reversible_gap", 5.0)) / 2.0
    x0, y0 = start
    x1, y1 = end
    # Forward (→): shifted up
    fwd = _arrow((x0, y0 - half), (x1, y1 - half), style)
    # Backward (←): shifted down, direction reversed
    bwd = _arrow((x1, y1 + half), (x0, y0 + half), style)
    return fwd + bwd


def _wrap_conditions(text: str, max_chars: int = 28) -> list[str]:
    """Split long condition strings at ', ' boundaries into ≤max_chars lines."""
    if len(text) <= max_chars:
        return [text]
    parts = text.split(", ")
    lines: list[str] = []
    current = ""
    for part in parts:
        candidate = f"{current}, {part}" if current else part
        if len(candidate) > max_chars and current:
            lines.append(current)
            current = part
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines or [text]


def _emit_conditions(
    group: svgwrite.container.Group,
    conditions: dict | None,
    above_lines: list[str],
    arrow_mid_x: float,
    y_mol_top: float,
    mol_h: float,
    style: dict,
) -> None:
    """Render above/below condition text centred on ``arrow_mid_x``.

    Shared by ``render_multistep_reaction``; the geometry matches the
    closure inside ``render_reaction`` so single- and multi-step schemes
    place conditions identically.
    """
    if not conditions:
        return
    cond_size = int(style["chem_conditions_font_size"])
    cond_offset = float(style["chem_conditions_offset"])
    line_gap = cond_size * 1.3

    def _ctext(text: str, y: float) -> svgwrite.text.Text:
        # Render chemical numeric subscripts (H2SO4 → H₂SO₄). Plain strings come
        # back as a byte-identical flat <text>, so non-formula conditions and
        # existing goldens are unchanged.
        return _formula_text(
            text,
            (arrow_mid_x, y),
            font_family=str(style["label_font_family"]),
            font_size=cond_size,
            fill=str(style["chem_conditions_color"]),
        )

    if above_lines:
        n = len(above_lines)
        for i, line in enumerate(above_lines):
            y = y_mol_top - cond_offset - line_gap * (n - 1 - i)
            group.add(_ctext(line, y))
    if conditions.get("below"):
        group.add(_ctext(
            str(conditions["below"]),
            y_mol_top + mol_h + cond_offset + cond_size,
        ))


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


def render_reaction(
    reactants_smiles: list[str],
    products_smiles: list[str],
    conditions: dict | None = None,
    style_dict: dict | None = None,
    molecule_size: tuple[int, int] = (140, 100),
    reversible: bool = False,
    stack: bool = False,
    stacked_row_gap: float = 24.0,
) -> svgwrite.container.Group:
    """Render a full reaction scheme: reactants + arrow (+ conditions) + products.

    Args:
        reactants_smiles: One SMILES per reactant; joined left-to-right with "+".
        products_smiles:  One SMILES per product; same layout, right of arrow.
        conditions: Optional {'above': str, 'below': str} -- either or both keys
            allowed. Text renders above/below the arrow centerline.
        style_dict: Optional preset overlay; merged onto DEFAULT_STYLE.
        molecule_size: Per-molecule bbox in pixels. Fixed (not auto-bbox) so
            arrow alignment is predictable.
        reversible: When True, draws a paired forward/backward equilibrium
            arrow instead of a single forward arrow (V2/R2).
        stack: When True, places the reactant block on row 1 and the
            arrow + product block on row 2 (V2/R1). Used when the horizontal
            extent of the reaction exceeds the available canvas width.
        stacked_row_gap: Vertical gap between molecule rows when stack=True.

    Returns:
        An svgwrite.container.Group containing the full reaction scheme,
        positioned with its top-left at the Group's local origin.

    Raises:
        ValueError: *reactants_smiles* or *products_smiles* is empty, or any
            SMILES fails to parse.
    """
    if not reactants_smiles:
        raise ValueError("reactants_smiles must contain at least one SMILES")
    if not products_smiles:
        raise ValueError("products_smiles must contain at least one SMILES")
    style = {**DEFAULT_STYLE, **(style_dict or {})}
    mol_w, mol_h = molecule_size
    gap = float(style["chem_reaction_gap"])
    arrow_len = float(style["chem_reaction_arrow_length"])
    plus_size = int(style["chem_reaction_plus_font_size"])
    plus_color = str(style["chem_reaction_plus_color"])
    cond_size = int(style["chem_conditions_font_size"])
    cond_offset = float(style["chem_conditions_offset"])
    line_gap = cond_size * 1.3  # leading between wrapped lines
    arrow_fn = _reversible_arrow if reversible else _arrow

    # Pre-compute above-condition lines so we know how much top padding is needed
    # before placing molecules.  All molecule/arrow y-coords shift down by top_pad
    # so the "above" text sits in positive SVG space and is never clipped.
    above_lines: list[str] = []
    if conditions and conditions.get("above"):
        above_lines = _wrap_conditions(str(conditions["above"]))
    top_pad = (len(above_lines) * line_gap + cond_offset) if above_lines else 0.0

    group = svgwrite.container.Group()

    def _place_block_at(smiles_list: list[str], cursor: float, y_top: float) -> float:
        """Place molecules in a horizontal block starting at (cursor, y_top).

        Returns the cursor x-position after the last molecule.
        """
        y_mid = y_top + mol_h / 2.0
        for i, smi in enumerate(smiles_list):
            mol = _smiles_to_mol(smi)
            group.add(_inline_molecule(mol, (mol_w, mol_h), "skeletal", style,
                                       translate=(cursor, y_top)))
            cursor += mol_w
            if i < len(smiles_list) - 1:
                cursor += gap
                group.add(svgwrite.text.Text(
                    "+",
                    insert=(cursor + plus_size * 0.3, y_mid + plus_size * 0.35),
                    font_size=plus_size, fill=plus_color,
                    font_family=str(style["label_font_family"]),
                ))
                cursor += plus_size + gap
        return cursor

    def _render_conditions_at(arrow_mid_x: float, y_mol_top: float) -> None:
        """Render above/below condition text centred on arrow_mid_x.

        Thin wrapper over the shared ``_emit_conditions`` so single- and
        multi-step schemes place conditions identically.
        """
        _emit_conditions(
            group, conditions, above_lines, arrow_mid_x, y_mol_top, mol_h, style,
        )

    if not stack:
        # ---- Original horizontal layout ----
        mol_top = top_pad
        midline_y = mol_top + mol_h / 2.0
        cursor = _place_block_at(reactants_smiles, 0.0, mol_top) + gap
        arrow_start = (cursor, midline_y)
        arrow_end = (cursor + arrow_len, midline_y)
        for elem in arrow_fn(arrow_start, arrow_end, style):
            group.add(elem)
        _render_conditions_at(cursor + arrow_len / 2.0, mol_top)
        cursor += arrow_len + gap
        _place_block_at(products_smiles, cursor, mol_top)
    else:
        # ---- Stacked layout: reactants row 1, arrow + products row 2 ----
        # Row 1: reactants (top padding applies here if conditions are above row 1)
        mol_top_1 = top_pad
        _place_block_at(reactants_smiles, 0.0, mol_top_1)
        # Row 2: arrow at left, products to the right
        mol_top_2 = mol_top_1 + mol_h + stacked_row_gap
        midline_y_2 = mol_top_2 + mol_h / 2.0
        arrow_start_2 = (0.0, midline_y_2)
        arrow_end_2 = (arrow_len, midline_y_2)
        for elem in arrow_fn(arrow_start_2, arrow_end_2, style):
            group.add(elem)
        _render_conditions_at(arrow_len / 2.0, mol_top_2)
        _place_block_at(products_smiles, arrow_len + gap, mol_top_2)

    return group


def render_multistep_reaction(
    molecules_smiles: list[str],
    step_conditions: list[dict | None] | None = None,
    style_dict: dict | None = None,
    molecule_size: tuple[int, int] = (140, 100),
    step_reversible: list[bool] | None = None,
) -> svgwrite.container.Group:
    """Render a linear multi-step reaction: m0 → m1 → … → mn.

    Each consecutive molecule pair is joined by a reaction arrow carrying that
    step's optional ``conditions`` ({'above', 'below'}). Layout is a single
    horizontal row — the same geometry as ``render_reaction``'s flat mode,
    generalised to N molecules and N-1 arrows. Intermediates are drawn once
    (a molecule that is the product of one step and the reactant of the next
    appears a single time in the chain).

    V2 / R6.

    Args:
        molecules_smiles: Ordered SMILES for the chain, reactant → … → product.
            Must contain at least two molecules.
        step_conditions: One conditions dict (or None) per arrow; length must
            equal ``len(molecules_smiles) - 1`` when given. None → no labels on
            any arrow.
        style_dict: Optional preset overlay; merged onto DEFAULT_STYLE.
        molecule_size: Per-molecule bbox in pixels (fixed, like render_reaction).
        step_reversible: One bool per arrow; True draws a paired equilibrium
            arrow for that step. None → all forward.

    Returns:
        An svgwrite.container.Group with the chain laid out left-to-right,
        top-left at the Group's local origin.

    Raises:
        ValueError: fewer than two molecules, a per-step list length mismatch,
            or any SMILES fails to parse.
    """
    if len(molecules_smiles) < 2:
        raise ValueError(
            "render_multistep_reaction requires at least two molecules"
        )
    n_steps = len(molecules_smiles) - 1
    step_conditions = step_conditions if step_conditions is not None else [None] * n_steps
    step_reversible = step_reversible if step_reversible is not None else [False] * n_steps
    if len(step_conditions) != n_steps:
        raise ValueError(
            f"step_conditions must have length {n_steps} (n_molecules - 1), "
            f"got {len(step_conditions)}"
        )
    if len(step_reversible) != n_steps:
        raise ValueError(
            f"step_reversible must have length {n_steps} (n_molecules - 1), "
            f"got {len(step_reversible)}"
        )

    style = {**DEFAULT_STYLE, **(style_dict or {})}
    mol_w, mol_h = molecule_size
    gap = float(style["chem_reaction_gap"])
    arrow_len = float(style["chem_reaction_arrow_length"])
    cond_size = int(style["chem_conditions_font_size"])
    cond_offset = float(style["chem_conditions_offset"])
    line_gap = cond_size * 1.3

    # Pre-wrap each step's above-text; top_pad is the max across steps so every
    # molecule shares one baseline and the tallest condition block never clips.
    above_lines_per_step: list[list[str]] = []
    for c in step_conditions:
        if c and c.get("above"):
            above_lines_per_step.append(_wrap_conditions(str(c["above"])))
        else:
            above_lines_per_step.append([])
    max_above = max((len(lines) for lines in above_lines_per_step), default=0)
    top_pad = (max_above * line_gap + cond_offset) if max_above else 0.0

    group = svgwrite.container.Group()
    mol_top = top_pad
    midline_y = mol_top + mol_h / 2.0
    cursor = 0.0
    for i, smi in enumerate(molecules_smiles):
        mol = _smiles_to_mol(smi)
        group.add(_inline_molecule(mol, (mol_w, mol_h), "skeletal", style,
                                   translate=(cursor, mol_top)))
        cursor += mol_w
        if i < n_steps:
            cursor += gap
            arrow_fn = _reversible_arrow if step_reversible[i] else _arrow
            arrow_start = (cursor, midline_y)
            arrow_end = (cursor + arrow_len, midline_y)
            for elem in arrow_fn(arrow_start, arrow_end, style):
                group.add(elem)
            _emit_conditions(
                group, step_conditions[i], above_lines_per_step[i],
                cursor + arrow_len / 2.0, mol_top, mol_h, style,
            )
            cursor += arrow_len + gap
    return group


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
