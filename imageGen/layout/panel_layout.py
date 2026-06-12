"""Multi-panel layout engine.

Translates a top-level IR `Figure` whose `panels` list is populated into
a flat `list[LayoutEntry]` for the Phase 5 renderer. Each panel's
`content` (itself a Figure) is dispatched to the appropriate sub-engine
by archetype; the returned entries are offset by the panel's top-left
in the parent canvas via `LayoutEntry.position` — this engine is the
first real consumer of that field.

Grid model:
  Panels declare `grid = (row, col, rowspan, colspan)` in IR units. The
  global grid dimensions are inferred from the panels' max extents
  (rows = max(row + rowspan), cols = max(col + colspan)). Cell pixel
  size is derived from `panel_canvas`, an outer `panel_margin`, and an
  inter-cell `panel_gutter`.

Archetype dispatch:
  `ARCHETYPE_TO_LAYOUT` selects the sub-engine. REACTION_SCHEME →
  `layout_reaction` (requires a per-panel SMILES map, looked up in
  `smiles_maps[panel.id]`); PATHWAY / WORKFLOW / CELLULAR_SCHEMATIC /
  MECHANISM_CARTOON → `layout_pathway`. Any other archetype raises
  NotImplementedError naming the archetype.

Panel chrome:
  When `panel_show_chrome=True` (default) each panel emits a thin border
  rect plus an optional title text. The chrome appears *before* the
  panel's content entries so it sits visually behind them.

v1 limitations (explicit gaps; not oversights):
  - Depth = 1. A panel whose content also has panels raises
    NotImplementedError. Nested panel grids are a Phase 4+ concern.
  - A single global `style_dict` flows into every sub-engine; per-panel
    style overrides aren't wired up. Phase 4's master preset will own
    the per-figure-area style routing.
  - Panel title height is reserved as a constant strip at the top of
    the cell (`panel_title_height`); content origin is shifted down by
    that amount so titles never overlap content.
  - Title text is left-anchored at the cell top-left; richer header
    layouts (centered, multi-line, badges) belong in archetype code.
"""
from __future__ import annotations

from typing import Any, Callable

import svgwrite.container
import svgwrite.shapes
import svgwrite.text

from imageGen.ir.schema import Archetype, Figure
from imageGen.layout._archetype_plan import _ARCHETYPE_PLAN
from imageGen.layout.types import LayoutEntry


# ---------------------------------------------------------------------------
# Layout knobs (Phase 4 master preset will union these alongside primitive
# DEFAULT_STYLE dicts; flat namespaced keys for predictable union).
# ---------------------------------------------------------------------------

PANEL_DEFAULT_PARAMS: dict[str, Any] = {
    "panel_canvas":           (1200.0, 600.0),  # (w, h) of full multi-panel area
    "panel_origin":           (0.0, 0.0),       # top-left of the figure
    "panel_margin":           20.0,             # outer margin around the panel grid
    "panel_gutter":           20.0,             # space between adjacent cells
    "panel_title_height":     24.0,             # vertical strip reserved for titles
    "panel_show_chrome":      True,             # draw per-panel border + title
    "panel_border_stroke":    "#9AA9B5",
    "panel_border_stroke_width": 0.75,
    "panel_border_fill":      "none",
    "panel_title_color":      "#1A1A1A",
    "panel_title_size":       12,
    "panel_title_family":     "Helvetica, Arial, sans-serif",
    "panel_title_weight":     "bold",
    "panel_title_align":      "left",   # V2/L12: "left" | "center" | "right"
}


# ---------------------------------------------------------------------------
# Archetype dispatch (public so callers can introspect; tests pin the table).
# ---------------------------------------------------------------------------

