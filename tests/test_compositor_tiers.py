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
    # P0a.3/P5.2 seam: tiered figures place their scene labels inside the tier
    # engine (scene_label_requests + place_labels), where the per-scene geometry
    # lives, so the coordinator's tier arm is an identity pass-through. Pinning
    # it keeps any future move of placement out of the engine a deliberate change.
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
    # tracks the molecule's CONTENT extent (now content-aware sized to its real
    # ink), NOT the cell right edge — so a cross-cell arrow spans the visible
    # molecule gap rather than the inter-cell gutter.
    from imageGen.layout.tier_layout import _slot_drawn_size
    scene = Scene.model_validate({
        "id": "s", "slots": [{"id": "mol", "kind": "molecule",
                              "style": {"smiles": "CCO"}}]})
    reg = AnchorRegistry()
    cell = (0.0, 0.0, 400.0, 200.0)  # cell much wider than the molecule
    _layout_scene(scene, cell, reg, dict(TIER_DEFAULT_PARAMS))
    mol_w, _h = _slot_drawn_size(scene.slots[0], TIER_DEFAULT_PARAMS["tier_slot_size"],
                                 dict(TIER_DEFAULT_PARAMS))
    cell_cx = cell[0] + cell[2] / 2.0
    right_x, _y = reg.resolve("s.right")
    assert right_x == pytest.approx(cell_cx + mol_w / 2.0)  # at the molecule edge
    assert cell_cx < right_x < cell[0] + cell[2]  # past centre, inside the cell


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
# Scene-local labels (P5.2) + annotation occupancy seed (P5.3)
# ---------------------------------------------------------------------------

def test_scene_captions_stay_in_their_scene_cells():
    # P5.2: each caption is placed local to its own scene — the left scene's
    # caption sits left of the figure centre, the right scene's right of it.
    fig = _hydrolysis_figure()
    entries = layout_tiers(fig)
    w, _h = tier_canvas(fig)
    caps = {e.ir_id: e.args[1] for e in entries
            if e.ir_id in ("label_scene_s_aspirin_label",
                           "label_scene_s_salicylic_label")}
    assert set(caps) == {"label_scene_s_aspirin_label",
                         "label_scene_s_salicylic_label"}
    assert (caps["label_scene_s_aspirin_label"][0] < w / 2.0
            < caps["label_scene_s_salicylic_label"][0])


def test_scene_edge_and_slot_labels_render(tmp_path):
    # P5.2: a non-TEXT Slot.label and a SceneEdge.label (both previously
    # unrendered) now appear in the SVG, placed by the scene-local pass.
    fig = Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [{"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [
                {"id": "mol", "kind": "molecule", "label": "ligand",
                 "style": {"smiles": ASPIRIN,
                           "anchor_names": {"1": "a1", "3": "a3"}}}],
             "connect": [{"from_anchor": "mol.a1", "to_anchor": "mol.a3",
                          "type": "dashed", "label": "Hbond"}]}]}]})
    out = render_figure(fig, tmp_path / "scene_labels.svg")
    svg = out.read_text()
    assert "label_slot_s_mol_label" in svg and ">ligand<" in svg
    assert "label_edge_mol.a1_mol.a3_label" in svg and "Hbond" in svg


def test_annotation_is_nudged_off_a_scene_label():
    # P5.3: a figure-level annotation authored on top of a scene-local label is
    # pushed clear of it (occupancy seed). With occupied=None it stays put.
    from imageGen.layout.label_placement import (
        _bbox_from_center, _estimate_text_bbox, _overlaps,
    )
    from imageGen.render.annotations import annotation_entries
    fig = Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "entities": [{"id": "e", "type": "protein", "label": "E"}],
        "annotations": [{"type": "caption", "text": "note", "position": [0.5, 0.5]}],
    })
    canvas = (400.0, 300.0)
    occ = _bbox_from_center((200.0, 150.0), _estimate_text_bbox("note", 11))
    # seeded: the annotation moves off the occupied box.
    seeded = annotation_entries(fig, canvas, {}, occupied=[occ])
    override = seeded[0].kwargs.get("position_override")
    assert override is not None
    moved = _bbox_from_center(override, _estimate_text_bbox("note", 11))
    assert not _overlaps(moved, occ, 1.0)
    # unseeded (every non-tier path): no override → authored position verbatim.
    assert "position_override" not in annotation_entries(fig, canvas, {})[0].kwargs


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
