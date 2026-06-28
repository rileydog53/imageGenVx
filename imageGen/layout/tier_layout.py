"""V3 scene-chassis layout engine — minimal vertical slice (Step 3).

Lowers a tiered ``Figure`` to a ``list[LayoutEntry]``, proving the
schema -> engine -> SVG path end to end through real engine code (not the
hand-assembled keystone slice).

Scope is deliberately a SLICE, not the finished chassis:
  - Tiers: a TITLE band (title + subtitle) and a SCENE_ROW of equal columns;
    SUMMARY_BAR / BAND render only their band background (no inner content yet).
  - Scenes: MOLECULE and TEXT slots, placed by the topological attach/offset
    solver (roots centred, face attach = edge-to-edge gap, then co-located boxes
    de-overlapped — P5.1). Scene-local label collision is still pending (P5.2).
  - Edges: intra-scene ``SceneEdge`` (dashed / curved H-bond) and cross-cell
    ``TierEdge`` (transition arrow), resolved through the ``AnchorRegistry`` with
    endpoint standoff and optional rail clamping.
  - ``step_sequence`` expands to one concrete ``Scene`` per step
    (``expand_step_sequence`` — Step 6), which then flows through the same
    column layout as authored scenes. Unsupported ``SlotKind``s still raise
    ``NotImplementedError`` (mirrors the compositor's unregistered-archetype
    guard) — they arrive with the primitive refresh.
  - ``Tier.overlays`` (gutter/free scenes) lay out in a bottom gutter strip of
    the band and publish anchors before transitions resolve, so a ``TierEdge``
    can connect a row scene to an overlay (the departing-fragment pattern).

Coordinate model: every entry carries baked absolute coordinates. ``position``
is the slot's top-left for MOLECULE slots (the only entry whose primitive draws
at a local origin); it is ``(0, 0)`` for text, intra-scene edges, and transition
arrows, which bake their absolute points into the closure — the same pattern
``_write_svg`` already consumes. Anchors are published into a fresh per-call
``AnchorRegistry`` keyed ``"scene.slot.anchor"`` (atom anchors) and
``"scene.<frame>"`` (scene-edge anchors), the grammar the schema's reference
strings use.

Phase coupling: the compositor does not call this engine yet — Step 4 wires it
into ``render_figure`` (canvas sizing, band chrome, label placement, crop). For
now the engine is exercised directly (like the other layout engines in tests).
"""
from __future__ import annotations

import copy
import math
from typing import Any, Callable

import svgwrite.container
import svgwrite.path
import svgwrite.shapes
import svgwrite.text

from imageGen.ir.schema import (
    Figure,
    RailAxis,
    Scene,
    SceneEdge,
    SceneEdgeType,
    Slot,
    SlotKind,
    StepOp,
    StepSequence,
    Tier,
    TierEdge,
    TierRole,
)
from imageGen.layout.anchors import AnchorRegistry
from imageGen.layout.label_placement import LabelRequest, place_labels
from imageGen.layout.types import LayoutEntry
from imageGen.primitives.chemistry import (
    molecule_natural_size,
    render_molecule_anchored,
    render_residue_anchored,
)
from imageGen.primitives._mol_render import (
    _RESIDUE_SMILES,
    _align_to_reference,
    _orient_conformer,
    _smiles_to_mol,
)
from imageGen.primitives.primitive_specs import PRIMITIVE_REGISTRY, PRIMITIVE_TO_BBOX
from imageGen.primitives.proteins import protein_blob
from imageGen.styles.loader import merge_style


# ---------------------------------------------------------------------------
# Layout knobs (flat namespaced keys, Phase-4 preset union convention).
# ---------------------------------------------------------------------------

TIER_DEFAULT_PARAMS: dict[str, Any] = {
    # ``tier_canvas`` is a FALLBACK only: when ``layout_params`` does not pin it,
    # ``tier_canvas()`` computes a content-aware canvas (cols x cell width,
    # per-tier natural heights). Pinning it (the tests do) bypasses that.
    "tier_canvas": (600.0, 300.0),
    "tier_margin": 20.0,
    "tier_gutter": 24.0,
    # Vertical gap between stacked tiers. A clean strip between bands (a) reads as
    # intentional panel separation so a reader can tell the bands apart, and (b)
    # buffers the seam so a caption at the bottom of one band and a label/arrow at
    # the top of the next don't collide (the cross-band overlap defect).
    "tier_band_gap": 18.0,
    "tier_slot_size": (180.0, 140.0),
    # dim-1/5: BLOB / GLYPH slots no longer fill the uniform slot cell. A GLYPH
    # draws at its primitive's *registered* natural bbox (PRIMITIVE_TO_BBOX) ×
    # ``style['scale']`` — so a tablet / pg_cluster renders molecule-scale and a
    # protein blob renders bigger, in proportion with the chemistry (which is
    # content-sized to ``chem_target_bond_px``) instead of every glyph filling the
    # same 180×140 box. A BLOB is a cavity *container* (it can hold a molecule in
    # its pocket — succinate is ~120px wide), so it keeps a generous dedicated box
    # rather than the small protein_blob glyph bbox; ``style['scale']`` still tunes
    # it. Sized to comfortably hold a typical small-molecule substrate.
    "tier_blob_size": (160.0, 124.0),
    # Content-aware chemistry sizing (pub-grade): every MOLECULE/RESIDUE renders
    # at this bond length, so the whole figure shares one chemistry scale instead
    # of each molecule auto-filling its slot box (which made bond length swing
    # ~10x). The drawn box is derived from the molecule, not the slot. ``tier_mol_pad``
    # is the label margin around that box. Set ``chem_target_bond_px`` to 0/None to
    # fall back to the legacy slot-box sizing.
    "chem_target_bond_px": 22.0,
    "tier_mol_pad": 14.0,
    "tier_edge_standoff": 8.0,
    # D5 (pub-grade): cross-cell transition arrows stand off the scene *content*
    # edge by more than intra-scene atom edges do, so the arrowhead clears the
    # next scene's structure instead of crowding it (~one bond length). Kept
    # separate from tier_edge_standoff, which must stay tight so curly/H-bond
    # arrows still originate on their atoms.
    "tier_transition_standoff": 20.0,
    # D4: clearance between a transition arrow shaft and its label baseline (added
    # to half the caption font), so the label rides above the arrow not across it.
    "tier_transition_label_gap": 6.0,
    "tier_title_font_size": 18,
    "tier_subtitle_font_size": 13,
    # Title->subtitle baseline separation as a multiple of the title font size.
    # Must clear the legibility bbox heuristic (~0.24*title + 0.96*subtitle of
    # box height) regardless of how thin the TITLE band's height_frac makes it,
    # so the two lines never trip a false overlap report. 1.25 leaves margin.
    "tier_title_subtitle_em": 1.25,
    "tier_text_font_size": 12,
    "tier_text_color": "#1A1A1A",
    "tier_font_family": "Helvetica, Arial, sans-serif",
    # Content-aware sizing knobs (consumed by tier_canvas / _tier_rects).
    "tier_cell_pad_x": 45.0,       # horizontal slack each side of a slot in its cell
    "tier_scene_row_extra": 50.0,  # headroom for a scene row beyond the slot height
    "tier_title_band_height": 64.0,
    "tier_bar_band_height": 60.0,
    "tier_canvas_min": (400.0, 200.0),
    # Scene chrome.
    "tier_badge_radius": 11.0,
    "tier_badge_fill": "#444444",
    "tier_badge_text_color": "#FFFFFF",
    "tier_badge_inset": 6.0,       # badge centre inset from the cell top-left
    "tier_caption_font_size": 12,
    "tier_caption_gap": 12.0,      # gap below content before the scene caption
    "tier_caption_line_step": 1.25,  # line height as a multiple of font size
    # Overlay (gutter/free) scenes: when a SCENE_ROW tier carries ``overlays``,
    # the main row takes the top (1 - frac) of the band and the overlays a
    # bottom gutter strip of this fraction. First-cut heuristic — tune as the
    # aspirin/COX-1 north-star (departing-fragment overlay) is built out.
    "tier_overlay_gutter_frac": 0.3,
    # Band chrome defaults (a tier's ``style`` overrides per key).
    "tier_band_radius": 4.0,
    "tier_band_stroke_width": 1.0,
    "tier_divider_color": "#BBBBBB",
    "tier_divider_width": 1.0,
}

# P0b.1: project the base journal preset's text keys onto the tier engine's
# param names, so a tiered figure honours its journal preset (the engine
# previously dropped ``style_dict`` entirely). Only colour + family are mapped —
# NOT ``label_font_size``: the tier engine uses three distinct sizes
# (title/subtitle/caption) that a single preset size would wrongly collapse, and
# remapping it can flip the geometric legibility check. Structural styling (edge
# colours, band chrome) deliberately keeps its own per-type defaults — the base
# preset's primitive vocabulary (bare ``stroke``/``stroke_width``) collides with
# the chassis edge keys, so it must NOT bleed there (see the content/structural
# split in :func:`_layout_scene` — P0b.2).
_PRESET_TO_TIER_PARAM: dict[str, str] = {
    "label_font_color": "tier_text_color",
    "label_font_family": "tier_font_family",
}


def _preset_tier_params(style_dict: dict[str, Any] | None) -> dict[str, Any]:
    """Map the base preset's text keys onto tier param names (P0b.1)."""
    if not style_dict:
        return {}
    return {param: style_dict[key]
            for key, param in _PRESET_TO_TIER_PARAM.items()
            if key in style_dict}


# Per-SceneEdgeType drawing defaults; ``edge.style`` overrides "stroke" and
# "stroke_width".  Dim-4 (layering/contrast): each semantic type carries its own
# colour so that overlapping ink remains distinguishable:
#   hbond  — biochem blue  (universal H-bond convention; distinct from inhibits red)
#   dashed — neutral gray  (partial/TS bond; distinct from hbond and inhibits)
#   curly  — dark auburn   (electron-flow arrows; distinct from black bond ink)
_EDGE_DEFAULTS: dict[str, dict[str, Any]] = {
    "hbond":      {"stroke": "#1A6FC9", "stroke_width": 1.5,
                   "dash": "4,3", "curved": True,  "arrow": False},
    "dashed":     {"stroke": "#888888", "dash": "4,3", "curved": False, "arrow": False},
    "curly":      {"stroke": "#8B2500", "dash": None,  "curved": True,  "arrow": True, "head_w": 0.4},
    "transition": {"stroke": "#1A1A1A", "dash": None,  "curved": False, "arrow": True},
    "departs":    {"stroke": "#33AA33", "dash": None,  "curved": False, "arrow": True},
    "binds":      {"stroke": "#1A1A1A", "dash": None,  "curved": False, "arrow": True},
    "activates":  {"stroke": "#1A1A1A", "dash": None,  "curved": False, "arrow": True},
    "inhibits":   {"stroke": "#CC2222", "dash": None,  "curved": False, "arrow": False, "tbar": True},
    "generic":    {"stroke": "#1A1A1A", "dash": None,  "curved": False, "arrow": True},
}


# ---------------------------------------------------------------------------
# Geometry helpers
# ---------------------------------------------------------------------------

def _tier_natural_height(tier: Tier, params: dict[str, Any]) -> float:
    """A tier's intrinsic height for content-aware sizing, by role.

    A TITLE band needs only typography headroom; a SCENE_ROW needs a slot plus
    caption/badge headroom; SUMMARY_BAR / BAND are thin strips. Used both to
    size the canvas (``tier_canvas``) and to weight the band split when no
    ``height_frac`` is declared (``_tier_rects``)."""
    _sw, sh = params["tier_slot_size"]
    if tier.role == TierRole.TITLE:
        return float(params["tier_title_band_height"])
    if tier.role == TierRole.SCENE_ROW:
        return float(sh) + float(params["tier_scene_row_extra"])
    return float(params["tier_bar_band_height"])


def _tier_rects(
    tiers: list[Tier], canvas: tuple[float, float], margin: float,
    params: dict[str, Any],
) -> list[tuple[Tier, tuple[float, float, float, float]]]:
    """Stack tiers vertically, distributing the content height by weight.

    Weights are each tier's ``height_frac`` when *every* tier declares one
    (author intent), else each tier's role-based natural height (so a title
    band stays compact and a scene row gets room without manual fractions).
    Either way the weights are normalised to fill the inner height, so a pinned
    canvas is honoured exactly and an auto-sized canvas (whose inner height is
    the natural sum) is filled without remainder."""
    w, h = canvas
    inner_w = w - 2 * margin
    inner_h = h - 2 * margin
    gap = float(params["tier_band_gap"])
    # Reserve the inter-band gaps before distributing the rest by weight, so the
    # bands + gaps exactly fill the inner height (pinned or auto-sized).
    avail_h = max(0.0, inner_h - gap * max(0, len(tiers) - 1))
    fracs = [t.height_frac for t in tiers]
    if tiers and all(f is not None for f in fracs):
        weights = [float(f) for f in fracs]
    else:
        weights = [_tier_natural_height(t, params) for t in tiers]
    total = sum(weights) or 1.0
    heights = [avail_h * (wt / total) for wt in weights]
    rects: list[tuple[Tier, tuple[float, float, float, float]]] = []
    y = margin
    for tier, th in zip(tiers, heights):
        rects.append((tier, (margin, y, inner_w, th)))
        y += th + gap
    return rects


