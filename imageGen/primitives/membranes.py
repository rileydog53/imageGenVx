"""Membrane primitives for scientific figure generation.

Visual conventions followed here:
- Lipid bilayer: two parallel boundary strokes with small filled circles (phospholipid
  head groups) at regular intervals on both leaflets. Head groups face outward (away from
  the hydrophobic tail region), as in textbook membrane diagrams.
- Cell membrane outline: a closed curve — either a perfect circle or a low-frequency
  perturbed circle that reads as "organic" without looking sloppy.
- Nuclear envelope: two concentric rings (inner + outer nuclear membrane) separated by
  a fixed gap, with evenly spaced pore-complex accents.

Anchor protocol (Phase 3 coupling):
  receptor() and gpcr() in proteins.py accept (position, orientation) directly.
  The MembraneCurve class exposes .anchor_at(t) -> (position, tangent_angle_radians)
  so layout code can place membrane proteins along any membrane without importing
  this module. Future membrane types (ER, Golgi, thylakoid) return the same
  MembraneCurve type -- proteins never need to know what surface they sit on.

Phase 4 assumption:
  DEFAULT_STYLE uses flat namespaced keys (bilayer_*, membrane_*, nuclear_*, label_*)
  so the Phase 4 master preset JSON can union all primitive modules without collision.

Future extensibility:
  - Add new head_style options (e.g., 'lollipop', 'wedge') in _place_heads() only.
  - Add organelle membranes (ER, Golgi) by calling _sample_irregular() with different
    parameters and returning a MembraneCurve -- no changes to the anchor protocol.
  - Pore count, gap, and head spacing are all style-key-driven; Phase 4 presets can
    dial them per journal style without touching this module.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import svgwrite
import svgwrite.container
import svgwrite.shapes

from imageGen.primitives._svg import polyline_to_svg_points as _polyline_to_svg_points

# ---------------------------------------------------------------------------
# Style defaults -- flat namespaced keys for Phase 4 preset union
# ---------------------------------------------------------------------------

DEFAULT_STYLE: dict[str, object] = {
    # lipid bilayer
    "bilayer_outer_stroke":       "#2C3E50",
    "bilayer_outer_stroke_width":  1.5,
    "bilayer_inner_stroke":       "#2C3E50",
    "bilayer_inner_stroke_width":  1.5,
    "bilayer_head_fill":          "#5B8DB8",   # conventional phospholipid blue
    "bilayer_head_radius":         4.0,
    "bilayer_tail_fill":          "#D6E8C8",   # pale green tail region
    "bilayer_tail_stroke":        "none",
    "bilayer_head_spacing":        14.0,        # px between head-center positions
    "bilayer_thickness":           20.0,        # total bilayer depth in pixels

    # cell membrane outline (shape only, no head groups)
    "membrane_stroke":            "#2C3E50",
    "membrane_stroke_width":       2.5,
    "membrane_fill":              "none",
    "membrane_sample_points":     128,          # resolution of the curve polyline

    # nuclear envelope
    "nuclear_outer_stroke":       "#2C3E50",
    "nuclear_outer_stroke_width":  2.0,
    "nuclear_inner_stroke":       "#2C3E50",
    "nuclear_inner_stroke_width":  1.5,
    "nuclear_gap":                 7.0,         # px between inner/outer ring
    "nuclear_pore_fill":          "#7FB3D3",    # pore complex accent
    "nuclear_pore_radius":         3.5,
    "nuclear_pore_count":          8,           # evenly spaced around the envelope

    # shared label
    "label_font_family":          "Helvetica, Arial, sans-serif",
    "label_font_size":             11,
    "label_font_color":           "#1A1A1A",
}


# ---------------------------------------------------------------------------
# MembraneCurve -- the anchor protocol
# ---------------------------------------------------------------------------

@dataclass
class MembraneCurve:
    """Parametric membrane curve providing the anchor protocol for membrane proteins.

    proteins.py functions (receptor, gpcr) accept (position, orientation) directly.
    Layout code calls .anchor_at(t) to obtain those values from any MembraneCurve,
    keeping proteins.py and membranes.py fully decoupled.

    Any future membrane surface (ER, Golgi, thylakoid) that exposes the same
    .anchor_at() signature is immediately compatible with all protein primitives.

    Args:
        points: List of (x, y) tuples sampled along the curve in order.
        closed: True when the curve is a closed loop (cell/nuclear membranes).
    """
    points: list[tuple[float, float]]
    closed: bool = True

    def anchor_at(self, t: float) -> tuple[tuple[float, float], float]:
        """Return (position, tangent_angle_radians) at parameter t in [0, 1].

        Linearly interpolates between sampled points and computes the local
        tangent direction from adjacent points -- sufficient for placing receptors
        and GPCRs. The tangent_angle matches the `orientation` parameter of
        receptor() and gpcr() in proteins.py.

        Args:
            t: Curve parameter in [0, 1]. 0 and 1 map to the same point on a
               closed curve. Values outside [0, 1] are clamped.

        Returns:
            ((x, y), angle_radians): position on the curve and local tangent angle.
        """
        t = max(0.0, min(1.0, t))
        pts = self.points
        n = len(pts)

        # Map t to a float index into pts
        idx_f = t * (n if self.closed else n - 1)
        i0 = int(idx_f) % n
        i1 = (i0 + 1) % n

        frac = idx_f - int(idx_f)
        x0, y0 = pts[i0]
        x1, y1 = pts[i1]

        # Interpolated position
        pos = (x0 + frac * (x1 - x0), y0 + frac * (y1 - y0))

        # Tangent from the adjacent pair (SVG y-axis points down)
        dx = x1 - x0
        dy = y1 - y0
        angle = math.atan2(dy, dx)

        return pos, angle


# ---------------------------------------------------------------------------
# Private geometry helpers -- extend here, not in public functions
# ---------------------------------------------------------------------------

def _sample_circle(
    cx: float, cy: float, r: float, n: int
) -> list[tuple[float, float]]:
    """Return n equally-spaced (x, y) points on a circle, starting at angle 0.

    Used by cell_membrane_outline (shape='circle') and nuclear_envelope.
    The list is not closed (pts[0] != pts[-1]); MembraneCurve wraps them as a loop.
    """
    return [
        (cx + r * math.cos(2 * math.pi * k / n),
         cy + r * math.sin(2 * math.pi * k / n))
        for k in range(n)
    ]


def _sample_irregular(
    cx: float, cy: float, r: float, n: int, seed: int = 7
) -> list[tuple[float, float]]:
    """Return n points on a radius-perturbed circle that reads as organic.

    Uses a sum of low-frequency sine waves to perturb the radius, keeping the
    shape recognisably round while avoiding perfect-circle rigidity. The seed
    controls the frequency/phase combination, making the shape deterministic
    (same seed -> same shape, required for reproducible layout in Phase 3).

    Args:
        cx, cy: Centre of the irregular outline.
        r: Nominal radius; perturbations stay within ~8% of r.
        n: Number of sample points (more = smoother curve).
        seed: Frequency/phase selector for the harmonic perturbations.

    Returns:
        List of (x, y) tuples forming the closed outline.
    """
    # Low-frequency harmonics produce smooth, cell-like deformations
    harmonics = [
        (2, 0.04 * (seed % 3 + 1)),  # ellipse-like deformation
        (3, 0.03 * (seed % 5 + 1)),  # triangular bulge
        (5, 0.015),                  # subtle high-frequency irregularity
    ]
    pts = []
    for k in range(n):
        theta = 2 * math.pi * k / n
        dr = sum(a * math.sin(f * theta + seed) for f, a in harmonics)
        rk = r * (1.0 + dr)
        pts.append((cx + rk * math.cos(theta), cy + rk * math.sin(theta)))
    return pts


def _parallel_offset(
    points: list[tuple[float, float]], d: float, closed: bool
) -> list[tuple[float, float]]:
    """Offset each point by distance d along its local inward normal.

    For closed curves, positive d offsets inward (toward centre).
    For open curves, positive d offsets to the left of the direction of travel.
    Used by lipid_bilayer to compute inner and outer bilayer boundaries from
    a single source curve.

    Args:
        points: Ordered (x, y) points on the source curve.
        d: Signed offset distance in pixels.
        closed: True when the curve forms a closed loop.

    Returns:
        Offset list of (x, y) points, same length as input.
    """
    n = len(points)
    result = []
    for i, (x, y) in enumerate(points):
        # Average normals from the two flanking segments for a smooth offset
        prev_i = (i - 1) % n if closed else max(0, i - 1)
        next_i = (i + 1) % n if closed else min(n - 1, i + 1)

        px, py = points[prev_i]
        nx, ny = points[next_i]

        # Tangent direction spanning prev->next
        tx = nx - px
        ty = ny - py
        length = math.hypot(tx, ty)
        if length < 1e-9:
            result.append((x, y))
            continue

        # Inward normal: rotate tangent 90 deg clockwise (SVG y-down, so CW = left)
        inx = -ty / length
        iny =  tx / length

        result.append((x + d * inx, y + d * iny))
    return result


def _place_heads(
    points: list[tuple[float, float]],
    spacing: float,
    radius: float,
    fill: str,
    group: svgwrite.container.Group,
) -> None:
    """Add circular phospholipid head groups to `group` along a polyline.

    Walks the polyline, placing a filled circle every `spacing` pixels of
    arc length. This is the 'circles' head_style implementation.
    Future styles (lollipop, wedge) add new branches here -- lipid_bilayer()
    never needs to change when a new style is added.

    Args:
        points: Ordered (x, y) positions forming one bilayer leaflet boundary.
        spacing: Arc-length distance between head group centres in pixels.
        radius: Radius of each head-group circle.
        fill: SVG fill colour for head groups.
        group: svgwrite Group to append circle elements into.
    """
    accumulated = 0.0
    for i in range(len(points)):
        x0, y0 = points[i]
        x1, y1 = points[(i + 1) % len(points)]
        seg_len = math.hypot(x1 - x0, y1 - y0)

        while accumulated + seg_len >= spacing:
            # t along this segment where the next head centre falls
            t = (spacing - accumulated) / seg_len
            hx = x0 + t * (x1 - x0)
            hy = y0 + t * (y1 - y0)
            group.add(svgwrite.shapes.Circle(
                center=(round(hx, 2), round(hy, 2)),
                r=radius,
                fill=fill,
            ))
            # Advance the local origin to the placed head, update remaining length
            x0, y0 = hx, hy
            seg_len *= (1.0 - t)
            accumulated = 0.0

        accumulated += seg_len



# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def cell_membrane_outline(
    shape: str = "circle",
    size: tuple[float, float] = (200.0, 200.0),
    style_dict: dict | None = None,
) -> tuple[svgwrite.container.Group, MembraneCurve]:
    """Closed membrane outline representing a cell or vesicle boundary.

    Returns a renderable svgwrite Group and a MembraneCurve for protein anchoring.
    Layout code calls curve.anchor_at(t) to place receptors/GPCRs without importing
    this module -- keeping primitives decoupled (Phase 3 wires them together).

    Convention: the outline is the outer boundary only (no head groups); pair with
    lipid_bilayer() to render the full phospholipid bilayer structure.

    Args:
        shape: 'circle' for a geometrically perfect circle, 'irregular' for an
               organic-looking perturbed circle suitable for generic cell outlines.
        size: (width, height) bounding box. Radius is min(w, h) / 2. For 'irregular',
              perturbations stay within ~8% of that radius.
        style_dict: Optional style-key overrides merged onto DEFAULT_STYLE.

    Returns:
        (group, curve): SVG group containing the outline, and a MembraneCurve
        anchored to the outline path.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    w, h = size
    cx, cy = w / 2, h / 2
    r = min(w, h) / 2
    n = int(s["membrane_sample_points"])

    pts = _sample_circle(cx, cy, r, n) if shape == "circle" else _sample_irregular(cx, cy, r, n)

    group = svgwrite.container.Group()

    # Render as a Polygon so the visual boundary is derived from the same point list
    # as the MembraneCurve -- anchor positions and visible outline are always in sync.
    group.add(svgwrite.shapes.Polygon(
        points=_polyline_to_svg_points(pts),
        fill=str(s["membrane_fill"]),
        stroke=str(s["membrane_stroke"]),
        stroke_width=float(s["membrane_stroke_width"]),
    ))

    return group, MembraneCurve(points=pts, closed=True)


