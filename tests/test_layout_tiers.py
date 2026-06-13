"""Step-3 vertical slice: lower a tiered IR Figure through the real engine.

This is the chassis-driven counterpart to the hand-assembled keystone slice
(test_anchor_keystone.py). The same aspirin -> salicylic acid scene is authored
as a ``Figure`` with tiers and lowered by ``layout_tiers`` into LayoutEntries,
proving the schema -> engine -> SVG path end to end. Coordinate-math correctness
is already covered by the keystone tests; here we assert the IR lowers to the
expected tagged entries and renders.
"""
from __future__ import annotations

import pytest

from imageGen.ir import Figure, Scene
from imageGen.layout.tier_layout import layout_tiers
from tests._helpers import render_entries_to_png

ASPIRIN = "C[C:1](=O)[O:3]c1ccccc1C(=O)O"   # :1 acetyl C, :3 ester O
SALICYLIC = "O=C(O)c1ccccc1O"


def _aspirin_hydrolysis_figure() -> Figure:
    return Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [
            {"id": "title", "role": "title", "height_frac": 0.18,
             "label": "Aspirin hydrolysis", "subtitle": "acyl-oxygen cleavage"},
            {"id": "row", "role": "scene_row", "layout": "equal_columns",
             "height_frac": 0.82,
             "rails": [{"name": "midline", "axis": "y", "at": 0.5}],
             "scenes": [
                 {"id": "s_aspirin", "badge": "1",
                  "slots": [
                      {"id": "mol", "kind": "molecule",
                       "style": {"smiles": ASPIRIN,
                                 "anchor_names": {"1": "acetyl_C", "3": "ester_O"}}},
                      {"id": "cap", "kind": "text", "label": "aspirin"},
                  ],
                  "attach": [{"child": "cap", "parent": "mol", "edge": "bottom",
                              "offset": [0, 10]}],
                  "connect": [{"from_anchor": "mol.acetyl_C",
                               "to_anchor": "mol.ester_O", "type": "dashed"}]},
                 {"id": "s_salicylic", "badge": "2",
                  "slots": [
                      {"id": "mol", "kind": "molecule",
                       "style": {"smiles": SALICYLIC}},
                      {"id": "cap", "kind": "text", "label": "salicylic acid"},
                  ],
                  "attach": [{"child": "cap", "parent": "mol", "edge": "bottom",
                              "offset": [0, 10]}]},
             ],
             "transitions": [{"from_ref": "s_aspirin@right",
                              "to_ref": "s_salicylic@left",
                              "type": "transition", "on_rail": "midline"}]},
        ],
    })


def test_tiered_figure_lowers_to_entries():
    fig = _aspirin_hydrolysis_figure()
    entries = layout_tiers(fig, layout_params={"tier_canvas": (600, 300)})
    assert entries, "expected non-empty LayoutEntry list"
    ir_ids = {e.ir_id for e in entries if e.ir_id}
    # title + both molecules + the intra-scene bond + the cross-cell arrow
    assert "tier_title_title" in ir_ids
    assert "s_aspirin.mol" in ir_ids
    assert "s_salicylic.mol" in ir_ids
    assert "edge_mol.acetyl_C_mol.ester_O" in ir_ids
    assert "tedge_s_aspirin@right_s_salicylic@left" in ir_ids


def test_every_entry_primitive_is_callable_and_returns_group():
    import svgwrite.container
    entries = layout_tiers(_aspirin_hydrolysis_figure(),
                           layout_params={"tier_canvas": (600, 300)})
    for e in entries:
        g = e.primitive(*e.args, **e.kwargs)
        assert isinstance(g, svgwrite.container.Group)


def test_tiered_slice_renders_to_png():
    entries = layout_tiers(_aspirin_hydrolysis_figure(),
                           layout_params={"tier_canvas": (600, 300)})
    out = render_entries_to_png(entries, "tier_slice_aspirin.png", canvas=(600, 300))
    assert out.exists() and out.stat().st_size > 0


