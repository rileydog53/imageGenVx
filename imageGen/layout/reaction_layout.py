"""Reaction-scheme layout engine.

Translates an IR `Figure` whose `archetype == REACTION_SCHEME` into a
list of `LayoutEntry` tuples that the Phase 5 renderer consumes. Each
LayoutEntry packages a primitive callable, its positional args, its
keyword args, and the (x, y) at which the resulting svgwrite Group
should be translated.

v1 produces a single entry calling `primitives.chemistry.render_reaction`
which already handles the left-to-right horizontal layout of reactants
+ arrow + products. The engine's job here is purely the IR → arguments
translation: classifying entities into reactants vs products from the
relation graph, mapping the IR's ReactionConditions to render_reaction's
{"above", "below"} dict, and routing SMILES from a caller-supplied map.

SMILES sourcing:
  The IR has no SMILES field on entities (entities carry only `label`
  for human-readable names). Rather than baking a label-to-SMILES
  lookup into layout (brittle, gives layout chemistry knowledge),
  overloading `entity.style` (style is for visual presets), or
  modifying the Phase 1 IR schema for a single Phase 3 task, the engine
  takes a required `smiles_map: dict[str, str]` parameter mapping
  entity id → SMILES. Missing keys raise ValueError listing the gap.

v1 limitations (explicit gaps; not oversights):
  - Vertical stacking when reactant/product count would overflow panel
    width is not yet implemented; render_reaction lays everything out
    horizontally.
  - `ReactionConditions.reversible` is silently ignored; chemistry's
    arrow primitive draws single-direction only. Honor this once
    chemistry exposes a reversible-arrow option.
  - Multi-step reactions (an entity that is both source and target of
    different relations -- an intermediate) are rendered as a molecule
    sequence (m0 → m1 → … → mn) when the relation graph is a single linear
    chain (V2/R6, via `render_multistep_reaction`). Non-linear multi-step
    graphs (branching / convergence / cycles) still raise NotImplementedError;
    the compositor routes those through pathway_layout instead.
  - Per-molecule annotations / compound numbers are deferred to
    label_placement.py paired with a v2 of this engine that decomposes
    into per-molecule LayoutEntry items.

Phase 5 coupling:
  All layout engines emit `LayoutEntry` so the renderer is uniform.
  The renderer calls `entry.primitive(*entry.args, **entry.kwargs)`,
  receives an svgwrite Group, then wraps it in a translate by
  `entry.position` before adding to the Drawing.
"""
from __future__ import annotations

import warnings
from typing import Any

from imageGen.ir.schema import Archetype, Figure, ReactionConditions
from imageGen.layout.types import LayoutEntry
from imageGen.primitives.chemistry import render_multistep_reaction, render_reaction


# ---------------------------------------------------------------------------
# Layout knobs (Phase 4 master preset will union these alongside primitive
# DEFAULT_STYLE dicts; flat namespaced keys for predictable union).
# ---------------------------------------------------------------------------

REACTION_DEFAULT_PARAMS: dict[str, Any] = {
    "reaction_molecule_size": (140, 100),   # forwarded to render_reaction
    "reaction_origin":        (0.0, 0.0),   # top-left of the reaction Group
    "reaction_canvas":        (800.0, 300.0),  # SVG viewport for compositor (Phase 5)
    "reaction_max_width":     800.0,        # V2/R1: total px before switching to stacked layout
    "reaction_stacked_row_gap": 24.0,       # V2/R1: vertical gap between stacked rows
    "reaction_molecule_min_width": 60.0,    # V2/P2: floor for auto-shrunk molecule width
}