def tier_canvas(
    figure: Figure, layout_params: dict[str, Any] | None = None
) -> tuple[float, float]:
    """Content-aware canvas ``(w, h)`` for a tiered figure.

    Width is driven by the widest SCENE_ROW (columns x cell width + gutters +
    margins); height is the sum of per-tier natural heights + margins. When
    ``layout_params`` pins ``tier_canvas`` it is returned verbatim (the tests
    and any caller that wants a fixed envelope), so the layout engine and the
    compositor's viewport agree by both routing through this one function.

    Mirrors ``pathway_layout.compute_pathway_canvas``: the size formula lives in
    one place so ``layout_tiers`` (which bakes absolute coords) and
    ``compositor._canvas_size`` (the SVG viewport) never drift apart."""
    if layout_params and "tier_canvas" in layout_params:
        w, h = layout_params["tier_canvas"]
        return (float(w), float(h))
    params = {**TIER_DEFAULT_PARAMS, **(layout_params or {})}
    margin = float(params["tier_margin"])
    gutter = float(params["tier_gutter"])
    # Content-aware, PER-TIER width: each SCENE_ROW sizes its columns to its own
    # widest scene (not a single slot, and not one global max), so a multi-slot
    # scene no longer overflows its cell into the neighbour ("steps out of the
    # box / merged steps") AND a wide summary band doesn't blow the mechanism row
    # out to a sparse, long-arrow layout. The canvas is the widest tier's block.
    width = 2 * margin + max(
        (_tier_block_width(t, params, gutter)
         for t in figure.tiers if t.role == TierRole.SCENE_ROW),
        default=0.0,
    )
    naturals = [_tier_natural_height(t, params) for t in figure.tiers]
    gap_total = float(params["tier_band_gap"]) * max(0, len(figure.tiers) - 1)
    fracs = [t.height_frac for t in figure.tiers]
    if figure.tiers and all(f is not None and f > 0 for f in fracs):
        # Honour the author's fracs as PROPORTIONS, but size the inner height so
        # every band's frac-share still clears its natural height (content + label
        # room) — otherwise a small-frac band (e.g. a 0.25 summary) is too short to
        # hold its labels and they spill across the band edge.
        sf = sum(float(f) for f in fracs)
        inner = max(n * sf / float(f) for n, f in zip(naturals, fracs))
    else:
        inner = sum(naturals)
    height = 2 * margin + inner + gap_total
    min_w, min_h = params["tier_canvas_min"]
    return (max(width, float(min_w)), max(height, float(min_h)))


def _column_rects(
    rect: tuple[float, float, float, float], n: int, gutter: float
) -> list[tuple[float, float, float, float]]:
    """Split ``rect`` into ``n`` equal-width columns separated by ``gutter``."""
    x, y, w, h = rect
    if n <= 0:
        return []
    col_w = (w - gutter * (n - 1)) / n
    return [(x + i * (col_w + gutter), y, col_w, h) for i in range(n)]


# ---------------------------------------------------------------------------
# Edge drawing
# ---------------------------------------------------------------------------

def _arrow_head(p0: tuple[float, float], p1: tuple[float, float], color: str,
                size: float = 8.0, width_frac: float = 0.5) -> svgwrite.shapes.Polygon:
    """A filled triangular arrowhead at ``p1`` pointing along p0->p1.

    ``width_frac`` is the half-width as a fraction of ``size``; the 0.5 default is
    the blunt pathway/transition head, a smaller value (P7.2) gives the narrower,
    pen-like head of an organic-chem arrow-pushing curly arrow."""
    x0, y0 = p0
    x1, y1 = p1
    angle = math.atan2(y1 - y0, x1 - x0)
    bx = x1 - size * math.cos(angle)
    by = y1 - size * math.sin(angle)
    px, py = -math.sin(angle) * size * width_frac, math.cos(angle) * size * width_frac
    return svgwrite.shapes.Polygon(
        points=[(round(x1, 2), round(y1, 2)),
                (round(bx + px, 2), round(by + py, 2)),
                (round(bx - px, 2), round(by - py, 2))],
        fill=color, stroke="none",
    )


def _edge_group(
    p0: tuple[float, float], p1: tuple[float, float], edge_type: SceneEdgeType,
    edge_style: dict[str, Any] | None,
) -> svgwrite.container.Group:
    """Draw one edge p0->p1 per its type (dashed/curved line, arrow, or both)."""
    spec = _EDGE_DEFAULTS.get(edge_type.value, _EDGE_DEFAULTS["generic"])
    stroke = str((edge_style or {}).get("stroke", spec["stroke"]))
    # Per-type default width from spec (e.g. hbond is thinner at 1.5); caller
    # can still override via edge_style["stroke_width"].
    width = float((edge_style or {}).get("stroke_width", spec.get("stroke_width", 2.0)))
    g = svgwrite.container.Group()
    if (edge_style or {}).get("partial"):
        # P7.3b: a transition-state partial bond — a thin, finely-dashed straight
        # stub between two atom anchors (a breaking/forming half-bond). An
        # anchor-pair overlay, never an arrow or T-bar; overrides the type's
        # heavier dash/width so it reads as a fractional bond.
        bond = svgwrite.shapes.Line(
            start=p0, end=p1, stroke=stroke,
            stroke_width=float((edge_style or {}).get("stroke_width", 1.2)))
        bond["stroke-dasharray"] = str((edge_style or {}).get("dash", "2,2.5"))
        bond["stroke-linecap"] = "round"
        g.add(bond)
        return g
    head_from = p0  # arrowhead is aimed along this->p1; for a curve, the tangent
    if spec["curved"]:
        (x0, y0), (x1, y1) = p0, p1
        dx, dy = x1 - x0, y1 - y0
        length = math.hypot(dx, dy) or 1.0
        bow = float((edge_style or {}).get("bow", min(20.0, length * 0.25)))
        # P7.2 (MF-2): handedness + arc control for arrow-pushing. ``px,py`` is the
        # unit perpendicular to the left of p0->p1; ``side`` flips which way the
        # arc bulges. Both default so every existing curved edge (hbond / curly)
        # stays byte-identical: side=+1 reproduces the old single-perp control.
        px, py = -dy / length, dx / length
        curl = str((edge_style or {}).get("curl", "")).lower()
        side = -1.0 if curl in ("cw", "right", "-1", "-") else 1.0
        arc = str((edge_style or {}).get("arc", "c")).lower()
        attrs = {"fill": "none", "stroke": stroke, "stroke_width": width}
        if spec["dash"]:
            attrs["stroke_dasharray"] = spec["dash"]
        if arc == "s":
            # S-shaped cubic: the two control points bow to OPPOSITE sides, the
            # swing-out-and-back of electron flow around an intervening atom.
            c1 = (x0 + dx / 3.0 + px * bow * side, y0 + dy / 3.0 + py * bow * side)
            c2 = (x0 + 2.0 * dx / 3.0 - px * bow * side,
                  y0 + 2.0 * dy / 3.0 - py * bow * side)
            g.add(svgwrite.path.Path(
                d=(f"M {x0:.2f},{y0:.2f} C {c1[0]:.2f},{c1[1]:.2f} "
                   f"{c2[0]:.2f},{c2[1]:.2f} {x1:.2f},{y1:.2f}"), **attrs))
            head_from = c2  # cubic arrives at p1 tangent to c2->p1
        else:
            mx, my = (x0 + x1) / 2.0, (y0 + y1) / 2.0
            cx, cy = mx + px * bow * side, my + py * bow * side
            g.add(svgwrite.path.Path(
                d=f"M {x0:.2f},{y0:.2f} Q {cx:.2f},{cy:.2f} {x1:.2f},{y1:.2f}",
                **attrs))
            head_from = (cx, cy)  # quadratic arrives at p1 tangent to c->p1
    else:
        attrs = {"start": p0, "end": p1, "stroke": stroke, "stroke_width": width}
        if spec["dash"]:
            attrs["stroke_dasharray"] = spec["dash"]
        g.add(svgwrite.shapes.Line(**attrs))
    if spec["arrow"]:
        head_w = float((edge_style or {}).get("head_width", spec.get("head_w", 0.5)))
        g.add(_arrow_head(head_from, p1, stroke, width_frac=head_w))
    if spec.get("tbar"):
        # P7.3c: an INHIBITS edge terminates in a flat perpendicular T-bar, never
        # an arrowhead (repression vs. activation carry opposite meaning). Mirrors
        # the pathway T-bar convention `convention_check` enforces: a square-capped
        # <line> across p1, perpendicular to the incoming tangent.
        hx, hy = head_from
        dx, dy = p1[0] - hx, p1[1] - hy
        length = math.hypot(dx, dy) or 1.0
        px, py = -dy / length, dx / length
        half = float((edge_style or {}).get("tbar_len", 7.0))
        bar = svgwrite.shapes.Line(
            start=(round(p1[0] - px * half, 2), round(p1[1] - py * half, 2)),
            end=(round(p1[0] + px * half, 2), round(p1[1] + py * half, 2)),
            stroke=stroke, stroke_width=width)
        bar["stroke-linecap"] = "square"
        g.add(bar)
    return g


# ---------------------------------------------------------------------------
# Scene + tier lowering
# ---------------------------------------------------------------------------

_SLOT_EDGE_OFFSETS = {
    "top": (0.0, -0.5), "bottom": (0.0, 0.5),
    "left": (-0.5, 0.0), "right": (0.5, 0.0), "center": (0.0, 0.0),
    # cavity_* drop a child INSIDE the parent box (a ligand in a binding
    # pocket) — a quarter-extent off centre, never at the rim.
    "cavity_top": (0.0, -0.25), "cavity_bottom": (0.0, 0.25),
    "cavity_center": (0.0, 0.0),
}

# D6 (orientation / dim 3): map an Attach edge to the facing direction
# _orient_conformer understands, and to its opposite (a child sits at the
# parent's edge, so the parent faces that edge and the child faces back).
_EDGE_TO_DIRECTION = {"top": "up", "bottom": "down", "left": "left", "right": "right"}
_OPPOSITE_EDGE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}

# Only re-pose a molecule whose reactive atom is more than this far from the
# desired direction — i.e. correct *gross* (≈right-angle-or-worse) misorientation
# and leave a structure that already reads roughly the right way in its canonical
# pose (avoids needless churn / new collisions: a near-aligned aldehyde rotated
# fully upright would collide with its own caption — corpus fig 05). The corpus
# separates "must fix" substrates (~85–96° off) from "already fine" ones (~71°
# off), so the cut sits at 80°. MUST be identical in the predictor and the
# renderer or their boxes desync. See D6_ORIENTATION_SCOPE.md (open question 4).
_ORIENT_DEADBAND_DEG = 80.0


_ORIENT_DRIVERS = (SceneEdgeType.CURLY, SceneEdgeType.HBOND, SceneEdgeType.DASHED)