def test_empty_tiers_rejected():
    with pytest.raises(ValueError, match="tiers populated"):
        layout_tiers(Figure.model_validate(
            {"archetype": "pathway",
             "entities": [{"id": "a", "type": "protein", "label": "A"}]}))


def test_step_sequence_not_yet_supported():
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row",
         "step_sequence": {"id": "q", "base": {"id": "b"}, "steps": []}}]})
    with pytest.raises(NotImplementedError, match="step_sequence"):
        layout_tiers(fig)


def test_unsupported_slot_kind_raises():
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [{"id": "b", "kind": "blob"}]}]}]})
    with pytest.raises(NotImplementedError, match="SlotKind"):
        layout_tiers(fig)


def test_molecule_slot_requires_smiles():
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [{"id": "m", "kind": "molecule"}]}]}]})
    with pytest.raises(ValueError, match="style\\['smiles'\\]"):
        layout_tiers(fig)


# ---------------------------------------------------------------------------
# Attach solver robustness (from the Step-3 adversarial review)
# ---------------------------------------------------------------------------

def _scene_with_attach(attach):
    from imageGen.ir import Scene
    return Scene.model_validate({
        "id": "s",
        "slots": [{"id": "a", "kind": "text"}, {"id": "b", "kind": "text"},
                  {"id": "c", "kind": "text"}],
        "attach": attach,
    })


def test_attach_resolves_regardless_of_declaration_order():
    from imageGen.layout.tier_layout import _solve_slot_centers
    # declared child-first (c<-b before b<-a); must still resolve topologically
    scene = _scene_with_attach([
        {"child": "c", "parent": "b", "edge": "right"},
        {"child": "b", "parent": "a", "edge": "right"},
    ])
    centers = _solve_slot_centers(scene, (0.0, 0.0, 300.0, 100.0), (50.0, 40.0))
    # a is the only root -> cell centre; b/c step right by half a slot width each
    assert centers["a"] == (150.0, 50.0)
    assert centers["b"] == (175.0, 50.0)
    assert centers["c"] == (200.0, 50.0)


def test_attach_cycle_raises():
    from imageGen.layout.tier_layout import _solve_slot_centers
    scene = _scene_with_attach([
        {"child": "a", "parent": "b", "edge": "right"},
        {"child": "b", "parent": "a", "edge": "right"},
    ])
    with pytest.raises(ValueError, match="cyclic or unresolvable"):
        _solve_slot_centers(scene, (0.0, 0.0, 300.0, 100.0), (50.0, 40.0))


def test_unsupported_attach_edge_raises():
    # P5.1: cavity_* is now resolvable, so the unsupported-edge contract is
    # pinned by `custom` (anchor/custom + parent_anchor resolution land in Step 7).
    from imageGen.layout.tier_layout import _solve_slot_centers
    scene = _scene_with_attach([{"child": "b", "parent": "a", "edge": "custom"}])
    with pytest.raises(NotImplementedError, match="attach edge"):
        _solve_slot_centers(scene, (0.0, 0.0, 300.0, 100.0), (50.0, 40.0))


def test_cavity_edges_resolve_inside_parent():
    # P5.1: cavity_top / cavity_bottom drop a child a quarter-extent off the
    # parent centre (inside the parent box, a binding-pocket region).
    from imageGen.layout.tier_layout import _solve_slot_centers
    scene = _scene_with_attach([
        {"child": "b", "parent": "a", "edge": "cavity_top"},
        {"child": "c", "parent": "a", "edge": "cavity_bottom"},
    ])
    centers = _solve_slot_centers(scene, (0.0, 0.0, 300.0, 100.0), (50.0, 40.0))
    assert centers["a"] == (150.0, 50.0)            # sole root → cell centre
    assert centers["b"] == (150.0, 50.0 - 0.25 * 40.0)  # quarter up, inside
    assert centers["c"] == (150.0, 50.0 + 0.25 * 40.0)  # quarter down, inside