# Derived from the single source of truth (_ARCHETYPE_PLAN). Kept as a plain
# mutable dict so callers/tests can introspect and mutate it (e.g. pop an entry
# to exercise the "no engine registered" path).
ARCHETYPE_TO_LAYOUT: dict[Archetype, Callable[..., list[LayoutEntry]]] = {
    archetype: plan.engine for archetype, plan in _ARCHETYPE_PLAN.items()
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _grid_extent(figure: Figure) -> tuple[int, int]:
    """Return (rows, cols) inferred from panel grid extents."""
    rows = max(p.grid[0] + p.grid[2] for p in figure.panels)
    cols = max(p.grid[1] + p.grid[3] for p in figure.panels)
    return rows, cols


def _cell_size(
    canvas: tuple[float, float],
    margin: float,
    gutter: float,
    rows: int,
    cols: int,
) -> tuple[float, float]:
    """Pixel (width, height) of a single grid cell."""
    cw, ch = canvas
    cell_w = (cw - 2 * margin - gutter * (cols - 1)) / cols
    cell_h = (ch - 2 * margin - gutter * (rows - 1)) / rows
    return cell_w, cell_h


def _panel_rect(
    grid: tuple[int, int, int, int],
    origin: tuple[float, float],
    margin: float,
    gutter: float,
    cell_w: float,
    cell_h: float,
) -> tuple[float, float, float, float]:
    """Pixel (x, y, w, h) of a panel's outer rect inside the parent canvas."""
    row, col, rowspan, colspan = grid
    ox, oy = origin
    x = ox + margin + col * (cell_w + gutter)
    y = oy + margin + row * (cell_h + gutter)
    w = colspan * cell_w + (colspan - 1) * gutter
    h = rowspan * cell_h + (rowspan - 1) * gutter
    return x, y, w, h


def _panel_chrome(
    title: str | None,
    x: float,
    y: float,
    w: float,
    h: float,
    params: dict,
) -> svgwrite.container.Group:
    """Border rect (always) + title text (when title is non-empty).

    V2/L12: honors ``panel_title_align`` ("left" | "center" | "right") and
    newline-split multi-line titles via SVG tspan dy offsets.
    """
    g = svgwrite.container.Group()
    border = svgwrite.shapes.Rect(
        insert=(x, y),
        size=(w, h),
        fill=params["panel_border_fill"],
        stroke=params["panel_border_stroke"],
    )
    border["stroke-width"] = float(params["panel_border_stroke_width"])
    g.add(border)
    if title:
        size = float(params["panel_title_size"])
        align = str(params.get("panel_title_align", "left"))
        if align == "center":
            tx = x + w / 2.0
            anchor = "middle"
        elif align == "right":
            tx = x + w - 8.0
            anchor = "end"
        else:
            tx = x + 8.0
            anchor = "start"
        ty = y + size + 4.0
        common_attrs = dict(
            font_family=params["panel_title_family"],
            font_size=size,
            fill=params["panel_title_color"],
        )
        lines = title.split("\n")
        t = svgwrite.text.Text("", insert=(tx, ty), **common_attrs)
        t["font-weight"] = params["panel_title_weight"]
        t["text-anchor"] = anchor
        line_h = size * 1.2
        for i, line in enumerate(lines):
            dy = [0.0] if i == 0 else [line_h]
            span = svgwrite.text.TSpan(line, x=[tx], dy=dy)
            t.add(span)
        g.add(t)
    return g


def _override_subengine_canvas(
    archetype: Archetype,
    base_params: dict | None,
    canvas: tuple[float, float],
    origin: tuple[float, float],
) -> dict:
    """Inject canvas/origin keys appropriate to the sub-engine.

    The two sub-engines use differently-prefixed keys (pathway_*,
    reaction_*); this helper picks the right names per archetype.
    Panel layout owns canvas + origin for its sub-engines (any
    user-supplied pathway_canvas/reaction_origin in `base_params` is
    intentionally clobbered — panels must fit their cell).
    """
    overrides = dict(base_params or {})
    plan = _ARCHETYPE_PLAN.get(archetype)
    if plan is not None:
        if plan.inject_canvas:
            overrides[f"{plan.canvas_key}_canvas"] = canvas
        overrides[f"{plan.canvas_key}_origin"] = origin
    return overrides


def _shift_entry(entry: LayoutEntry, dx: float, dy: float) -> LayoutEntry:
    """Return a copy of `entry` with its position translated by (dx, dy)."""
    px, py = entry.position
    return entry._replace(position=(px + dx, py + dy))


def _scope_entry(entry: LayoutEntry, panel_id: str) -> LayoutEntry:
    """Prepend `panel_id` to the entry's panel_chain (D1 SVG-id scoping).

    Prepend (not append) so that nested-panel support post-v1 produces
    outer-to-inner chains automatically: an entry already scoped by an
    inner panel gets the outer panel prepended on the way up.
    """
    return entry._replace(panel_chain=(panel_id, *entry.panel_chain))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def layout_panel(
    figure: Figure,
    smiles_maps: dict[str, dict[str, str]] | None = None,
    layout_params: dict | None = None,
    style_dict: dict | None = None,
    style_dicts: dict[str, dict] | None = None,
) -> list[LayoutEntry]:
    """Lay out a multi-panel IR Figure as a flat list of LayoutEntry tuples.

    Args:
        figure: IR Figure with non-empty `panels`. The IR validator already
            enforces panels-XOR-leaf-content and non-overlapping grids.
        smiles_maps: For panels whose content has archetype REACTION_SCHEME,
            maps panel.id → entity_id → SMILES. A reaction panel without an
            entry raises ValueError.
        layout_params: Optional overlay onto PANEL_DEFAULT_PARAMS plus any
            sub-engine knobs to forward (the engine threads `pathway_*` and
            `reaction_*` keys through unchanged).
        style_dict: Global style dict forwarded to sub-engines when no
            panel-specific entry exists in ``style_dicts``.
        style_dicts: Per-panel style overrides keyed by ``panel.id``
            (V2/ST4). When a panel has an entry here it takes precedence
            over the global ``style_dict`` for that panel's sub-engine call.

    Returns:
        A flat `list[LayoutEntry]` in render order: per panel, chrome
        (border + title) first, then its content entries shifted into
        the panel's grid cell.

    Raises:
        ValueError: figure.panels is empty, or a REACTION_SCHEME panel
            lacks a smiles_maps entry.
        NotImplementedError: a panel's archetype has no engine in
            ARCHETYPE_TO_LAYOUT (leaf panels only; nested grids recurse).
    """
    if not figure.panels:
        raise ValueError("layout_panel requires a non-empty panels list")

    params = {**PANEL_DEFAULT_PARAMS, **(layout_params or {})}
    canvas = params["panel_canvas"]
    origin = params["panel_origin"]
    margin = float(params["panel_margin"])
    gutter = float(params["panel_gutter"])
    title_h = float(params["panel_title_height"]) if params["panel_show_chrome"] else 0.0

    rows, cols = _grid_extent(figure)
    cell_w, cell_h = _cell_size(canvas, margin, gutter, rows, cols)

    entries: list[LayoutEntry] = []

    for panel in figure.panels:
        archetype = panel.content.archetype

        px, py, pw, ph = _panel_rect(
            panel.grid, origin, margin, gutter, cell_w, cell_h,
        )

        if params["panel_show_chrome"]:
            entries.append(LayoutEntry(
                primitive=_panel_chrome,
                args=(panel.title, px, py, pw, ph),
                kwargs={"params": params},
                position=(0.0, 0.0),
                ir_id=f"{panel.id}_chrome",
            ))

        # Sub-engines operate in their own (0, 0)-origin coordinate space
        # sized to the panel's content area; the per-entry position offset
        # below moves them into the panel's cell.
        content_w = pw
        content_h = ph - title_h
        # ST4: per-panel style wins over global style_dict when provided.
        effective_style = (style_dicts or {}).get(panel.id, style_dict)

        if panel.content.panels:
            # V2/L10: nested grid — recurse with content area as the new canvas.
            nested_params = {
                **(layout_params or {}),
                "panel_canvas": (content_w, content_h),
                "panel_origin": (0.0, 0.0),
            }
            nested_kwargs: dict = {"layout_params": nested_params}
            if smiles_maps is not None:
                nested_kwargs["smiles_maps"] = smiles_maps
            if effective_style is not None:
                nested_kwargs["style_dict"] = effective_style
            if style_dicts is not None:
                nested_kwargs["style_dicts"] = style_dicts
            sub_entries = layout_panel(panel.content, **nested_kwargs)
        else:
            sub_engine = ARCHETYPE_TO_LAYOUT.get(archetype)
            if sub_engine is None:
                raise NotImplementedError(
                    f"No layout engine registered for archetype "
                    f"{archetype!r} (panel '{panel.id}')"
                )
            sub_params = _override_subengine_canvas(
                archetype, layout_params, (content_w, content_h), (0.0, 0.0),
            )
            sub_kwargs: dict = {"layout_params": sub_params}
            if effective_style is not None:
                sub_kwargs["style_dict"] = effective_style
            if archetype is Archetype.REACTION_SCHEME:
                if not smiles_maps or panel.id not in smiles_maps:
                    raise ValueError(
                        f"smiles_maps is missing an entry for reaction panel "
                        f"'{panel.id}'"
                    )
                sub_kwargs["smiles_map"] = smiles_maps[panel.id]
            sub_entries = sub_engine(panel.content, **sub_kwargs)

        offset_y = py + title_h
        for sub in sub_entries:
            entries.append(_scope_entry(_shift_entry(sub, px, offset_y), panel.id))

    return entries