def _scene_orientations(
    scene: Scene, drivers: tuple[SceneEdgeType, ...] = _ORIENT_DRIVERS,
) -> dict[str, tuple[str, str]]:
    """Per-slot ``(reactive_atom_token, direction)`` so each reactant is posed to
    face its partner — the D6 orientation inference (see ``D6_ORIENTATION_SCOPE.md``).

    Drivers (orientation-v2 D6.4): a ``CURLY`` nucleophilic-attack ``SceneEdge``
    names the two reacting atoms (``from`` = nucleophile, ``to`` = electrophile);
    the ``Attach`` that places the two reacting slots gives the spatial
    relationship (the child sits at the parent's ``edge``). The parent's reactive
    atom is aimed toward that edge and the child's toward the opposite edge, so the
    attacked atom and the attacking atom point at each other and the step reads
    directionally. When a step has **no** curly arrow but an ``HBOND`` / ``DASHED``
    edge does name the interacting atoms (the binding / recognition step — fig
    01-s1, 08-s1), those drive the same way as a fallback, so the H-bond donor and
    acceptor aim at each other instead of posing canonically. Curly wins where both
    are present (processed first; ``setdefault`` keeps it). Returns only slots it
    can resolve; everything else keeps RDKit's canonical pose. Conservative by
    design — ``center``/``cavity_*`` attaches and indirectly-related slots are
    left alone."""
    out: dict[str, tuple[str, str]] = {}
    # Priority order: a reaction's curly arrow drives first; H-bond/dashed edges
    # only fill slots a curly didn't already constrain. ``drivers`` restricts the
    # set (the cross-scene reconciliation passes ``(CURLY,)`` to find the primary,
    # consistency-preferred pose before falling back to H-bond-derived ones).
    for driver in drivers:
        for edge in scene.connect:
            if edge.type != driver:
                continue
            from_slot, _, from_atom = edge.from_anchor.partition(".")
            to_slot, _, to_atom = edge.to_anchor.partition(".")
            if not from_atom or not to_atom or from_slot == to_slot:
                continue
            att = next(
                (a for a in scene.attach
                 if a.parent is not None
                 and {a.parent, a.child} == {from_slot, to_slot}),
                None,
            )
            if att is None or att.edge.value not in _EDGE_TO_DIRECTION:
                continue  # no direct attach, or center/cavity edge -> no facing
            atom_of = {from_slot: from_atom, to_slot: to_atom}
            out.setdefault(
                att.parent, (atom_of[att.parent], _EDGE_TO_DIRECTION[att.edge.value]))
            out.setdefault(
                att.child,
                (atom_of[att.child],
                 _EDGE_TO_DIRECTION[_OPPOSITE_EDGE[att.edge.value]]))
    return out


def _resolve_tier_orientations(
    scenes: list[Scene],
) -> dict[str, dict[str, tuple[str, str]]]:
    """Per-scene ``{slot_id: (atom, direction)}`` maps, reconciled across a tier so
    a molecule that recurs in several scenes shares one pose (orientation-v2 A).

    D6-v1 infers orientation per scene independently (:func:`_scene_orientations`),
    so the *same* substrate can be posed differently from one scene to the next —
    e.g. aspirin's ``asp`` is canonical in s1/s3 but rotated in s2 to aim its
    carbonyl at Ser530, so it visibly flips panel-to-panel. This pass groups
    MOLECULE/RESIDUE slots by their effective SMILES and, when a group has exactly
    one distinct inferred orientation, propagates it to every otherwise
    unconstrained recurrence — the unconstrained scenes had no partner to aim at,
    so adopting the constrained pose is free and makes the row read consistently.

    Curly drivers take priority in reconciliation: if the recurring molecule's
    *curly*-derived poses agree on one pose, it is applied to **every** instance —
    overriding an H-bond-derived pose in some other scene — so a recurring
    substrate keeps its reaction pose across the row rather than flipping when one
    scene's H-bond happens to aim a different atom (the acceptance aspirin case).
    Only if curly gives no single pose does the full-driver pose fill the
    unconstrained recurrences. A genuine conflict (different *curly* poses, or
    different full poses with no curly) is left per-scene; cross-step consistency
    for a *transforming* scaffold (different SMILES each scene) is the v2-B job.
    Deterministic: the same scene list yields the same maps, so the size-predictor
    path and the render path stay in lock-step (the box must match the drawn pose).
    """
    per_scene = {sc.id: dict(_scene_orientations(sc)) for sc in scenes}
    curly_only = {sc.id: dict(_scene_orientations(sc, drivers=(SceneEdgeType.CURLY,)))
                  for sc in scenes}
    groups: dict[str, list[tuple[str, str]]] = {}
    for sc in scenes:
        for slot in sc.slots:
            if slot.kind not in (SlotKind.MOLECULE, SlotKind.RESIDUE):
                continue
            smi = _slot_eff_smiles(slot)
            if smi:
                groups.setdefault(smi, []).append((sc.id, slot.id))
    for members in groups.values():
        if len({sid for sid, _ in members}) < 2:
            continue  # not a recurring structure — nothing to reconcile
        cur = {curly_only[sid].get(slid) for sid, slid in members}
        cur.discard(None)
        if len(cur) == 1:
            shared = next(iter(cur))
            for sid, slid in members:
                per_scene[sid][slid] = shared  # reaction pose wins everywhere
            continue
        distinct = {per_scene[sid].get(slid) for sid, slid in members}
        distinct.discard(None)
        if len(distinct) == 1:
            shared = next(iter(distinct))
            for sid, slid in members:
                # fill only the unconstrained recurrences; a slot that already
                # carries an orientation keeps it (it equals ``shared`` here).
                per_scene[sid].setdefault(slid, shared)
        # otherwise genuine per-scene facing conflict: leave as-is.
    return per_scene


# orientation-v2 B thresholds. A molecule must have at least this many atoms to be
# a scaffold-series candidate (excludes water / tiny fragments); the shared MCS
# must have at least this many atoms AND cover at least this fraction of the
# smallest member, so a trivial common group (a lone carboxyl) never triggers
# alignment of two otherwise-unrelated species.
_SCAFFOLD_MIN_ATOMS = 6
_SCAFFOLD_MIN_MCS = 6
_SCAFFOLD_MIN_FRACTION = 0.5


def _resolve_tier_scaffold(
    scenes: list[Scene],
    tier_orients: dict[str, dict[str, tuple[str, str]]],
) -> dict[str, dict[str, "object"]]:
    """Per-scene ``{slot_id: (ref_mol, mcs_pattern)}`` alignment specs so a
    *transforming* scaffold keeps one pose across a step row (orientation-v2 B).

    β-lactamase's ``sub→ti→acyl→prod`` are different SMILES that share a penicillin
    bicyclic core; D6-v1 poses each independently, so the conserved core visibly
    rotates panel-to-panel. This pass finds the series (MOLECULE slots across ≥2
    scenes with *different* SMILES — identical SMILES is v2-A), computes their
    maximum common substructure, and aligns every non-template member's depiction
    to a shared reference on that MCS, so only the reacting atoms move.

    Template = the *most-constrained* member (per the chosen policy): the series
    SMILES whose instances carry a v1 orientation (earliest scene wins), so the
    shared pose already satisfies the common partner-facing; the rest align to it
    and drop their own facing. Falls back to the first member when none is
    constrained. Returns ``{}`` (no alignment) when there is no transforming
    series or the MCS is too small to be a real shared scaffold — leaving v1/v2-A
    untouched. Deterministic, so the size predictor and renderer agree."""
    from rdkit.Chem import rdFMCS  # noqa: PLC0415
    from rdkit import Chem  # noqa: PLC0415
    from rdkit.Chem import rdDepictor  # noqa: PLC0415

    scene_order = {sc.id: i for i, sc in enumerate(scenes)}
    by_smiles: dict[str, list[tuple[str, str, Slot]]] = {}
    for sc in scenes:
        for slot in sc.slots:
            if slot.kind != SlotKind.MOLECULE:
                continue  # residues recur with one SMILES → handled by v2-A
            smi = _slot_eff_smiles(slot)
            if smi:
                by_smiles.setdefault(smi, []).append((sc.id, slot.id, slot))
    if len(by_smiles) < 2:
        return {}  # no transforming series (one species, or none)

    mols: dict[str, "Chem.Mol"] = {}
    for smi in by_smiles:
        try:
            m = _smiles_to_mol(smi)
        except Exception:
            continue
        if m is not None and m.GetNumAtoms() >= _SCAFFOLD_MIN_ATOMS:
            mols[smi] = m
    if len(mols) < 2:
        return {}

    res = rdFMCS.FindMCS(
        list(mols.values()), timeout=5,
        atomCompare=rdFMCS.AtomCompare.CompareElements,
        bondCompare=rdFMCS.BondCompare.CompareOrder,
        ringMatchesRingOnly=True, completeRingsOnly=True,
    )
    smallest = min(m.GetNumAtoms() for m in mols.values())
    if (res.canceled or res.numAtoms < _SCAFFOLD_MIN_MCS
            or res.numAtoms < _SCAFFOLD_MIN_FRACTION * smallest):
        return {}
    patt = Chem.MolFromSmarts(res.smartsString)
    if patt is None:
        return {}

    def _first_scene(smi: str) -> int:
        return min(scene_order[sid] for sid, _slid, _s in by_smiles[smi])

    # Template = a constrained series member if any (so the shared pose carries the
    # common facing), else the earliest member.
    constrained = [
        smi for smi in mols
        if any(tier_orients.get(sid, {}).get(slid) is not None
               for sid, slid, _s in by_smiles[smi])
    ]
    template_smi = min(constrained or list(mols), key=_first_scene)

    tref_sid, tref_slid, tref_slot = min(
        by_smiles[template_smi], key=lambda t: scene_order[t[0]])
    ref_mol = _smiles_to_mol(template_smi)
    t_orient = tier_orients.get(tref_sid, {}).get(tref_slid)
    names = {int(k): v
             for k, v in (tref_slot.style or {}).get("anchor_names", {}).items()}
    if t_orient is not None:
        # Same rotation (and deadband) the template scene will apply, so the
        # reference's relative pose equals the template's drawn pose.
        _orient_conformer(ref_mol, t_orient[0], t_orient[1], names,
                          deadband_deg=_ORIENT_DEADBAND_DEG)
    else:
        rdDepictor.Compute2DCoords(ref_mol)

    out: dict[str, dict[str, "object"]] = {}
    for smi, insts in by_smiles.items():
        if smi == template_smi or smi not in mols:
            continue
        if not mols[smi].HasSubstructMatch(patt):
            continue
        for sid, slid, _s in insts:
            out.setdefault(sid, {})[slid] = (ref_mol, patt)
    return out


# Gap left between two slot boxes that the attach solve landed on the same
# point and that ``_deoverlap_coincident`` then pushes apart.
_DEOVERLAP_MARGIN = 8.0


def _coincident_key(center: tuple[float, float]) -> tuple[int, int]:
    """Bucket a centre to ~0.5px so genuinely co-located slots group together
    while the historic half-step attach chain (distinct centres) does not."""
    return (round(center[0] * 2.0), round(center[1] * 2.0))


def _deoverlap_coincident(
    scene: Scene, centers: dict[str, tuple[float, float]],
    extent: Callable[[str], tuple[float, float]],
) -> None:
    """Spread slots whose centres coincide so their boxes are disjoint (MF-3).

    Only *coincident* centres are separated — the genuine stacked-on-top
    pathology (e.g. two slots both attached ``center`` to one parent: the
    His513-vs-ligand tangle). Distinct centres whose boxes merely overlap (the
    Step-3 half-step ``right`` attach chain) are left untouched, so the existing
    attach behaviour and every single-slot scene stay byte-identical.

    Members of a coincident group are laid side by side, centred on the shared
    point, in scene declaration order (deterministic). The spread is vertical
    when every member binds via a horizontal edge (left/right) — stacking
    same-edge siblings — and horizontal otherwise, the common case.

    A **cavity**-attached child (P7.3a) is exempt: it is *deliberately* placed
    inside its parent's binding pocket (a ligand/residue in a blob cavity), so it
    must stay coincident with the parent rather than be pushed out. Two children
    sharing one pocket are separated with the cavity_top/cavity_bottom edges, not
    by this pass."""
    cavity_attached = {a.child for a in scene.attach
                       if a.edge.value.startswith("cavity")}
    order = [s.id for s in scene.slots
             if s.id in centers and s.id not in cavity_attached]
    groups: dict[tuple[int, int], list[str]] = {}
    for sid in order:
        groups.setdefault(_coincident_key(centers[sid]), []).append(sid)
    edge_of = {a.child: a.edge.value for a in scene.attach}
    for members in groups.values():
        if len(members) < 2:
            continue
        shared = centers[members[0]]
        all_horizontal = all(edge_of.get(m) in ("left", "right") for m in members)
        axis = 1 if all_horizontal else 0
        sizes = [extent(m)[axis] for m in members]
        total = sum(sizes) + _DEOVERLAP_MARGIN * (len(members) - 1)
        run = shared[axis] - total / 2.0
        for sid, size in zip(members, sizes):
            pos = run + size / 2.0
            centers[sid] = (pos, shared[1]) if axis == 0 else (shared[0], pos)
            run += size + _DEOVERLAP_MARGIN


