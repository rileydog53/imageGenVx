"""Cell outline and organelle primitives for scientific figure generation.

Visual conventions followed here:
- cell_outline: closed cell boundary in four biological styles. Returns (Group, MembraneCurve)
  using the same anchor protocol as membranes.py, so receptors and GPCRs can be placed on
  any cell type without knowing which style was used.
- organelle: per-type builders using established schematic conventions:
    mitochondrion — bean-shaped oval with horizontal cristae lines inside
    er            — sinusoidal membrane tube with ribosome dots (rough ER convention)
    golgi         — stack of curved, filled cisternae arcs (cis face top, trans face bottom)
    lysosome      — small filled purple circle (no internal structure at this scale)
    nucleus       — delegates to nuclear_envelope() from membranes.py (double ring + pores)
- compose_cell: assembles a complete cell schematic from outline + organelles +
  pre-positioned membrane protein Groups.

Cross-module imports:
  MembraneCurve and nuclear_envelope are imported from membranes.py. All other geometry is
  local -- membranes.py's private helpers (_sample_circle, _sample_irregular) are not
  accessible; equivalent helpers are reimplemented here as _sample_oval and
  _sample_irregular_oval (generalized to ellipses for neuron/epithelial shapes).

Phase 3 coupling:
  cell_outline returns a MembraneCurve, which layout code uses to place receptors/GPCRs via
  .anchor_at(t) without importing this module or membranes.py. compose_cell accepts pre-
  positioned protein Groups -- callers anchor them using the curve before calling compose_cell,
  keeping the composition step simple.

Phase 4 assumption:
  DEFAULT_STYLE uses flat namespaced keys (cell_*, organelle_*, label_*) so the Phase 4
  master preset JSON can union all primitive modules without collision.

Future extensibility:
  - New cell styles: add a branch in cell_outline() and a new _sample_* geometry helper.
  - New organelle types: add to _ORGANELLE_BUILDERS and a _<type>_group() helper -- no
    changes to the organelle() public API.
  - Organelle membrane anchoring: if future figures need receptors on mitochondria,
    return (Group, MembraneCurve) from _mito_group() and expose via a dedicated accessor.
"""
from __future__ import annotations

import math

import svgwrite
import svgwrite.container
import svgwrite.shapes

from imageGen.primitives._svg import polyline_to_svg_points as _polyline_to_svg_points
from imageGen.primitives.membranes import MembraneCurve, nuclear_envelope

# ---------------------------------------------------------------------------
# Style defaults -- flat namespaced keys for Phase 4 preset union
# ---------------------------------------------------------------------------

DEFAULT_STYLE: dict[str, object] = {
    # Cell outline (shared by all style_name variants)
    "cell_stroke":                       "#2C3E50",
    "cell_stroke_width":                  2.5,
    "cell_fill":                         "none",
    "cell_sample_points":                128,

    # Mitochondrion
    "organelle_mito_fill":               "#E8F5E9",   # light green outer
    "organelle_mito_stroke":             "#388E3C",
    "organelle_mito_stroke_width":        1.5,
    "organelle_mito_crista_stroke":      "#388E3C",
    "organelle_mito_crista_stroke_width": 1.0,
    "organelle_mito_crista_count":        4,

    # Endoplasmic Reticulum
    "organelle_er_stroke":               "#5C6BC0",   # indigo-blue
    "organelle_er_stroke_width":          1.5,
    "organelle_er_fill":                 "none",
    "organelle_er_ribosome_fill":        "#5C6BC0",
    "organelle_er_ribosome_radius":       2.5,
    "organelle_er_ribosome_spacing":     12.0,

    # Golgi
    "organelle_golgi_fill":              "#FFF9C4",   # light yellow cisternae
    "organelle_golgi_stroke":            "#F9A825",
    "organelle_golgi_stroke_width":       1.5,
    "organelle_golgi_cisterna_count":     4,
    "organelle_golgi_cisterna_gap":       5.0,

    # Lysosome
    "organelle_lysosome_fill":           "#CE93D8",   # light purple
    "organelle_lysosome_stroke":         "#7B1FA2",
    "organelle_lysosome_stroke_width":    1.5,

    # Shared label
    "label_font_family":                 "Helvetica, Arial, sans-serif",
    "label_font_size":                    11,
    "label_font_color":                  "#1A1A1A",
}