# A REACTION_SCHEME renders as a single composite group (molecules are
# drawn from SMILES as one unit, not per-entity). This is the ir_id that
# group carries — and the only semantic anchor verify/ can check for it.
REACTION_GROUP_IR_ID = "reaction_0"


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _classify_entities(figure: Figure) -> tuple[list[str], list[str]]:
    """Return (reactant_ids, product_ids) preserving entity declaration order.

    Reactant = entity that is the source of any relation.
    Product = entity that is the target of any relation.
    Intermediates (both source and target -- multi-step reactions) raise
    NotImplementedError; the compositor routes such figures through
    pathway_layout before this engine is reached (R3).

    Output preserves the entity declaration order from the IR: callers who
    care about left-to-right ordering of reactants in the rendered figure
    set it by ordering the entity list in the IR.
    """
    sources = {r.source for r in figure.relations}
    targets = {r.target for r in figure.relations}
    intermediates = sources & targets
    if intermediates:
        raise NotImplementedError(
            f"Multi-step reactions (entities {sorted(intermediates)} are both "
            f"source and target) are not supported by reaction_layout; use "
            f"pathway_layout instead."
        )
    reactants = [e.id for e in figure.entities if e.id in sources]
    products = [e.id for e in figure.entities if e.id in targets]
    return reactants, products


def _extract_conditions(figure: Figure) -> dict[str, str] | None:
    """Merge ReactionConditions from all relations into render_reaction's dict.

    V2 / R5: honors each relation's conditions independently:
      - ``above`` key: union of all reagents lists, comma-separated.
      - ``below`` key: all notes / yield strings, semicolon-separated.
    Returns None when no relation carries any conditions.
    """
    all_reagents: list[str] = []
    all_below: list[str] = []
    for relation in figure.relations:
        c = relation.conditions
        if c is None:
            continue
        if isinstance(c, dict):
            c = ReactionConditions.model_validate(c)
        all_reagents.extend(c.reagents)
        if c.notes:
            all_below.append(c.notes)
        elif c.yield_pct is not None:
            all_below.append(f"{c.yield_pct:.0f}%")
    result: dict[str, str] = {}
    if all_reagents:
        result["above"] = ", ".join(all_reagents)
    if all_below:
        result["below"] = "; ".join(all_below)
    return result or None


def _resolve_smiles(entity_ids: list[str], smiles_map: dict[str, str]) -> list[str]:
    """Look up SMILES for each entity id; raise ValueError listing any misses."""
    missing = [eid for eid in entity_ids if eid not in smiles_map]
    if missing:
        raise ValueError(
            f"smiles_map is missing entries for entity id(s): {missing}"
        )
    return [smiles_map[eid] for eid in entity_ids]


def _is_reversible(figure: Figure) -> bool:
    """Return True if any relation in *figure* has conditions.reversible=True.

    V2 / R2: the first truthy flag wins; a single reversible relation makes
    the whole reaction arrow reversible.
    """
    for rel in figure.relations:
        c = rel.conditions
        if c is None:
            continue
        if isinstance(c, dict):
            c = ReactionConditions.model_validate(c)
        if c.reversible:
            return True
    return False


def _block_width(n_mols: int, mol_w: float, gap: float, plus_w: float) -> float:
    """Total pixel width of a horizontal molecule block with "+" signs.

    For *n_mols* molecules of width *mol_w* separated by a gap + plus glyph +
    gap, the total is ``n_mols * mol_w + (n_mols - 1) * (2*gap + plus_w)``.
    Returns 0 when *n_mols* == 0.

    V2 / R1.
    """
    if n_mols <= 0:
        return 0.0
    return n_mols * mol_w + (n_mols - 1) * (2.0 * gap + plus_w)


def _should_stack(
    n_reactants: int,
    n_products: int,
    mol_w: float,
    gap: float,
    arrow_len: float,
    plus_w: float,
    max_width: float,
) -> bool:
    """Return True when the flat horizontal layout would exceed *max_width*.

    Total flat width = reactants_block + gap + arrow + gap + products_block.
    V2 / R1.
    """
    total = (
        _block_width(n_reactants, mol_w, gap, plus_w)
        + gap + arrow_len + gap
        + _block_width(n_products, mol_w, gap, plus_w)
    )
    return total > max_width


