"""Ring edge-label decluttering, label-request emission + leader lines.

Phase R1.e, extracted from ``pathway_layout``. The label layer of the pathway
engine: it decides what text the figure asks the label solver to place
(``pathway_label_requests`` — entity, relation and ring-edge labels) and draws
the dashed leaders that tie an externalized (rung-4) label back to its entity
(``pathway_extlabel_leaders``), plus the ring-label tangential fan-out that keeps
co-located edge labels legible.

Top of the pathway-engine DAG: imports down into ``_pathway_rings`` (ring order),
``_pathway_bands`` (bbox exit), and ``_pathway_common`` (arrow table). The
``label_placement`` imports stay function-local (lazy) — a module-level import
would re-create the documented ``pathway_layout`` <-> ``label_placement`` cycle.
The orchestrator re-exports the two public ``pathway_*`` entry points the
compositor calls.
"""
from __future__ import annotations

import math

import svgwrite.container
import svgwrite.shapes

from imageGen.layout._geom import ENTITY_BBOX, PRIMITIVE_REGISTRY
from imageGen.layout._pathway_bands import _bbox_exit_point
from imageGen.layout._pathway_common import RELATION_TO_ARROW
from imageGen.layout._pathway_rings import _ring_order
from imageGen.layout.types import LayoutEntry
from imageGen.primitives import proteins
from imageGen.primitives._text import fit_label


# ---------------------------------------------------------------------------
# Bug 6: ring edge-label decluttering knobs.
# ---------------------------------------------------------------------------

_RING_RADIAL_NUDGE = 24.0        # px — outward push of an edge label off the ring
_RING_DIVERGE_THRESHOLD = 20.0   # px — pairs closer than this get fanned apart
_RING_DIVERGE_PUSH = 12.0        # px — tangential push applied to each of the pair


def _fan_apart_ring_labels(ring_label_data: list[tuple]) -> list[tuple]:
    """Push co-located ring edge labels apart along their tangents.

    Each item is ``(anchor, (ux, uy), priority, text, ir_id)`` where ``(ux, uy)``
    is the outward radial unit vector at the label's anchor. When two labels'
    anchors fall within ``_RING_DIVERGE_THRESHOLD`` px, each is shifted by
    ``_RING_DIVERGE_PUSH`` px along its own tangent (perpendicular to its
    radial), in the direction that increases their separation, so the pair fans
    apart instead of stacking. Order is preserved; a label is pushed at most
    once (by its nearest close neighbour). Returns a new list.
    """
    n = len(ring_label_data)
    if n < 2:
        return ring_label_data

    anchors = [item[0] for item in ring_label_data]
    out = list(ring_label_data)
    for i in range(n):
        ax, ay = anchors[i]
        # Find the nearest other label within the divergence threshold.
        nearest_j = -1
        nearest_d = _RING_DIVERGE_THRESHOLD
        for j in range(n):
            if j == i:
                continue
            d = math.hypot(anchors[j][0] - ax, anchors[j][1] - ay)
            if d < nearest_d:
                nearest_d = d
                nearest_j = j
        if nearest_j < 0:
            continue
        # Tangent = perpendicular to this label's radial unit vector.
        ux, uy = ring_label_data[i][1]
        tx, ty = -uy, ux
        # Push along the tangent in whichever direction moves away from the
        # neighbour (positive dot with the neighbour→self vector).
        away_x, away_y = ax - anchors[nearest_j][0], ay - anchors[nearest_j][1]
        sign = 1.0 if (tx * away_x + ty * away_y) >= 0 else -1.0
        new_anchor = (ax + tx * _RING_DIVERGE_PUSH * sign,
                      ay + ty * _RING_DIVERGE_PUSH * sign)
        item = out[i]
        out[i] = (new_anchor, item[1], item[2], item[3], item[4])
    return out


# FR8: candidate-side order for a relation label, keyed by the preferred side.
# Each tuple leads with the requested side, then a sensible fallback sweep, so
# place_labels still resolves when the preferred side is occupied.
_SIDE_PRIORITY: dict[str, tuple[str, ...]] = {
    "above": ("above", "below", "right", "left", "center"),
    "below": ("below", "above", "right", "left", "center"),
    "left":  ("left", "right", "above", "below", "center"),
    "right": ("right", "left", "above", "below", "center"),
}


