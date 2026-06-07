"""
Primitive protein functions for scientific figure generation.

All public functions return ``svgwrite.container.Group`` — never raw SVG strings (Hard Rule #2).
All public functions accept a ``style`` dict; pass ``None`` to fall back to ``DEFAULT_STYLE``.

Visual conventions (composed throughout the figure pipeline):
    * generic_protein → rounded rectangle (the universal "protein" shape)
    * kinase          → hexagon, distinguishing enzymes from inert proteins;
                        optional "P" badge in upper-right when phosphorylated=True
    * receptor        → asymmetric hourglass (wide extracellular ligand-binding pocket,
                        narrow transmembrane neck, modest intracellular tail)
    * gpcr            → seven-helix transmembrane bundle (N-term extracellular, C-term intracellular)
    * transcription_factor → rounded rectangle with optional DNA-binding domain protrusion

Future-proofing notes:
    * Membrane anchoring (Phase 3): receptor and gpcr take ``position + orientation`` directly.
      When ``membranes.py`` (Phase 2 Step 3) is built, ``lipid_bilayer.anchor_at(t)`` will return
      ``(position, tangent_angle_radians)`` — callers feed those values in here. No coupling
      between proteins.py and membranes.py.
    * Layout anchors (Phase 3): callers know ``position`` and ``size``, so they can compute
      attachment points (top/bottom/left/right) for incoming arrows themselves. If a third
      module needs the same logic, lift a ``_anchors(position, size) -> dict`` helper into
      a shared geometry module.
    * Style presets (Phase 4): ``DEFAULT_STYLE`` here uses flat, prefixed keys
      (``protein_*``, ``kinase_*``, ``gpcr_*``, etc.) so the master preset JSON can union
      every primitive module's keys without collision.
"""
from __future__ import annotations

import math
from typing import Optional

import svgwrite
import svgwrite.container
import svgwrite.path
import svgwrite.shapes
import svgwrite.text

from imageGen.primitives._text import (
    centered_label as _centered_label,
    fit_label as _fit_label,
    label_for_fit as _label_for_fit,
)