def _fit_mol_width(
    n_reactants: int,
    n_products: int,
    mol_w: float,
    gap: float,
    arrow_len: float,
    plus_w: float,
    max_width: float,
    min_mol_w: float,
    stack: bool,
) -> float:
    """Return the largest mol_w ≤ default that keeps every row within max_width.

    V2 / P2 — bond-line packing.

    In *flat* mode the single row holds reactants + arrow + products; all mols
    share the available space after subtracting fixed costs (plus glyphs, gaps,
    arrow). In *stacked* mode rows are independent: row 1 is the reactant block
    only, row 2 is arrow + product block; the binding constraint is whichever
    row requires smaller molecules. Result is clamped to [min_mol_w, mol_w].
    """
    if stack:
        w_r = (
            (max_width - max(0, n_reactants - 1) * (2.0 * gap + plus_w)) / n_reactants
            if n_reactants > 0 else mol_w
        )
        w_p = (
            (max_width - arrow_len - gap - max(0, n_products - 1) * (2.0 * gap + plus_w)) / n_products
            if n_products > 0 else mol_w
        )
        adapted = min(w_r, w_p)
    else:
        n_total = n_reactants + n_products
        if n_total > 0:
            fixed = (
                max(0, n_reactants - 1) * (2.0 * gap + plus_w)
                + gap + arrow_len + gap
                + max(0, n_products - 1) * (2.0 * gap + plus_w)
            )
            adapted = (max_width - fixed) / n_total
        else:
            adapted = mol_w
    return max(min_mol_w, min(mol_w, adapted))


def _molecule_centers(
    reactant_ids: list[str],
    product_ids: list[str],
    mol_w: float,
    mol_h: float,
    gap: float,
    arrow_len: float,
    plus_w: float,
    top_pad: float,
    stack: bool,
    row_gap: float,
) -> dict[str, tuple[float, float]]:
    """Return the (cx, cy) centre for every molecule in the rendered reaction.

    Replicates the cursor-based geometry of ``render_reaction`` so that
    ``reaction_label_requests`` can anchor compound-name labels at the
    correct position without having to inspect the rendered SVG.

    V2 / R4.
    """
    result: dict[str, tuple[float, float]] = {}
    # -- Row 1: reactants --
    mol_top_1 = top_pad
    cursor = 0.0
    for i, eid in enumerate(reactant_ids):
        cx = cursor + mol_w / 2.0
        cy = mol_top_1 + mol_h / 2.0
        result[eid] = (cx, cy)
        cursor += mol_w
        if i < len(reactant_ids) - 1:
            cursor += gap + plus_w + gap
    # -- Row 2 (or continuation of row 1): products --
    if stack:
        mol_top_2 = mol_top_1 + mol_h + row_gap
        cursor_p = arrow_len + gap     # products start after the stacked arrow
    else:
        cursor_p = cursor + gap + arrow_len + gap  # skip arrow in flat mode
        mol_top_2 = mol_top_1
    for i, eid in enumerate(product_ids):
        cx = cursor_p + mol_w / 2.0
        cy = mol_top_2 + mol_h / 2.0
        result[eid] = (cx, cy)
        cursor_p += mol_w
        if i < len(product_ids) - 1:
            cursor_p += gap + plus_w + gap
    return result


# ---------------------------------------------------------------------------
# V2 / R6: multi-step (linear-chain) reaction helpers
# ---------------------------------------------------------------------------

def _linear_chain_order(figure: Figure) -> list[str] | None:
    """Return the entity ids of a single linear reaction chain, or None.

    A linear chain is a simple path m0 → m1 → … → mn: every node has at most
    one outgoing and one incoming relation, there is exactly one start (no
    incoming) node, the walk visits every entity once, and the relation count
    equals ``len(chain) - 1``. Branching (a source with two products),
    convergence (a target with two reactants), cycles, and disconnected
    entities all return None — those can't be drawn as one molecule row.
    """
    out_edge: dict[str, str] = {}
    in_count: dict[str, int] = {}
    for r in figure.relations:
        if r.source in out_edge:
            return None  # branching: source has >1 outgoing edge
        out_edge[r.source] = r.target
        in_count[r.target] = in_count.get(r.target, 0) + 1
    if any(v > 1 for v in in_count.values()):
        return None  # convergence: target has >1 incoming edge

    entity_ids = [e.id for e in figure.entities]
    starts = [eid for eid in entity_ids if in_count.get(eid, 0) == 0]
    if len(starts) != 1:
        return None  # zero or multiple chain heads (disconnected / branched)

    order: list[str] = []
    seen: set[str] = set()
    node: str | None = starts[0]
    while node is not None:
        if node in seen:
            return None  # cycle
        order.append(node)
        seen.add(node)
        node = out_edge.get(node)

    if len(order) != len(entity_ids) or len(figure.relations) != len(order) - 1:
        return None  # not every entity on the path, or extra/parallel edges
    return order