# ---------------------------------------------------------------------------
# Private geometry helpers
# ---------------------------------------------------------------------------

def _sample_oval(
    cx: float, cy: float, rx: float, ry: float, n: int
) -> list[tuple[float, float]]:
    """Return n evenly-spaced (x, y) points on an ellipse with semi-axes rx, ry.

    Used by cell_outline for 'neuron' (rx > ry) and 'epithelial' (rx < ry) styles.
    Not closed; MembraneCurve wraps the list as a loop.
    """
    return [
        (cx + rx * math.cos(2 * math.pi * k / n),
         cy + ry * math.sin(2 * math.pi * k / n))
        for k in range(n)
    ]


def _sample_irregular_oval(
    cx: float, cy: float, rx: float, ry: float, n: int, seed: int = 7
) -> list[tuple[float, float]]:
    """Return n points on a radius-perturbed ellipse that reads as organic.

    Uses low-frequency harmonic perturbations (same approach as membranes.py's
    _sample_irregular, reimplemented here for ellipses). The seed is deterministic --
    same seed always produces the same shape, required for reproducible layouts.
    """
    harmonics = [
        (2, 0.04 * (seed % 3 + 1)),
        (3, 0.03 * (seed % 5 + 1)),
        (5, 0.015),
    ]
    pts: list[tuple[float, float]] = []
    for k in range(n):
        theta = 2 * math.pi * k / n
        dr = sum(a * math.sin(f * theta + seed) for f, a in harmonics)
        pts.append((
            cx + rx * (1.0 + dr) * math.cos(theta),
            cy + ry * (1.0 + dr) * math.sin(theta),
        ))
    return pts


def _sample_spiky_circle(
    cx: float,
    cy: float,
    r: float,
    n_smooth: int,
    n_spikes: int,
    spike_height: float,
    seed: int = 0,
) -> list[tuple[float, float]]:
    """Return points tracing a circle with evenly-spaced radial spike projections.

    Between each pair of consecutive spikes, n_smooth points lie at radius r.
    Each spike tip projects to r + spike_height. seed offsets the angular start
    position for visual variety while remaining deterministic.
    Used by cell_outline('immune') to represent pseudopods.
    """
    pts: list[tuple[float, float]] = []
    angle_per_spike = 2 * math.pi / n_spikes
    angle_offset = seed * math.pi / 7

    for spike_k in range(n_spikes):
        spike_angle = angle_offset + 2 * math.pi * spike_k / n_spikes
        for j in range(n_smooth):
            t = j / n_smooth
            theta = spike_angle - angle_per_spike / 2 + t * angle_per_spike
            pts.append((cx + r * math.cos(theta), cy + r * math.sin(theta)))
        pts.append((
            cx + (r + spike_height) * math.cos(spike_angle),
            cy + (r + spike_height) * math.sin(spike_angle),
        ))

    return pts



# ---------------------------------------------------------------------------
# Private organelle builders
# ---------------------------------------------------------------------------