def lipid_bilayer(
    curve: MembraneCurve,
    thickness: float | None = None,
    head_style: str = "circles",
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """Render a phospholipid bilayer along a MembraneCurve.

    Produces: a filled tail region (hydrophobic core) flanked by two rows of head
    group circles -- one per leaflet, at regular arc-length intervals. Convention:
    outer leaflet heads face away from cell interior; inner leaflet heads face
    the cytoplasm -- matching every cell-biology textbook diagram.

    The `curve` is typically returned by cell_membrane_outline() or
    nuclear_envelope(), but any MembraneCurve works -- compatible with future
    membrane types (ER, Golgi, thylakoid) by design.

    Args:
        curve: MembraneCurve defining the membrane midline path.
        thickness: Total bilayer depth in pixels. Overrides 'bilayer_thickness'
                   in style if provided.
        head_style: 'circles' (default) -- filled circles for phospholipid heads.
                    Extend _place_heads() to add 'lollipop', 'wedge', etc.
        style_dict: Optional style-key overrides merged onto DEFAULT_STYLE.

    Returns:
        svgwrite.container.Group containing all bilayer SVG elements.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    half = (thickness if thickness is not None else float(s["bilayer_thickness"])) / 2.0

    # Positive offset = inward; negative = outward (see _parallel_offset docstring)
    outer_pts = _parallel_offset(curve.points, -half, curve.closed)
    inner_pts = _parallel_offset(curve.points,  half, curve.closed)

    group = svgwrite.container.Group()

    # Tail region: filled polygon spanning outer -> inner (reverse) boundaries.
    # For a closed curve, repeat each ring's first point so both leaflet arcs
    # close fully; the two radial bridges then coincide at the seam (a zero-area
    # spoke), filling a clean annulus instead of leaving a one-segment wedge gap.
    if curve.closed:
        outer_loop = outer_pts + [outer_pts[0]]
        inner_loop = inner_pts + [inner_pts[0]]
    else:
        outer_loop, inner_loop = outer_pts, inner_pts
    tail_pts = _polyline_to_svg_points(outer_loop + list(reversed(inner_loop)))
    group.add(svgwrite.shapes.Polygon(
        points=tail_pts,
        fill=str(s["bilayer_tail_fill"]),
        stroke=str(s["bilayer_tail_stroke"]),
    ))

    # Outer leaflet boundary stroke
    group.add(svgwrite.shapes.Polygon(
        points=_polyline_to_svg_points(outer_pts),
        fill="none",
        stroke=str(s["bilayer_outer_stroke"]),
        stroke_width=float(s["bilayer_outer_stroke_width"]),
    ))

    # Inner leaflet boundary stroke
    group.add(svgwrite.shapes.Polygon(
        points=_polyline_to_svg_points(inner_pts),
        fill="none",
        stroke=str(s["bilayer_inner_stroke"]),
        stroke_width=float(s["bilayer_inner_stroke_width"]),
    ))

    # Head groups on both leaflets
    if head_style == "circles":
        head_r = float(s["bilayer_head_radius"])
        head_fill = str(s["bilayer_head_fill"])
        head_spacing = float(s["bilayer_head_spacing"])
        _place_heads(outer_pts, head_spacing, head_r, head_fill, group)
        _place_heads(inner_pts, head_spacing, head_r, head_fill, group)

    return group


def nuclear_envelope(
    center: tuple[float, float] = (100.0, 100.0),
    radius: float = 80.0,
    style_dict: dict | None = None,
) -> tuple[svgwrite.container.Group, MembraneCurve]:
    """Double nuclear membrane with evenly spaced nuclear pore complex accents.

    Renders two concentric rings (outer + inner nuclear membrane) separated by
    `nuclear_gap` pixels, with small filled circles at `nuclear_pore_count`
    evenly spaced positions indicating nuclear pore complexes (simplified icon).

    Convention: pore complexes are shown as filled discs at the midpoint between
    the two rings -- a simplified but immediately recognizable representation.
    The returned MembraneCurve is anchored to that same midpoint so membrane
    proteins inserted here appear correctly positioned.

    Args:
        center: (cx, cy) centre of the nucleus in SVG coordinate frame.
        radius: Outer ring radius in pixels.
        style_dict: Optional style-key overrides merged onto DEFAULT_STYLE.

    Returns:
        (group, curve): SVG group and a MembraneCurve at the envelope midline.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    cx, cy = center
    gap = float(s["nuclear_gap"])
    inner_r = radius - gap
    pore_r = float(s["nuclear_pore_radius"])
    pore_n = int(s["nuclear_pore_count"])
    n_sample = int(s["membrane_sample_points"])

    group = svgwrite.container.Group()

    # Outer nuclear membrane
    group.add(svgwrite.shapes.Circle(
        center=(cx, cy),
        r=radius,
        fill="none",
        stroke=str(s["nuclear_outer_stroke"]),
        stroke_width=float(s["nuclear_outer_stroke_width"]),
    ))

    # Inner nuclear membrane
    group.add(svgwrite.shapes.Circle(
        center=(cx, cy),
        r=inner_r,
        fill="none",
        stroke=str(s["nuclear_inner_stroke"]),
        stroke_width=float(s["nuclear_inner_stroke_width"]),
    ))

    # Pore complexes at even angular intervals at the midpoint between the two rings
    pore_mid_r = (radius + inner_r) / 2.0
    for k in range(pore_n):
        angle = 2 * math.pi * k / pore_n
        group.add(svgwrite.shapes.Circle(
            center=(round(cx + pore_mid_r * math.cos(angle), 2),
                    round(cy + pore_mid_r * math.sin(angle), 2)),
            r=pore_r,
            fill=str(s["nuclear_pore_fill"]),
        ))

    # MembraneCurve anchored to the midline between inner and outer rings
    pts = _sample_circle(cx, cy, pore_mid_r, n_sample)
    return group, MembraneCurve(points=pts, closed=True)