def _solve_slot_centers(
    scene: Scene, rect: tuple[float, float, float, float],
    slot_size: tuple[float, float],
    *,
    slot_extents: dict[str, tuple[float, float]] | None = None,
) -> dict[str, tuple[float, float]]:
    """Topological attach/offset solver: root slots centred, attached slots
    placed adjacent to the parent's edge (+ offset), then co-located boxes
    de-overlapped.

    Attaches resolve in DEPENDENCY order (a parent is placed before its child),
    so author declaration order is irrelevant; a cyclic or unresolvable chain
    raises rather than silently overlapping. For a **face edge** the placement is
    edge-to-edge: it uses BOTH the parent's and the child's extent
    (``slot_extents`` when supplied, else the uniform ``slot_size``), so ``offset``
    is the gap between the two boxes and a wide parent OR child can't overrun the
    other (the dim-5 arrow-clamp residual). Cavity / center edges drop the child
    INSIDE the parent and use only the parent extent.

    After placement, ``_deoverlap_coincident`` separates any slots the solve
    landed on the same point (two children center-attached to one parent — the
    His513-vs-ligand tangle, **MF-3**) so their boxes never overlap; distinct
    centres are untouched.

    Supported edges: the face edges (top/bottom/left/right/center) and the
    cavity edges (cavity_top/cavity_bottom/cavity_center). ``anchor``/``custom``
    edges (and ``Attach.parent_anchor`` resolution) arrive with the primitive
    refresh (Step 7) and raise ``NotImplementedError`` until then.
    """
    cx, cy = rect[0] + rect[2] / 2.0, rect[1] + rect[3] / 2.0
    sw, sh = slot_size

    def extent(sid: str | None) -> tuple[float, float]:
        if sid is not None and slot_extents and sid in slot_extents:
            return slot_extents[sid]
        return (sw, sh)

    for att in scene.attach:
        if att.edge.value not in _SLOT_EDGE_OFFSETS:
            raise NotImplementedError(
                f"scene '{scene.id}' attach edge '{att.edge.value}' is not yet "
                "supported (face/cavity edges only; anchor/custom arrive with "
                "the primitive refresh, Step 7)")
    attached = {a.child for a in scene.attach}
    roots = [s.id for s in scene.slots if s.id not in attached]
    centers: dict[str, tuple[float, float]] = {}
    if len(roots) <= 1:
        for rid in roots:
            centers[rid] = (cx, cy)
    else:  # spread multiple roots horizontally across the cell
        step = rect[2] / (len(roots) + 1)
        for i, rid in enumerate(roots, start=1):
            centers[rid] = (rect[0] + step * i, cy)
    pending = list(scene.attach)
    while pending:
        still: list = []
        progressed = False
        for att in pending:
            if att.parent is None:
                parent_center = (cx, cy)
            elif att.parent in centers:
                parent_center = centers[att.parent]
            else:
                still.append(att)  # parent not placed yet — retry next pass
                continue
            ex, ey = _SLOT_EDGE_OFFSETS[att.edge.value]
            pw, ph = extent(att.parent)
            ox, oy = att.offset
            # Face edges (top/bottom/left/right) seat the child OUTSIDE the parent,
            # adjacent to that edge: add the CHILD's half-extent in the edge
            # direction so ``offset`` is a true edge-to-edge gap, not edge-to-centre.
            # Without this a wide child (a 160px blob) overruns its half-width back
            # into the parent — the boxes overlap and the connecting arrow has no
            # room, so its standoff clamps inside the shape (dim-5 residual). Cavity
            # / center edges drop the child INSIDE the parent, so they keep the bare
            # parent-extent placement (no child term).
            cw, ch = extent(att.child)
            face = att.edge.value in ("top", "bottom", "left", "right")
            kx = ex * cw if face else 0.0
            ky = ey * ch if face else 0.0
            centers[att.child] = (parent_center[0] + ex * pw + kx + ox,
                                  parent_center[1] + ey * ph + ky + oy)
            progressed = True
        if not progressed:
            raise ValueError(
                f"scene '{scene.id}' has a cyclic or unresolvable attach chain: "
                f"{[a.child for a in still]}")
        pending = still
    _deoverlap_coincident(scene, centers, extent)
    # Centre the whole scene's content in the cell. The solve pins a single root
    # at the cell centre and grows children outward (a left->right chain then
    # occupies only the right half and spills past the cell edge — ERK hanging
    # out of the band). Shifting every centre by (cell centre − content centre)
    # seats the content symmetrically in its cell on both axes.
    if centers:
        boxes = [
            (c[0] - extent(sid)[0] / 2.0, c[1] - extent(sid)[1] / 2.0,
             c[0] + extent(sid)[0] / 2.0, c[1] + extent(sid)[1] / 2.0)
            for sid, c in centers.items()
        ]
        bcx = (min(b[0] for b in boxes) + max(b[2] for b in boxes)) / 2.0
        bcy = (min(b[1] for b in boxes) + max(b[3] for b in boxes)) / 2.0
        dx, dy = cx - bcx, cy - bcy
        if dx or dy:
            centers = {sid: (c[0] + dx, c[1] + dy) for sid, c in centers.items()}
    return centers


def scene_label_requests(
    scene: Scene,
    *,
    content_extent: tuple[float, float, float, float],
    centers: dict[str, tuple[float, float]],
    slot_size: tuple[float, float],
    edge_anchors: dict[str, tuple[float, float]],
    params: dict[str, Any],
) -> list[LabelRequest]:
    """Emit the scene's ``LabelRequest``s for the scene-local placement pass (P5.2).

    Sibling of ``pathway_label_requests`` for the tier engine. Covers the scene
    caption (``scene.label``, one request per ``\\n`` line, stacked below the
    content extent — replacing the old fixed ``_caption_group``) plus the two
    previously-unrendered label channels: a non-TEXT ``Slot.label`` (a TEXT slot
    already renders its label as its body, so it is skipped) and a
    ``SceneEdge.label`` at the edge midpoint. ``ir_id``s are preserved so the
    emitted ``label_<ir_id>`` ids keep matching existing token assertions
    (line 0 of the caption stays ``scene_<id>_label``).
    """
    minx, _miny, maxx, maxy = content_extent
    fcx = (minx + maxx) / 2.0
    width = maxx - minx
    sw, sh = slot_size
    fs = int(params["tier_caption_font_size"])
    step = fs * float(params["tier_caption_line_step"])
    requests: list[LabelRequest] = []

    if scene.label:
        for i, line in enumerate(scene.label.split("\n")):
            requests.append(LabelRequest(
                text=line,
                anchor=(fcx, maxy + i * step),
                anchor_size=(width, 0.0),
                priority=("below", "above"),
                ir_id=(f"scene_{scene.id}_label" if i == 0
                       else f"scene_{scene.id}_label_l{i}"),
            ))

    for slot in scene.slots:
        if slot.label and slot.kind != SlotKind.TEXT and slot.id in centers:
            requests.append(LabelRequest(
                text=slot.label,
                anchor=centers[slot.id],
                anchor_size=(sw, sh),
                priority=("below", "right", "above", "left"),
                ir_id=f"slot_{scene.id}_{slot.id}_label",
                leader=True,   # park in whitespace + tether (tier_label_leaders)
            ))

    for edge in scene.connect:
        if edge.label and edge.ir_id in edge_anchors:
            requests.append(LabelRequest(
                text=edge.label,
                anchor=edge_anchors[edge.ir_id],
                anchor_size=(0.0, 0.0),
                priority=("above", "below", "right", "left"),
                ir_id=f"{edge.ir_id}_label",
                leader=True,   # park off the shaft in whitespace + tether (D3)
            ))
    return requests


# px between a slot/edge anchor box edge and its label edge before the label
# reads as detached and earns a tether. A label that lands snug (gap ≈ the
# caption anchor gap, ~12px) stays leader-free so the figure isn't cluttered;
# only a label that ``place_labels`` had to push into far whitespace — the D1
# residue-label drift, the D3 edge-label flight — crosses this threshold.
_TIER_LEADER_MIN_GAP = 22.0


def tier_label_leaders(
    entries: list[LayoutEntry],
    leader_anchors: dict[str, tuple[tuple[float, float], tuple[float, float]]],
    style_dict: dict | None = None,
) -> list[LayoutEntry]:
    """Tether drifted scene-local labels back to their slot/edge anchor (D1, D3).

    Sibling of ``pathway_extlabel_leaders`` for the tier engine. Runs as a
    post-pass on the ``place_labels`` output: a slot or edge label that the
    placement ladder pushed into far whitespace (its edge sits more than
    ``_TIER_LEADER_MIN_GAP`` from its anchor box) gets a hairline dashed leader
    so a reader can see which structure it names. A label that landed snug beside
    its anchor gets none — no clutter. Captions are deliberately absent from
    ``leader_anchors`` (they are positional + band-clamped), so they never tether.

    ``leader_anchors`` maps a *placed* label ir_id (``label_<…>``) to its anchor
    ``(center, (half_w, half_h))`` — a slot's drawn box, or an edge midpoint with
    a zero-size box. Leaders are inserted immediately before the first label entry
    so they draw over content but under the label text, mirroring the pathway
    pass. A no-op (returns the input unchanged) when nothing drifted.
    """
    from imageGen.layout._pathway_bands import _bbox_exit_point  # noqa: PLC0415
    from imageGen.layout._pathway_labels import _leader_line  # noqa: PLC0415
    from imageGen.layout.label_placement import (  # noqa: PLC0415 — break cycle
        _DEFAULT_LABEL_STYLE,
        _estimate_text_bbox,
        _label_primitive,
    )

    leaders: list[LayoutEntry] = []
    first_label_idx = len(entries)
    for i, e in enumerate(entries):
        if e.primitive is not _label_primitive:
            continue
        first_label_idx = min(first_label_idx, i)
        geom = leader_anchors.get(e.ir_id or "")
        if geom is None:
            continue
        anchor_center, (ahw, ahh) = geom
        label_center = e.args[1]
        fs = float(
            (e.kwargs.get("style_dict") or _DEFAULT_LABEL_STYLE)["label_font_size"]
        )
        lw, lh = _estimate_text_bbox(str(e.args[0]), fs)
        box_exit = _bbox_exit_point(anchor_center, ahw, ahh, label_center, 0.0)
        label_exit = _bbox_exit_point(label_center, lw / 2, lh / 2, anchor_center, 0.0)
        if math.hypot(label_exit[0] - box_exit[0],
                      label_exit[1] - box_exit[1]) <= _TIER_LEADER_MIN_GAP:
            continue
        leaders.append(LayoutEntry(
            primitive=_leader_line,
            args=(label_exit, box_exit),
            kwargs={"style_dict": style_dict} if style_dict else {},
            position=(0.0, 0.0),
            ir_id=f"leader_{(e.ir_id or '')[len('label_'):]}",
        ))

    if not leaders:
        return entries
    return entries[:first_label_idx] + leaders + entries[first_label_idx:]


