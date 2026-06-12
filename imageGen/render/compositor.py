"""Renderer & compositor — Phase 5.

Orchestrates the full pipeline from a validated IR `Figure` to a final
SVG/PNG/PDF file on disk.

Pipeline per call to `render_figure`:
  1. Resolve style preset (`style_name` kwarg overrides `ir.style_preset`;
     falls back to DEFAULT_PRESET from `styles/loader.py`).
  2. Dispatch IR archetype → layout engine → list[LayoutEntry].
  3. Auto-invoke label placement if the dispatched engine has a sibling
     `*_label_requests` helper and `labels=True` (D3).
  4. Compose into a single `svgwrite.Drawing` with IR-id tagging (D1)
     and write to disk.
  5. For non-SVG formats, convert the on-disk SVG into PNG/PDF via
     `render/export.py`. The SVG is persisted at
     `output_path.with_suffix(".svg")` next to the requested output so
     callers can inspect / debug it.

Archetype dispatch (v1 scope):
  - Multi-panel (`ir.panels` populated) → `layout_panel`; labels run
    per-panel via `LabelCoordinator.place` (render/label_coordinator.py).
    The flat `smiles_map` is broadcast to all panels (entity ids are
    unique by IR validation).
  - PATHWAY → `layout_pathway`; siblings: `pathway_label_requests`
  - REACTION_SCHEME → `layout_reaction`; requires `smiles_map` kwarg (D4).
    No label-request sibling — labels are baked into render_reaction.
  - All other leaf archetypes raise `NotImplementedError`.

IR-id tagging (D1):
  Every emitted `<g>` carries:
  - `data-ir-id="<raw-ir-id>"` — always; used by Phase 6 semantic_check.
  - `id="<scoped-id>"` — panel-chain prefix for document uniqueness.
    At depth 0 (no panel): scoped-id == raw-ir-id.

Step coupling:
  - Step 2 (done): REACTION_SCHEME + smiles_map dispatch.
  - Step 3 (done): PANEL dispatch — panel-keyed `_dispatch_layout`
    branch, per-panel placement via `LabelCoordinator`, per-entry
    panel_chain SVG-id scoping.
  - Step 4 (done): `render/export.py` wired in below; format != "svg"
    writes a sibling SVG then converts via cairosvg.
"""
from __future__ import annotations

import warnings
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Literal, NamedTuple

import svgwrite

from imageGen.ir.schema import Archetype, Figure
from imageGen.layout._archetype_plan import _ARCHETYPE_PLAN, ArchetypePlan
from imageGen.layout.panel_layout import (
    PANEL_DEFAULT_PARAMS,
    layout_panel,
)
from imageGen.layout.pathway_layout import compute_pathway_canvas
from imageGen.layout.reaction_layout import (
    is_linear_chain_reaction,
    layout_reaction,
)
from imageGen.layout.tier_layout import layout_tiers, tier_canvas
from imageGen.layout.types import LayoutEntry
from imageGen.render.export import svg_to_pdf, svg_to_png
# Label-step dispatch (P0a.3). _label_requests_fn lives here now but is
# re-exported so callers/tests that import it from compositor keep working.
from imageGen.render.label_coordinator import LabelCoordinator, _label_requests_fn
from imageGen.styles.loader import DEFAULT_PRESET, load_style