def test_two_center_attached_slots_do_not_overlap():
    # MF-3: two slots both bound at `center` previously landed on the same point
    # (the His513-vs-ligand tangle). The solver now spreads co-located boxes so
    # they are disjoint, centred symmetrically on the shared point.
    from imageGen.layout.tier_layout import _solve_slot_centers
    sw, sh = 60.0, 40.0
    scene = Scene.model_validate({
        "id": "s",
        "slots": [{"id": "his", "kind": "text"}, {"id": "lig", "kind": "text"}],
        "attach": [{"child": "his", "edge": "center"},
                   {"child": "lig", "edge": "center"}],
    })
    centers = _solve_slot_centers(scene, (0.0, 0.0, 300.0, 200.0), (sw, sh))
    his_maxx = centers["his"][0] + sw / 2.0
    lig_minx = centers["lig"][0] - sw / 2.0
    assert his_maxx <= lig_minx                                  # disjoint boxes
    assert (centers["his"][0] + centers["lig"][0]) / 2.0 == pytest.approx(150.0)
    assert centers["his"][1] == 100.0 and centers["lig"][1] == 100.0


def test_solve_slot_centers_is_deterministic():
    # Co-location de-overlap must be order-stable: solving twice yields an
    # identical dict (Kahn order + declaration tiebreak, no set iteration).
    from imageGen.layout.tier_layout import _solve_slot_centers
    scene = Scene.model_validate({
        "id": "s",
        "slots": [{"id": "his", "kind": "text"}, {"id": "lig", "kind": "text"}],
        "attach": [{"child": "his", "edge": "center"},
                   {"child": "lig", "edge": "center"}],
    })
    rect, size = (0.0, 0.0, 300.0, 200.0), (60.0, 40.0)
    assert _solve_slot_centers(scene, rect, size) == _solve_slot_centers(scene, rect, size)


def test_slot_extents_widen_the_parent_slide():
    # P5.1: when a per-slot extent is supplied, the child slide uses the
    # *parent's* real width (not the uniform slot size) so a wide parent pushes
    # its child clear of its actual box. Absent extents → uniform fallback.
    from imageGen.layout.tier_layout import _solve_slot_centers
    scene = Scene.model_validate({
        "id": "s",
        "slots": [{"id": "a", "kind": "text"}, {"id": "b", "kind": "text"}],
        "attach": [{"child": "b", "parent": "a", "edge": "right"}],
    })
    rect = (0.0, 0.0, 300.0, 100.0)
    # a sole root → cell centre 150; uniform: b = a + 0.5 * 50
    assert _solve_slot_centers(scene, rect, (50.0, 40.0))["b"][0] == 150.0 + 25.0
    # wide parent extent: b = a + 0.5 * 200
    wide = _solve_slot_centers(scene, rect, (50.0, 40.0),
                               slot_extents={"a": (200.0, 40.0)})
    assert wide["b"][0] == 150.0 + 100.0


def test_scene_label_requests_covers_caption_slot_and_edge():
    # P5.2: scene_label_requests emits the caption, a non-TEXT Slot.label, and a
    # SceneEdge.label (the latter two previously unrendered); a TEXT slot's label
    # is the body, never a separate request. ir_ids are preserved.
    from imageGen.layout.tier_layout import (
        TIER_DEFAULT_PARAMS, scene_label_requests,
    )
    scene = Scene.model_validate({
        "id": "s", "label": "caption",
        "slots": [
            {"id": "blob", "kind": "molecule", "label": "His513",
             "style": {"smiles": "CCO"}},
            {"id": "note", "kind": "text", "label": "ignored"},
        ],
        "connect": [{"from_anchor": "blob.center", "to_anchor": "note.center",
                     "type": "dashed", "label": "H-bond"}],
    })
    reqs = scene_label_requests(
        scene, content_extent=(0.0, 0.0, 100.0, 80.0),
        centers={"blob": (50.0, 40.0), "note": (50.0, 40.0)},
        slot_size=(60.0, 40.0),
        edge_anchors={"edge_blob.center_note.center": (50.0, 40.0)},
        params=dict(TIER_DEFAULT_PARAMS))
    ids = {r.ir_id for r in reqs}
    assert "scene_s_label" in ids                        # caption (line 0)
    assert "slot_s_blob_label" in ids                    # non-TEXT slot label
    assert "edge_blob.center_note.center_label" in ids   # scene-edge label
    assert not any(r.text == "ignored" for r in reqs)    # TEXT slot label skipped


