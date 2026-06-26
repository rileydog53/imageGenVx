# Build: direct-manipulation figure editor (drag widget → WYSIWYG overrides)

> Handoff for a fresh chat. This folder (`masterhand/`) is the home for the
> inline-editor effort: handoff/spec docs now, editor code as it lands.

## Goal
Add an iterative editing loop to imageGen: render a figure → show it in an
in-chat interactive widget with drag/rotate handles per part → user moves parts →
widget posts exact per-element deltas back to chat → apply them as a WYSIWYG
override layer and re-render. Repeat until it looks right.

## Decisions already locked (do not relitigate)
- **Edit surface:** in-chat interactive HTML widget via the `mcp__visualize`
  show_widget tool (call `read_me` with the "interactive" module first). The
  widget posts results back via its global `sendPrompt(text)`.
- **Edit semantics:** WYSIWYG pin — a drag becomes an ABSOLUTE override stamped
  over the solver's result; "where you put it is where it stays."
- **Test figure:** `showcase/corpus/05_imine_formation.json` (simple: 2 molecules
  per scene, one attach; s2 has an `amine→ald` curly attack to verify edges stay
  attached when a part moves).

## Repo state (as of this handoff)
- Branch `main`, clean, synced with origin (github `rileydog53/imageGenVx`).
  HEAD = `cdfa8a1` (D6 orientation). Suite **1205 green**. Venv `~/Desktop/.venv`.
- Render: `~/Desktop/.venv/bin/python -m imageGen render-spec <spec.json> -o out.{png,svg}`

## Architecture facts (verified — don't re-derive)
- Figures are IR-driven; positions are **computed by a solver**, not stored. So
  edits must come back as something the system applies, or a re-render wipes them.
- The rendered SVG tags every part with its IR id: molecules = `<scene>.<slot>`
  (e.g. `s2.ald`, `s2.amine`), labels = `label_slot_<scene>_<slot>_label` /
  `label_scene_<scene>_label`, edges = `edge_*` / `tedge_*`, plus badges/chrome.
  (60 id'd groups in 05.) These are the addressable handles.
- Layout entry: `imageGen/layout/tier_layout.py::layout_tiers(figure, layout_params,
  style_dict)` → `list[LayoutEntry]` (baked absolute coords, each has `.ir_id`);
  builds the `AnchorRegistry` internally.
- Compositor: `imageGen/render/compositor.py::render_figure` (line 176); tier path
  calls `layout_tiers` at line 505; `_write_svg` at 589 serializes.
- Per-scene layout: `tier_layout.py::_layout_scene` (~line 740+): computes
  `centers` (solved slot positions), renders each slot (publishing anchors), THEN
  resolves edges against those anchors. **Order matters for the override.**
- **D6 orientation already exists and should be REUSED for manual rotation:**
  `_mol_render.py::_orient_conformer` rotates a molecule's shared conformer about
  its centroid; `render_molecule_anchored` takes `orient_to` / `orient_direction`
  / `orient_reflect` / `orient_deadband_deg`. NOTE: it currently takes a
  DIRECTION (up/down/left/right) + target atom, NOT an arbitrary angle — for
  manual rotate you'll add an explicit-angle path (rotate the whole conformer by
  θ about the centroid) so atom anchors + curly edges stay consistent.

## Override-layer design (the WYSIWYG mechanism)
- New input: `overrides = { "<scene>.<slot>": {"dx": px, "dy": px, "angle_deg":
  deg} }`, threaded `render_figure` → `layout_tiers` (via `layout_params`) →
  `_layout_scene`.
- **CRITICAL GOTCHA:** apply overrides INSIDE `_layout_scene` by perturbing the
  solved `centers[slot]` (dx, dy) and feeding the angle into the orient call,
  BEFORE anchors are published and edges resolve. Do NOT translate the flat SVG
  groups as a post-pass — that detaches every edge/leader from its moved element.
  Perturbing the center lets the existing pipeline (anchors → edges → labels)
  follow for free.
- **Molecule rotate MUST go through the conformer** (orient primitive w/ explicit
  angle), not an SVG group rotate, or atom anchors desync from drawn atoms and
  curly arrows miss. Labels/glyphs can take a simple group rotate.
- Overrides are cumulative/absolute per element: each Apply round, merge new
  deltas into stored overrides (the widget reports deltas from the currently-shown
  pose).
- Coordinate frame: SVG px throughout; degrees for rotation. Mind RDKit y-up vs
  SVG y-down (handled in `_orient_conformer`; define + test the angle sign).

## Widget design (show_widget)
- Backdrop: inline the rendered SVG (it has the ids). Overlay drag/rotate handles
  per movable part. Movable granularity = IR PARTS (molecule / residue / label /
  glyph / scene caption), NOT individual atoms.
- On drag: move the matching SVG group by id live; track cumulative {dx, dy, angle}.
- "Apply" → `sendPrompt(JSON of {id: {dx, dy, angle_deg}})` → parse, merge into
  overrides, re-render, show the new widget. Loop closes in-chat.
- Constraints: show_widget scripts run after streaming; no external fetch (inline
  everything); SVG ~30–100KB inline is fine.

## Incremental build plan
0. Render 05; list movable element ids + their centers (parse layout entries / SVG).
1. **TRIAL LOOP, no override code yet:** build the widget, get deltas, hand-edit
   05's `Attach.offset` / orient in the JSON, re-render — validate the UX feels
   right.
2. Build the override layer: overrides map → `_layout_scene` perturbs center +
   orient angle before edges resolve. Add explicit-angle path to
   `_orient_conformer` / `render_molecule_anchored`. Tests: an override moves a
   part; its edges/leaders still attach; the leaf path (`target_bond_px=None`)
   stays byte-identical.
3. Wire widget Apply → `sendPrompt(deltas)` → apply overrides → re-render. Close
   the loop.
4. Persist overrides (sidecar JSON or in the spec) so manual tweaks survive a
   re-render; tests; short doc.

## Test figure (05 imine) structure — real element ids
- s1: `s1.ald` + `s1.amine` (amine attached `top` of ald, offset [0,-40]). No connect.
- s2: `s2.ald` + `s2.amine` (same attach); connect: `amine.lp_aminN → ald.carbonylC`
  (curly attack) + an internal ald curly. **This is the oriented/edge scene — the
  one to verify edges stay attached on a move.**
- s3: `s3.prod` only.
- Labels: `label_slot_s2_ald_label`, `label_scene_s2_label`, etc. Transitions:
  `tedge_s1@right_s2@left`, `tedge_s2@right_s3@left`.

## Read order
`D6_ORIENTATION_SCOPE.md` (orient infra to reuse) → `tier_layout._layout_scene`
(centers → render → edges order) → `compositor.render_figure` / `_write_svg` →
`_mol_render` orient API. Context: `V3_STATUS.md`, `PUBGRADE_ROADMAP.md`.

## First message to the new agent
Confirm the plan, then start at step 0 (render 05 + element manifest), then build
the step-1 trial widget.
