"""Label placement coordinator (P0a.3).

Single entry point for the compositor's label step. Routes the three label
strategies through one ``LabelCoordinator.place()`` dispatch keyed on container
mode (container-mode-first, exactly like ``_lowering_plan``):

  * **leaf** — one figure-wide placement pass (``_run_leaf``);
  * **per-panel** — one collision-isolated pass per panel (``_run_panels``);
  * **tier** — currently *inert* (``return entries``). Tier captions are still
    baked by the tier engine (``tier_layout._caption_group``); Step 5 (P5.2)
    flips **only** this arm to scene-local placement.

This is a behaviour-preserving extraction of the label logic that previously
lived inline in ``render_figure`` plus ``_place_labels_per_panel`` /
``_panel_cell_bounds`` / ``_label_requests_fn`` in ``compositor.py``. Building
the seam now lets P5.2 swap the tier branch without touching the leaf/panel
paths. ``_label_requests_fn`` is re-exported from ``compositor`` for callers
(and tests) that still import it from there.

Import direction is one-directional: this module imports the layout layer
(``_archetype_plan`` / ``label_placement`` / ``pathway_layout``) but **nothing**
from ``compositor`` — ``compositor`` imports *this*. No cycle.
"""
from __future__ import annotations

from typing import Any, NamedTuple

from imageGen.ir.schema import Archetype, Figure
from imageGen.layout._archetype_plan import _ARCHETYPE_PLAN
from imageGen.layout.label_placement import LabelRequest, place_labels
from imageGen.layout.pathway_layout import pathway_extlabel_leaders
from imageGen.layout.types import LayoutEntry


class LabelScope(NamedTuple):
    """One collision-isolated label-placement unit.

    ``entries`` is BOTH the entry-subset placed against AND the occupancy seed
    — and it must be the *same list object* whose ``len()`` anchors the
    original-entries / new-labels split after ``place_labels`` (the panel path
    relies on ``placed[:n]`` being the originals and ``placed[n:]`` the drifted
    labels; a future copy of this list would silently break the split).

    ``position`` ``None`` ⇒ no re-stamp (leaf: labels render where placed). A
    tuple ⇒ drifted labels are re-stamped with ``panel_chain`` + this offset
    (panel: sub-engines lay out in panel-local coords, so the label group needs
    the panel's render offset to land in its cell).
    """
    entries: list[LayoutEntry]
    requests: list[LabelRequest]
    canvas: tuple[float, float] | None
    style_dict: dict[str, Any]
    panel_chain: tuple[str, ...] = ()
    position: tuple[float, float] | None = None
    emit_leaders: bool = True


def _label_requests_fn(archetype: Archetype) -> Any | None:
    """Return the *_label_requests sibling for the given archetype, or None.

    Implements D3: the compositor discovers label-request helpers by
    archetype, rather than each layout engine auto-invoking placement.
    Returns None when no helper exists (reaction layouts in v1).

    Pathway-family archetypes (PATHWAY / WORKFLOW / CELLULAR_SCHEMATIC /
    MECHANISM_CARTOON) all dispatch through `layout_pathway` and share
    `pathway_label_requests`; REACTION_SCHEME has `reaction_label_requests`.
    The mapping is read from the single `_ARCHETYPE_PLAN` table.
    """
    plan = _ARCHETYPE_PLAN.get(archetype)
    return plan.label_fn if plan is not None else None


def _panel_cell_bounds(ir: Figure) -> dict[str, tuple[float, float]]:
    """Map each top-level panel id → its content-cell ``(w, h)`` in local coords.

    LT4. ``layout_panel`` lays each panel's content out in (0, 0)-origin
    coordinates sized to ``(pw, ph - title_h)``; this recomputes that cell so
    ``place_labels`` can bound candidates to the cell. Mirrors layout_panel's
    geometry with ``PANEL_DEFAULT_PARAMS`` (the compositor calls layout_panel
    with no param overrides).
    """
    from imageGen.layout.panel_layout import (  # noqa: PLC0415
        PANEL_DEFAULT_PARAMS,
        _cell_size,
        _grid_extent,
        _panel_rect,
    )

    p = PANEL_DEFAULT_PARAMS
    margin = float(p["panel_margin"])
    gutter = float(p["panel_gutter"])
    title_h = float(p["panel_title_height"]) if p["panel_show_chrome"] else 0.0
    rows, cols = _grid_extent(ir)
    cell_w, cell_h = _cell_size(p["panel_canvas"], margin, gutter, rows, cols)

    bounds: dict[str, tuple[float, float]] = {}
    for panel in ir.panels:
        _x, _y, pw, ph = _panel_rect(
            panel.grid, p["panel_origin"], margin, gutter, cell_w, cell_h
        )
        bounds[panel.id] = (pw, ph - title_h)
    return bounds


