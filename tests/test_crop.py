"""Tests for render/crop.py and the band-aware content_bounds helper."""
from __future__ import annotations

import re
from pathlib import Path

from imageGen.ir.builder import build
from imageGen.ir.schema import (
    Annotation,
    AnnotationType,
    Archetype,
    Entity,
    EntityType,
    Figure,
)
from imageGen.render.compositor import render_figure
from imageGen.render.crop import (
    apply_crop,
    crop_box,
    cropped_path,
    expand_box,
)
from imageGen.verify.legibility_check import content_bounds

CANVAS = (0.0, 0.0, 800.0, 600.0)


def _render(tmp_path: Path, *, name: str = "fig") -> Path:
    """Render a small 3-entity pathway and return the SVG path."""
    ir = build(
        "pathway",
        entities=[("a", "protein", "A"), ("b", "kinase", "B"), ("c", "protein", "C")],
        relations=[("a", "activates", "b"), ("b", "activates", "c")],
    )
    out = tmp_path / f"{name}.png"
    render_figure(ir, out)
    return out.with_suffix(".svg")


# ---------------------------------------------------------------------------
# content_bounds — band exclusion
# ---------------------------------------------------------------------------


def test_content_bounds_excludes_band(tmp_path):
    """A single-band pathway's content box is the entities, not the full canvas."""
    svg = _render(tmp_path)
    content, canvas = content_bounds(svg)
    # L19: 1-band figure floor is n_bands * _BAND_BASELINE (100), not old hardcoded 600.
    assert canvas == (0.0, 0.0, 800.0, 100.0)
    # Content occupies only a thin strip — far shorter than the full canvas,
    # which proves the full-canvas decorative band was excluded.
    content_h = content[3] - content[1]
    assert content_h < 200.0


# ---------------------------------------------------------------------------
# crop_box geometry
# ---------------------------------------------------------------------------


def test_crop_box_fit_content_adds_margin():
    box = crop_box((100, 100, 200, 200), CANVAS, 0.15)
    assert box == (85.0, 85.0, 215.0, 215.0)


def test_crop_box_fit_content_does_not_force_aspect():
    # Wide content stays wide (no aspect adjustment in fit mode).
    box = crop_box((0, 290, 800, 310), CANVAS, 0.0)
    assert box == (0.0, 290.0, 800.0, 310.0)
    assert (box[2] - box[0]) > (box[3] - box[1])


def test_crop_box_keep_aspect_matches_canvas_ratio():
    box = crop_box((100, 100, 200, 200), CANVAS, 0.15, keep_aspect=True)
    w, h = box[2] - box[0], box[3] - box[1]
    assert abs((w / h) - (800.0 / 600.0)) < 1e-6


def test_crop_box_clamps_into_canvas():
    box = crop_box((0, 0, 50, 50), CANVAS, 0.15)
    assert box[0] >= 0.0 and box[1] >= 0.0
    assert box[2] <= 800.0 and box[3] <= 600.0


# ---------------------------------------------------------------------------
# apply_crop — sibling output, original preserved
# ---------------------------------------------------------------------------


def test_cropped_path_naming():
    assert cropped_path(Path("/x/figure.png")) == Path("/x/figure_cropped.png")
    assert cropped_path(Path("/x/figure.svg")) == Path("/x/figure_cropped.svg")


def test_apply_crop_writes_sibling_keeps_original(tmp_path):
    svg = _render(tmp_path)
    png = svg.with_suffix(".png")
    original_svg_text = svg.read_text()

    out, box = apply_crop(svg, png, "png", keep_aspect=False)

    # Sibling files exist; originals are untouched.
    assert out == tmp_path / "fig_cropped.png"
    assert out.exists() and out.stat().st_size > 0
    assert (tmp_path / "fig_cropped.svg").exists()
    assert svg.read_text() == original_svg_text  # original SVG not modified
    assert box[2] > box[0] and box[3] > box[1]


def test_apply_crop_fit_sets_width_height_to_box(tmp_path):
    svg = _render(tmp_path)
    apply_crop(svg, svg.with_suffix(".png"), "png", keep_aspect=False)
    cropped = (tmp_path / "fig_cropped.svg").read_text()
    m = re.search(r'<svg\b[^>]*>', cropped)
    tag = m.group(0)
    vb = re.search(r'viewBox="[\d.\- ]+"', tag)
    assert vb is not None
    # fit-content: width/height equal the viewBox extent (a true 1:1 crop)
    vb_w = float(vb.group(0).split('"')[1].split()[2])
    width = float(re.search(r'\swidth="([\d.]+)"', tag).group(1))
    assert abs(width - vb_w) < 1e-6


def test_apply_crop_keep_aspect_preserves_canvas_size(tmp_path):
    svg = _render(tmp_path)
    apply_crop(svg, svg.with_suffix(".png"), "png", keep_aspect=True)
    cropped = (tmp_path / "fig_cropped.svg").read_text()
    tag = re.search(r'<svg\b[^>]*>', cropped).group(0)
    width = float(re.search(r'\swidth="([\d.]+)"', tag).group(1))
    height = float(re.search(r'\sheight="([\d.]+)"', tag).group(1))
    # keep-aspect leaves the canvas dimensions so content scales uniformly.
    # L19: single-band canvas is now 800 × 100 (not 800 × 600).
    assert (width, height) == (800.0, 100.0)


# ---------------------------------------------------------------------------
# FR3 — frame expansion to rescue off-canvas labels
# ---------------------------------------------------------------------------


def test_expand_box_grows_only_overflow_sides():
    canvas = (0.0, 0.0, 800.0, 600.0)
    # content overflows the right edge by 40px; other sides fit.
    box = expand_box((10.0, 10.0, 840.0, 500.0), canvas, margin=6.0)
    assert box is not None
    x0, y0, x1, y1 = box
    assert (x0, y0, y1) == (0.0, 0.0, 600.0)  # untouched sides
    assert x1 == 840.0 + 6.0                  # overflow side + margin


def test_expand_box_noop_when_content_fits():
    canvas = (0.0, 0.0, 800.0, 600.0)
    assert expand_box((10.0, 10.0, 790.0, 590.0), canvas) is None


def test_expand_box_handles_negative_overflow():
    canvas = (0.0, 0.0, 800.0, 600.0)
    box = expand_box((-30.0, 10.0, 500.0, 500.0), canvas, margin=6.0)
    assert box is not None
    assert box[0] == -36.0  # left edge grows outward (negative)


def test_render_grows_frame_to_enclose_offcanvas_label():
    """FR3: a label drawn past the canvas edge expands the SVG frame in-place."""
    import tempfile
    from pathlib import Path as _P

    ir = Figure(
        archetype=Archetype.PATHWAY,
        entities=[Entity(id="a", type=EntityType.METABOLITE, label="A")],
        relations=[],
        annotations=[
            Annotation(
                type=AnnotationType.LABEL,
                text="lithification and burial",
                position=(0.97, 0.5),
            )
        ],
    )
    with tempfile.TemporaryDirectory() as d:
        out = _P(d) / "fr3.svg"
        render_figure(ir, out)
        svg = out.read_text()
        content, canvas = content_bounds(out)
    assert "lithification and burial" in svg
    # the long edge-anchored label is fully enclosed by the (grown) frame.
    assert content[2] <= canvas[2] + 0.6
    assert canvas[2] > 800.0  # frame grew past the default 800px width