def _mito_group(
    center: tuple[float, float],
    size: tuple[float, float],
    style: dict,
) -> svgwrite.container.Group:
    """Build a mitochondrion: bean-shaped oval with horizontal cristae folds.

    Convention: outer oval filled light green; cristae are evenly-spaced horizontal
    lines clipped to 85% of the ellipse x-extent at each y position.
    """
    cx, cy = center
    rx, ry = size[0] / 2, size[1] / 2
    group = svgwrite.container.Group()

    pts = _sample_oval(cx, cy, rx, ry, 64)
    group.add(svgwrite.shapes.Polygon(
        points=_polyline_to_svg_points(pts),
        fill=str(style["organelle_mito_fill"]),
        stroke=str(style["organelle_mito_stroke"]),
        stroke_width=float(style["organelle_mito_stroke_width"]),
    ))

    crista_n = int(style["organelle_mito_crista_count"])
    c_stroke = str(style["organelle_mito_crista_stroke"])
    c_sw = float(style["organelle_mito_crista_stroke_width"])

    for k in range(crista_n):
        dy = ry * 0.7 * (-1 + 2 * (k + 0.5) / crista_n)
        if ry > 0 and abs(dy) < ry:
            x_ext = rx * math.sqrt(max(0.0, 1 - (dy / ry) ** 2))
            group.add(svgwrite.shapes.Line(
                start=(round(cx - x_ext * 0.85, 2), round(cy + dy, 2)),
                end=(round(cx + x_ext * 0.85, 2), round(cy + dy, 2)),
                stroke=c_stroke,
                stroke_width=c_sw,
            ))

    return group


def _er_group(
    center: tuple[float, float],
    size: tuple[float, float],
    style: dict,
) -> svgwrite.container.Group:
    """Build a rough ER segment: sinusoidal membrane with ribosome dots.

    Convention: a horizontal sinusoidal polyline represents the ER membrane; small
    filled circles placed along the outward normal at regular intervals represent
    ribosomes on the cytoplasmic face.
    """
    cx, cy = center
    half_w = size[0] / 2
    amplitude = size[1] / 4
    period = max(size[0] / 3, 1.0)
    n_pts = 64

    pts: list[tuple[float, float]] = []
    for i in range(n_pts):
        d = (i / (n_pts - 1)) * size[0]
        pts.append((cx - half_w + d, cy + amplitude * math.sin(2 * math.pi * d / period)))

    group = svgwrite.container.Group()
    group.add(svgwrite.shapes.Polyline(
        points=_polyline_to_svg_points(pts),
        fill=str(style["organelle_er_fill"]),
        stroke=str(style["organelle_er_stroke"]),
        stroke_width=float(style["organelle_er_stroke_width"]),
    ))

    r_r = float(style["organelle_er_ribosome_radius"])
    r_fill = str(style["organelle_er_ribosome_fill"])
    spacing = float(style["organelle_er_ribosome_spacing"])

    x = cx - half_w + spacing / 2
    while x <= cx + half_w:
        d = x - (cx - half_w)
        wave_y = cy + amplitude * math.sin(2 * math.pi * d / period)
        dy_dx = amplitude * (2 * math.pi / period) * math.cos(2 * math.pi * d / period)
        norm_len = math.hypot(1.0, dy_dx)
        nx, ny = -dy_dx / norm_len, 1.0 / norm_len   # outward normal
        group.add(svgwrite.shapes.Circle(
            center=(round(x + nx * (r_r + 1.5), 2),
                    round(wave_y + ny * (r_r + 1.5), 2)),
            r=r_r,
            fill=r_fill,
        ))
        x += spacing

    return group


def _golgi_group(
    center: tuple[float, float],
    size: tuple[float, float],
    style: dict,
) -> svgwrite.container.Group:
    """Build a Golgi apparatus: stack of curved, filled cisternae arcs.

    Convention: cisterna_count arcs stacked vertically; each is a filled crescent
    polygon spanning ~200° of an ellipse. Radius increases from the cis face (inner,
    smaller) to the trans face (outer, larger), producing the characteristic
    asymmetric Golgi stack shape.
    """
    cx, cy = center
    cisterna_n = int(style["organelle_golgi_cisterna_count"])
    gap = float(style["organelle_golgi_cisterna_gap"])
    fill = str(style["organelle_golgi_fill"])
    stroke = str(style["organelle_golgi_stroke"])
    sw = float(style["organelle_golgi_stroke_width"])

    rx_base = size[0] * 0.38
    ry_base = max(size[1] * 0.08, 4.0)
    total_h = cisterna_n * ry_base * 2 + (cisterna_n - 1) * gap
    top_y = cy - total_h / 2 + ry_base

    start_angle = -math.pi * 100 / 180
    end_angle = math.pi * 100 / 180
    n_arc = 32
    inner_factor = 0.65

    group = svgwrite.container.Group()

    for k in range(cisterna_n):
        cisterna_cy = top_y + k * (ry_base * 2 + gap)
        rx = rx_base * (1.0 + 0.06 * k)
        ry = ry_base

        outer_pts: list[tuple[float, float]] = []
        inner_pts: list[tuple[float, float]] = []
        for j in range(n_arc + 1):
            theta = start_angle + (end_angle - start_angle) * j / n_arc
            outer_pts.append((cx + rx * math.cos(theta),
                               cisterna_cy + ry * math.sin(theta)))
            inner_pts.append((cx + rx * inner_factor * math.cos(theta),
                               cisterna_cy + ry * inner_factor * math.sin(theta)))

        polygon_pts = outer_pts + list(reversed(inner_pts))
        group.add(svgwrite.shapes.Polygon(
            points=_polyline_to_svg_points(polygon_pts),
            fill=fill,
            stroke=stroke,
            stroke_width=sw,
        ))

    return group