# Post-write SVG passes + figure-title chrome (R5 split). Imported here so they
# stay importable from ``imageGen.render.compositor`` unchanged; render_figure
# calls the first four and the rest are re-exported for any existing importer.
from imageGen.render._svg_post import (
    _PAGE_BG_DEFAULT,
    _SVG_OPEN_RE,
    _TITLE_GAP,
    _TITLE_SIZE_DEFAULT,
    _TITLED_ARCHETYPES,
    _VIEWBOX_RE,
    _WIDTH_RE,
    _HEIGHT_RE,
    _autocrop_svg,
    _expand_svg_to_content,
    _figure_title_group,
    _frame_box,
    _paint_page_background,
    _title_entry,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_CANVAS = (800.0, 600.0)

Format = Literal["svg", "png", "pdf"]


# ---------------------------------------------------------------------------
# Lowering plan (P0a.2) — resolve the dispatch axis ONCE, container-mode-first.
# ---------------------------------------------------------------------------


class LabelStrategy(Enum):
    """How a figure's labels are placed.

    BAKED   — the engine emits its own labels (tiers: scene-local placement).
    PER_PANEL — one collision-isolated placement pass per panel.
    LEAF    — a single figure-wide placement pass.
    """
    BAKED = "baked"
    PER_PANEL = "panel"
    LEAF = "leaf"


class LoweringPlan(NamedTuple):
    """The single record that decides how an IR Figure lowers to a render.

    Resolved once at the top of ``render_figure`` by ``_lowering_plan`` so the
    container/archetype precedence is decided in exactly one place
    (container-mode-first, archetype-second via ``_ARCHETYPE_PLAN``) instead of
    being re-tested at each concern. ``engine``/``archetype_plan`` are carried
    for introspection + the Step 6/7 adapters; ``render_figure`` itself reads
    ``canvas_fn`` / ``label_strategy`` / ``style_base`` (dispatch keeps going
    through ``_dispatch_layout`` so its pinned signature is untouched).
    """
    engine: Callable[..., list[LayoutEntry]] | None
    canvas_fn: Callable[[Figure], tuple[float, float]]
    label_strategy: LabelStrategy
    style_base: dict[str, Any]
    archetype_plan: ArchetypePlan | None


def _lowering_plan(ir: Figure, style_name: str | None) -> LoweringPlan:
    """Resolve the lowering plan once, container-mode-first.

    The schema's at-most-one-of-{leaf, panels, tiers} guard
    (``Figure._validate_structure``) makes this ``if/elif/else`` provably unable
    to mis-route. Archetype is resolved second, only for the leaf arm, via the
    single ``_ARCHETYPE_PLAN`` table. Call AFTER any archetype normalisation
    (e.g. the PH.1 multi-step coercion) so the plan sees the final archetype.
    """
    style_base = _resolve_style(ir, style_name)
    if ir.tiers:
        return LoweringPlan(layout_tiers, tier_canvas, LabelStrategy.BAKED,
                            style_base, None)
    if ir.panels:
        return LoweringPlan(layout_panel, lambda _fig: PANEL_DEFAULT_PARAMS["panel_canvas"],
                            LabelStrategy.PER_PANEL, style_base, None)
    plan = _ARCHETYPE_PLAN.get(ir.archetype)
    canvas_fn = plan.canvas_fn if plan is not None else (lambda _fig: _DEFAULT_CANVAS)
    engine = plan.engine if plan is not None else None
    return LoweringPlan(engine, canvas_fn, LabelStrategy.LEAF, style_base, plan)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def render_figure(
    ir: Figure,
    output_path: str | Path,
    *,
    style_name: str | None = None,
    format: Format | None = None,
    smiles_map: dict[str, str] | None = None,
    labels: bool = True,
    dpi: int = 300,
    display_dpi: int | None = None,
    canvas: tuple[float, float] | None = None,
    strict_labels: bool = False,
    autocrop: bool = False,
    legend: bool = False,
    credits: bool | str = "auto",
    pathway_fallback: bool = False,
) -> Path:
    """Render an IR Figure to a file and return the resolved output Path.

    Args:
        ir: Validated IR Figure (from `ir.schema`).
        output_path: Destination file path. Format is inferred from the
            suffix when `format` is None.
        style_name: Journal preset name (e.g., "nature"). Overrides
            `ir.style_preset`. Defaults to DEFAULT_PRESET when both
            are absent.
        format: Output format ("svg", "png", or "pdf"). None means infer
            from `output_path` suffix.
        smiles_map: {entity_id: SMILES string} for REACTION_SCHEME
            figures (required by `layout_reaction`).
        labels: When True (default), auto-invoke label placement if the
            dispatched layout engine has a sibling `*_label_requests`
            helper (D3). Pass False to suppress labels (debugging).
        dpi: Output resolution (default 300, journal quality). Forwarded
            to cairosvg for both PNG and PDF; PDFs use it only for any
            embedded raster bitmaps. Ignored when format == "svg".
        display_dpi: When set (e.g. 96), also writes a low-resolution
            screen copy at ``<stem>_display.png`` next to the deliverable.
            Never overwrites the main output. Ignored when format != "png".
        autocrop: When True, post-process the written SVG to trim excess
            whitespace (L22). If any canvas edge has more than 15% dead
            margin, the SVG's ``viewBox`` and ``width``/``height`` are
            rewritten in-place before any PNG/PDF export. Default False
            to preserve canonical dimensions in existing golden tests.
        pathway_fallback: When a REACTION_SCHEME is a *non-linear* multi-step
            graph (branching / convergence / cycle) the reaction engine cannot
            draw it (PH.1). Default False fails loud (NotImplementedError),
            matching ``layout_reaction``. Pass True to opt into rendering it
            through the pathway engine instead — entities render as labelled
            boxes and SMILES structures are dropped; a ``UserWarning`` is always
            emitted naming the original and coerced archetype.

    Returns:
        Resolved Path to the written file. For non-SVG formats a sibling
        SVG is also written at `output_path.with_suffix(".svg")`.

    Raises:
        NotImplementedError: For archetypes not yet wired in the
            compositor, or a non-linear multi-step REACTION_SCHEME when
            ``pathway_fallback`` is False.
        ValueError: For unrecognised file suffix when `format` is None.
        LabelPlacementError: Propagated from `place_labels` when a label
            cannot be placed at any candidate position.
    """
    output_path = Path(output_path)
    fmt = _resolve_format(output_path, format)
    # R6/PH.1: a multi-step reaction (one entity is both source and target) that
    # forms a single linear chain renders as a molecule sequence by
    # layout_reaction. Only non-linear multi-step graphs (branching / convergence
    # / cycles) can't be drawn as a reaction. Those FAIL LOUD by default (matching
    # layout_reaction's own NotImplementedError); the pathway fallback is an
    # explicit opt-in (pathway_fallback=True) that *always* warns (not just when a
    # smiles_map is present, which previously made the no-smiles downgrade silent)
    # and names the original + coerced archetype. This normalise runs BEFORE the
    # lowering plan resolves, so the plan + every downstream consumer (dispatch,
    # label strategy, canvas sizing) see the final archetype in one decision.
    if _is_multistep_reaction(ir) and not is_linear_chain_reaction(ir):
        if not pathway_fallback:
            raise NotImplementedError(
                f"{ir.archetype.value!r} figure is a non-linear multi-step "
                "reaction (branching / convergence / cycle); the reaction "
                "engine cannot draw it. Re-encode parallel reactions as "
                "separate reactant→product edges, or pass pathway_fallback=True "
                "to render it through the pathway engine (SMILES structures "
                "will not be drawn)."
            )
        warnings.warn(
            f"Non-linear multi-step reaction coerced from "
            f"{ir.archetype.value!r} to {Archetype.PATHWAY.value!r}: SMILES "
            "structures will not be drawn (entities render as labelled boxes). "
            "Re-encode parallel reactions as separate reactant→product edges "
            "to keep chemical structures.",
            UserWarning,
            stacklevel=2,
        )
        ir = ir.model_copy(update={"archetype": Archetype.PATHWAY})

    # P0a.2: resolve the lowering plan ONCE (container-mode-first); route style,
    # canvas, and the label strategy through it. Dispatch keeps going through
    # _dispatch_layout (pinned signature) which makes the same container decision.
    plan = _lowering_plan(ir, style_name)
    style_dict = plan.style_base
    # ST4: build per-panel style dicts for panels whose preset differs from top-level.
    panel_styles = _build_panel_styles(ir, style_name) if ir.panels else {}
    entries = _dispatch_layout(ir, style_dict, smiles_map, panel_styles=panel_styles)

    # L18: compute canvas before label placement so the bounds can be forwarded
    # to place_labels, preventing labels from rendering outside the SVG viewport.
    computed_canvas = plan.canvas_fn(ir)

    # Label placement (P0a.3): the LabelCoordinator dispatches container-mode-
    # first — tiers bake their own scene labels (inert pass-through today; P5.2
    # flips that arm to scene-local placement), panels place per-cell, leaf
    # places figure-wide. plan.label_strategy is the same decision, carried for
    # introspection; the labels=False short-circuit stays here.
    if labels:
        entries = LabelCoordinator.place(
            ir, entries, style_dict, strict_labels=strict_labels,
            canvas=computed_canvas, panel_styles=panel_styles,
        )

    final_canvas = canvas if canvas is not None else computed_canvas

    # FR1: draw figure annotations (label / caption / scale_bar) last so they
    # sit above figure content. Until this, `figure.annotations` was never read
    # and these were silent no-ops despite fixtures relying on them.
    if ir.annotations:
        from imageGen.render.annotations import annotation_entries  # noqa: PLC0415
        # P5.3: for tiered figures, seed the annotation pass with the bboxes of
        # the scene-local labels the tier engine already placed, so a global
        # annotation and a scene label can no longer silently overlap. Every
        # other path passes occupied=None → annotations render verbatim.
        occupied = None
        if ir.tiers:
            from imageGen.layout.label_placement import label_entry_bbox  # noqa: PLC0415
            occupied = [b for e in entries
                        if (b := label_entry_bbox(e)) is not None]
        entries = entries + annotation_entries(
            ir, final_canvas, style_dict, occupied=occupied)

    # Render the spec title as a heading above the figure for the archetypes
    # that otherwise ship headless. Placed in negative-y headroom that the FR3
    # frame-expansion below grows into, so it needs no canvas pre-sizing. Scoped
    # to top-level mechanism_cartoon / workflow figures (panels carry their own
    # per-panel title chrome).
    title_entry = _title_entry(ir, final_canvas, style_dict)
    if title_entry is not None:
        entries = entries + [title_entry]

    # Unified info box (Issue #4 legend + FR9 abbreviation glossary + icon
    # credits) in a strip *below* the figure (canvas grows downward) so the key
    # never overlaps figure content. Consolidates what used to be a top-right
    # legend overlay and a separate glossary strip into one box for ease of
    # reading. Drawn only when a section has content (an all-empty box is never
    # emitted, so figures with none of the three stay byte-identical).
    legend_keys: list[str] = []
    legend_captions: dict[str, str] = {}
    if legend:
        from imageGen.render.legend import (  # noqa: PLC0415
            legend_captions_for_figure,
            legend_glyph_keys_for_figure,
        )
        legend_keys = legend_glyph_keys_for_figure(ir)
        legend_captions = legend_captions_for_figure(ir)
    glossary_entries = list(ir.glossary or [])
    from imageGen.render.credits import (  # noqa: PLC0415
        credit_lines as _credit_lines,
        write_credits_sidecar as _write_credits_sidecar,
    )
    credit_section = _credit_lines(ir, credits)
    if legend_keys or glossary_entries or credit_section:
        from imageGen.render.info_box import info_box, info_box_size  # noqa: PLC0415
        bw, bh = info_box_size(
            legend_keys, glossary_entries, credit_section, style_dict,
            legend_captions,
        )
        cw, ch = final_canvas
        ipad = 12.0
        entries = entries + [LayoutEntry(
            info_box,
            ((ipad, ch + ipad),),
            {"legend_keys": legend_keys, "glossary_entries": glossary_entries,
             "credit_lines": credit_section, "style_dict": style_dict,
             "legend_captions": legend_captions},
            position=(0.0, 0.0),
            ir_id="info_box",
        )]
        final_canvas = (max(cw, bw + 2 * ipad), ch + bh + 2 * ipad)
    # Durable per-figure attribution record for any embedded icons used.
    _write_credits_sidecar(ir, output_path, credits)

    svg_path = output_path if fmt == "svg" else output_path.with_suffix(".svg")
    _write_svg(entries, final_canvas, svg_path)
    # FR3: grow the frame to rescue any label/annotation drawn past the canvas
    # edge. Always on — a truncated label is never desired — and a no-op when
    # content fits, so figures without overflow stay byte-identical. Runs before
    # autocrop so the (now fully-enclosed) content survives any subsequent trim.
    _expand_svg_to_content(svg_path)
    if autocrop:
        _autocrop_svg(svg_path)
    # Paint the page background LAST, after the frame is finalized, so the rect
    # always matches the shipped viewBox (a write-time rect wouldn't cover the
    # headroom FR3 grows for a title). Kills the transparent→black void.
    _paint_page_background(svg_path, style_dict)
    if fmt == "png":
        svg_to_png(svg_path, output_path, dpi=dpi)
        if display_dpi is not None:
            display_path = output_path.with_stem(output_path.stem + "_display")
            svg_to_png(svg_path, display_path, dpi=display_dpi)
    elif fmt == "pdf":
        svg_to_pdf(svg_path, output_path, dpi=dpi)
    return output_path


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _resolve_style(ir: Figure, style_name: str | None) -> dict[str, Any]:
    """Return the style overrides dict, preferring kwarg > ir.style_preset > default."""
    name = style_name or ir.style_preset or DEFAULT_PRESET
    return load_style(name)


def _build_panel_styles(
    ir: Figure, top_style_name: str | None
) -> dict[str, dict[str, Any]]:
    """Return per-panel style dicts for panels whose preset differs from the top level.

    ST4: ``panel.content.style_preset`` is the per-panel preset selector. If a
    panel's preset matches the top-level preset (resolved from kwarg >
    ir.style_preset > default), we skip it — the global style_dict already
    covers it. Only panels that differ from the top-level get entries here;
    the caller falls back to the global style for the rest.
    """
    top_name = top_style_name or ir.style_preset or DEFAULT_PRESET
    result: dict[str, dict[str, Any]] = {}
    for panel in ir.panels:
        panel_preset = panel.content.style_preset or DEFAULT_PRESET
        if panel_preset != top_name:
            result[panel.id] = load_style(panel_preset)
    return result or {}


def _resolve_format(
    output_path: Path, format: Format | None
) -> Format:
    if format is not None:
        return format
    suffix = output_path.suffix.lstrip(".")
    if suffix not in {"svg", "png", "pdf"}:
        raise ValueError(
            f"Cannot infer output format from suffix {output_path.suffix!r}; "
            "pass format= explicitly or use .svg / .png / .pdf"
        )
    return suffix  # type: ignore[return-value]


def _is_multistep_reaction(ir: Figure) -> bool:
    """True when *ir* is a REACTION_SCHEME with an intermediate entity.

    An intermediate is an entity that is both the source of one relation and
    the target of another -- i.e. a multi-step reaction (A→B→C). `layout_reaction`
    raises NotImplementedError on these because a single-row reactant→product
    layout can't express a chain; the official answer (BACKLOG R3) is to render
    them as a pathway. The routing decision lives here at dispatch time;
    `layout_reaction` keeps its fail-loud contract when called directly.
    """
    if ir.archetype != Archetype.REACTION_SCHEME:
        return False
    sources = {r.source for r in ir.relations}
    targets = {r.target for r in ir.relations}
    return bool(sources & targets)


def _dispatch_layout(
    ir: Figure,
    style_dict: dict[str, Any],
    smiles_map: dict[str, str] | None,
    panel_styles: dict[str, dict[str, Any]] | None = None,
) -> list[LayoutEntry]:
    """Call the appropriate layout engine for the IR shape.

    Multi-panel figures (`ir.panels` populated) dispatch to
    `layout_panel` regardless of top-level archetype. Leaf figures
    dispatch on `ir.archetype`: every pathway-compatible archetype
    (PATHWAY, WORKFLOW, CELLULAR_SCHEMATIC, MECHANISM_CARTOON) →
    layout_pathway, REACTION_SCHEME → layout_reaction. The trailing
    NotImplementedError guards any future archetype enum addition.

    The flat `smiles_map: {entity_id: SMILES}` is adapted to the nested
    `{panel.id: smiles_map}` shape that `layout_panel` expects — entity
    ids are unique across the figure (IR validates), so broadcasting
    the same dict to every panel is safe.

    ``panel_styles`` (V2/ST4): per-panel style dicts keyed by panel id.
    Passed through to ``layout_panel`` so each panel's sub-engine uses
    its own preset.
    """
    if ir.tiers:
        # V3 scene chassis: lower the tier/scene graph through the tier engine.
        # It self-sizes via tier_canvas (the same function _canvas_size uses for
        # the SVG viewport), so baked coords and viewport agree. Scene labels /
        # badges are emitted by the engine, so the compositor skips the pathway
        # label pass for tiered figures (see render_figure).
        return layout_tiers(ir, style_dict=style_dict)
    if ir.panels:
        smiles_maps = (
            {p.id: smiles_map for p in ir.panels} if smiles_map else None
        )
        return layout_panel(
            ir, smiles_maps=smiles_maps, style_dict=style_dict,
            style_dicts=panel_styles or None,
        )
    plan = _ARCHETYPE_PLAN.get(ir.archetype)
    if plan is None:
        raise NotImplementedError(
            f"Archetype {ir.archetype!r} is not yet wired in the compositor "
            "(and the figure has no panels)."
        )
    if plan.engine is layout_reaction:
        if smiles_map is None:
            missing = [e.id for e in ir.entities]
            raise ValueError(
                f"smiles_map required for REACTION_SCHEME; "
                f"missing entity ids: {missing}"
            )
        return layout_reaction(ir, smiles_map=smiles_map, style_dict=style_dict)
    return plan.engine(ir, style_dict=style_dict)


def _canvas_size(ir: Figure, entries: list[LayoutEntry]) -> tuple[float, float]:
    """Return (width, height) of the SVG viewport.

    Pathway-family figures get a content-aware canvas (see
    `_compute_pathway_canvas`) clamped to the v1 default `(800, 600)` so
    small figures stay golden-image-identical. Panels and reactions still
    use their respective static defaults — those engines lay out within a
    fixed envelope already. Tiered figures size through `tier_canvas`, the
    same function `layout_tiers` uses, so the viewport matches the baked
    coordinates exactly.
    """
    if ir.tiers:
        return tier_canvas(ir)
    if ir.panels:
        return PANEL_DEFAULT_PARAMS["panel_canvas"]
    plan = _ARCHETYPE_PLAN.get(ir.archetype)
    if plan is not None:
        return plan.canvas_fn(ir)
    return _DEFAULT_CANVAS


def _compute_pathway_canvas(figure: Figure) -> tuple[float, float]:
    """Content-aware canvas for pathway-family figures.

    V2: delegates to ``pathway_layout.compute_pathway_canvas`` so the
    formula is defined in one place and both the compositor (SVG viewport)
    and ``layout_pathway`` (band geometry) agree on the canvas size.

    Kept as a private function here so existing tests that import it from
    this module continue to work unchanged.
    """
    return compute_pathway_canvas(figure)


def scoped_id(raw_ir_id: str, panel_chain: tuple[str, ...]) -> str:
    """Build a document-unique SVG id from the panel hierarchy prefix + raw id (D1)."""
    if panel_chain:
        return "__".join((*panel_chain, raw_ir_id))
    return raw_ir_id


def _tag_group(
    group: svgwrite.container.Group,
    raw_ir_id: str,
    panel_chain: tuple[str, ...] = (),
) -> None:
    """Set id (scoped) and data-ir-id (raw) on a Group in-place (D1).

    Disables debug-mode validation on the group before writing so that
    data-* attributes (valid SVG 1.1 / HTML5 custom attributes) are not
    rejected by svgwrite's strict built-in allowlist. The group's
    children are unaffected — each element carries its own debug flag.
    """
    group._parameter.debug = False  # allow data-* attrs; debug is a read-only property
    group.attribs["id"] = scoped_id(raw_ir_id, panel_chain)
    group.attribs["data-ir-id"] = raw_ir_id


def _write_svg(
    entries: list[LayoutEntry],
    canvas: tuple[float, float],
    output_path: Path,
) -> None:
    """Execute layout entries into an svgwrite Drawing and write to disk.

    Per-entry `panel_chain` (set by `layout_panel`) drives SVG-id
    scoping; non-panel figures leave it as () and scoped id == raw id.
    """
    w, h = canvas
    # debug=False disables svgwrite's strict SVG attribute validation so we
    # can emit data-* attributes (data-ir-id) which are valid SVG 1.1/HTML5
    # but not in svgwrite's built-in allowlist.
    dwg = svgwrite.Drawing(str(output_path), size=(w, h), debug=False)

    for entry in entries:
        group: svgwrite.container.Group = entry.primitive(*entry.args, **entry.kwargs)
        px, py = entry.position
        if px != 0.0 or py != 0.0:
            group["transform"] = f"translate({px},{py})"
        if entry.ir_id is not None:
            _tag_group(group, entry.ir_id, entry.panel_chain)
        dwg.add(group)

    dwg.save()