DEFAULT_STYLE: dict = {
    # Generic protein (rounded rectangle)
    "protein_fill": "#7BB6E0",
    "protein_stroke": "#1F4E79",
    "protein_stroke_width": 1.5,
    "protein_corner_radius": 6,

    # Kinase (hexagon)
    "kinase_fill": "#F5A623",
    "kinase_stroke": "#8B5A00",
    "kinase_badge_fill": "#D32F2F",
    "kinase_badge_text_color": "#FFFFFF",

    # Receptor (asymmetric hourglass)
    "receptor_fill": "#9CC4A0",
    "receptor_stroke": "#3D6B43",

    # GPCR (seven-helix bundle)
    "gpcr_helix_fill": "#C19CD0",
    "gpcr_helix_stroke": "#5B3173",
    "gpcr_loop_stroke": "#5B3173",
    "gpcr_loop_stroke_width": 1.5,

    # Transcription factor (rounded rect + DBD protrusion)
    "tf_fill": "#E8B4B8",
    "tf_stroke": "#8B3A3F",
    "tf_dbd_fill": "#8B3A3F",

    # Labels (shared across all primitive modules — keep these values
    # synchronized with arrows.py, membranes.py, nucleic_acids.py, cells.py,
    # chemistry.py, lab_equipment.py so the Phase 4 master preset union
    # produces a single coherent label style)
    "label_font_family": "Helvetica, Arial, sans-serif",
    "label_font_size": 11,
    "label_font_color": "#1A1A1A",
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _maybe_rotate(
    group: svgwrite.container.Group,
    angle_rad: float,
    center: tuple[float, float],
) -> None:
    """Apply a rotation transform to *group* if angle is nonzero. SVG uses degrees."""
    if angle_rad != 0:
        group.rotate(math.degrees(angle_rad), center=center)


# ---------------------------------------------------------------------------
# Public protein functions
# ---------------------------------------------------------------------------

def generic_protein(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (60, 30),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """
    Generic protein: rounded rectangle with centered label.

    Convention: the universal "protein" shape — used for any entity that's a protein
    but doesn't have a more specific representation (kinase, receptor, transcription
    factor). The label is rendered centered inside the rectangle.

    Args:
        label:    text rendered inside the rectangle
        position: (x, y) center of the rectangle
        size:     (width, height) of the rectangle
        color:    optional fill color override (defaults to ``style["protein_fill"]``)
        style_dict:    presentation attrs dict; falls back to DEFAULT_STYLE for missing keys

    Returns:
        ``svgwrite.container.Group`` containing the rectangle and label.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["protein_fill"]

    rect = svgwrite.shapes.Rect(
        insert=(cx - w / 2, cy - h / 2),
        size=(w, h),
        rx=float(s["protein_corner_radius"]),
        ry=float(s["protein_corner_radius"]),
        fill=fill,
        stroke=s["protein_stroke"],
    )
    rect["stroke-width"] = float(s["protein_stroke_width"])
    g.add(rect)
    # Fit the label to the box (LABEL_FIT): wrap / shrink so it never spills
    # past the border. An external (rung-4) fit renders the box empty — the
    # layout engine places the full label outside on a leader.
    fit = _fit_label(label, w, h, s)
    if not fit.external:
        g.add(_label_for_fit(fit, cx, cy, s))
    return g


def _tint_toward_white(hex_color: str, frac: float) -> str:
    """Blend ``hex_color`` toward white by ``frac`` (0 = unchanged, 1 = white).

    Used to give the back subunit of a complex a lighter shade so the two
    overlapping rects read as one layered assembly (front-over-back depth)
    rather than two equal, separate boxes. Non ``#RRGGBB`` inputs (e.g. named
    colors) are returned unchanged so the back subunit simply matches the front.
    """
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return hex_color
    try:
        r, g_, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return hex_color
    f = max(0.0, min(1.0, frac))
    r = round(r + (255 - r) * f)
    g_ = round(g_ + (255 - g_) * f)
    b = round(b + (255 - b) * f)
    return f"#{r:02X}{g_:02X}{b:02X}"


def protein_complex(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (72, 38),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """
    Multi-subunit complex: two overlapping rounded rectangles + centered label.

    Convention: a bound assembly of subunits. The two diagonally-offset
    rounded rects read as "more than one protein joined together", which
    distinguishes a complex from a single generic protein (one rect). The back
    subunit is drawn in a lighter shade of the fill so the pair reads as one
    layered object with front-over-back depth (rather than two equal, separate
    boxes). The two subunits together exactly span ``size``; the label is
    centered over the union. Reuses the generic-protein fill/stroke so it
    harmonizes with the protein family across presets.

    Args:
        label:    text rendered centered over the assembly
        position: (x, y) center of the bounding box
        size:     (width, height) of the full bounding box (both subunits)
        color:    optional fill override (defaults to ``style["protein_fill"]``)
        style_dict:    presentation attrs dict; falls back to DEFAULT_STYLE

    Returns:
        ``svgwrite.container.Group`` with two rects (back, then front) and the label.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["protein_fill"]
    sw = float(s["protein_stroke_width"])
    r = float(s["protein_corner_radius"])

    # Each subunit is smaller than the box; the diagonal offset makes the two
    # together span the full (w, h) so the bbox matches ENTITY_BBOX[COMPLEX].
    sub_w, sub_h = w * 0.7, h * 0.74
    off_x = (w - sub_w) / 2
    off_y = (h - sub_h) / 2
    # Back subunit (lower-right) is lightened for depth; front (upper-left) keeps
    # the full fill. The shade difference disambiguates "one bound assembly" from
    # "two separate boxes".
    back_fill = _tint_toward_white(fill, 0.45)
    subunits = (
        (off_x, off_y, back_fill),    # back  (lower-right), lightened
        (-off_x, -off_y, fill),       # front (upper-left), full color
    )
    for ox, oy, sub_fill in subunits:
        rect = svgwrite.shapes.Rect(
            insert=(cx + ox - sub_w / 2, cy + oy - sub_h / 2),
            size=(sub_w, sub_h),
            rx=r, ry=r,
            fill=sub_fill,
            stroke=s["protein_stroke"],
        )
        rect["stroke-width"] = sw
        g.add(rect)
    # Label is centered over the union of both subunits; fit it to the full box.
    # A wide label crosses the seam between the front and (lighter) back subunit
    # and that subunit's border, so render it with a white halo for legibility.
    fit = _fit_label(label, w, h, s)
    if not fit.external:
        g.add(_label_for_fit(fit, cx, cy, s, halo=True))
    return g


def kinase(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (70, 32),
    phosphorylated: bool = False,
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """
    Kinase: hexagonal shape with optional phosphorylation 'P' badge.

    Convention: the hexagonal outline distinguishes enzymes (kinases) from generic
    proteins (rounded rects). When ``phosphorylated=True``, a red 'P' badge is rendered
    in the upper-right; otherwise the badge is omitted entirely. The badge sits outside
    the hex outline so the body's bbox is identical between phosphorylation states.

    Args:
        label:          text rendered inside the hexagon
        position:       (x, y) center of the hexagon
        size:           (width, height) of the hexagon's bounding box
        phosphorylated: if True, render a 'P' badge in the upper-right
        color:          optional fill color override (defaults to ``style["kinase_fill"]``)
        style_dict:          presentation attrs dict; falls back to DEFAULT_STYLE for missing keys

    Returns:
        ``svgwrite.container.Group`` containing the hexagon, label, and optional P badge.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["kinase_fill"]
    sw = float(s["protein_stroke_width"])

    half_w, half_h = w / 2, h / 2
    chamfer = h * 0.4
    hex_points = [
        (cx - half_w + chamfer, cy - half_h),
        (cx + half_w - chamfer, cy - half_h),
        (cx + half_w, cy),
        (cx + half_w - chamfer, cy + half_h),
        (cx - half_w + chamfer, cy + half_h),
        (cx - half_w, cy),
    ]
    hexagon = svgwrite.shapes.Polygon(
        points=hex_points, fill=fill, stroke=s["kinase_stroke"]
    )
    hexagon["stroke-width"] = sw
    g.add(hexagon)
    # Fit the label to the hex bbox; the text centers at cy where the hexagon
    # is at full width, so measuring against (w, h) is a fair approximation.
    fit = _fit_label(label, w, h, s)
    if not fit.external:
        g.add(_label_for_fit(fit, cx, cy, s))

    if phosphorylated:
        badge_r = max(7.0, h * 0.3)
        bx = cx + half_w - chamfer * 0.6
        by = cy - half_h
        badge = svgwrite.shapes.Circle(
            center=(bx, by),
            r=badge_r,
            fill=s["kinase_badge_fill"],
            stroke=s["kinase_stroke"],
        )
        badge["stroke-width"] = sw
        g.add(badge)
        g.add(_centered_label(
            "P", bx, by, s,
            weight="bold",
            color=s["kinase_badge_text_color"],
            size_override=float(s["label_font_size"]) * 0.95,
        ))

    return g


def receptor(
    label: str,
    position: tuple[float, float],
    orientation: float = 0.0,
    size: tuple[float, float] = (28, 60),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """
    Single-pass transmembrane receptor: asymmetric hourglass with widest point on the
    extracellular side (ligand-binding pocket).

    Drawn in canonical orientation (vertical body, horizontal membrane at *position*),
    then rotated by ``orientation`` radians around *position*. Use ``orientation=0`` for
    a horizontal membrane (extracellular = above = lower y in SVG; intracellular = below).
    The receptor narrows in the middle to suggest the transmembrane segment.

    For Phase 3+ membrane integration: pass ``position`` from the membrane curve's anchor
    point and ``orientation`` from its tangent angle. proteins.py is intentionally
    decoupled from membranes.py.

    Args:
        label:       text rendered to the right of the receptor
        position:    (x, y) anchor point on the membrane (center of the body)
        orientation: rotation in radians; 0 = horizontal membrane
        size:        (max width, total height); height runs across the membrane
        color:       optional fill color override (defaults to ``style["receptor_fill"]``)
        style_dict:       presentation attrs dict; falls back to DEFAULT_STYLE for missing keys

    Returns:
        ``svgwrite.container.Group`` containing the receptor body and label.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["receptor_fill"]
    sw = float(s["protein_stroke_width"])

    # Asymmetric hourglass:
    #   extracellular (top, smaller y) — widest, ligand-binding pocket
    #   transmembrane (middle) — narrowest neck
    #   intracellular (bottom) — medium width, signaling domain
    ec_w = w
    tm_w = w * 0.45
    ic_w = w * 0.7
    half_h = h / 2
    points = [
        (cx - ec_w / 2, cy - half_h),
        (cx + ec_w / 2, cy - half_h),
        (cx + tm_w / 2, cy),
        (cx + ic_w / 2, cy + half_h),
        (cx - ic_w / 2, cy + half_h),
        (cx - tm_w / 2, cy),
    ]
    body = svgwrite.shapes.Polygon(
        points=points, fill=fill, stroke=s["receptor_stroke"]
    )
    body["stroke-width"] = sw
    g.add(body)

    # Label sits to the LEFT of the receptor body, vertically centered.
    # Above-placement was the original position but it collides with incoming
    # vertical arrows (ligand-binding arrows arrive at the extracellular tip).
    # The left side is always clear of arrows, which enter/exit top and bottom.
    label_t = svgwrite.text.Text(
        label,
        insert=(cx - ec_w / 2 - 6, cy),
        font_family=s["label_font_family"],
        font_size=float(s["label_font_size"]),
        fill=s["label_font_color"],
    )
    label_t["text-anchor"] = "end"
    label_t["dominant-baseline"] = "central"
    g.add(label_t)

    _maybe_rotate(g, orientation, position)
    return g


def gpcr(
    label: str,
    position: tuple[float, float],
    orientation: float = 0.0,
    size: tuple[float, float] = (90, 50),
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """
    G-protein coupled receptor: iconic seven-helix transmembrane bundle.

    Seven vertical rectangles represent transmembrane helices TM1–TM7, connected by
    alternating intracellular and extracellular loops (I1, E1, I2, E2, I3, E3 in the
    canonical ordering). The N-terminus extends extracellular (up), the C-terminus
    extends intracellular (down). Drawn in canonical orientation then rotated by
    ``orientation`` radians.

    For Phase 3+ membrane integration: same contract as ``receptor`` — pass
    ``position`` and ``orientation`` from the membrane curve.

    Args:
        label:       text rendered below the GPCR
        position:    (x, y) anchor point at the center of the membrane plane
        orientation: rotation in radians; 0 = horizontal membrane
        size:        (total bundle width, helix height)
        color:       optional helix fill color override
        style_dict:       presentation attrs dict; falls back to DEFAULT_STYLE for missing keys

    Returns:
        ``svgwrite.container.Group`` containing 7 helices, 6 loops, N/C termini, and label.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["gpcr_helix_fill"]
    sw = float(s["protein_stroke_width"])
    loop_sw = float(s["gpcr_loop_stroke_width"])
    loop_color = s["gpcr_loop_stroke"]

    n_helices = 7
    helix_w = w / (n_helices * 1.6)
    total_helix_w = helix_w * n_helices
    helix_gap = (w - total_helix_w) / (n_helices - 1)
    helix_h = h
    first_x = cx - w / 2 + helix_w / 2
    helix_centers_x = [first_x + i * (helix_w + helix_gap) for i in range(n_helices)]

    # Loops first (so helix outlines visually clip them at junctions).
    # Convention: first loop after H1 is intracellular (I1), then alternating.
    for i in range(n_helices - 1):
        x1, x2 = helix_centers_x[i], helix_centers_x[i + 1]
        if i % 2 == 0:
            y_anchor = cy + helix_h / 2
            y_arc = y_anchor + helix_gap * 0.7
        else:
            y_anchor = cy - helix_h / 2
            y_arc = y_anchor - helix_gap * 0.7
        d = (
            f"M {x1:.2f},{y_anchor:.2f} "
            f"Q {(x1 + x2) / 2:.2f},{y_arc:.2f} {x2:.2f},{y_anchor:.2f}"
        )
        loop = svgwrite.path.Path(d=d, fill="none", stroke=loop_color)
        loop["stroke-width"] = loop_sw
        g.add(loop)

    # Helices (rounded rectangles for the cylinder feel)
    for hx in helix_centers_x:
        helix = svgwrite.shapes.Rect(
            insert=(hx - helix_w / 2, cy - helix_h / 2),
            size=(helix_w, helix_h),
            rx=helix_w / 2,
            ry=helix_w / 2,
            fill=fill,
            stroke=s["gpcr_helix_stroke"],
        )
        helix["stroke-width"] = sw
        g.add(helix)

    # N-terminus: extracellular tail extending up-left from H1
    nt_x, nt_y = helix_centers_x[0], cy - helix_h / 2
    nterm = svgwrite.path.Path(
        d=f"M {nt_x:.2f},{nt_y:.2f} L {nt_x - 8:.2f},{nt_y - 14:.2f}",
        fill="none",
        stroke=loop_color,
    )
    nterm["stroke-width"] = loop_sw
    g.add(nterm)

    # C-terminus: intracellular tail extending down-right from H7
    ct_x, ct_y = helix_centers_x[-1], cy + helix_h / 2
    cterm = svgwrite.path.Path(
        d=f"M {ct_x:.2f},{ct_y:.2f} L {ct_x + 8:.2f},{ct_y + 14:.2f}",
        fill="none",
        stroke=loop_color,
    )
    cterm["stroke-width"] = loop_sw
    g.add(cterm)

    # Label below the bundle, clear of intracellular loops + C-terminus
    label_y = cy + helix_h / 2 + helix_gap * 0.7 + 22
    label_t = svgwrite.text.Text(
        label,
        insert=(cx, label_y),
        font_family=s["label_font_family"],
        font_size=float(s["label_font_size"]),
        fill=s["label_font_color"],
    )
    label_t["text-anchor"] = "middle"
    g.add(label_t)

    _maybe_rotate(g, orientation, position)
    return g


def transcription_factor(
    label: str,
    position: tuple[float, float],
    size: tuple[float, float] = (60, 30),
    dna_binding: bool = False,
    color: Optional[str] = None,
    style_dict: Optional[dict] = None,
) -> svgwrite.container.Group:
    """
    Transcription factor: rounded rectangle with optional DNA-binding domain protrusion.

    Convention: the body is a rounded rectangle (like generic_protein) in a distinct
    palette. When ``dna_binding=True``, a small darker rectangle protrudes from the
    bottom — this is the DNA-binding domain (DBD). It signals "this protein contacts
    DNA" without committing to a specific DBD type (zinc finger, helix-turn-helix, etc.).

    Args:
        label:       text rendered inside the protein body
        position:    (x, y) center of the protein body (DBD extends below when present)
        size:        (width, height) of the main body
        dna_binding: if True, render the DBD protrusion at the bottom
        color:       optional fill color override (defaults to ``style["tf_fill"]``)
        style_dict:       presentation attrs dict; falls back to DEFAULT_STYLE for missing keys

    Returns:
        ``svgwrite.container.Group`` containing the body, label, and optional DBD.
    """
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    g = svgwrite.container.Group()
    cx, cy = position
    w, h = size
    fill = color or s["tf_fill"]
    sw = float(s["protein_stroke_width"])

    body = svgwrite.shapes.Rect(
        insert=(cx - w / 2, cy - h / 2),
        size=(w, h),
        rx=float(s["protein_corner_radius"]),
        ry=float(s["protein_corner_radius"]),
        fill=fill,
        stroke=s["tf_stroke"],
    )
    body["stroke-width"] = sw
    g.add(body)
    g.add(_centered_label(label, cx, cy, s))

    if dna_binding:
        dbd_w = w * 0.45
        dbd_h = h * 0.4
        dbd = svgwrite.shapes.Rect(
            insert=(cx - dbd_w / 2, cy + h / 2),
            size=(dbd_w, dbd_h),
            rx=2,
            ry=2,
            fill=s["tf_dbd_fill"],
            stroke=s["tf_stroke"],
        )
        dbd["stroke-width"] = sw
        g.add(dbd)

    return g


# Primitives that fit their in-box label via ``_text.fit_label`` and therefore
# render an empty box when the fit escalates to rung 4 (external). The layout
# engine consults this set to decide which entities need an off-box leader
# label placed for them (see ``pathway_layout.pathway_label_requests``).
FIT_AWARE_PRIMITIVES: frozenset = frozenset({
    generic_protein,
    protein_complex,
    kinase,
})