def _relation_label_priority(
    relation: Relation, dx: float, dy: float, has_reciprocal: bool
) -> tuple[str, ...]:
    """Candidate-side order for a relation label (FR8).

    Resolution order:
      1. Explicit ``relation.label_side`` wins — leads the priority with that side.
      2. Otherwise, a relation that is half of a labeled reciprocal pair
         (``A→B`` and ``B→A`` both labeled) is auto-assigned the side
         *perpendicular* to the edge, opposite to its twin: for a mostly-
         horizontal pair one label goes above and the other below; for a
         mostly-vertical pair, left/right. Which twin gets the primary side is
         decided deterministically by endpoint ordering.
      3. Otherwise, the orientation default (unchanged pre-FR8 behavior).
    """
    if relation.label_side is not None:
        return _SIDE_PRIORITY[relation.label_side.value]
    if has_reciprocal:
        horizontal = abs(dx) >= abs(dy)
        primary = (relation.source, relation.target) < (relation.target, relation.source)
        if horizontal:
            side = "above" if primary else "below"
        else:
            side = "left" if primary else "right"
        return _SIDE_PRIORITY[side]
    if abs(dx) >= abs(dy):
        return ("above", "below", "right", "left", "center")
    return ("right", "left", "above", "below", "center")


def pathway_label_requests(
    figure: Figure,
    entries: list[LayoutEntry],
    layout_params: dict | None = None,
) -> list:
    """Emit one `LabelRequest` per labeled relation in a pathway figure.

    Walks `figure.relations`; for each relation whose `label` is a
    non-empty string, anchors a request at the midpoint of the
    corresponding arrow's start/end (read back from the matching arrow
    LayoutEntry). The anchor bbox is small (a thin shaft point), so
    label_placement's offset gap dominates the spacing.

    Imported lazily by `label_placement.py` callers; declared here so
    the IR-shape walk lives next to its archetype's other concerns.
    Returns `list[label_placement.LabelRequest]` (typed as `list` to
    avoid an import cycle in this module).

    Args:
        figure: The same IR Figure passed to `layout_pathway`.
        entries: The exact list returned from `layout_pathway(figure)`.
            Used to recover the bbox-inset arrow endpoints (so labels
            anchor at the rendered arrow midpoint, not the raw entity
            centers).
        layout_params: Optional overlay; reserved for future use
            (currently no params are read).

    Returns:
        A list of LabelRequest items, one per `Relation.label` that is
        truthy. Empty when no relations carry labels.
    """
    from imageGen.layout.label_placement import LabelRequest  # noqa: PLC0415 — break import cycle

    arrow_entries = [e for e in entries if e.primitive in RELATION_TO_ARROW.values()]
    if len(arrow_entries) != len(figure.relations):
        raise ValueError(
            "pathway_label_requests requires the entries list returned by "
            "layout_pathway(figure); arrow count does not match relations"
        )

    # LT1: in ring mode, push edge labels radially outward from the ring centre
    # so enzyme/reaction names sit outside the ring instead of inside it. The
    # centre is the mean of the entity centres (exact for an evenly-spaced ring).
    ring_mode = _ring_order(figure) is not None
    ring_center: tuple[float, float] | None = None
    if ring_mode:
        _ent_prims = frozenset(PRIMITIVE_REGISTRY.values())
        ent_pts = [e.args[1] for e in entries if e.primitive in _ent_prims]
        if ent_pts:
            ring_center = (
                sum(p[0] for p in ent_pts) / len(ent_pts),
                sum(p[1] for p in ent_pts) / len(ent_pts),
            )

    # Bug 5: entity-anchored labels (external rung-4 labels + sublabels) are
    # collected separately from relation labels so they can be submitted to
    # place_labels FIRST. A relation label can roam the whole canvas, but an
    # external entity label has only one sensible home — beside its own box.
    # Submitting it first lets it claim that slot before a relation label takes
    # it (which is what made "Fluorescence-activated cell sorting" land on top
    # of "load onto sorter" in stress3).
    relation_requests: list[LabelRequest] = []
    sublabel_requests: list[LabelRequest] = []
    extlabel_requests: list[LabelRequest] = []
    # Bug 6: ring edge labels are collected here (anchor, radial unit vector,
    # priority, text, ir_id) and emitted after the loop so a divergence pass can
    # fan apart any co-located pair before requests are built.
    ring_label_data: list[tuple] = []
    # FR8: directed endpoint pairs that carry a label, so a relation can tell
    # whether it is half of a labeled reciprocal (A→B + B→A) pair.
    _labeled_pairs = {
        (r.source, r.target) for r in figure.relations if r.label
    }
    for relation, arrow in zip(figure.relations, arrow_entries):
        text = relation.label
        if not text:
            continue
        (sx, sy), (ex, ey) = arrow.args
        midpoint = ((sx + ex) / 2, (sy + ey) / 2)
        anchor = midpoint

        if ring_center is not None:
            # Radial outward direction from ring centre through the chord
            # midpoint; bias the label off the ring and try the outward
            # side first. Bug 6: nudge further out (was 14px) so edge labels
            # clear their adjacent ring node instead of jamming against it
            # (e.g. "SDH"/"SCS" beside "Succinate" at the bottom of the ring).
            rx, ry = midpoint[0] - ring_center[0], midpoint[1] - ring_center[1]
            norm = math.hypot(rx, ry) or 1.0
            ux, uy = rx / norm, ry / norm
            anchor = (midpoint[0] + ux * _RING_RADIAL_NUDGE,
                      midpoint[1] + uy * _RING_RADIAL_NUDGE)
            if abs(ux) >= abs(uy):
                priority = (("right", "above", "below", "left", "center")
                            if ux > 0 else
                            ("left", "above", "below", "right", "center"))
            else:
                priority = (("below", "right", "left", "above", "center")
                            if uy > 0 else
                            ("above", "right", "left", "below", "center"))
            ring_label_data.append(
                (anchor, (ux, uy), priority, text, relation.ir_id)
            )
            continue
        else:
            # Place the label perpendicular to the arrow shaft so it doesn't
            # render directly on top of the line. FR8: an explicit
            # ``relation.label_side`` (or auto-detected reciprocal pair) leads
            # the priority so parallel forward/back labels separate onto opposite
            # sides; otherwise the orientation default applies.
            dx, dy = ex - sx, ey - sy
            has_reciprocal = (relation.target, relation.source) in _labeled_pairs
            priority = _relation_label_priority(relation, dx, dy, has_reciprocal)
        # Anchor is a notional point on the arrow shaft; small bbox so
        # label_placement's gap dominates spacing.
        relation_requests.append(LabelRequest(
            text=text,
            anchor=anchor,
            anchor_size=(2.0, 2.0),
            priority=priority,
            ir_id=relation.ir_id,
        ))

    # Bug 6: ring edge labels were deferred above so co-located pairs can be
    # fanned apart along the tangent before their requests are built. Two
    # adjacent chords can share nearly the same radial angle (a tight ring),
    # placing their outward-nudged anchors on top of each other; push each
    # along its tangent away from the other so the labels diverge.
    fanned = _fan_apart_ring_labels(ring_label_data)
    for anchor, _radial, priority, text, ir_id in fanned:
        relation_requests.append(LabelRequest(
            text=text,
            anchor=anchor,
            anchor_size=(2.0, 2.0),
            priority=priority,
            ir_id=ir_id,
        ))

    # V2 / L5: entity sublabels — text anchored to entity bbox, placed below
    # first (avoids arrow shafts which run beside / above most entities).
    _entity_prim_set = frozenset(PRIMITIVE_REGISTRY.values())
    entity_entry_by_id = {
        e.ir_id: e for e in entries if e.primitive in _entity_prim_set
    }
    for entity in figure.entities:
        sublabel = (entity.style or {}).get("sublabel")
        if not sublabel:
            continue
        entry = entity_entry_by_id.get(entity.id)
        if entry is None:
            continue
        cx, cy = entry.args[1]
        size = entry.kwargs.get("size", ENTITY_BBOX.get(entity.type, (60.0, 30.0)))
        sublabel_requests.append(LabelRequest(
            text=sublabel,
            anchor=(cx, cy),
            anchor_size=size,
            priority=("below", "above", "right", "left", "center"),
            ir_id=f"{entity.id}_sublabel",
        ))

    # LABEL_FIT rung 4: a fit-aware entity whose label can't fit even at the
    # font floor renders an empty box (see proteins.FIT_AWARE_PRIMITIVES). The
    # primitive and this walk both call _text.fit_label with the same box size
    # and style, so they agree on which entities are external; here we re-place
    # the full label just outside the box via the standard placement machinery.
    for entity in figure.entities:
        entry = entity_entry_by_id.get(entity.id)
        if entry is None or entry.primitive not in proteins.FIT_AWARE_PRIMITIVES:
            continue
        cx, cy = entry.args[1]
        size = entry.kwargs.get("size", ENTITY_BBOX.get(entity.type, (60.0, 30.0)))
        style = entry.kwargs.get("style_dict") or proteins.DEFAULT_STYLE
        fit = fit_label(entity.label, size[0], size[1], style)
        if not fit.external:
            continue
        extlabel_requests.append(LabelRequest(
            text=entity.label,
            anchor=(cx, cy),
            anchor_size=size,
            priority=("below", "above", "right", "left", "center"),
            ir_id=f"{entity.id}_extlabel",
        ))

    # External entity labels first (claim their box-adjacent slot), then
    # relation labels (free to roam), then sublabels.
    return extlabel_requests + relation_requests + sublabel_requests