def test_scene_caption_multiline_emits_one_request_per_line():
    # P5.2: a multi-line caption stacks one request per line; line 0 keeps the
    # canonical id so token assertions survive, later lines get a distinct id.
    from imageGen.layout.tier_layout import (
        TIER_DEFAULT_PARAMS, scene_label_requests,
    )
    scene = Scene.model_validate({"id": "s", "label": "line one\nline two",
                                  "slots": [{"id": "m", "kind": "text"}]})
    reqs = scene_label_requests(
        scene, content_extent=(0.0, 0.0, 100.0, 80.0),
        centers={"m": (50.0, 40.0)}, slot_size=(60.0, 40.0),
        edge_anchors={}, params=dict(TIER_DEFAULT_PARAMS))
    ids = [r.ir_id for r in reqs]
    assert ids == ["scene_s_label", "scene_s_label_l1"]
    assert reqs[1].anchor[1] > reqs[0].anchor[1]   # second line anchored lower


def test_rail_endpoint_transition_not_supported():
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row",
         "rails": [{"name": "midline", "axis": "y", "at": 0.5}],
         "scenes": [{"id": "a", "slots": [
             {"id": "m", "kind": "molecule", "style": {"smiles": "CCO"}}]}],
         "transitions": [{"from_ref": "rail:midline", "to_ref": "a@right"}]}]})
    with pytest.raises(NotImplementedError, match="rail.*endpoint"):
        layout_tiers(fig)


def test_scene_connect_aggregates_unresolved_anchor_refs():
    """P0a.5: two bad connect anchors surface in ONE error naming both (the
    schema validates the slot token at build time but not the anchor segment)."""
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "s", "slots": [{"id": "m", "kind": "text", "label": "X"}],
             "connect": [{"from_anchor": "m.ghost1", "to_anchor": "m.ghost2"}]}]}]})
    with pytest.raises(ValueError, match="unresolved connect") as exc:
        layout_tiers(fig)
    msg = str(exc.value)
    assert "ghost1" in msg and "ghost2" in msg, msg


def test_tier_transition_aggregates_unresolved_refs():
    """P0a.5: two bad transition endpoints surface in ONE error."""
    fig = Figure.model_validate({"archetype": "mechanism_cartoon", "tiers": [
        {"id": "row", "role": "scene_row", "scenes": [
            {"id": "a", "slots": [{"id": "m", "kind": "text", "label": "A"}]},
            {"id": "b", "slots": [{"id": "m", "kind": "text", "label": "B"}]}],
         "transitions": [{"from_ref": "a.m.ghost", "to_ref": "b.m.ghost"}]}]})
    with pytest.raises(ValueError, match="unresolved transition") as exc:
        layout_tiers(fig)
    msg = str(exc.value)
    assert "a.m.ghost" in msg and "b.m.ghost" in msg, msg


# ---------------------------------------------------------------------------
# P5.4 placement nits
# ---------------------------------------------------------------------------

def test_text_parent_slide_uses_text_width():
    # Nit-1: a child attached to a TEXT parent slides by the parent's measured
    # text width (threaded via slot_extents), not the full molecule slot width.
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import (
        TIER_DEFAULT_PARAMS, _layout_scene, _slot_bbox_size,
    )
    params = dict(TIER_DEFAULT_PARAMS)
    scene = Scene.model_validate({"id": "s", "slots": [
        {"id": "p", "kind": "text", "label": "His"},
        {"id": "c", "kind": "text", "label": "x"}],
        "attach": [{"child": "c", "parent": "p", "edge": "right"}]})
    reg = AnchorRegistry()
    _layout_scene(scene, (0.0, 0.0, 400.0, 200.0), reg, params)
    px, _py = reg.resolve("s.p.center")
    cx_c, _cy = reg.resolve("s.c.center")
    sw, _sh = params["tier_slot_size"]
    parent_w = _slot_bbox_size(scene.slots[0], (sw, _sh), params)[0]
    assert cx_c == pytest.approx(px + 0.5 * parent_w)
    assert cx_c < px + 0.5 * sw  # strictly less than the old molecule-width slide