def _layout_scene(
    scene: Scene, rect: tuple[float, float, float, float],
    registry: AnchorRegistry, params: dict[str, Any],
    *,
    base_style: dict[str, Any] | None = None,
    tier_style: dict[str, Any] | None = None,
    orient_map: dict[str, tuple[str, str]] | None = None,
    align_map: dict[str, "object"] | None = None,
) -> list[LayoutEntry]:
    """Render a scene's slots into ``rect``, publish anchors, emit connect edges.

    Order matters: slots are solved and placed first so the scene-frame anchors
    can be published from the *content* extent (the union of slot boxes) rather
    than the cell rect — a cross-cell transition arrow then spans the visible
    molecule gap, not the narrow inter-cell gutter. The badge is emitted next,
    then intra-scene edges (which need the atom anchors above), and finally the
    scene labels are placed by the shared greedy pass (P5.2).

    P0b.2 — two-channel additive style cascade:
      * ``base_style`` (the *content* base = preset ⊕ tier.style) layers under
        ``scene.style`` then each ``slot.style`` to style molecules + text, so
        tiered content follows the journal preset exactly as the leaf path does.
      * ``tier_style`` (the *structural* base, NO preset) layers under
        ``scene.style`` then ``edge.style`` for connect edges — the preset's
        bare ``stroke``/``stroke_width`` (set by acs/nature) must NOT bleed onto
        the per-``SceneEdgeType`` semantic colours, so edges take no preset base.
    For Step 6, an expanded step folds ``step.style`` into ``scene.style``, so it
    rides this same cascade as the outermost (most-specific) layer — no new path.
    """
    sw, sh = params["tier_slot_size"]
    standoff = float(params["tier_edge_standoff"])
    cx, cy, cw, ch = rect
    entries: list[LayoutEntry] = []

    # Scene-level effective styles for the two channels (slot/edge layer added
    # at each site). With both bases None (the direct-call path), these collapse
    # to ``scene.style or {}`` → byte-identical to the pre-cascade behaviour.
    scene_content = merge_style(base_style, scene.style)
    scene_struct = merge_style(tier_style, scene.style)

    # P5.4 Nit-1: give the solver each slot's real extent so the child slide
    # uses the *parent's* box (a TEXT parent no longer pushes a child a full
    # molecule-width away) and de-overlap uses the child's own width.
    # D6: infer per-slot orientation (reactive atom -> facing direction) from the
    # scene's curly edges + attaches BEFORE sizing, so the predicted box matches
    # the box the *posed* molecule will draw (the solve depends on it).
    # orientation-v2 A: prefer the tier-reconciled per-scene map (a recurring
    # molecule keeps one pose across the row); fall back to per-scene inference on
    # the direct-call path so a standalone scene is byte-identical to v1.
    if orient_map is None:
        orient_map = _scene_orientations(scene)
    align_map = align_map or {}
    slot_extents = {
        s.id: _slot_bbox_size(s, (sw, sh), params,
                              orient_map.get(s.id), align_map.get(s.id))
        for s in scene.slots}
    centers = _solve_slot_centers(scene, rect, (sw, sh), slot_extents=slot_extents)
    boxes: list[tuple[float, float, float, float]] = []
    for slot in scene.slots:
        center = centers.get(slot.id, (cx + cw / 2.0, cy + ch / 2.0))
        scoped = f"{scene.id}.{slot.id}"
        # P7.4: a slot may render at a fraction of its box (style['scale']) so a
        # small molecule/residue sits *inside* a full-size blob cavity without
        # dwarfing it. Defaults to 1.0. dim-1/5: a BLOB / GLYPH draws within its
        # primitive's natural box (``_glyph_natural_box``) — a tablet/cluster
        # molecule-scale, a protein blob bigger — not the uniform slot cell, so the
        # rendered size matches what the layout sizer (_slot_drawn_size) predicted.
        scale = float((slot.style or {}).get("scale", 1.0))
        if slot.kind in (SlotKind.BLOB, SlotKind.GLYPH):
            _bw, _bh = _glyph_natural_box(slot, params)
            ssw, ssh = _bw * scale, _bh * scale
        else:
            ssw, ssh = sw * scale, sh * scale
        if slot.kind in (SlotKind.MOLECULE, SlotKind.RESIDUE):
            # MOLECULE and RESIDUE share the anchored-fragment path (MF-1: one
            # chemistry convention everywhere). A RESIDUE additionally resolves a
            # named side chain (style['residue']) and renders with an open-valence
            # dangling bond + an attachment anchor.
            style = slot.style or {}
            is_residue = slot.kind == SlotKind.RESIDUE
            smiles = style.get("smiles")
            residue = style.get("residue")
            if not smiles and not (is_residue and residue):
                need = "style['smiles']" + (" or style['residue']" if is_residue else "")
                raise ValueError(
                    f"{slot.kind.value} slot '{scene.id}.{slot.id}' needs {need}")
            names = {int(k): v for k, v in (style.get("anchor_names") or {}).items()}
            o_to, o_dir = orient_map.get(slot.id, (None, None))
            # Pub-grade content-aware sizing: render at the shared
            # ``chem_target_bond_px`` bond length so every structure in the figure
            # is one consistent scale; the box is derived from the molecule (not the
            # slot). ``style['scale']`` multiplies the bond length. Passing
            # ``center=`` lets the renderer bake the placement + return absolute
            # anchors (no slot-box top-left math). Falls back to the legacy
            # slot-box size when ``chem_target_bond_px`` is unset.
            tbp = float(params.get("chem_target_bond_px") or 0.0) * scale
            target_bp = tbp if tbp > 0.0 else None
            mol_pad = float(params["tier_mol_pad"])
            size_arg = ((int(round(ssw)), int(round(ssh)))
                        if target_bp is None else (1, 1))
            # Content cascade: preset ⊕ tier ⊕ scene ⊕ this slot's style
            # overrides (content/control keys dropped). Empty → the renderer's
            # DEFAULT_STYLE, byte-identical to the no-style call.
            mol_style = merge_style(
                scene_content,
                {k: v for k, v in style.items()
                 if k not in ("smiles", "anchor_names", "residue", "attach_anchor",
                              "scale")})
            if is_residue:
                ag = render_residue_anchored(
                    str(residue or smiles), size=size_arg, center=center,
                    anchor_names=names, style_dict=mol_style or None,
                    attach_anchor=str(style.get("attach_anchor", "attach")),
                    target_bond_px=target_bp, size_pad=mol_pad,
                    orient_to=o_to, orient_direction=o_dir,
                    orient_deadband_deg=_ORIENT_DEADBAND_DEG)
            else:
                ag = render_molecule_anchored(
                    str(smiles), size=size_arg, center=center, anchor_names=names,
                    style_dict=mol_style or None, target_bond_px=target_bp,
                    size_pad=mol_pad, orient_to=o_to, orient_direction=o_dir,
                    orient_deadband_deg=_ORIENT_DEADBAND_DEG,
                    align_to=align_map.get(slot.id))
            # center= baked the placement → anchors are already absolute.
            registry.publish(scoped, ag.anchors)
            entries.append(LayoutEntry(
                (lambda g=ag.group: g), (), {}, (0.0, 0.0), ir_id=scoped))
        elif slot.kind == SlotKind.TEXT:
            # P5.4 Nit-3: publish the `center` anchor at the visual MIDLINE (so an
            # edge to a text slot's centre meets its middle), and drop the
            # rendered baseline 0.35 em so the glyphs straddle that midline (SVG
            # <text> y is the baseline; mirrors the _badge_group cy + r*0.35 fix).
            fs = int(params["tier_text_font_size"])
            # Content cascade overrides the preset-derived param default.
            col = str(scene_content.get("label_font_color", params["tier_text_color"]))
            fam = str(scene_content.get("label_font_family", params["tier_font_family"]))
            registry.publish(scoped, {"center": (0.0, 0.0)}, offset=center)
            entries.append(LayoutEntry(
                (lambda t=slot.label or "", c=center, f=fs, col=col, fam=fam:
                    _text_group(t, (c[0], c[1] + f * 0.35), f, col, fam,
                                anchor="middle")),
                (), {}, (0.0, 0.0), ir_id=scoped))
        elif slot.kind == SlotKind.BLOB:
            # P7.3a: an organic protein surface with a binding cavity. The label
            # is placed by the scene-label pass (like MOLECULE), so the primitive
            # renders unlabelled. Publish cavity_* anchors at the box centre +
            # quarter-offsets — matching _SLOT_EDGE_OFFSETS — so an attach-into-
            # cavity edge and any SceneEdge land where the pocket is drawn.
            blob_style = merge_style(
                scene_content,
                {k: v for k, v in (slot.style or {}).items()
                 if k not in ("glyph", "scale")})
            grp = protein_blob("", center, (ssw, ssh), style_dict=blob_style or None)
            # Cavity anchors track the blob's DRAWN height (ssh), not the slot cell,
            # so an attach-into-cavity edge lands in the pocket at any blob size.
            registry.publish(scoped, {
                "center": center,
                "cavity_center": center,
                "cavity_top": (center[0], center[1] - 0.25 * ssh),
                "cavity_bottom": (center[0], center[1] + 0.25 * ssh),
            })
            entries.append(LayoutEntry(
                (lambda g=grp: g), (), {}, (0.0, 0.0), ir_id=scoped))
        elif slot.kind == SlotKind.GLYPH:
            # P7.3c: render any registered primitive (P0c.1) as a scene icon —
            # tablet, pg_cluster, protein_blob, or any other registry entry —
            # named by style['glyph']. Label placed by the scene-label pass.
            gname = (slot.style or {}).get("glyph")
            if gname not in PRIMITIVE_REGISTRY:
                raise ValueError(
                    f"glyph slot '{scene.id}.{slot.id}' needs a known "
                    f"style['glyph'] (got {gname!r}); register it as a "
                    "PrimitiveSpec to use it as a scene glyph")
            glyph_style = merge_style(
                scene_content,
                {k: v for k, v in (slot.style or {}).items()
                 if k not in ("glyph", "scale")})
            grp = PRIMITIVE_REGISTRY[gname](
                "", center, (ssw, ssh), style_dict=glyph_style or None)
            registry.publish(scoped, {"center": center})
            entries.append(LayoutEntry(
                (lambda g=grp: g), (), {}, (0.0, 0.0), ir_id=scoped))
        else:
            raise NotImplementedError(
                f"SlotKind {slot.kind.value!r} is not yet supported by the "
                f"tier-layout engine (slot '{scene.id}.{slot.id}')")
        boxes.append(_slot_bbox(slot, center, (sw, sh), params))

    # Scene-frame anchors from the CONTENT extent (cell-vs-content fix). Falls
    # back to the cell rect for an empty scene so the keys always resolve.
    if boxes:
        minx = min(b[0] for b in boxes); miny = min(b[1] for b in boxes)
        maxx = max(b[2] for b in boxes); maxy = max(b[3] for b in boxes)
    else:
        minx, miny, maxx, maxy = cx, cy, cx + cw, cy + ch
    fcx, fcy = (minx + maxx) / 2.0, (miny + maxy) / 2.0
    registry.publish(scene.id, {
        "left": (minx, fcy), "right": (maxx, fcy),
        "top": (fcx, miny), "bottom": (fcx, maxy),
        "center": (fcx, fcy),
    })

    # Step badge (top-left of the cell, so badges align across a row).
    if scene.badge:
        inset = float(params["tier_badge_inset"])
        r = float(params["tier_badge_radius"])
        entries.append(LayoutEntry(
            (lambda b=scene.badge, c=(cx + inset + r, cy + inset + r), p=params:
                _badge_group(b, c, p)),
            (), {}, (0.0, 0.0), ir_id=f"scene_{scene.id}_badge"))

    # P0a.5: aggregate-validate every connect endpoint before resolving so all
    # bad refs in this scene surface in one error. The schema validates the slot
    # token of a "slot.anchor" ref at build time, but not the dynamic anchor
    # segment — that's only known once the scene's slots have published.
    _connect_refs = [
        (edge, anchor, f"{scene.id}.{anchor}")
        for edge in scene.connect
        for anchor in (edge.from_anchor, edge.to_anchor)
    ]
    _bad = set(registry.validate_refs(key for _e, _a, key in _connect_refs))
    if _bad:
        offenders = "; ".join(
            f"{edge.ir_id}: {anchor!r}"
            for edge, anchor, key in _connect_refs if key in _bad
        )
        raise ValueError(
            f"Scene '{scene.id}' has unresolved connect endpoint(s): {offenders}"
        )

    # Intra-scene edges: refs are scene-local ("slot.anchor"); resolve_edge
    # applies (clamped) endpoint standoff so the line clears both atoms. The
    # midpoint of any labelled edge is captured for its scene-local label.
    # dim-5: the standoff is ink-relative for a whole-slot BLOB/GLYPH centre
    # endpoint (so the arrow stops at the silhouette, not inside it); atom /
    # molecule / text endpoints keep the tight fixed standoff.
    slots_by_id = {s.id: s for s in scene.slots}
    edge_anchors: dict[str, tuple[float, float]] = {}
    for edge in scene.connect:
        p0_raw = registry.resolve(f"{scene.id}.{edge.from_anchor}")
        p1_raw = registry.resolve(f"{scene.id}.{edge.to_anchor}")
        fs = _ink_relative_standoff(
            edge.from_anchor, p0_raw, p1_raw, slots_by_id, slot_extents, standoff)
        ts = _ink_relative_standoff(
            edge.to_anchor, p1_raw, p0_raw, slots_by_id, slot_extents, standoff)
        q0, q1 = registry.resolve_edge(
            f"{scene.id}.{edge.from_anchor}", f"{scene.id}.{edge.to_anchor}",
            from_standoff=fs, to_standoff=ts)
        # Structural cascade: tier ⊕ scene ⊕ edge (NO preset base).
        edge_style = merge_style(scene_struct, edge.style)
        entries.append(LayoutEntry(
            (lambda a=q0, b=q1, t=edge.type, s=edge_style: _edge_group(a, b, t, s)),
            (), {}, (0.0, 0.0), ir_id=edge.ir_id))
        if edge.label:
            edge_anchors[edge.ir_id] = ((q0[0] + q1[0]) / 2.0,
                                        (q0[1] + q1[1]) / 2.0)

    # P5.2: scene-local label placement through the shared greedy pass instead
    # of the old fixed-coordinate caption. Molecule / text / badge / edge
    # entries are zero-footprint to place_labels, so the caption lands just
    # below the content extent (the caption gap carried over as the anchor gap),
    # and the previously-unrendered slot / edge labels place around their
    # anchors. canvas is left unbounded: the FR3 frame expansion grows the page
    # to include a caption below the bottom row, exactly as the fixed caption
    # relied on.
    requests = scene_label_requests(
        scene, content_extent=(minx, miny, maxx, maxy), centers=centers,
        slot_size=(sw, sh), edge_anchors=edge_anchors, params=params)
    if requests:
        label_style = {
            "label_font_size": int(params["tier_caption_font_size"]),
            "label_font_family": str(scene_content.get(
                "label_font_family", params["tier_font_family"])),
            "label_font_color": str(scene_content.get(
                "label_font_color", params["tier_text_color"])),
        }
        # Band-clamp: forbid label positions outside this scene's band (the cell's
        # vertical slice) so a caption / slot label / edge label never crosses into
        # a neighbouring tier or spills onto the white page below its band — the
        # "out of the box / in and out of the background" defect. Modelled as two
        # wide occupancy walls (above the band top, below the band bottom); a label
        # that would cross a seam is pushed to an in-band position instead.
        rx, ry, rw, rh = rect
        big = 1.0e5
        band_walls = [
            (rx - big, ry - big, rx + rw + big, ry),             # above band top
            (rx - big, ry + rh, rx + rw + big, ry + rh + big),   # below band bottom
            (rx - big, ry - big, rx, ry + rh + big),             # left of cell
            (rx + rw, ry - big, rx + rw + big, ry + rh + big),   # right of cell
        ]
        # Transition lanes: a cross-cell transition arrow (s@right -> s@left)
        # enters/leaves this scene at its frame `left`/`right` anchors — the
        # content vertical centre `fcy`, running through the cell's side margins.
        # Those arrows resolve at the tier level AFTER this scene placed its
        # labels, so a slot label placed `right`/`left` at mid-height lands on the
        # (not-yet-drawn) shaft and renders struck-through (fig 03 "hydroxide").
        # Reserve the two side-margin strips at `fcy` so labels go above/below
        # instead — the gutter at mid-height is bad placement regardless (it reads
        # as detached from the molecule), so reserving it unconditionally is safe.
        lane_hw = float(params["tier_caption_font_size"])
        transition_lanes = [
            (rx, fcy - lane_hw, minx, fcy + lane_hw),          # left margin lane
            (maxx, fcy - lane_hw, rx + rw, fcy + lane_hw),     # right margin lane
        ]
        entries = place_labels(
            entries, requests,
            layout_params={"label_anchor_gap": float(params["tier_caption_gap"])},
            style_dict=label_style,
            # Seed occupancy with the slot ink boxes so a caption / residue label
            # never lands on top of the chemistry (molecule entries are closures,
            # invisible to place_labels' own bbox extraction), plus the band walls
            # and the transition lanes.
            extra_occupied=boxes + band_walls + transition_lanes,
        )
        # dim-2 leader lines: tether any slot / edge label that the placement
        # ladder pushed far from its anchor (D1 residue-label drift, D3 edge
        # labels) back to the structure it names. Anchors keyed by the *placed*
        # label ir_id; captions are intentionally excluded → never tethered.
        leader_anchors: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
        for slot in scene.slots:
            if slot.label and slot.kind != SlotKind.TEXT and slot.id in centers:
                bx0, by0, bx1, by1 = _slot_bbox(slot, centers[slot.id], (sw, sh), params)
                leader_anchors[f"label_slot_{scene.id}_{slot.id}_label"] = (
                    ((bx0 + bx1) / 2.0, (by0 + by1) / 2.0),
                    ((bx1 - bx0) / 2.0, (by1 - by0) / 2.0),
                )
        for edge in scene.connect:
            if edge.label and edge.ir_id in edge_anchors:
                leader_anchors[f"label_{edge.ir_id}_label"] = (
                    edge_anchors[edge.ir_id], (0.0, 0.0))
        entries = tier_label_leaders(entries, leader_anchors, style_dict=label_style)
    return entries