# ---------------------------------------------------------------------------
# Bug 5: leader lines for externalized (rung-4) entity labels.
# A fit-aware entity whose label can't fit even at the font floor renders an
# empty box; its label is re-placed outside the box by place_labels. Without a
# connector, the floating text reads as unrelated to the box. After placement
# we walk the entries, pair each placed `_extlabel` with its entity box, and
# draw a thin dashed edge-to-edge connector.
# ---------------------------------------------------------------------------

_LEADER_DASH = "3,2"            # dash pattern for the external-label connector
_LEADER_STROKE_WIDTH = 0.5      # px — deliberately hairline so it never competes
# A relation label normally sits ~15-19 px off its arrow shaft (offset gap +
# half its own height). When collision avoidance pushes it further than this,
# the association with its arrow is lost (e.g. "Thr24" floating ~40 px away,
# beside an unrelated box) — tether it back to the shaft with a hairline leader.
_RELATION_LEADER_MIN_GAP = 28.0


def _nearest_point_on_polyline(
    p: tuple[float, float],
    pts: list[tuple[float, float]],
) -> tuple[tuple[float, float], float]:
    """Closest point on a polyline to ``p`` and its distance.

    Walks each segment, projecting ``p`` onto it (clamped to the segment), and
    returns the nearest projection found. ``pts`` must hold at least one point;
    a single point degenerates to that point.
    """
    if len(pts) == 1:
        q = pts[0]
        return q, math.hypot(p[0] - q[0], p[1] - q[1])
    best_q = pts[0]
    best_d = math.inf
    px, py = p
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        dx, dy = bx - ax, by - ay
        L = dx * dx + dy * dy
        if L == 0.0:
            qx, qy = ax, ay
        else:
            t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L))
            qx, qy = ax + t * dx, ay + t * dy
        d = math.hypot(px - qx, py - qy)
        if d < best_d:
            best_d, best_q = d, (qx, qy)
    return best_q, best_d


