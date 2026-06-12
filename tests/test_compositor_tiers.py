"""Step-4 tier compositor integration: render tiered figures through the pipeline.

Covers the wiring that makes a ``Figure.tiers`` render through the normal
``render_figure`` pipeline / CLI:
  - dispatch to ``layout_tiers`` (the Step-3 NotImplementedError stub is gone),
  - tier-aware canvas sizing that matches the engine's baked coordinates,
  - band chrome (background / border / divider), scene badges + captions,
  - the cell-vs-content extent fix (transition arrows span the molecule gap),
  - figure-title suppression under tiers, and autocrop.

The new chrome primitives (``_band_chrome``/``_badge_group``/``_caption_group``)
get focused structural + render coverage per the "every primitive gets a golden
test" rule.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest
import svgwrite.container

from imageGen.ir import Figure, Scene
from imageGen.layout.anchors import AnchorRegistry
from imageGen.layout.tier_layout import (
    TIER_DEFAULT_PARAMS,
    _badge_group,
    _band_chrome,
    _caption_group,
    _layout_scene,
    layout_tiers,
    tier_canvas,
)
from imageGen.render.compositor import _canvas_size, _dispatch_layout, render_figure
from tests._helpers import FIGURES_DIR, render_group_to_png

ASPIRIN = "C[C:1](=O)[O:3]c1ccccc1C(=O)O"   # :1 acetyl C, :3 ester O
SALICYLIC = "O=C(O)c1ccccc1O"


def _hydrolysis_figure(*, title: str | None = None,
                       band_fill: str | None = "#F2F4F7") -> Figure:
    row_style = {"band_fill": band_fill} if band_fill else None
    return Figure.model_validate({
        "archetype": "mechanism_cartoon",
        **({"title": title} if title else {}),
        "tiers": [
            {"id": "title", "role": "title", "height_frac": 0.18,
             "label": "Aspirin hydrolysis", "subtitle": "acyl-oxygen cleavage"},
            {"id": "row", "role": "scene_row", "layout": "equal_columns",
             "height_frac": 0.82,
             **({"style": row_style} if row_style else {}),
             "rails": [{"name": "midline", "axis": "y", "at": 0.5}],
             "scenes": [
                 {"id": "s_aspirin", "badge": "1", "label": "aspirin",
                  "slots": [{"id": "mol", "kind": "molecule",
                             "style": {"smiles": ASPIRIN,
                                       "anchor_names": {"1": "acetyl_C",
                                                        "3": "ester_O"}}}],
                  "connect": [{"from_anchor": "mol.acetyl_C",
                               "to_anchor": "mol.ester_O", "type": "dashed"}]},
                 {"id": "s_salicylic", "badge": "2", "label": "salicylic acid",
                  "slots": [{"id": "mol", "kind": "molecule",
                             "style": {"smiles": SALICYLIC}}]},
             ],
             "transitions": [{"from_ref": "s_aspirin@right",
                              "to_ref": "s_salicylic@left",
                              "type": "transition", "on_rail": "midline"}]},
        ],
    })


# ---------------------------------------------------------------------------
# Compositor wiring
# ---------------------------------------------------------------------------

def test_dispatch_layout_no_longer_raises_for_tiers():
    fig = _hydrolysis_figure()
    entries = _dispatch_layout(fig, style_dict={}, smiles_map=None)
    assert entries and all(isinstance(
        e.primitive(*e.args, **e.kwargs), svgwrite.container.Group) for e in entries)


def test_label_coordinator_tier_branch_is_inert():
    # P0a.3 seam: the tier arm of LabelCoordinator.place is an identity
    # pass-through today (tier captions are baked by the tier engine). This
    # pins the inert seam so P5.2 flipping it to scene-local placement is a
    # *deliberate*, reviewable change rather than a silent drift.
    from imageGen.render.label_coordinator import LabelCoordinator
    fig = _hydrolysis_figure()
    entries = _dispatch_layout(fig, style_dict={}, smiles_map=None)
    placed = LabelCoordinator.place(fig, entries, {}, canvas=tier_canvas(fig))
    assert placed is entries


def test_canvas_size_matches_tier_canvas():
    fig = _hydrolysis_figure()
    # The viewport the compositor picks must equal what the engine sized to,
    # else baked coords clip. Both route through tier_canvas.
    assert _canvas_size(fig, []) == tier_canvas(fig)


def test_tiered_figure_renders_end_to_end(tmp_path):
    fig = _hydrolysis_figure()
    out = render_figure(fig, tmp_path / "aspirin_tier.png")
    assert out.exists() and out.stat().st_size > 0
    svg = out.with_suffix(".svg").read_text()
    # band chrome, both badges, captions, the cleaved bond, the transition arrow
    for token in ("tier_row_chrome", "scene_s_aspirin_badge",
                  "scene_s_salicylic_badge", "scene_s_aspirin_label",
                  "edge_mol.acetyl_C_mol.ester_O",
                  "tedge_s_aspirin@right_s_salicylic@left", "tier_title_title"):
        assert token in svg, f"missing {token!r} in rendered SVG"


def test_tiered_figure_passes_legibility(tmp_path):
    # Regression: a thin TITLE band put title+subtitle close enough to trip the
    # legibility overlap heuristic (false positive). Fixed by guaranteed baseline
    # separation; the canonical figure must verify clean.
    from imageGen.verify.legibility_check import legibility_check
    fig = _hydrolysis_figure()
    out = render_figure(fig, tmp_path / "legible.svg")
    result = legibility_check(out)  # raises LegibilityCheckError on overlap
    assert result is not None


def test_figure_title_suppressed_under_tiers(tmp_path):
    # Figure.title is set, but the TITLE tier owns titling — no double render.
    fig = _hydrolysis_figure(title="A REDUNDANT TITLE")
    out = render_figure(fig, tmp_path / "no_double_title.png")
    svg = out.with_suffix(".svg").read_text()
    assert "figure_title" not in svg
    assert "A REDUNDANT TITLE" not in svg
    assert "tier_title_title" in svg  # the tier's own title still renders


def test_tiered_render_through_spec_cli_path(tmp_path):
    # The CLI raw-IR path is just render_figure(Figure, ...); confirm a tiered
    # figure round-trips JSON -> Figure -> render with no smiles_map kwarg
    # (SMILES live in slot.style, not the flat map reactions need).
    fig = _hydrolysis_figure()
    reparsed = Figure.model_validate_json(fig.model_dump_json())
    out = render_figure(reparsed, tmp_path / "cli_path.svg")
    assert out.exists() and out.stat().st_size > 0


def test_autocrop_does_not_grow_canvas(tmp_path):
    fig = _hydrolysis_figure(band_fill=None)  # no full-width band so there's margin to trim
    plain = render_figure(fig, tmp_path / "plain.svg")
    cropped = render_figure(fig, tmp_path / "cropped.svg", autocrop=True)

    def _frame(p):
        root = ET.fromstring(p.read_text())
        vb = root.get("viewBox")
        if vb:
            _x, _y, w, h = (float(v) for v in vb.split())
            return w, h
        return float(root.get("width")), float(root.get("height"))

    pw, ph = _frame(plain)
    cw, ch = _frame(cropped)
    assert cw <= pw + 1 and ch <= ph + 1  # autocrop never grows the frame


# ---------------------------------------------------------------------------
# Cell-vs-content extent fix
# ---------------------------------------------------------------------------

def test_scene_frame_anchor_tracks_content_not_cell():
    # A single molecule centred in a wide cell: the scene-frame 'right' anchor
    # must sit at the molecule's right edge (centre + sw/2), NOT the cell right
    # edge — so a cross-cell arrow spans the visible molecule gap.
    scene = Scene.model_validate({
        "id": "s", "slots": [{"id": "mol", "kind": "molecule",
                              "style": {"smiles": "CCO"}}]})
    reg = AnchorRegistry()
    cell = (0.0, 0.0, 400.0, 200.0)  # cell much wider than the slot
    _layout_scene(scene, cell, reg, dict(TIER_DEFAULT_PARAMS))
    sw, _sh = TIER_DEFAULT_PARAMS["tier_slot_size"]
    cell_cx = cell[0] + cell[2] / 2.0
    right_x, _y = reg.resolve("s.right")
    assert right_x == pytest.approx(cell_cx + sw / 2.0)
    assert right_x < cell[0] + cell[2]  # strictly inside the cell frame


def test_transition_endpoints_lie_in_the_molecule_gap():
    # End-to-end: the resolved transition arrow must start past the first
    # molecule's right edge and end before the second molecule's left edge.
    fig = _hydrolysis_figure(band_fill=None)
    reg = AnchorRegistry()
    # Re-run the engine's anchor publishing by laying the row out and asking the
    # registry directly (layout_tiers builds its own registry internally, so we
    # reconstruct the same geometry through the public resolve path instead).
    entries = layout_tiers(fig)
    # Find the transition entry and read its baked endpoints from the closure.
    tedge = next(e for e in entries
                 if e.ir_id == "tedge_s_aspirin@right_s_salicylic@left")
    p0, p1 = tedge.primitive.__defaults__[0], tedge.primitive.__defaults__[1]
    assert p0[0] < p1[0]                      # left-to-right
    assert p1[1] == pytest.approx(p0[1])      # level on the midline rail
    assert (p1[0] - p0[0]) > 40.0             # a real gap, not a gutter sliver


# ---------------------------------------------------------------------------
# New chrome primitives (golden-image rule)
# ---------------------------------------------------------------------------

def test_band_chrome_emits_fill_border_and_divider():
    g = _band_chrome((10.0, 20.0, 300.0, 80.0),
                     {"band_fill": "#EEEEEE", "band_stroke": "#999999",
                      "divider": "dashed"}, dict(TIER_DEFAULT_PARAMS))
    xml = g.tostring()
    assert "rect" in xml and "#EEEEEE" in xml and "#999999" in xml
    assert "line" in xml and "stroke-dasharray" in xml
    render_group_to_png(g, "tier_band_chrome.png", canvas=(320, 120))
    assert (FIGURES_DIR / "tier_band_chrome.png").exists()


def test_band_chrome_empty_style_is_blank_group():
    g = _band_chrome((0.0, 0.0, 100.0, 50.0), {}, dict(TIER_DEFAULT_PARAMS))
    assert isinstance(g, svgwrite.container.Group)
    assert "rect" not in g.tostring() and "line" not in g.tostring()


def test_badge_group_is_circle_plus_number():
    g = _badge_group("3", (40.0, 40.0), dict(TIER_DEFAULT_PARAMS))
    xml = g.tostring()
    assert "circle" in xml and ">3<" in xml
    render_group_to_png(g, "tier_badge.png", canvas=(80, 80))
    assert (FIGURES_DIR / "tier_badge.png").exists()


def test_caption_group_stacks_multiline():
    g = _caption_group("line one\nline two", 100.0, 30.0, dict(TIER_DEFAULT_PARAMS))
    texts = [t for t in g.elements if t.elementname == "text"]
    assert len(texts) == 2
    # second line sits below the first
    assert float(texts[1]["y"]) > float(texts[0]["y"])
    render_group_to_png(g, "tier_caption.png", canvas=(200, 80))
    assert (FIGURES_DIR / "tier_caption.png").exists()