def is_linear_chain_reaction(figure: Figure) -> bool:
    """True when *figure* is a multi-step REACTION_SCHEME that is a linear chain.

    Multi-step = some entity is both a relation source and target (an
    intermediate). Such a figure can be rendered as a molecule sequence by
    ``layout_reaction`` only when its relation graph is a single linear chain;
    the compositor uses this to decide whether to keep the reaction renderer
    or fall back to the pathway engine (R6).
    """
    if figure.archetype != Archetype.REACTION_SCHEME:
        return False
    sources = {r.source for r in figure.relations}
    targets = {r.target for r in figure.relations}
    if not (sources & targets):
        return False  # single-step scheme, not multi-step
    return _linear_chain_order(figure) is not None


def _conditions_for_relation(relation) -> dict | None:
    """Build a single relation's render_reaction-style {'above','below'} dict.

    Per-step analogue of ``_extract_conditions`` (which merges every relation).
    ``above`` = comma-joined reagents; ``below`` = notes, else a formatted
    yield percentage. Returns None when the relation carries no conditions.
    """
    c = relation.conditions
    if c is None:
        return None
    if isinstance(c, dict):
        c = ReactionConditions.model_validate(c)
    result: dict[str, str] = {}
    if c.reagents:
        result["above"] = ", ".join(c.reagents)
    if c.notes:
        result["below"] = c.notes
    elif c.yield_pct is not None:
        result["below"] = f"{c.yield_pct:.0f}%"
    return result or None


def _step_reversible(relation) -> bool:
    """Return True when this relation's conditions mark it reversible."""
    c = relation.conditions
    if c is None:
        return False
    if isinstance(c, dict):
        c = ReactionConditions.model_validate(c)
    return bool(c.reversible)


def _multistep_molecule_centers(
    chain: list[str],
    mol_w: float,
    mol_h: float,
    gap: float,
    arrow_len: float,
    top_pad: float,
) -> dict[str, tuple[float, float]]:
    """Return the (cx, cy) centre of every molecule in a linear-chain render.

    Replicates ``render_multistep_reaction``'s cursor geometry so
    ``reaction_label_requests`` can anchor compound labels without inspecting
    the rendered SVG (R4-style, extended to N molecules).
    """
    result: dict[str, tuple[float, float]] = {}
    cursor = 0.0
    cy = top_pad + mol_h / 2.0
    n = len(chain)
    for i, eid in enumerate(chain):
        result[eid] = (cursor + mol_w / 2.0, cy)
        cursor += mol_w
        if i < n - 1:
            cursor += gap + arrow_len + gap
    return result


