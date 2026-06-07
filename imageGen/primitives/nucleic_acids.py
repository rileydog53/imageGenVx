"""Nucleic acid primitives for scientific figure generation.

Visual conventions followed here:
- DNA double helix: two sine waves with 180° phase offset projected perpendicularly
  onto the helix axis. Crossover depth is conveyed by alternating z-order at each
  half-period -- even segments show strand 1 in front (drawn last), odd segments
  show strand 2 in front. Base pair rungs are drawn at the half-period midpoints;
  when a sequence string is provided, rungs are color-coded (A-T red, G-C blue)
  and labeled with both bases ("A-T", "G-C").
- RNA: a single sine wave in orange (convention: RNA is orange, DNA is blue in
  most cell-biology pathway figures). double-stranded RNA uses the same crossover
  z-order logic as DNA.
- Chromatin: beads-on-string at condensation_level=0 (nucleosome circles on a thin
  backbone), condensed fiber at condensation_level=1. Intermediate values interpolate:
  nucleosome radius shrinks and fiber opacity rises linearly.

Phase 3 coupling:
  dna_segment and rna_segment accept start/end axis coordinates directly. Composability
  is by caller convention -- a transcription schematic places rna_segment(start=tx_site)
  at a coordinate derived from a dna_segment call without importing this module twice.
  No anchor protocol needed here (contrast: membranes.py MembraneCurve, which exists
  because membrane proteins must anchor to an arbitrary closed curve).

Phase 4 assumption:
  DEFAULT_STYLE uses flat namespaced keys (dna_*, rna_*, chromatin_*, label_*)
  so the Phase 4 master preset JSON can union all primitive modules without collision.

Future extensibility:
  - Methylation marks: extend the rung-drawing section of dna_segment with an
    optional methyl marker at CpG positions -- no changes to the public signature.
  - New RNA colors: change rna_stroke in the preset, not this module.
  - Supercoiled accuracy: _supercoiled_axis() currently uses a secondary sine wave.
    Replace it with a true plectonemic algorithm in Phase 6 without changing the
    dna_segment() public API.
  - Chromatin detail: add histone tail glyphs by extending the bead loop in
    chromatin() without changing its signature.
"""
from __future__ import annotations

import math

import svgwrite
import svgwrite.container
import svgwrite.shapes
import svgwrite.text

from imageGen.primitives._svg import polyline_to_svg_points as _polyline_to_svg_points

# ---------------------------------------------------------------------------
# Style defaults -- flat namespaced keys for Phase 4 preset union
# ---------------------------------------------------------------------------

DEFAULT_STYLE: dict[str, object] = {
    # DNA strands
    "dna_strand1_stroke":           "#1565C0",   # convention: DNA strand 1 blue
    "dna_strand2_stroke":           "#0D47A1",   # strand 2, slightly darker
    "dna_strand_stroke_width":       2.0,
    "dna_amplitude":                15.0,        # px, peak perpendicular offset
    "dna_period":                   40.0,        # px per full helical turn along axis
    "dna_sample_rate":               8,           # points per half-period (curve smoothness)
    # DNA base pair rungs
    "dna_rung_stroke":              "#607D8B",   # neutral rung color (no sequence)
    "dna_rung_stroke_width":         1.5,
    "dna_rung_at_fill":             "#E53935",   # A-T pair rung (with sequence)
    "dna_rung_gc_fill":             "#1E88E5",   # G-C pair rung (with sequence)
    "dna_base_label_font_size":      8,           # pt, base-pair label on rungs
    "dna_base_label_show":           True,        # show "A-T" labels when sequence given
    # DNA double-strand break (LT7): when a segment is drawn broken, both strands
    # are interrupted by a clear axis gap of this width (px), with a short blunt
    # cap line drawn across each cut end so the break reads as a DSB, not a join.
    "dna_break_gap":                14.0,
    "dna_break_cap_show":           True,
    "dna_break_cap_stroke":         "#37474F",
    "dna_break_cap_stroke_width":    1.5,
    # RNA
    "rna_stroke":                   "#E65100",   # convention: RNA orange
    "rna_stroke_width":              2.0,
    "rna_amplitude":                10.0,
    "rna_period":                   30.0,
    "rna_sample_rate":               8,
    # Chromatin
    "chromatin_backbone_stroke":    "#546E7A",
    "chromatin_backbone_stroke_width": 1.5,
    "chromatin_nucleosome_fill":    "#7E57C2",   # histone purple
    "chromatin_nucleosome_stroke":  "#512DA8",
    "chromatin_nucleosome_stroke_width": 1.0,
    "chromatin_nucleosome_radius":  12.0,
    "chromatin_nucleosome_spacing": 40.0,        # px between nucleosome centres
    "chromatin_fiber_fill":         "#7E57C2",
    "chromatin_fiber_stroke":       "#512DA8",
    "chromatin_fiber_stroke_width":  1.5,
    "chromatin_fiber_width":        20.0,        # px, condensed fiber thickness
    # Shared label
    "label_font_family":            "Helvetica, Arial, sans-serif",
    "label_font_size":               11,
    "label_font_color":             "#1A1A1A",
}