def _transition_label_pos(
    p0: tuple[float, float], p1: tuple[float, float], offset: float,
) -> tuple[float, float]:
    """Baseline point for a transition label, ``offset`` px above the shaft midpoint.

    The label sits perpendicular to the arrow on its *upper* side (the unit
    normal with the more-negative ``y``), so a horizontal arrow gets its label
    straight above the midpoint. A near-vertical arrow has no meaningful "above",
    so it falls back to the right-hand normal (positive ``x``)."""
    mx, my = (p0[0] + p1[0]) / 2.0, (p0[1] + p1[1]) / 2.0
    dx, dy = p1[0] - p0[0], p1[1] - p0[1]
    length = math.hypot(dx, dy)
    if length == 0.0:
        return (mx, my - offset)
    # Two unit normals; pick the upper one, breaking a vertical tie toward +x.
    nx, ny = -dy / length, dx / length
    if ny > 0 or (abs(ny) < 1e-9 and nx < 0):
        nx, ny = -nx, -ny
    return (mx + nx * offset, my + ny * offset)


def _text_group(text: str, pos: tuple[float, float], size: int, color: str,
                family: str, anchor: str = "start", italic: bool = False,
                weight: str = "normal") -> svgwrite.container.Group:
    """A Group wrapping one Text element — keeps every entry's primitive
    returning a Group (the LayoutEntry contract / _tag_group target)."""
    g = svgwrite.container.Group()
    g.add(svgwrite.text.Text(
        text, insert=pos, font_size=size, fill=color, font_family=family,
        text_anchor=anchor,
        font_style="italic" if italic else "normal", font_weight=weight,
    ))
    return g


def _band_chrome(
    rect: tuple[float, float, float, float], tier_style: dict[str, Any],
    params: dict[str, Any],
) -> svgwrite.container.Group:
    """Background / border / top-divider chrome for one tier band.

    Driven by the tier's ``style`` bag (declarative, like every other primitive's
    visual intent): ``band_fill`` paints the rounded background, ``band_stroke``
    (+ ``band_stroke_width``) the border, and ``divider`` ('solid' | 'dashed')
    draws a rule across the tier's TOP edge — the convention that fences a
    summary bar off from the steps above it."""
    x, y, w, h = rect
    g = svgwrite.container.Group()
    fill = tier_style.get("band_fill")
    stroke = tier_style.get("band_stroke")
    if fill or stroke:
        g.add(svgwrite.shapes.Rect(
            insert=(x, y), size=(w, h),
            rx=float(params["tier_band_radius"]), ry=float(params["tier_band_radius"]),
            fill=str(fill) if fill else "none",
            stroke=str(stroke) if stroke else "none",
            stroke_width=float(tier_style.get(
                "band_stroke_width", params["tier_band_stroke_width"])) if stroke else 0,
        ))
    divider = tier_style.get("divider")
    if divider:
        attrs: dict[str, Any] = {
            "start": (x, y), "end": (x + w, y),
            "stroke": str(tier_style.get("divider_color", params["tier_divider_color"])),
            "stroke_width": float(tier_style.get(
                "divider_width", params["tier_divider_width"])),
        }
        if divider == "dashed":
            attrs["stroke_dasharray"] = "6,4"
        g.add(svgwrite.shapes.Line(**attrs))
    return g


def _badge_group(
    text: str, center: tuple[float, float], params: dict[str, Any],
) -> svgwrite.container.Group:
    """A small filled circle with a centred number — a scene's step badge.

    Vertical centring is done by nudging the baseline down ~0.35 em rather than
    relying on ``dominant-baseline`` (cairosvg ignores it on <text>)."""
    cx, cy = center
    r = float(params["tier_badge_radius"])
    g = svgwrite.container.Group()
    g.add(svgwrite.shapes.Circle(
        center=(cx, cy), r=r, fill=str(params["tier_badge_fill"]), stroke="none"))
    g.add(svgwrite.text.Text(
        text, insert=(cx, cy + r * 0.35), font_size=r * 1.1,
        fill=str(params["tier_badge_text_color"]),
        font_family=str(params["tier_font_family"]),
        text_anchor="middle", font_weight="bold"))
    return g


def _caption_group(
    text: str, cx: float, top_y: float, params: dict[str, Any],
) -> svgwrite.container.Group:
    """A centred, possibly multi-line scene caption below the content.

    ``\\n`` splits into stacked lines (the schema documents scene labels as
    multi-line); ``top_y`` is the baseline of the first line."""
    fs = int(params["tier_caption_font_size"])
    step = fs * float(params["tier_caption_line_step"])
    g = svgwrite.container.Group()
    for i, line in enumerate(text.split("\n")):
        g.add(svgwrite.text.Text(
            line, insert=(cx, top_y + i * step), font_size=fs,
            fill=str(params["tier_text_color"]),
            font_family=str(params["tier_font_family"]),
            text_anchor="middle", font_style="italic"))
    return g


def _slot_eff_smiles(slot: Slot) -> str | None:
    """The SMILES a MOLECULE/RESIDUE slot draws (resolving a residue name)."""
    style = slot.style or {}
    if slot.kind == SlotKind.RESIDUE:
        res = style.get("residue")
        if res:
            return _RESIDUE_SMILES.get(res, res)
        return style.get("smiles")
    return style.get("smiles")


def _glyph_natural_box(
    slot: Slot, params: dict[str, Any],
) -> tuple[float, float]:
    """The unscaled natural ``(w, h)`` box a BLOB / GLYPH slot draws within (dim-1/5).

    A GLYPH uses its primitive's *registered* bbox (``PRIMITIVE_TO_BBOX``), so a
    tablet (40×40) / pg_cluster (50×50) renders molecule-scale while a protein-blob
    glyph (96×80) renders bigger — in proportion with the chemistry instead of every
    glyph filling the uniform slot cell. A BLOB is a cavity *container* (it can hold
    a molecule in its pocket), so it uses the generous ``tier_blob_size`` rather than
    the small protein_blob glyph bbox. ``style['scale']`` (applied by the caller) is
    a multiplier on this box. An unregistered glyph name falls back to the slot box."""
    if slot.kind == SlotKind.BLOB:
        return tuple(params["tier_blob_size"])
    gname = (slot.style or {}).get("glyph")
    fn = PRIMITIVE_REGISTRY.get(gname)
    if fn is not None and fn in PRIMITIVE_TO_BBOX:
        return PRIMITIVE_TO_BBOX[fn]
    return tuple(params["tier_slot_size"])


def _slot_drawn_size(
    slot: Slot, slot_size: tuple[float, float], params: dict[str, Any],
    orient: tuple[str, str] | None = None,
    align: "object | None" = None,
) -> tuple[float, float]:
    """The ``(w, h)`` a slot's glyph actually draws at — the ink, not the cell.

    Pub-grade sizing: a MOLECULE/RESIDUE is sized to its *content* at the shared
    ``chem_target_bond_px`` bond length (so every structure in the figure renders
    at one scale), a BLOB / GLYPH at its primitive's natural box
    (``_glyph_natural_box``) — NOT the uniform slot cell (dim-1/5), so glyphs sit in
    proportion with the molecules. ``style['scale']`` is an optional multiplier on
    the bond length (chemistry) or the natural box (blob/glyph). Falls back to the
    legacy slot-box size when ``chem_target_bond_px`` is unset or the SMILES can't
    be parsed.

    D6: when *orient* ``(reactive_atom, direction)`` is given the predicted box is
    measured on the *oriented* pose (rotating a wide molecule upright makes it
    tall) — the renderer applies the same deterministic rotation, so the predicted
    box matches the drawn one."""
    sw, sh = slot_size
    style = slot.style or {}
    scale = float(style.get("scale", 1.0))
    if slot.kind in (SlotKind.MOLECULE, SlotKind.RESIDUE):
        tbp = float(params.get("chem_target_bond_px") or 0.0) * scale
        smi = _slot_eff_smiles(slot)
        if tbp > 0.0 and smi:
            try:
                o_to, o_dir = orient or (None, None)
                names = {int(k): v
                         for k, v in (style.get("anchor_names") or {}).items()}
                return molecule_natural_size(
                    str(smi), tbp, float(params["tier_mol_pad"]),
                    orient_to=o_to, orient_direction=o_dir, anchor_names=names,
                    orient_deadband_deg=_ORIENT_DEADBAND_DEG, align_to=align)
            except Exception:
                pass
        return (sw * scale, sh * scale)
    if slot.kind in (SlotKind.BLOB, SlotKind.GLYPH):
        bw, bh = _glyph_natural_box(slot, params)
        return (bw * scale, bh * scale)
    return (sw, sh)