class LabelCoordinator:
    """Routes the compositor's label step by container mode (P0a.3 seam)."""

    @classmethod
    def place(
        cls,
        ir: Figure,
        entries: list[LayoutEntry],
        style_dict: dict[str, Any],
        *,
        strict_labels: bool = False,
        canvas: tuple[float, float] | None = None,
        panel_styles: dict[str, dict[str, Any]] | None = None,
    ) -> list[LayoutEntry]:
        """Place labels for *entries*, dispatching container-mode-first.

        Tiers: inert pass-through (``return entries``) — captions are baked by
        the tier engine today; P5.2 flips this arm. Panels: one collision-
        isolated scope per panel. Leaf: a single figure-wide scope. The
        ``labels=False`` short-circuit stays in the caller (``if labels:``).
        """
        if ir.tiers:
            # Inert seam: tier captions/labels are baked by the tier engine
            # (tier_layout._caption_group). P5.2 swaps this arm to per-scene
            # placement. The `is entries` identity is pinned by a unit test.
            return entries
        if ir.panels:
            return cls._run_panels(
                ir, entries, style_dict, strict_labels=strict_labels,
                canvas=canvas, panel_styles=panel_styles,
            )
        return cls._run_leaf(
            ir, entries, style_dict, strict_labels=strict_labels, canvas=canvas,
        )

    @classmethod
    def _place_scope(
        cls, scope: LabelScope, *, strict_labels: bool
    ) -> list[LayoutEntry]:
        """Run ``place_labels`` (+ optional ext-label leaders) for one scope.

        Returns the full placed list. ``len(scope.entries)`` anchors the
        original/label split the caller uses to merge (panel) or return
        verbatim (leaf).
        """
        placed = place_labels(
            scope.entries, scope.requests, style_dict=scope.style_dict,
            canvas=scope.canvas, strict_labels=strict_labels,
        )
        if scope.emit_leaders:
            # Bug 5: connect any externalized (rung-4) entity label back to its
            # empty box with a dashed leader (no-op when none exist).
            placed = pathway_extlabel_leaders(placed, scope.style_dict)
        return placed

    @classmethod
    def _run_leaf(
        cls,
        ir: Figure,
        entries: list[LayoutEntry],
        style_dict: dict[str, Any],
        *,
        strict_labels: bool,
        canvas: tuple[float, float] | None,
    ) -> list[LayoutEntry]:
        """Single figure-wide placement pass (the former leaf else-branch)."""
        label_fn = _label_requests_fn(ir.archetype)
        if label_fn is None:
            return entries
        requests = label_fn(ir, entries)
        scope = LabelScope(entries, requests, canvas, style_dict)
        return cls._place_scope(scope, strict_labels=strict_labels)

    @classmethod
    def _run_panels(
        cls,
        ir: Figure,
        entries: list[LayoutEntry],
        style_dict: dict[str, Any],
        *,
        strict_labels: bool,
        canvas: tuple[float, float] | None,
        panel_styles: dict[str, dict[str, Any]] | None,
    ) -> list[LayoutEntry]:
        """Run label placement separately for each panel's slice of entries.

        Buckets entries by `entry.panel_chain[0]` (chrome lives in the
        empty-chain bucket and passes through untouched). For each panel
        whose content archetype has a `*_label_requests` sibling, requests
        are computed from that panel's content + entries, labels are placed
        using only that bucket (collision-isolated), and each newly-placed
        label entry is re-stamped with `panel_chain=(panel.id,)` and the
        panel's render offset so it lands inside its cell.

        Sub-engines lay out in (0, 0)-origin panel-local coordinates and
        rely on a per-entry `position` to translate the rendered group into
        the parent canvas. `pathway_label_requests` reads `arrow.args`
        (local coords), so labels come back in panel-local coords with
        `position=(0, 0)` — they would otherwise render at the same
        absolute spot in every panel. The panel offset is shared across all
        sub-entries (set by `_shift_entry` in `layout_panel`), so we read it
        from any bucket entry.
        """
        buckets: dict[str | None, list[LayoutEntry]] = {None: []}
        for entry in entries:
            key = entry.panel_chain[0] if entry.panel_chain else None
            buckets.setdefault(key, []).append(entry)

        # LT4: each panel's sub-engine lays out in (0, 0)-origin local coords
        # sized to its content cell, so the canvas bound for that panel's
        # place_labels call must be the cell — not the full figure canvas, which
        # let labels spill out of their cell into adjacent panels. Mirror
        # layout_panel's grid geometry (the compositor calls it with defaults).
        cell_bounds = _panel_cell_bounds(ir)

        result: list[LayoutEntry] = list(buckets[None])
        for panel in ir.panels:
            bucket = buckets.get(panel.id, [])
            label_fn = _label_requests_fn(panel.content.archetype)
            if label_fn is None or not bucket:
                result.extend(bucket)
                continue
            panel_offset = bucket[0].position  # shared by every sub-entry
            requests = label_fn(panel.content, bucket)
            effective_style = (panel_styles or {}).get(panel.id, style_dict)
            scope = LabelScope(
                bucket, requests, cell_bounds.get(panel.id, canvas),
                effective_style, panel_chain=(panel.id,), position=panel_offset,
            )
            placed = cls._place_scope(scope, strict_labels=strict_labels)
            # Leaders land between bucket and label entries, so the slice below
            # keeps them grouped with the labels for re-stamping.
            n = len(scope.entries)
            result.extend(placed[:n])
            for label_entry in placed[n:]:
                result.append(label_entry._replace(
                    panel_chain=scope.panel_chain,
                    position=scope.position,
                ))
        return result
