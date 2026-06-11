"""RNA / primer / chromatin primitives.

Internals of :mod:`imageGen.primitives.nucleic_acids` (R4 split). Holds the RNA
strand glyphs (`rna_segment`, `rna_helix`, `mrna_helix`), the DNA primer glyph
(`primer_helix` — a short ssDNA with a 3' arrowhead) and the `chromatin`
beads-on-string/fiber primitive. Shared helix geometry (`_axis_frame`,
`_sample_strand_on_path`, `_add_strand_polyline`), the shared `DEFAULT_STYLE`
table, and `dna_segment` (used by `primer_helix`) are imported from the sibling
``_dna`` module.

Visual conventions:
- RNA: a single sine wave in orange (convention: RNA is orange, DNA is blue in
  most cell-biology pathway figures). double-stranded RNA uses the same crossover
  z-order logic as DNA.
- Chromatin: beads-on-string at condensation_level=0 (nucleosome circles on a thin
  backbone), condensed fiber at condensation_level=1. Intermediate values interpolate:
  nucleosome radius shrinks and fiber opacity rises linearly.
"""
from __future__ import annotations

import math

import svgwrite
import svgwrite.container
import svgwrite.shapes
import svgwrite.text

from imageGen.primitives._svg import polyline_to_svg_points as _polyline_to_svg_points
from imageGen.primitives._dna import (
    DEFAULT_STYLE,
    _add_strand_polyline,
    _axis_frame,
    _sample_strand_on_path,
    dna_segment,
)


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