def _slot_bbox(
    slot: Slot, center: tuple[float, float], slot_size: tuple[float, float],
    params: dict[str, Any], orient: tuple[str, str] | None = None,
    align: "object | None" = None,
) -> tuple[float, float, float, float]:
    """Absolute ``(minx, miny, maxx, maxy)`` a slot occupies around its centre.

    Sized by the *drawn ink* (``_slot_drawn_size``) for chemistry/blob/glyph and by
    the measured label for TEXT. The union of these (computed by the caller) is the
    scene's *content* extent — what cross-cell transition arrows reach to, instead
    of the wider cell frame (the cell-vs-content fix)."""
    cxc, cyc = center
    if slot.kind == SlotKind.TEXT:
        fs = int(params["tier_text_font_size"])
        w = max(1, len(slot.label or "")) * fs * 0.6
        half_h = fs * 0.7
        return (cxc - w / 2.0, cyc - half_h, cxc + w / 2.0, cyc + half_h)
    if slot.kind in (SlotKind.MOLECULE, SlotKind.RESIDUE, SlotKind.BLOB,
                     SlotKind.GLYPH):
        w, h = _slot_drawn_size(slot, slot_size, params, orient, align)
        return (cxc - w / 2.0, cyc - h / 2.0, cxc + w / 2.0, cyc + h / 2.0)
    return (cxc, cyc, cxc, cyc)


def _slot_bbox_size(
    slot: Slot, slot_size: tuple[float, float], params: dict[str, Any],
    orient: tuple[str, str] | None = None,
    align: "object | None" = None,
) -> tuple[float, float]:
    """The ``(w, h)`` a slot occupies (P5.4 Nit-1).

    The per-kind extent the solver slides a child by (the parent's box) and
    de-overlaps by (the child's own box). Reuses ``_slot_bbox``'s per-kind logic
    at a neutral origin, so a TEXT parent reports its measured width rather than
    the full molecule slot size. *orient* (D6) measures the box on the posed
    molecule so the solve uses the same extent the renderer will draw."""
    minx, miny, maxx, maxy = _slot_bbox(
        slot, (0.0, 0.0), slot_size, params, orient, align)
    return (maxx - minx, maxy - miny)


def _ink_relative_standoff(
    anchor: str, this_pt: tuple[float, float], other_pt: tuple[float, float],
    slots_by_id: dict[str, Slot], slot_extents: dict[str, tuple[float, float]],
    base: float,
) -> float:
    """Per-endpoint connect-edge standoff, made *ink-relative* for big shapes (dim 5).

    A connect edge resolved ``<slot>.center -> <slot>.center`` between a molecule
    and a wide ``blob`` / ``glyph`` buried its arrowhead deep inside the shape: a
    fixed ``base`` (8px) pulled back from the *centre* of a ~140px blob still lands
    ~60px inside the silhouette. When the endpoint is a whole-slot ``center``
    anchor on a BLOB / GLYPH, this returns the slot's drawn half-extent along the
    edge direction (ray-box intersection) plus ``base`` — so the line stops at the
    shape's edge with a one-clearance gap, not in its middle. Every other endpoint
    (atom anchors like ``mol.a1`` / ``mol.bond_a1_a2``, or molecule / residue / text
    centres) keeps the tight fixed ``base``, so curly / H-bond arrows are untouched.
    """
    if "." not in anchor:
        return base
    slot_id, sub = anchor.split(".", 1)
    slot = slots_by_id.get(slot_id)
    if slot is None or sub != "center" or slot.kind not in (SlotKind.BLOB, SlotKind.GLYPH):
        return base
    w, h = slot_extents.get(slot_id, (0.0, 0.0))
    dx, dy = other_pt[0] - this_pt[0], other_pt[1] - this_pt[1]
    length = math.hypot(dx, dy)
    if length == 0.0:
        return base
    ux, uy = abs(dx / length), abs(dy / length)
    hw, hh = w / 2.0, h / 2.0
    cand = []
    if ux > 1e-9:
        cand.append(hw / ux)
    if uy > 1e-9:
        cand.append(hh / uy)
    edge_dist = min(cand) if cand else 0.0
    return edge_dist + base


def _scene_content_width(
    scene: Scene, params: dict[str, Any],
    orient_map: dict[str, tuple[str, str]] | None = None,
    align_map: dict[str, "object"] | None = None,
) -> float:
    """The intrinsic drawn width of a scene's content (max−min x of its solved
    slot boxes). Pub-grade containment: cells were sized for a *single* slot, so
    a scene that spreads several slots horizontally (e.g. ``enz`` right of
    ``sub`` right of ``pill``) overflows its cell and collides with the next
    scene. Sizing the column to the widest scene's content keeps each step inside
    its own cell. For a single-root scene the span is offset-driven and so
    independent of the rect; multi-root scenes spread across the neutral rect, so
    they report a sensible (generous) width rather than a circular one.

    ``orient_map`` is the tier-reconciled pose map (orientation-v2 A); when given,
    the predicted width uses the same pose the renderer will draw (a propagated
    rotation changes a molecule's width), so the cell sizing and the draw agree."""
    slots = scene.slots
    if not slots:
        return 0.0
    sw, sh = params["tier_slot_size"]
    if orient_map is None:
        orient_map = _scene_orientations(scene)
    align_map = align_map or {}
    slot_extents = {
        s.id: _slot_bbox_size(s, (sw, sh), params,
                              orient_map.get(s.id), align_map.get(s.id))
        for s in slots}
    neutral = (0.0, 0.0, float(sw) * max(1, len(slots)), float(sh))
    try:
        centers = _solve_slot_centers(scene, neutral, (sw, sh),
                                      slot_extents=slot_extents)
    except Exception:
        return neutral[2]
    boxes = [_slot_bbox(s, centers[s.id], (sw, sh), params,
                        orient_map.get(s.id), align_map.get(s.id))
             for s in slots if s.id in centers]
    if not boxes:
        return 0.0
    return max(b[2] for b in boxes) - min(b[0] for b in boxes)


def _tier_cell_width(tier: Tier, params: dict[str, Any]) -> float:
    """The cell width a SCENE_ROW tier needs: its widest scene's drawn content
    (floored at one slot) plus horizontal cell padding each side."""
    sw, _sh = params["tier_slot_size"]
    scenes = tier_rendered_scenes(tier)
    tier_orients = _resolve_tier_orientations(scenes)
    tier_align = _resolve_tier_scaffold(scenes, tier_orients)
    content = max(
        (_scene_content_width(sc, params, tier_orients.get(sc.id),
                              tier_align.get(sc.id)) for sc in scenes),
        default=0.0,
    )
    return max(float(sw), content) + 2 * float(params["tier_cell_pad_x"])


def _tier_block_width(tier: Tier, params: dict[str, Any], gutter: float) -> float:
    """The total horizontal extent a SCENE_ROW tier's columns occupy
    (``n * cell_w + (n-1) * gutter``) — the per-tier driver of canvas width."""
    n = _tier_scene_count(tier)
    if n <= 0:
        return 0.0
    return n * _tier_cell_width(tier, params) + (n - 1) * gutter


def _row_cell_rects(
    rect: tuple[float, float, float, float], n: int, gutter: float,
    cell_w: float,
) -> list[tuple[float, float, float, float]]:
    """Split ``rect`` into ``n`` columns of width ``cell_w``, centred in ``rect``.

    Unlike ``_column_rects`` (which stretches columns to fill ``rect``), this
    keeps each column at its natural content width and centres the block, so a
    tight mechanism row stays compact even when the canvas is widened by another
    tier. Falls back to fill when ``cell_w`` would exceed the available
    fill-width (a pinned/cramped canvas) — so pinned-canvas callers are
    unchanged."""
    x, y, w, h = rect
    if n <= 0:
        return []
    fill_w = (w - gutter * (n - 1)) / n
    cw = min(cell_w, fill_w) if cell_w > 0 else fill_w
    block = n * cw + (n - 1) * gutter
    x0 = x + max(0.0, (w - block) / 2.0)
    return [(x0 + i * (cw + gutter), y, cw, h) for i in range(n)]


def _ref_to_key(ref: str) -> str:
    """Translate a TierEdge ref into a registry key: 'scene@edge' -> 'scene.edge';
    'scene.slot.anchor' is already a key."""
    return ref.replace("@", ".")


# ---------------------------------------------------------------------------
# Step 6 — StepSequence expansion (slot-granular, produces real Scenes)
# ---------------------------------------------------------------------------

def _delta_slot_dict(
    value: dict[str, Any] | None,
) -> tuple[dict[str, Any], str | None]:
    """Pull a slot dict + optional parent id from an ADD/REPLACE delta value.

    Accepts both shapes the schema validates: a flat slot dict
    (``{"id": ..., "kind": ...}``, optionally with ``"parent"``) or
    ``{"slot": {...}, "parent": ...}``. ``parent`` is the attach target and is
    never a ``Slot`` field, so it is stripped from the slot dict in BOTH shapes
    (a stray ``parent`` inside the inner ``slot`` dict would otherwise trip
    ``Slot``'s ``extra='forbid'``)."""
    value = value or {}
    inner = value["slot"] if isinstance(value.get("slot"), dict) else value
    slot = {k: v for k, v in inner.items() if k != "parent"}
    return slot, value.get("parent")


def _apply_step_delta(state: dict[str, Any], delta: Any) -> None:
    """Apply one slot-granular ``StepDelta`` to a mutable scene-dict in place.

    ``target`` is slot-oriented (a slot id or ``slot.anchor``) so REMOVE /
    REPLACE / ADD_LABEL act on that slot; REMOVE also drops every attach/connect
    that referenced it, so the rebuilt Scene never carries a dangling edge.
    Anything outside the four slot-granular ops (e.g. the GENERIC escape hatch)
    raises — there is no sub-atom mutation of opaque primitive groups (P6.2).

    The ``StepSequence`` validator's ``known`` set is looser than what these ops
    can honour: it registers nested GROUP-slot ids (recursive collect) and never
    discards an id after a REMOVE. A target that resolves to a nested slot, or to
    a slot a prior cumulative step deleted, therefore passes build-time
    validation but has no live top-level slot here — so we **fail loud** rather
    than silently dropping the author's mutation."""
    op = delta.op
    slots = state.setdefault("slots", [])
    if op == StepOp.ADD:
        slot, parent = _delta_slot_dict(delta.value)
        slots.append(slot)
        if parent is not None:
            state.setdefault("attach", []).append(
                {"child": slot.get("id"), "parent": parent})
        return
    target = (delta.target or "").split(".", 1)[0]
    if not any(s.get("id") == target for s in slots):
        raise ValueError(
            f"step delta {op.value!r} target {delta.target!r} does not resolve "
            "to a live top-level slot in the expanded scene (nested or already "
            "removed)")
    if op == StepOp.ADD_LABEL:
        label = (delta.value or {}).get("label")
        if label is None:
            raise ValueError(
                f"step add_label delta for {delta.target!r} requires "
                "value['label']")
        for s in slots:
            if s.get("id") == target:
                s["label"] = label
        return
    if op == StepOp.REMOVE:
        state["slots"] = [s for s in slots if s.get("id") != target]
        state["attach"] = [
            a for a in state.get("attach", [])
            if a.get("child") != target and a.get("parent") != target]
        state["connect"] = [
            e for e in state.get("connect", [])
            if e.get("from_anchor", "").split(".", 1)[0] != target
            and e.get("to_anchor", "").split(".", 1)[0] != target]
        return
    if op == StepOp.REPLACE:
        new_slot, _parent = _delta_slot_dict(delta.value)
        new_slot["id"] = target  # REPLACE keeps the slot's identity
        state["slots"] = [new_slot if s.get("id") == target else s for s in slots]
        return
    raise ValueError(
        f"step delta op {op.value!r} is not supported by expansion "
        "(slot-granular add / remove / replace / add_label only)")


def expand_step_sequence(seq: StepSequence) -> list[Scene]:
    """Expand a ``StepSequence`` to one concrete, validated ``Scene`` per step.

    Each step's scene is the base scene with that step's deltas applied; with
    ``cumulative=True`` (default) deltas accumulate across steps, otherwise each
    step re-derives from the base. The produced ``Scene.id`` IS the step id —
    the Tier validator already reserves step ids as scene tokens, so cross-step
    transitions (``s1@right`` -> ``s2@left``) resolve and label/badge ir_ids keep
    the ``scene_<step.id>_*`` convention. ``step.badge``/``step.label`` override
    the base; ``step.style`` folds into the scene ``style`` as the cascade's
    outermost layer (P6.4), so per-step restyle rides the P0b.2 cascade with no
    fourth path. Building real ``Scene`` models means each expanded scene
    re-runs ``_validate_scene`` — a delta leaving a dangling attach/connect
    fails loud here.

    Pure (no I/O, no registry) so the layout loop and the canvas sizer can both
    call it and get identical scene lists."""
    base_dict = seq.base.model_dump()
    scenes: list[Scene] = []
    state = copy.deepcopy(base_dict)
    for step in seq.steps:
        if not seq.cumulative:
            state = copy.deepcopy(base_dict)
        for delta in step.deltas:
            _apply_step_delta(state, delta)
        spec = {
            **state,
            "id": step.id,
            "badge": step.badge if step.badge is not None else base_dict.get("badge"),
            "label": step.label if step.label is not None else base_dict.get("label"),
            "style": merge_style(base_dict.get("style"), step.style) or None,
        }
        scenes.append(Scene.model_validate(copy.deepcopy(spec)))
    return scenes