# ---------------------------------------------------------------------------
# Private geometry helpers
# ---------------------------------------------------------------------------

def _axis_frame(
    start: tuple[float, float],
    end: tuple[float, float],
) -> tuple[float, float, float, float, float]:
    """Return (length, tangent_x, tangent_y, perp_x, perp_y) for the axis start→end.

    The perpendicular vector is the tangent rotated 90° CCW -- in SVG's y-down
    coordinate system, CCW means the perpendicular points "upward" for a left-to-right
    axis. Used by _sample_strand_on_path to project sine waves perpendicularly.
    """
    x0, y0 = start
    x1, y1 = end
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return 0.0, 1.0, 0.0, 0.0, 1.0
    tx, ty = dx / length, dy / length
    return length, tx, ty, -ty, tx  # perp = (-ty, tx) is CCW rotation


def _supercoiled_axis(
    start: tuple[float, float],
    end: tuple[float, float],
    n_pts: int,
    amp_factor: float,
) -> list[tuple[float, float]]:
    """Return n_pts positions on a secondary-sinusoidal axis from start to end.

    The axis oscillates with two full cycles over its length (period = axis_length/2),
    simulating the writhing of plectonemic supercoiled DNA. amp_factor controls the
    lateral displacement in pixels. This is a schematic approximation sufficient for
    v1 -- replace with a true plectonemic algorithm in Phase 6 via this helper only.
    """
    x0, y0 = start
    x1, y1 = end
    _, _, _, px, py = _axis_frame(start, end)
    pts: list[tuple[float, float]] = []
    for i in range(n_pts):
        t = i / (n_pts - 1) if n_pts > 1 else 0.0
        bx = x0 + t * (x1 - x0)
        by = y0 + t * (y1 - y0)
        secondary = amp_factor * math.sin(4 * math.pi * t)  # two full oscillations
        pts.append((bx + secondary * px, by + secondary * py))
    return pts


def _sample_strand_on_path(
    axis_pts: list[tuple[float, float]],
    amplitude: float,
    period: float,
    phase: float,
) -> list[tuple[float, float]]:
    """Return (x, y) positions for one strand of a helix along an axis path.

    Projects a sine wave perpendicularly onto the local frame at each axis point.
    Arc length along the axis drives the sine phase so the period is in pixels of
    helix-axis distance, consistent for both straight and supercoiled axes.

    Args:
        axis_pts: Ordered (x, y) positions defining the helix axis.
        amplitude: Peak perpendicular offset in pixels.
        period: Helix repeat distance in pixels. Must be > 0.
        phase: Initial sine phase in radians. 0 for strand A, π for strand B.

    Returns:
        List of (x, y) positions tracing one strand.
    """
    n = len(axis_pts)
    arc = [0.0]
    for i in range(1, n):
        arc.append(arc[-1] + math.hypot(
            axis_pts[i][0] - axis_pts[i - 1][0],
            axis_pts[i][1] - axis_pts[i - 1][1],
        ))

    pts: list[tuple[float, float]] = []
    for i, (ax, ay) in enumerate(axis_pts):
        # Local perpendicular via central differences (stable at endpoints too)
        prev_i = max(0, i - 1)
        next_i = min(n - 1, i + 1)
        tx = axis_pts[next_i][0] - axis_pts[prev_i][0]
        ty = axis_pts[next_i][1] - axis_pts[prev_i][1]
        L = math.hypot(tx, ty)
        if L < 1e-9:
            perp_x, perp_y = 0.0, 1.0
        else:
            perp_x, perp_y = -ty / L, tx / L

        offset = amplitude * math.sin(2 * math.pi * arc[i] / period + phase)
        pts.append((ax + offset * perp_x, ay + offset * perp_y))
    return pts