def _lysosome_group(
    center: tuple[float, float],
    size: tuple[float, float],
    style: dict,
) -> svgwrite.container.Group:
    """Build a lysosome: small filled purple circle.

    Convention: a simple filled circle with a distinctive purple color to distinguish
    lysosomes from other organelles at a glance. No internal structure at this scale.
    """
    cx, cy = center
    r = min(size[0], size[1]) / 2
    group = svgwrite.container.Group()
    group.add(svgwrite.shapes.Circle(
        center=(round(cx, 2), round(cy, 2)),
        r=round(r, 2),
        fill=str(style["organelle_lysosome_fill"]),
        stroke=str(style["organelle_lysosome_stroke"]),
        stroke_width=float(style["organelle_lysosome_stroke_width"]),
    ))
    return group


def _nucleus_group(
    center: tuple[float, float],
    size: tuple[float, float],
    style: dict,
) -> svgwrite.container.Group:
    """Delegate nucleus rendering to nuclear_envelope() from membranes.py.

    Returns only the Group from the (Group, MembraneCurve) pair; organelle() always
    returns a plain Group. For nuclear MembraneCurve access, call nuclear_envelope()
    directly.
    """
    radius = min(size[0], size[1]) / 2
    grp, _ = nuclear_envelope(center=center, radius=radius, style_dict=style)
    return grp


_ORGANELLE_BUILDERS: dict = {
    "mitochondrion": _mito_group,
    "er":            _er_group,
    "golgi":         _golgi_group,
    "lysosome":      _lysosome_group,
    "nucleus":       _nucleus_group,
}


# ---------------------------------------------------------------------------
# Public functions
# ---------------------------------------------------------------------------