def _tier_scene_list(tier: Tier) -> list[Scene]:
    """The concrete scenes a SCENE_ROW tier lays out — expanding a
    ``step_sequence`` (Step 6) or returning the authored ``scenes``."""
    if tier.step_sequence is not None:
        return expand_step_sequence(tier.step_sequence)
    return list(tier.scenes)


def _tier_scene_count(tier: Tier) -> int:
    """Column count for a SCENE_ROW tier without building Scene models — a
    ``step_sequence`` contributes one column per step (so the canvas sizer
    matches the expanded layout)."""
    if tier.step_sequence is not None:
        return len(tier.step_sequence.steps)
    return len(tier.scenes)


def tier_rendered_scenes(tier: Tier) -> list[Scene]:
    """The scenes a tier lays out into tagged slot groups (P7.0).

    The verify-facing, lockstep view of what :func:`layout_tiers` actually draws:
    the SCENE_ROW main scenes (authored ``scenes`` or the expanded
    ``step_sequence``, via :func:`_tier_scene_list`) followed by the gutter
    ``overlays`` — exactly the scenes the SCENE_ROW branch passes through
    :func:`_layout_scene`, where each slot is tagged ``"<scene.id>.<slot.id>"``.
    Every other role lays out no scenes today, so it contributes none; if a
    future role grows scene rendering, update its branch in ``layout_tiers`` and
    this gate together. ``semantic_check`` / ``convention_check`` walk this so a
    tier figure is no longer silently un-audited.
    """
    if tier.role != TierRole.SCENE_ROW:
        return []
    return [*_tier_scene_list(tier), *tier.overlays]


def layout_tiers(
    figure: Figure,
    layout_params: dict[str, Any] | None = None,
    style_dict: dict[str, Any] | None = None,
) -> list[LayoutEntry]:
    """Lower a tiered ``Figure`` to a flat ``list[LayoutEntry]`` (Step-3 slice).

    Args:
        figure: a ``Figure`` with ``tiers`` populated.
        layout_params: overrides merged onto ``TIER_DEFAULT_PARAMS``. Pin
            ``tier_canvas`` for a fixed envelope; otherwise the canvas is
            content-aware via :func:`tier_canvas`.
        style_dict: the base journal preset (flat style dict). Its text keys
            (``label_font_color`` / ``label_font_family``) are layered under the
            tier params so captions/text follow the journal; molecule slots and
            the scene cascade consume it as the content-channel base (P0b.1/0b.2).

    Returns:
        Entries with baked absolute coordinates, ready for ``_write_svg`` /
        ``render_entries_to_png``.

    Raises:
        ValueError: the figure has no tiers, a molecule slot lacks SMILES, or a
            step delta uses an unsupported op.
        NotImplementedError: a slot uses a kind beyond molecule/text (primitive
            refresh).
    """
    if not figure.tiers:
        raise ValueError("layout_tiers requires a Figure with tiers populated")
    # Defaults < base-preset text keys < explicit layout_params (caller wins).
    params = merge_style(
        TIER_DEFAULT_PARAMS, _preset_tier_params(style_dict), layout_params)
    # Self-size through tier_canvas so the baked coords match the compositor's
    # SVG viewport (which sizes through the same function).
    canvas = tier_canvas(figure, layout_params)
    margin = float(params["tier_margin"])
    gutter = float(params["tier_gutter"])
    registry = AnchorRegistry()
    entries: list[LayoutEntry] = []

    for tier, rect in _tier_rects(figure.tiers, canvas, margin, params):
        tx, ty, tw, th = rect

        # Band chrome: background / border / top divider (all style-driven).
        tstyle = tier.style or {}
        if any(k in tstyle for k in ("band_fill", "band_stroke", "divider")):
            entries.append(LayoutEntry(
                (lambda r=rect, s=tstyle, p=params: _band_chrome(r, s, p)),
                (), {}, (0.0, 0.0), ir_id=f"tier_{tier.id}_chrome"))

        if tier.role == TierRole.TITLE:
            title_fs = int(params["tier_title_font_size"])
            sub_fs = int(params["tier_subtitle_font_size"])
            cxm = tx + tw / 2.0
            band_cy = ty + th / 2.0
            gap = title_fs * float(params["tier_title_subtitle_em"])
            # Fixed baseline geometry (not band fractions): a one- or two-line
            # block centred in the band with a separation guaranteed to clear the
            # legibility overlap heuristic even when the band is thin.
            if tier.label and tier.subtitle:
                title_y, sub_y = band_cy - gap * 0.4, band_cy - gap * 0.4 + gap
            elif tier.label:
                title_y, sub_y = band_cy + title_fs * 0.35, None
            else:
                title_y, sub_y = None, band_cy + sub_fs * 0.35
            if tier.label:
                entries.append(LayoutEntry(
                    (lambda t=tier.label, x=cxm, y=title_y, fs=title_fs,
                            p=params: _text_group(t, (x, y), fs,
                                            str(p["tier_text_color"]),
                                            str(p["tier_font_family"]),
                                            anchor="middle", weight="bold")),
                    (), {}, (0.0, 0.0), ir_id=f"tier_{tier.id}_title"))
            if tier.subtitle:
                entries.append(LayoutEntry(
                    (lambda t=tier.subtitle, x=cxm, y=sub_y, fs=sub_fs,
                            p=params: _text_group(t, (x, y), fs,
                                            str(p["tier_text_color"]),
                                            str(p["tier_font_family"]),
                                            anchor="middle", italic=True)),
                    (), {}, (0.0, 0.0), ir_id=f"tier_{tier.id}_subtitle"))
            continue

        if tier.role == TierRole.SCENE_ROW:
            # Step 6: a step_sequence expands to one concrete Scene per step,
            # then feeds the identical column-layout path as authored scenes.
            row_scenes = _tier_scene_list(tier)
            # P0b.2 cascade bases: the content channel layers the base preset
            # under tier.style; the structural channel (edges) takes tier.style
            # alone (no preset, so bare preset stroke can't recolour edges).
            content_base = merge_style(style_dict, tier.style)
            # orientation-v2 A: reconcile poses across the whole rendered scene
            # set (row + overlays) ONCE, so a molecule recurring across panels
            # keeps one pose and the same map drives both the cell sizing
            # (_tier_cell_width) and the per-scene render below.
            tier_orients = _resolve_tier_orientations(tier_rendered_scenes(tier))
            # orientation-v2 B: detect a transforming scaffold series and align
            # each member's depiction to a shared reference (conserved core keeps
            # one pose). Same map drives the cell sizing and the render below.
            tier_align = _resolve_tier_scaffold(
                tier_rendered_scenes(tier), tier_orients)
            # Overlays (gutter/free scenes) share the band: when present, the
            # main row takes the top (1 - frac) and the overlays a bottom gutter
            # strip. Carving only when overlays exist keeps every overlay-free
            # figure byte-identical. Both rows publish anchors BEFORE transitions
            # resolve, so a TierEdge (e.g. a "departs" arrow) can connect a row
            # scene to an overlay.
            if tier.overlays:
                gfrac = float(params["tier_overlay_gutter_frac"])
                main_rect = (tx, ty, tw, th * (1.0 - gfrac))
                gutter_rect = (tx, ty + th * (1.0 - gfrac), tw, th * gfrac)
            else:
                main_rect, gutter_rect = rect, None
            cell_w = _tier_cell_width(tier, params)
            cols = _row_cell_rects(main_rect, len(row_scenes), gutter, cell_w)
            for scene, cell in zip(row_scenes, cols):
                # P5.1: solve + publish each scene inside a registry layer so a
                # mid-scene failure rolls back its partial anchor publishes
                # rather than leaving half a scene in the figure-global table; a
                # clean scene commits to the base for the cross-cell transitions
                # resolved (outside any layer) after the whole row is laid out.
                with registry.layer():
                    scene_entries = _layout_scene(
                        scene, cell, registry, params,
                        base_style=content_base, tier_style=tier.style,
                        orient_map=tier_orients.get(scene.id),
                        align_map=tier_align.get(scene.id))
                entries.extend(scene_entries)

            # Overlay scenes in the gutter strip — same layout path + cascade,
            # each in its own committing layer, so their anchors join the base
            # registry for transition resolution below.
            if gutter_rect is not None:
                ocell_w = max(
                    (_scene_content_width(sc, params, tier_orients.get(sc.id),
                                          tier_align.get(sc.id))
                     + 2 * float(params["tier_cell_pad_x"]) for sc in tier.overlays),
                    default=float(params["tier_slot_size"][0]))
                ocols = _row_cell_rects(
                    gutter_rect, len(tier.overlays), gutter, ocell_w)
                for scene, cell in zip(tier.overlays, ocols):
                    with registry.layer():
                        overlay_entries = _layout_scene(
                            scene, cell, registry, params,
                            base_style=content_base, tier_style=tier.style,
                            orient_map=tier_orients.get(scene.id),
                            align_map=tier_align.get(scene.id))
                    entries.extend(overlay_entries)

            # Rails: resolve a fraction of the tier extent to an absolute scalar.
            for rail in tier.rails:
                if rail.axis == RailAxis.Y:
                    registry.publish_rail(rail.name, "y", ty + rail.at * th)
                else:
                    registry.publish_rail(rail.name, "x", tx + rail.at * tw)

            # P0a.5: aggregate-validate non-rail transition endpoints before
            # resolving so all bad refs surface in one error. 'rail:' endpoints
            # are screened here and handled by the NotImplementedError guard below
            # (preserving its ordering for the bare-rail-unsupported contract).
            _te_refs = [
                (te, raw, _ref_to_key(raw))
                for te in tier.transitions
                if not (te.from_ref.startswith("rail:") or te.to_ref.startswith("rail:"))
                for raw in (te.from_ref, te.to_ref)
            ]
            _bad_te = set(registry.validate_refs(key for _t, _r, key in _te_refs))
            if _bad_te:
                offenders = "; ".join(
                    f"{te.ir_id}: {raw!r}" for te, raw, key in _te_refs if key in _bad_te
                )
                raise ValueError(
                    f"Tier '{tier.id}' has unresolved transition endpoint(s): {offenders}"
                )

            # Cross-cell transition arrows.
            for te in tier.transitions:
                if te.from_ref.startswith("rail:") or te.to_ref.startswith("rail:"):
                    raise NotImplementedError(
                        f"Tier '{tier.id}' transition uses a 'rail:' endpoint; "
                        "bare-rail endpoints are not in the Step-3 slice "
                        "(use a scene/slot anchor with on_rail to ride a rail)")
                t_standoff = float(params["tier_transition_standoff"])
                p0, p1 = registry.resolve_edge(
                    _ref_to_key(te.from_ref), _ref_to_key(te.to_ref),
                    from_standoff=t_standoff,
                    to_standoff=t_standoff,
                    on_rail=te.on_rail,
                )
                # Structural cascade: tier ⊕ this transition's style (no preset).
                te_style = merge_style(tier.style, te.style)
                entries.append(LayoutEntry(
                    (lambda a=p0, b=p1, t=te.type, s=te_style: _edge_group(a, b, t, s)),
                    (), {}, (0.0, 0.0), ir_id=te.ir_id))
                # D4: a TierEdge label was silently dropped — only the arrow drew.
                # Place it just above the shaft midpoint (perpendicular offset) so
                # the transition reads "<label>" over its arrow rather than the
                # text crossing the shaft. A near-vertical arrow offsets to the
                # right instead (no "above" to speak of).
                if te.label:
                    lfs = int(params["tier_caption_font_size"])
                    lpos = _transition_label_pos(
                        p0, p1, float(params["tier_transition_label_gap"]) + lfs / 2.0)
                    lcol = str(te_style.get("label_font_color", params["tier_text_color"]))
                    lfam = str(te_style.get("label_font_family", params["tier_font_family"]))
                    entries.append(LayoutEntry(
                        (lambda t=te.label, c=lpos, fs=lfs, col=lcol, fam=lfam:
                            _text_group(t, c, fs, col, fam, anchor="middle")),
                        (), {}, (0.0, 0.0), ir_id=f"{te.ir_id}_label"))
            continue

        # SUMMARY_BAR / BAND: band background only in the slice (inner content
        # arrives with the full tier compositor in Step 4).

    return entries