def test_molecule_centering_uses_rounded_render_size():
    # Nit-2: a fractional slot size rounds for BOTH the render size and the
    # centring offset, so the rendered molecule box stays centred on the cell
    # centre (no int()-floor drift).
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import TIER_DEFAULT_PARAMS, _layout_scene
    params = {**TIER_DEFAULT_PARAMS, "tier_slot_size": (181.6, 141.4)}
    scene = Scene.model_validate({"id": "s", "slots": [
        {"id": "mol", "kind": "molecule", "style": {"smiles": "CCO"}}]})
    reg = AnchorRegistry()
    entries = _layout_scene(scene, (0.0, 0.0, 400.0, 200.0), reg, params)
    mol = next(e for e in entries if e.ir_id == "s.mol")
    rw = round(181.6)
    # the rendered box (top_left .. top_left + rw) is centred on the cell centre
    assert mol.position[0] + rw / 2.0 == pytest.approx(200.0)


def test_text_slot_center_anchor_is_midline():
    # Nit-3: a text slot's published `center` anchor is the visual midline, and
    # the rendered baseline drops 0.35 em below it.
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import TIER_DEFAULT_PARAMS, _layout_scene
    params = dict(TIER_DEFAULT_PARAMS)
    scene = Scene.model_validate({"id": "s", "slots": [
        {"id": "t", "kind": "text", "label": "His"}]})
    reg = AnchorRegistry()
    entries = _layout_scene(scene, (0.0, 0.0, 200.0, 100.0), reg, params)
    _cx, cy_anchor = reg.resolve("s.t.center")
    assert (_cx, cy_anchor) == (100.0, 50.0)            # midline at cell centre
    text_entry = next(e for e in entries if e.ir_id == "s.t")
    g = text_entry.primitive(*text_entry.args, **text_entry.kwargs)
    txt = next(el for el in g.elements if el.elementname == "text")
    fs = int(params["tier_text_font_size"])
    assert float(txt["y"]) == pytest.approx(cy_anchor + fs * 0.35)


def test_base_preset_drives_tier_text_colour_and_family():
    # P0b.1: the journal preset's label_font_color / label_font_family map onto
    # the tier text params so a tiered figure honours its journal (it previously
    # dropped style_dict entirely). cell_press is byte-identical to the engine
    # defaults; acs (Times serif, #000000) visibly differs. Font SIZE is NOT
    # remapped (the engine owns title/subtitle/caption sizes).
    from imageGen.layout.tier_layout import _preset_tier_params
    from imageGen.styles.loader import load_style

    mapped = _preset_tier_params(load_style("acs"))
    assert mapped == {"tier_text_color": "#000000",
                      "tier_font_family": "Times, Times New Roman, serif"}
    assert "tier_text_font_size" not in mapped     # size is engine-owned
    assert _preset_tier_params(None) == {}
    assert _preset_tier_params({}) == {}

    fig = _aspirin_hydrolysis_figure()

    def _cap_attrs(style_dict):
        entries = layout_tiers(fig, layout_params={"tier_canvas": (600, 300)},
                               style_dict=style_dict)
        e = next(x for x in entries if x.ir_id == "s_aspirin.cap")  # TEXT slot
        g = e.primitive(*e.args, **e.kwargs)
        t = next(el for el in g.elements if el.elementname == "text")
        return t["fill"], t["font-family"]

    # acs visibly differs; cell_press (the default preset) is byte-identical to
    # passing no preset at all — so the default render is unchanged.
    assert _cap_attrs(load_style("acs")) == (
        "#000000", "Times, Times New Roman, serif")
    assert _cap_attrs(load_style("cell_press")) == _cap_attrs(None)
    assert _cap_attrs(None) == ("#1A1A1A", "Helvetica, Arial, sans-serif")


