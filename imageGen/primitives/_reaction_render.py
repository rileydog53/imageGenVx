"""Reaction schemes: arrows, conditions, and single/multi-step layout.

Internals of :mod:`imageGen.primitives.chemistry` (R3 split). Holds the reaction
arrow glyphs (`_arrow`, `_reversible_arrow`), condition-text helpers
(`_wrap_conditions`, `_emit_conditions`), and the reaction-scheme public API
(`render_reaction`, `render_multistep_reaction`). Molecule depiction is reused
from the sibling ``_mol_render`` module.

Reactions read left-to-right: reactants joined by "+" glyphs, then a reaction
arrow with optional ``conditions={"above": ..., "below": ...}`` text, then
products. Per-block width is fixed so layout is predictable; auto-bbox packing
is deferred to Phase 6.
"""
from __future__ import annotations

import math

import svgwrite
import svgwrite.container
import svgwrite.shapes
import svgwrite.text

from imageGen.primitives._mol_render import (
    DEFAULT_STYLE,
    _inline_molecule,
    _smiles_to_mol,
)
from imageGen.primitives._text import formula_text as _formula_text


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

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