def _add_strand_polyline(
    group: svgwrite.container.Group,
    pts: list[tuple[float, float]],
    stroke: str,
    stroke_width: float,
) -> None:
    """Append a strand segment as a polyline to group. No-op if fewer than 2 points."""
    if len(pts) < 2:
        return
    group.add(svgwrite.shapes.Polyline(
        points=[(round(x, 2), round(y, 2)) for x, y in pts],
        fill="none",
        stroke=stroke,
        stroke_width=stroke_width,
    ))


def _complement(base: str) -> str:
    """Return the Watson-Crick complement of a base (A↔T, G↔C, U↔A).

    Unknown bases return '?' without raising an exception.
    """
    return {"A": "T", "T": "A", "G": "C", "C": "G", "U": "A"}.get(base.upper(), "?")


def _rung_color(base: str, style: dict) -> str:
    """Return the SVG fill color for a base pair rung from the active style.

    A-T (and U-A for RNA) rungs → dna_rung_at_fill.
    G-C rungs → dna_rung_gc_fill.
    Unknown bases → dna_rung_stroke (neutral).
    """
    b = base.upper()
    if b in ("A", "T", "U"):
        return str(style["dna_rung_at_fill"])
    if b in ("G", "C"):
        return str(style["dna_rung_gc_fill"])
    return str(style["dna_rung_stroke"])


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def _broken_dna_segment(
    start: tuple[float, float],
    end: tuple[float, float],
    double_helix: bool,
    supercoiled: bool,
    sequence: str | None,
    break_position: float,
    s: dict,
) -> svgwrite.container.Group:
    """Render a DNA double-strand break: two flanking helices with an axis gap.

    The gap is `dna_break_gap` px wide, centred at `break_position` along the
    axis. Each flank is an ordinary (unbroken) helix, so the two cut ends leave
    a visible coordinate gap. A short blunt cap line is drawn perpendicular to
    the axis at each cut end so the break reads as a clean DSB.
    """
    length, tx, ty, px, py = _axis_frame(start, end)
    gap = float(s["dna_break_gap"])
    t = min(0.95, max(0.05, float(break_position)))
    # Break centre on the axis.
    bx = start[0] + t * (end[0] - start[0])
    by = start[1] + t * (end[1] - start[1])
    half = gap / 2.0
    left_end = (bx - tx * half, by - ty * half)
    right_start = (bx + tx * half, by + ty * half)

    group = svgwrite.container.Group()
    # Flanking helices (recurse with broken=False).
    group.add(dna_segment(
        start, left_end, double_helix=double_helix, supercoiled=supercoiled,
        sequence=sequence, broken=False, style_dict=s,
    ))
    group.add(dna_segment(
        right_start, end, double_helix=double_helix, supercoiled=supercoiled,
        sequence=sequence, broken=False, style_dict=s,
    ))

    # Blunt caps across each cut end (perpendicular to the axis).
    if s.get("dna_break_cap_show", True):
        cap_h = float(s["dna_amplitude"]) + 4.0
        cap_stroke = str(s["dna_break_cap_stroke"])
        cap_sw = float(s["dna_break_cap_stroke_width"])
        for ex, ey in (left_end, right_start):
            group.add(svgwrite.shapes.Line(
                start=(round(ex + px * cap_h, 2), round(ey + py * cap_h, 2)),
                end=(round(ex - px * cap_h, 2), round(ey - py * cap_h, 2)),
                stroke=cap_stroke,
                stroke_width=cap_sw,
            ))
    return group