def _two_text_scene(extra=None):
    spec = {"id": "s",
            "slots": [{"id": "a", "kind": "text", "label": "A"},
                      {"id": "b", "kind": "text", "label": "B"}],
            "connect": [{"from_anchor": "a.center", "to_anchor": "b.center",
                         "type": "dashed"}]}
    if extra:
        spec.update(extra)
    return Scene.model_validate(spec)


def _drawn_stroke(entry):
    g = entry.primitive(*entry.args, **entry.kwargs)
    el = next(e for e in g.elements if e.elementname in ("path", "line"))
    return el["stroke"]


def test_cascade_preset_does_not_recolour_semantic_edges():
    # P0b.2 correctness guard: the base preset's bare `stroke` (acs/nature) must
    # NOT bleed onto chassis edges — a dashed edge keeps its semantic red even
    # though acs sets a black bare stroke. (The literal {**preset, **edge.style}
    # fold the plan sketched would have blackened every semantic edge.)
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import (
        TIER_DEFAULT_PARAMS, _EDGE_DEFAULTS, _layout_scene)
    from imageGen.styles.loader import load_style

    acs = load_style("acs")
    assert acs.get("stroke") == "#1A1A1A"            # the colliding preset key
    reg = AnchorRegistry()
    entries = _layout_scene(_two_text_scene(), (0.0, 0.0, 300.0, 120.0), reg,
                            dict(TIER_DEFAULT_PARAMS), base_style=acs)
    edge = next(e for e in entries if e.ir_id.startswith("edge_"))
    assert _drawn_stroke(edge) == _EDGE_DEFAULTS["dashed"]["stroke"]  # #CC2222
    assert _drawn_stroke(edge) != acs["stroke"]                       # not black


def test_cascade_scene_style_overrides_content_and_edge():
    # P0b.2 content + structural channels: scene.style layers over the base for
    # text colour (content) and an explicit edge stroke (structural).
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import TIER_DEFAULT_PARAMS, _layout_scene

    scene = _two_text_scene({"style": {"label_font_color": "#FF0000",
                                       "stroke": "#00FF00"}})
    reg = AnchorRegistry()
    entries = _layout_scene(scene, (0.0, 0.0, 300.0, 120.0), reg,
                            dict(TIER_DEFAULT_PARAMS))
    a = next(e for e in entries if e.ir_id == "s.a")
    txt = next(el for el in a.primitive(*a.args, **a.kwargs).elements
               if el.elementname == "text")
    assert txt["fill"] == "#FF0000"                  # content channel
    edge = next(e for e in entries if e.ir_id.startswith("edge_"))
    assert _drawn_stroke(edge) == "#00FF00"          # structural channel


def test_cascade_preset_reaches_molecules():
    # P0b.2: tier molecules follow the journal preset (like the leaf path) —
    # acs recolours bonds; cell_press (the default) is byte-identical to no
    # preset, so the default tier render is unchanged.
    from imageGen.layout.anchors import AnchorRegistry
    from imageGen.layout.tier_layout import TIER_DEFAULT_PARAMS, _layout_scene
    from imageGen.styles.loader import load_style

    scene = Scene.model_validate({"id": "s", "slots": [
        {"id": "mol", "kind": "molecule", "style": {"smiles": ASPIRIN}}]})

    def _mol_svg(style_dict):
        reg = AnchorRegistry()
        entries = _layout_scene(scene, (0.0, 0.0, 300.0, 200.0), reg,
                                dict(TIER_DEFAULT_PARAMS), base_style=style_dict)
        e = next(x for x in entries if x.ir_id == "s.mol")
        return e.primitive(*e.args, **e.kwargs).tostring()

    assert _mol_svg(load_style("acs")) != _mol_svg(None)          # journal reaches bonds
    assert _mol_svg(load_style("cell_press")) == _mol_svg(None)   # default unchanged