def _layout_multistep_reaction(
    figure: Figure,
    chain: list[str],
    smiles_map: dict[str, str],
    layout_params: dict | None,
    style_dict: dict | None,
) -> list[LayoutEntry]:
    """Emit the single ``reaction_0`` LayoutEntry for a linear-chain reaction.

    Resolves SMILES in chain order, shrinks molecule width to fit
    ``reaction_max_width`` (the flat-row analogue of P2's ``_fit_mol_width``),
    and pulls each step's conditions / reversibility from the relation joining
    consecutive molecules.
    """
    molecules_smiles = _resolve_smiles(chain, smiles_map)

    params = {**REACTION_DEFAULT_PARAMS, **(layout_params or {})}
    mol_w, mol_h = params["reaction_molecule_size"]

    from imageGen.primitives.chemistry import DEFAULT_STYLE as _CHEM_STYLE  # noqa: PLC0415
    _gap = float(_CHEM_STYLE["chem_reaction_gap"])
    _arrow_len = float(_CHEM_STYLE["chem_reaction_arrow_length"])
    max_width = float(params["reaction_max_width"])
    min_mol_w = float(params["reaction_molecule_min_width"])

    n_mol = len(chain)
    n_steps = n_mol - 1
    # Flat-row width = n_mol*mol_w + n_steps*(gap + arrow_len + gap). Solve for
    # the largest mol_w ≤ default that keeps the row within max_width.
    fixed = n_steps * (2.0 * _gap + _arrow_len)
    adapted = (max_width - fixed) / n_mol if n_mol else float(mol_w)
    mol_w_adapted = max(min_mol_w, min(float(mol_w), adapted))
    if mol_w_adapted < float(mol_w) and mol_w_adapted <= min_mol_w:
        warnings.warn(
            f"Multi-step reaction: molecules shrunk to minimum width "
            f"({min_mol_w}px) but the {n_mol}-molecule chain may still overflow. "
            f"Increase reaction_max_width or reduce the chain length.",
            UserWarning,
            stacklevel=2,
        )
    mol_h_adapted = float(mol_h) * (mol_w_adapted / float(mol_w)) if mol_w else float(mol_h)
    adapted_size = (int(round(mol_w_adapted)), int(round(mol_h_adapted)))

    rel_by_pair = {(r.source, r.target): r for r in figure.relations}
    step_conditions: list[dict | None] = []
    step_reversible: list[bool] = []
    for i in range(n_steps):
        r = rel_by_pair[(chain[i], chain[i + 1])]
        step_conditions.append(_conditions_for_relation(r))
        step_reversible.append(_step_reversible(r))

    kwargs: dict[str, Any] = {
        "step_conditions": step_conditions,
        "molecule_size": adapted_size,
        # #6: tag each chain molecule with its entity id for per-molecule verify.
        "mol_ids": list(chain),
    }
    if any(step_reversible):
        kwargs["step_reversible"] = step_reversible
    if style_dict is not None:
        kwargs["style_dict"] = style_dict
    return [LayoutEntry(
        primitive=render_multistep_reaction,
        args=(molecules_smiles,),
        kwargs=kwargs,
        position=params["reaction_origin"],
        ir_id=REACTION_GROUP_IR_ID,
    )]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def layout_reaction(
    figure: Figure,
    smiles_map: dict[str, str],
    layout_params: dict | None = None,
    style_dict: dict | None = None,
) -> list[LayoutEntry]:
    """Lay out an IR REACTION_SCHEME Figure as a list of LayoutEntry tuples.

    Args:
        figure: IR Figure with archetype=REACTION_SCHEME, non-empty entities
            and relations. Each relation's source is treated as a reactant
            and target as a product; intermediates (entity appearing on both
            sides) raise NotImplementedError.
        smiles_map: Required mapping from entity.id to SMILES string. Missing
            keys raise ValueError listing the gap.
        layout_params: Optional overlay onto REACTION_DEFAULT_PARAMS for layout
            knobs (molecule size, origin).
        style_dict: Optional preset overlay forwarded to render_reaction
            for visual styling.

    Returns:
        A list of LayoutEntry tuples ready for the renderer. A single entry
        calls render_reaction; ``reaction_label_requests`` can be called
        afterwards to generate per-molecule compound-name label requests.

    Raises:
        ValueError: figure.archetype is not REACTION_SCHEME; entities or
            relations are empty; smiles_map is missing required ids.
        NotImplementedError: figure contains an intermediate entity
            (multi-step reaction).
    """
    if figure.archetype != Archetype.REACTION_SCHEME:
        raise ValueError(
            f"layout_reaction requires archetype=REACTION_SCHEME, "
            f"got {figure.archetype!r}"
        )
    if not figure.entities:
        raise ValueError("layout_reaction requires a non-empty entities list")
    if not figure.relations:
        raise ValueError("layout_reaction requires a non-empty relations list")

    # V2 / R6: a multi-step reaction (some entity is both source and target)
    # renders as a molecule sequence when its graph is a single linear chain.
    # Non-linear multi-step graphs (branching / convergence) still raise; the
    # compositor routes those through pathway_layout instead.
    sources = {r.source for r in figure.relations}
    targets = {r.target for r in figure.relations}
    if sources & targets:
        chain = _linear_chain_order(figure)
        if chain is None:
            raise NotImplementedError(
                "Multi-step reaction graph is not a linear chain (branching, "
                "convergence, or a cycle); cannot render as a molecule sequence. "
                "Use pathway_layout, or re-encode parallel reactions as separate "
                "reactant→product edges."
            )
        return _layout_multistep_reaction(
            figure, chain, smiles_map, layout_params, style_dict
        )

    reactant_ids, product_ids = _classify_entities(figure)
    reactants_smiles = _resolve_smiles(reactant_ids, smiles_map)
    products_smiles = _resolve_smiles(product_ids, smiles_map)
    conditions = _extract_conditions(figure)

    params = {**REACTION_DEFAULT_PARAMS, **(layout_params or {})}
    mol_w, mol_h = params["reaction_molecule_size"]
    row_gap = float(params["reaction_stacked_row_gap"])

    # V2/R2: forward reversible flag from IR conditions
    reversible = _is_reversible(figure)

    # V2/R1: switch to stacked layout when horizontal extent overflows max_width
    # Use chemistry DEFAULT_STYLE constants for gap / arrow_len / plus_size so
    # the stacking decision matches what render_reaction will actually render.
    from imageGen.primitives.chemistry import DEFAULT_STYLE as _CHEM_STYLE  # noqa: PLC0415
    _gap = float(_CHEM_STYLE["chem_reaction_gap"])
    _arrow_len = float(_CHEM_STYLE["chem_reaction_arrow_length"])
    _plus_w = int(_CHEM_STYLE["chem_reaction_plus_font_size"])
    max_width = float(params["reaction_max_width"])
    stack = _should_stack(
        len(reactant_ids), len(product_ids),
        float(mol_w), _gap, _arrow_len, float(_plus_w),
        max_width,
    )

    # V2/P2: shrink molecule width to fit within max_width when crowded.
    min_mol_w = float(params["reaction_molecule_min_width"])
    mol_w_adapted = _fit_mol_width(
        len(reactant_ids), len(product_ids),
        float(mol_w), _gap, _arrow_len, float(_plus_w),
        max_width, min_mol_w, stack,
    )
    if mol_w_adapted < float(mol_w) and mol_w_adapted <= min_mol_w:
        warnings.warn(
            f"Reaction layout: molecules shrunk to minimum width ({min_mol_w}px) "
            f"but layout may still overflow. Increase reaction_max_width or "
            f"reaction_molecule_min_width, or reduce molecule count.",
            UserWarning,
            stacklevel=2,
        )
    mol_h_adapted = float(mol_h) * (mol_w_adapted / float(mol_w)) if mol_w else float(mol_h)
    adapted_size = (int(round(mol_w_adapted)), int(round(mol_h_adapted)))

    kwargs: dict[str, Any] = {
        "conditions": conditions,
        "molecule_size": adapted_size,
        # #6: tag each molecule with its entity id so the composite reaction is
        # verifiable per-molecule (semantic_check), not only at reaction_0.
        "reactant_ids": reactant_ids,
        "product_ids": product_ids,
    }
    if reversible:
        kwargs["reversible"] = True
    if stack:
        kwargs["stack"] = True
        kwargs["stacked_row_gap"] = row_gap
    # Only forward style_dict when the caller actually passed one — keeps
    # LayoutEntry.kwargs minimal and the renderer doesn't have to special-case
    # an explicit None.
    if style_dict is not None:
        kwargs["style_dict"] = style_dict
    return [LayoutEntry(
        primitive=render_reaction,
        args=(reactants_smiles, products_smiles),
        kwargs=kwargs,
        position=params["reaction_origin"],
        ir_id=REACTION_GROUP_IR_ID,
    )]