def _leader_line(
    start: tuple[float, float],
    end: tuple[float, float],
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """A hairline dashed connector from an external label to its entity box."""
    s = {**proteins.DEFAULT_STYLE, **(style_dict or {})}
    color = s.get("label_font_color", "#1A1A1A")
    g = svgwrite.container.Group()
    line = svgwrite.shapes.Line(start=start, end=end, stroke=color)
    line["stroke-width"] = _LEADER_STROKE_WIDTH
    line["stroke-dasharray"] = _LEADER_DASH
    g.add(line)
    return g


def pathway_extlabel_leaders(
    entries: list[LayoutEntry],
    style_dict: dict | None = None,
) -> list[LayoutEntry]:
    """Insert dashed leader lines that re-associate drifted labels with their owner.

    Operates on the post-`place_labels` entry list. Two kinds of leader are emitted:

    * **External entity label** (`label_{id}_extlabel`): a fit-aware entity whose
      label can't fit renders an empty box and the label is placed outside it;
      connect label edge to box edge (edge-to-edge).
    * **Relation label** (`label_{relation_id}`): when collision avoidance has
      pushed the label further than ``_RELATION_LEADER_MIN_GAP`` from its arrow
      shaft, tether the label edge to the nearest point on the shaft. Labels that
      sit comfortably beside their shaft get no leader (no clutter).

    Returns the entries with leader-line LayoutEntry items inserted immediately
    before the first placed label (so leaders draw over content but under label
    text). A no-op (returns the input unchanged) when no leaders are needed, so it
    is safe to call for every archetype.

    The split point — the index of the first label entry — equals the count of
    pre-label entries, so a caller that slices ``result[:n]`` / ``result[n:]``
    (e.g. the per-panel label path) keeps leaders grouped with the labels.
    """
    from imageGen.layout.label_placement import (  # noqa: PLC0415 — break cycle
        _DEFAULT_LABEL_STYLE,
        _estimate_text_bbox,
        _label_primitive,
    )

    ent_prims = frozenset(PRIMITIVE_REGISTRY.values())
    entity_geom: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
    for e in entries:
        if e.primitive in ent_prims and e.ir_id is not None and len(e.args) >= 2:
            size = e.kwargs.get("size", (60.0, 30.0))
            entity_geom[e.ir_id] = (e.args[1], size)

    # Relation-label leaders need the rendered shaft of each arrow (start, any
    # waypoints, end) keyed by the relation's ir_id (which the placed label
    # carries as `label_{relation_id}`).
    arrow_prims = frozenset(RELATION_TO_ARROW.values())
    arrow_geom: dict[str, list[tuple[float, float]]] = {}
    for e in entries:
        if e.primitive in arrow_prims and e.ir_id is not None and len(e.args) >= 2:
            start, end = e.args
            wps = e.kwargs.get("waypoints") or []
            arrow_geom[e.ir_id] = [start, *wps, end]

    def _font_size(e: LayoutEntry) -> float:
        return float(
            (e.kwargs.get("style_dict") or _DEFAULT_LABEL_STYLE)["label_font_size"]
        )

    leaders: list[LayoutEntry] = []
    first_label_idx = len(entries)
    for i, e in enumerate(entries):
        if e.primitive is not _label_primitive:
            continue
        first_label_idx = min(first_label_idx, i)
        ir_id = e.ir_id or ""
        if not ir_id.startswith("label_"):
            continue
        key = ir_id[len("label_"):]
        label_center = e.args[1]

        # (a) Externalized entity label -> connect to its box (edge-to-edge).
        if key.endswith("_extlabel"):
            entity_id = key[: -len("_extlabel")]
            geom = entity_geom.get(entity_id)
            if geom is None:
                continue
            box_center, box_size = geom
            lw, lh = _estimate_text_bbox(str(e.args[0]), _font_size(e))
            label_exit = _bbox_exit_point(label_center, lw / 2, lh / 2, box_center, 0.0)
            box_exit = _bbox_exit_point(
                box_center, box_size[0] / 2, box_size[1] / 2, label_center, 0.0
            )
            leaders.append(LayoutEntry(
                primitive=_leader_line,
                args=(label_exit, box_exit),
                kwargs={"style_dict": style_dict} if style_dict else {},
                position=(0.0, 0.0),
                ir_id=f"leader_{entity_id}",
            ))
            continue

        # (b) Relation label that drifted far from its shaft -> tether to shaft.
        shaft = arrow_geom.get(key)
        if shaft is None:
            continue
        nearest_pt, dist = _nearest_point_on_polyline(label_center, shaft)
        if dist <= _RELATION_LEADER_MIN_GAP:
            continue
        lw, lh = _estimate_text_bbox(str(e.args[0]), _font_size(e))
        label_exit = _bbox_exit_point(label_center, lw / 2, lh / 2, nearest_pt, 0.0)
        leaders.append(LayoutEntry(
            primitive=_leader_line,
            args=(label_exit, nearest_pt),
            kwargs={"style_dict": style_dict} if style_dict else {},
            position=(0.0, 0.0),
            ir_id=f"leader_{key}",
        ))

    if not leaders:
        return entries
    return entries[:first_label_idx] + leaders + entries[first_label_idx:]