def dna_segment(
    start: tuple[float, float],
    end: tuple[float, float],
    double_helix: bool = True,
    supercoiled: bool = False,
    sequence: str | None = None,
    broken: bool = False,
    break_position: float = 0.5,
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """Render a DNA segment as a sine-wave double (or single) helix.

    Convention: strand 1 is blue, strand 2 is a slightly darker blue. Depth is
    conveyed by alternating z-order at each crossover -- the strand that passes in
    front switches every half-period, matching the familiar double-helix ladder
    diagram used in textbooks and journal figures. Base pair rungs are drawn at the
    amplitude peak of each half-period; with a sequence string, rungs are color-coded
    and labeled (A-T red, G-C blue).

    Args:
        start: (x, y) start of the helix axis in SVG coordinates.
        end: (x, y) end of the helix axis in SVG coordinates.
        double_helix: True (default) renders both strands with crossover z-order and
                      base pair rungs. False renders only strand 1 (ssDNA, no rungs).
        supercoiled: True adds a secondary large-amplitude sinusoidal writhe to the
                     axis, giving a schematic plectonemic supercoil appearance.
        sequence: Optional sense-strand sequence (e.g. "ATGCATGC"). Each character is
                  assigned to one rung in order, cycling if shorter than the rung count.
                  Enables per-rung color coding and "A-T"/"G-C" labels centered on rungs.
        broken: LT7 — when True, the helix is interrupted by a clean axis gap
                (`dna_break_gap` px wide) centred at `break_position`, modelling a
                double-strand break. Both strands stop at the gap and a short blunt
                cap is drawn across each cut end. Implemented by rendering the two
                flanking sub-segments as ordinary (unbroken) helices.
        break_position: Fractional position of the break along the axis, in (0, 1).
                        Only used when `broken=True`. Defaults to the midpoint.
        style_dict: Optional style-key overrides merged onto DEFAULT_STYLE.

    Returns:
        svgwrite.container.Group containing all strand and rung SVG elements.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}

    if broken:
        return _broken_dna_segment(
            start, end, double_helix, supercoiled, sequence, break_position, s,
        )

    amplitude = float(s["dna_amplitude"])
    period = float(s["dna_period"])
    sample_rate = int(s["dna_sample_rate"])

    length, *_ = _axis_frame(start, end)
    n_half = max(2, round(length / (period / 2)))
    n_pts = n_half * sample_rate + 1

    if supercoiled:
        axis_pts = _supercoiled_axis(start, end, n_pts, amp_factor=amplitude * 2.5)
    else:
        x0, y0 = start
        x1, y1 = end
        axis_pts = [
            (x0 + (i / (n_pts - 1)) * (x1 - x0),
             y0 + (i / (n_pts - 1)) * (y1 - y0))
            for i in range(n_pts)
        ]

    strand_a = _sample_strand_on_path(axis_pts, amplitude, period, phase=0.0)
    group = svgwrite.container.Group()

    if not double_helix:
        _add_strand_polyline(
            group, strand_a,
            str(s["dna_strand1_stroke"]),
            float(s["dna_strand_stroke_width"]),
        )
        return group

    strand_b = _sample_strand_on_path(axis_pts, amplitude, period, phase=math.pi)
    stroke1 = str(s["dna_strand1_stroke"])
    stroke2 = str(s["dna_strand2_stroke"])
    sw = float(s["dna_strand_stroke_width"])

    # Alternating z-order: even segments have strand 1 on top, odd have strand 2 on top.
    # Drawing the "behind" strand first, then the "front" strand, within each segment.
    for seg in range(n_half):
        i0 = seg * sample_rate
        i1 = min((seg + 1) * sample_rate + 1, n_pts)
        seg_a = strand_a[i0:i1]
        seg_b = strand_b[i0:i1]

        if seg % 2 == 0:
            _add_strand_polyline(group, seg_b, stroke2, sw)
            _add_strand_polyline(group, seg_a, stroke1, sw)
        else:
            _add_strand_polyline(group, seg_a, stroke1, sw)
            _add_strand_polyline(group, seg_b, stroke2, sw)

    # Base pair rungs at the amplitude-peak index of each half-period segment
    seq_str = sequence or ""
    for k in range(n_half):
        mid_idx = k * sample_rate + sample_rate // 2
        if mid_idx >= n_pts:
            break

        pa = strand_a[mid_idx]
        pb = strand_b[mid_idx]

        if seq_str:
            base = seq_str[k % len(seq_str)].upper()
            comp = _complement(base)
            color = _rung_color(base, s)
        else:
            base = comp = None
            color = str(s["dna_rung_stroke"])

        group.add(svgwrite.shapes.Line(
            start=(round(pa[0], 2), round(pa[1], 2)),
            end=(round(pb[0], 2), round(pb[1], 2)),
            stroke=color,
            stroke_width=float(s["dna_rung_stroke_width"]),
        ))

        if seq_str and s.get("dna_base_label_show", True):
            mx = (pa[0] + pb[0]) / 2
            my = (pa[1] + pb[1]) / 2
            lbl = svgwrite.text.Text(
                f"{base}-{comp}",
                insert=(round(mx, 2), round(my, 2)),
                font_family=str(s["label_font_family"]),
                font_size=float(s["dna_base_label_font_size"]),
                fill=color,
            )
            lbl["text-anchor"] = "middle"
            lbl["dominant-baseline"] = "central"
            group.add(lbl)

    return group


def rna_segment(
    start: tuple[float, float],
    end: tuple[float, float],
    single_strand: bool = True,
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """Render an RNA segment as an orange sine wave.

    Convention: RNA is drawn in orange (vs DNA blue) following the most common
    cell-biology pathway figure standard. Single-stranded (default) renders one
    wavy line. Double-stranded uses the same alternating crossover z-order as
    dna_segment, but with a single RNA color for both strands.

    Args:
        start: (x, y) start of the RNA segment axis.
        end: (x, y) end of the RNA segment axis.
        single_strand: True (default) renders one sine wave. False renders dsRNA
                       with alternating crossover z-order.
        style_dict: Optional style-key overrides merged onto DEFAULT_STYLE.

    Returns:
        svgwrite.container.Group containing all RNA strand elements.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    amplitude = float(s["rna_amplitude"])
    period = float(s["rna_period"])
    sample_rate = int(s["rna_sample_rate"])
    stroke = str(s["rna_stroke"])
    sw = float(s["rna_stroke_width"])

    length, *_ = _axis_frame(start, end)
    n_half = max(2, round(length / (period / 2)))
    n_pts = n_half * sample_rate + 1

    x0, y0 = start
    x1, y1 = end
    axis_pts = [
        (x0 + (i / (n_pts - 1)) * (x1 - x0),
         y0 + (i / (n_pts - 1)) * (y1 - y0))
        for i in range(n_pts)
    ]

    strand_a = _sample_strand_on_path(axis_pts, amplitude, period, phase=0.0)
    group = svgwrite.container.Group()

    if single_strand:
        _add_strand_polyline(group, strand_a, stroke, sw)
        return group

    # dsRNA: same crossover z-order logic as dna_segment
    strand_b = _sample_strand_on_path(axis_pts, amplitude, period, phase=math.pi)
    for seg in range(n_half):
        i0 = seg * sample_rate
        i1 = min((seg + 1) * sample_rate + 1, n_pts)
        seg_a = strand_a[i0:i1]
        seg_b = strand_b[i0:i1]
        if seg % 2 == 0:
            _add_strand_polyline(group, seg_b, stroke, sw)
            _add_strand_polyline(group, seg_a, stroke, sw)
        else:
            _add_strand_polyline(group, seg_a, stroke, sw)
            _add_strand_polyline(group, seg_b, stroke, sw)

    return group


def gene_helix(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (80.0, 40.0),
    color: str | None = None,  # accepted for API parity with generic_protein; unused
    broken: bool = False,
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """Render a GENE entity as a horizontal DNA double helix with a label below.

    Follows the same (label, position, size, color, style_dict) calling
    convention as proteins.generic_protein so ENTITY_TO_PRIMITIVE dispatch
    works transparently. The helix axis runs across the bounding box,
    shifted upward so the label fits below without clipping. Amplitude
    scales with bbox height so the helix stays within the entity's collision
    footprint at all sizes.

    LT7: pass `broken=True` (or set `style_dict["dna_break"] = True`) to draw a
    double-strand break — a clear gap interrupting both strands. The break
    position can be set via `style_dict["dna_break_position"]` (default 0.5).
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    cx, cy = position
    w, h = size

    margin_x = max(4.0, w * 0.05)
    amplitude = min(h * 0.30, float(s["dna_amplitude"]))
    helix_cy = cy - h * 0.18        # shift helix up to leave room for label below

    broken = bool(broken or s.get("dna_break", False))
    break_position = float(s.get("dna_break_position", 0.5))

    helix_grp = dna_segment(
        (cx - w / 2 + margin_x, helix_cy),
        (cx + w / 2 - margin_x, helix_cy),
        double_helix=True,
        broken=broken,
        break_position=break_position,
        style_dict={**s, "dna_amplitude": amplitude},
    )

    group = svgwrite.container.Group()
    group.add(helix_grp)

    lbl = svgwrite.text.Text(
        label,
        insert=(round(cx, 2), round(cy + h * 0.35, 2)),
        font_family=str(s["label_font_family"]),
        font_size=float(s["label_font_size"]),
        fill=str(s["label_font_color"]),
    )
    lbl["text-anchor"] = "middle"
    lbl["dominant-baseline"] = "central"
    group.add(lbl)
    return group


def rna_helix(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (80.0, 40.0),
    color: str | None = None,  # accepted for API parity with generic_protein; unused
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """Render an RNA entity as a horizontal orange single-strand wave + label.

    LT8: mirrors `gene_helix` but calls `rna_segment` so RNA species (mRNA,
    sgRNA, miRNA) render as a single orange strand, visually distinct from the
    blue DNA double helix. Same (label, position, size, color, style_dict)
    calling convention as the other entity primitives for transparent
    ENTITY_TO_PRIMITIVE dispatch.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    cx, cy = position
    w, h = size

    margin_x = max(4.0, w * 0.05)
    amplitude = min(h * 0.30, float(s["rna_amplitude"]))
    strand_cy = cy - h * 0.18        # shift strand up to leave room for label below

    strand_grp = rna_segment(
        (cx - w / 2 + margin_x, strand_cy),
        (cx + w / 2 - margin_x, strand_cy),
        single_strand=True,
        style_dict={**s, "rna_amplitude": amplitude},
    )

    group = svgwrite.container.Group()
    group.add(strand_grp)

    lbl = svgwrite.text.Text(
        label,
        insert=(round(cx, 2), round(cy + h * 0.35, 2)),
        font_family=str(s["label_font_family"]),
        font_size=float(s["label_font_size"]),
        fill=str(s["label_font_color"]),
    )
    lbl["text-anchor"] = "middle"
    lbl["dominant-baseline"] = "central"
    group.add(lbl)
    return group


def mrna_helix(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (90.0, 40.0),
    color: str | None = None,  # accepted for API parity; unused
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """Render an mRNA entity as an orange single strand with a 5' cap and a
    poly(A) tail — the features that distinguish a mature mRNA from a bare RNA.

    Mirrors `rna_helix` (orange `rna_segment`, label below) and adds a filled
    cap disc at the 5' (left) terminus and an "AAA" poly(A) tail at the 3'
    (right) terminus. The strand polyline is added first so `convention_check`
    keys the RNA shape correctly.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    cx, cy = position
    w, h = size

    margin_x = max(4.0, w * 0.05)
    amplitude = min(h * 0.30, float(s["rna_amplitude"]))
    strand_cy = cy - h * 0.18
    cap_r = max(3.0, h * 0.10)
    left = cx - w / 2 + margin_x + cap_r * 1.8
    right = cx + w / 2 - margin_x - h * 0.30

    strand_grp = rna_segment(
        (left, strand_cy), (right, strand_cy),
        single_strand=True,
        style_dict={**s, "rna_amplitude": amplitude},
    )
    group = svgwrite.container.Group()
    group.add(strand_grp)

    cap = svgwrite.shapes.Circle(
        center=(cx - w / 2 + margin_x + cap_r, strand_cy), r=cap_r,
        fill=str(s["rna_stroke"]), stroke=str(s["rna_stroke"]),
    )
    group.add(cap)

    tail = svgwrite.text.Text(
        "AAA",
        insert=(round(right + 3, 2), round(strand_cy, 2)),
        font_family=str(s["label_font_family"]),
        font_size=float(s["label_font_size"]) * 0.8,
        fill=str(s["rna_stroke"]),
    )
    tail["text-anchor"] = "start"
    tail["dominant-baseline"] = "central"
    tail["font-weight"] = "bold"
    group.add(tail)

    lbl = svgwrite.text.Text(
        label,
        insert=(round(cx, 2), round(cy + h * 0.35, 2)),
        font_family=str(s["label_font_family"]),
        font_size=float(s["label_font_size"]),
        fill=str(s["label_font_color"]),
    )
    lbl["text-anchor"] = "middle"
    lbl["dominant-baseline"] = "central"
    group.add(lbl)
    return group


def primer_helix(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (60.0, 36.0),
    color: str | None = None,  # accepted for API parity; unused
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """Render an oligonucleotide primer as a short single DNA strand with a 3'
    arrowhead marking the direction of polymerase extension.

    Single-strand DNA (`dna_segment(double_helix=False)`, blue) so it reads as
    DNA, kept short, with a filled arrowhead at the 3' (right) end. The strand
    polyline is added first for `convention_check`.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    cx, cy = position
    w, h = size

    margin_x = max(4.0, w * 0.05)
    amplitude = min(h * 0.26, float(s["dna_amplitude"]))
    strand_cy = cy - h * 0.16
    left = cx - w / 2 + margin_x
    arrow = h * 0.18
    right = cx + w / 2 - margin_x - arrow * 1.6

    strand_grp = dna_segment(
        (left, strand_cy), (right, strand_cy),
        double_helix=False,
        style_dict={**s, "dna_amplitude": amplitude},
    )
    group = svgwrite.container.Group()
    group.add(strand_grp)

    head = svgwrite.shapes.Polygon(
        points=[
            (right, strand_cy - arrow),
            (right + arrow * 1.6, strand_cy),
            (right, strand_cy + arrow),
        ],
        fill=str(s["dna_strand1_stroke"]),
        stroke=str(s["dna_strand1_stroke"]),
    )
    group.add(head)

    lbl = svgwrite.text.Text(
        label,
        insert=(round(cx, 2), round(cy + h * 0.35, 2)),
        font_family=str(s["label_font_family"]),
        font_size=float(s["label_font_size"]),
        fill=str(s["label_font_color"]),
    )
    lbl["text-anchor"] = "middle"
    lbl["dominant-baseline"] = "central"
    group.add(lbl)
    return group


def chromatin(
    region: tuple[tuple[float, float], tuple[float, float]],
    condensation_level: float = 0.0,
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """Render a chromatin segment from beads-on-string to condensed fiber.

    Convention:
      condensation_level=0 → extended chromatin: thin backbone with purple nucleosome
      circles at regular intervals, the textbook beads-on-string representation.
      condensation_level=1 → condensed chromatin fiber: filled rectangle spanning the axis.
      Intermediate values interpolate: nucleosome radius shrinks linearly and fiber opacity
      rises linearly, giving a smooth visual transition between the two states.

    Args:
        region: ((x0, y0), (x1, y1)) defining the backbone axis start and end.
        condensation_level: Float in [0, 1]. 0 = extended, 1 = condensed. Clamped.
        style_dict: Optional style-key overrides merged onto DEFAULT_STYLE.

    Returns:
        svgwrite.container.Group containing backbone, fiber polygon, and bead elements.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    level = max(0.0, min(1.0, float(condensation_level)))

    (x0, y0), (x1, y1) = region
    dx, dy = x1 - x0, y1 - y0
    length = math.hypot(dx, dy)
    _, _, _, px, py = _axis_frame((x0, y0), (x1, y1))

    group = svgwrite.container.Group()

    # Condensed fiber (drawn first so beads render above it)
    if level > 0.0:
        half_w = float(s["chromatin_fiber_width"]) / 2
        fiber_pts = [
            (x0 + half_w * px, y0 + half_w * py),
            (x1 + half_w * px, y1 + half_w * py),
            (x1 - half_w * px, y1 - half_w * py),
            (x0 - half_w * px, y0 - half_w * py),
        ]
        group.add(svgwrite.shapes.Polygon(
            points=_polyline_to_svg_points(fiber_pts),
            fill=str(s["chromatin_fiber_fill"]),
            stroke=str(s["chromatin_fiber_stroke"]),
            stroke_width=float(s["chromatin_fiber_stroke_width"]),
            opacity=round(level, 3),
        ))

    # Backbone line (always visible; may be covered by fully-opaque fiber at level=1)
    group.add(svgwrite.shapes.Line(
        start=(round(x0, 2), round(y0, 2)),
        end=(round(x1, 2), round(y1, 2)),
        stroke=str(s["chromatin_backbone_stroke"]),
        stroke_width=float(s["chromatin_backbone_stroke_width"]),
    ))

    # Nucleosome beads (radius shrinks to zero as condensation increases)
    bead_r = float(s["chromatin_nucleosome_radius"]) * (1.0 - level)
    if bead_r > 0.5 and length > 0:
        spacing = float(s["chromatin_nucleosome_spacing"])
        n_beads = max(1, int(length / spacing))
        for k in range(n_beads):
            t = (k + 0.5) / n_beads
            group.add(svgwrite.shapes.Circle(
                center=(round(x0 + t * dx, 2), round(y0 + t * dy, 2)),
                r=round(bead_r, 2),
                fill=str(s["chromatin_nucleosome_fill"]),
                stroke=str(s["chromatin_nucleosome_stroke"]),
                stroke_width=float(s["chromatin_nucleosome_stroke_width"]),
            ))

    return group