def cell_outline(
    style_name: str = "generic",
    size: tuple[float, float] = (300.0, 300.0),
    style_dict: dict | None = None,
) -> tuple[svgwrite.container.Group, MembraneCurve]:
    """Render a closed cell boundary in one of four biological styles.

    Returns a renderable Group and a MembraneCurve for protein anchoring, using
    the same anchor protocol as membranes.cell_membrane_outline(). Layout code
    calls curve.anchor_at(t) to place proteins on any cell type without knowing
    which style was used.

    Args:
        style_name: 'generic' (organic irregular circle), 'neuron' (elongated oval,
                    2:1 width:height), 'epithelial' (tall narrow oval, ~1:2 ratio),
                    or 'immune' (round with 8 pseudopod spike projections).
        size: (width, height) bounding box in pixels. The outline fits within this box.
        style_dict: Optional style-key overrides merged onto DEFAULT_STYLE.

    Returns:
        (group, curve): SVG group containing the outline, and a MembraneCurve
        anchored to the outline path for membrane-protein placement.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    n = int(s["cell_sample_points"])
    w, h = size
    cx, cy = w / 2, h / 2

    if style_name == "generic":
        r = min(w, h) / 2 * 0.85
        pts = _sample_irregular_oval(cx, cy, r, r, n, seed=7)

    elif style_name == "neuron":
        rx = min(w, h) * 0.45
        ry = min(w, h) * 0.25
        pts = _sample_oval(cx, cy, rx, ry, n)

    elif style_name == "epithelial":
        rx = min(w, h) * 0.22
        ry = min(w, h) * 0.42
        pts = _sample_oval(cx, cy, rx, ry, n)

    elif style_name == "immune":
        r = min(w, h) / 2 * 0.55
        pts = _sample_spiky_circle(cx, cy, r, n_smooth=4, n_spikes=8,
                                   spike_height=min(w, h) * 0.07, seed=3)

    else:
        raise ValueError(
            f"Unknown cell style_name: {style_name!r}. "
            "Choose from: 'generic', 'neuron', 'epithelial', 'immune'."
        )

    group = svgwrite.container.Group()
    group.add(svgwrite.shapes.Polygon(
        points=_polyline_to_svg_points(pts),
        fill=str(s["cell_fill"]),
        stroke=str(s["cell_stroke"]),
        stroke_width=float(s["cell_stroke_width"]),
    ))

    return group, MembraneCurve(points=pts, closed=True)


def organelle(
    type: str,
    position: tuple[float, float],
    size: tuple[float, float],
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """Render a single organelle of the given type at a given position and size.

    Dispatches to a type-specific private builder. 'nucleus' delegates to
    nuclear_envelope() from membranes.py; all other types are self-contained.

    Args:
        type: Organelle type. One of: 'mitochondrion', 'er', 'golgi', 'lysosome',
              'nucleus'. Raises ValueError for unknown types.
        position: (cx, cy) centre of the organelle in SVG coordinates.
        size: (width, height) bounding box for the organelle in pixels.
        style_dict: Optional style-key overrides merged onto DEFAULT_STYLE. Nucleus style
               uses nuclear_* keys from membranes.DEFAULT_STYLE, which pass through
               this dict transparently.

    Returns:
        svgwrite.container.Group containing all organelle SVG elements.
    """
    if type not in _ORGANELLE_BUILDERS:
        known = "', '".join(_ORGANELLE_BUILDERS)
        raise ValueError(f"Unknown organelle type: {type!r}. Choose from: '{known}'.")

    s = {**DEFAULT_STYLE, **(style_dict or {})}
    return _ORGANELLE_BUILDERS[type](position, size, s)


def compose_cell(
    outline_style: str = "generic",
    organelles: list[tuple[str, tuple[float, float], tuple[float, float]]] | None = None,
    membrane_proteins: list[svgwrite.container.Group] | None = None,
    size: tuple[float, float] = (300.0, 300.0),
    style_dict: dict | None = None,
) -> svgwrite.container.Group:
    """Assemble a complete cell schematic from outline, organelles, and proteins.

    Renders the cell boundary, places organelles, and adds pre-positioned membrane
    protein Groups. The caller uses cell_outline()'s MembraneCurve to anchor proteins
    before passing them here -- keeping this function decoupled from protein-placement
    logic (Phase 3 wires those pieces together).

    Args:
        outline_style: Cell style passed to cell_outline(). Default 'generic'.
        organelles: List of (type, position, size) tuples forwarded to organelle().
                    Positions should share the SVG coordinate frame with the outline.
        membrane_proteins: Pre-positioned protein Groups to add on top of the outline.
                           Pass None or [] for no membrane proteins.
        size: (width, height) canvas, forwarded to cell_outline().
        style_dict: Optional style-key overrides forwarded to all sub-calls.

    Returns:
        svgwrite.container.Group containing the complete cell schematic.
    """
    outline_group, _ = cell_outline(outline_style, size, style_dict)

    group = svgwrite.container.Group()
    group.add(outline_group)

    for organ_type, position, organ_size in (organelles or []):
        group.add(organelle(organ_type, position, organ_size, style_dict))

    for protein_group in (membrane_proteins or []):
        group.add(protein_group)

    return group