def reaction_label_requests(
    figure: Figure,
    entries: list[LayoutEntry],
) -> list:
    """Emit one ``LabelRequest`` per entity in a REACTION_SCHEME figure.

    Places each entity's label (compound name) just below its molecule
    bounding box. Anchors are computed by replicating the geometry of
    ``render_reaction`` so labels land at the correct position without
    inspecting the rendered SVG.

    V2 / R4.

    Args:
        figure: The same IR Figure passed to ``layout_reaction``.
        entries: The list returned by ``layout_reaction(figure, ...)``.
            Must contain exactly one entry (the monolithic render_reaction
            entry); raises ``ValueError`` otherwise.

    Returns:
        A list of ``LabelRequest`` items, one per entity whose ``label``
        is non-empty. Imports ``LabelRequest`` lazily to avoid a circular
        import.
    """
    from imageGen.layout.label_placement import LabelRequest  # noqa: PLC0415

    if not entries:
        return []
    entry = entries[0]
    mol_w, mol_h = entry.kwargs["molecule_size"]

    from imageGen.primitives.chemistry import (  # noqa: PLC0415
        DEFAULT_STYLE as _CHEM_STYLE,
        _wrap_conditions,
    )
    _gap = float(_CHEM_STYLE["chem_reaction_gap"])
    _arrow_len = float(_CHEM_STYLE["chem_reaction_arrow_length"])
    _plus_w = int(_CHEM_STYLE["chem_reaction_plus_font_size"])
    cond_size = int(_CHEM_STYLE["chem_conditions_font_size"])
    cond_offset = float(_CHEM_STYLE["chem_conditions_offset"])
    line_gap = cond_size * 1.3

    sources = {r.source for r in figure.relations}
    targets = {r.target for r in figure.relations}
    if sources & targets:
        # V2 / R6: multi-step linear chain — molecules sit in one row, top_pad
        # is the tallest above-conditions block across all steps (mirrors
        # render_multistep_reaction).
        chain = _linear_chain_order(figure)
        step_conditions = entry.kwargs.get("step_conditions") or []
        max_above = 0
        for c in step_conditions:
            if c and c.get("above"):
                max_above = max(max_above, len(_wrap_conditions(str(c["above"]))))
        top_pad = (max_above * line_gap + cond_offset) if max_above else 0.0
        centers = _multistep_molecule_centers(
            chain or [], float(mol_w), float(mol_h), _gap, _arrow_len, top_pad,
        )
    else:
        conditions = entry.kwargs.get("conditions")
        stack = entry.kwargs.get("stack", False)
        row_gap = float(entry.kwargs.get("stacked_row_gap", 24.0))

        # Replicate top_pad from render_reaction (rough approximation based on
        # above-condition line count; matches render_reaction's _wrap logic).
        top_pad = 0.0
        if conditions and conditions.get("above"):
            above_text = str(conditions["above"])
            # Simple count: ceil(len / 28)
            n_lines = max(1, (len(above_text) + 27) // 28)
            top_pad = n_lines * line_gap + cond_offset

        reactant_ids, product_ids = _classify_entities(figure)
        centers = _molecule_centers(
            reactant_ids, product_ids,
            float(mol_w), float(mol_h),
            _gap, _arrow_len, float(_plus_w),
            top_pad, stack, row_gap,
        )

    entity_by_id = {e.id: e for e in figure.entities}
    requests: list[LabelRequest] = []
    for eid, (cx, cy) in centers.items():
        entity = entity_by_id.get(eid)
        if entity is None or not entity.label:
            continue
        requests.append(LabelRequest(
            text=entity.label,
            # Anchor at the molecule's bottom-centre; label goes below.
            anchor=(cx, cy + mol_h / 2.0),
            anchor_size=(float(mol_w), 0.0),
            priority=("below", "above", "right", "left", "center"),
            ir_id=eid,
        ))
    return requests
