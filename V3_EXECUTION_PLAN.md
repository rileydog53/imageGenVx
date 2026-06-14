# V3 Execution Plan — Steps 5 → 7 (hardened)

**Status:** active forward plan. Supersedes the *sequencing* of
`V3_IR_NODESHAPES_PROPOSAL.md §3` Steps 5–7 and `V3_SCENE_CHASSIS_SCOPE.md §4`
for everything **not yet landed**. Steps 1–4 stay as recorded in `V3_STATUS.md`.

**Grounding:** this plan folds in a full architecture scan of the v2.6 tree
(17 agents — 8 deep readers, 8 independent skeptics, 1 synthesis — 2026-06-11).
Every file:line below was re-verified against the working tree before being
written here. Where the scan **overturned** an assumption, the correction is
called out inline (look for ⚠️) so no one re-chases a non-problem.

Read order for a fresh agent: `V3_STATUS.md` → this doc → the detail docs it
references. The IR schema is load-bearing (`CONTRIBUTING.md`): **no `schema.py`
edit lands without explicit sign-off, and every test-matched error-string
substring is preserved.**

---

## 1. The one architectural idea this plan is built on

The V3 chassis did **not** create a 5-archetype × 3-container dispatch matrix.
The real shape is a **3-way container split** (tiers / panels / leaf) whose leaf
arm is a **2-engine split** (pathway-family vs reaction) wearing a 5-archetype
coat. The actual debt is that the same `tiers → panels → archetype` precedence is
**re-tested in four unsynchronised sites**, kept in sync only by golden tests:

| Site | File:line | What it re-decides |
|---|---|---|
| `_dispatch_layout` | `render/compositor.py:356` | container → engine |
| `_canvas_size` | `render/compositor.py:528` | container → canvas formula |
| render label branch | `render/compositor.py:~192` | container → label strategy |
| `ARCHETYPE_TO_LAYOUT` + its twin if/elif | `layout/panel_layout.py:82` **and** `:210` | archetype → engine (encoded **twice** in one file) |

**Every V3 pressure points the same way:** Steps 5/6/7 *deepen the tier engine's
internals* — they do **not** add container modes or archetypes (the `Archetype`
enum is frozen at 5, `schema.py:63`). So the branch explosion the original plan
feared only materialises if the compositor keeps re-testing the
container/archetype triple at every concern.

**The move:** make container mode the single explicit dispatch axis, decided
**once**, via a small `LoweringPlan` record `(engine, canvas_fn, label_strategy,
style_base)`. Then Steps 5/6/7 land as *tier-engine-internal work + thin adapters
that plug into existing seams* — N-scene expansion produces more scopes/requests,
never more branches. **Net goal: the dispatch / label / style branch count stays
roughly flat while the feature set triples.**

The mutual-exclusion guard at `schema.py:625` (`sum([leaf, panels, tiers]) > 1`)
is what makes a container-mode-first `if/elif` *provably* unable to mis-route.

---

## 2. Corrections the scan forced (do not re-chase these)

| ⚠️ Old framing | Verified reality |
|---|---|
| label→glyph inference lives in `entity_adapters.py` | It's in `layout/_geom.py:202` — `_INFERENCE_RULES`, `infer_primitive` (`:239`), `resolve_entity_primitive` (`:257`). The adapter file is **not** the god-module. |
| a bad `TierEdge` ref raises `KeyError` at render | `AnchorRegistry.resolve` raises a **guarded `ValueError`** (`anchors.py:132`/`:137`). The real gap is *loud-but-**late*** (layout time, not IR-build). |
| the multi-step downgrade **mutates** `ir.archetype` | `compositor.py:182` is a `model_copy(update=…)` rebind — the caller's IR is untouched (and the copy skips re-validation). The real gap is that the downgrade is **silent** when `smiles_map` is falsy. |
| greedy label placement is O(n²) and will melt under V3 | Panels already collision-isolate per cell; tiers skip `place_labels` entirely. The risk is the **tier seam doing zero overlap avoidance**, not algorithmic blow-up. |
| `style_dict` is dropped at the compositor for tiers | It **is** passed (`compositor.py:386 → layout_tiers(style_dict=…)`) but **never applied** inside `tier_layout` — per-node `slot.style`/`tier.style`/`edge.style` are read standalone (`:355`,`:578`,`:416`) and never layered over the base preset. Tiered figures silently ignore their journal preset. |
| `model_rebuild()` block is redundant/fragile | **Load-bearing.** `from __future__ import annotations` makes the forward refs require it. Leave it. |
| the validators waste real work on tiered figures | The "waste" is free empty-list iteration. The only real debt is the 71-line undifferentiated `_validate_structure` (`schema.py:622`). |

---

## 3. Sequencing rule

> **Anything a step will build *on a seam* must precede that step. Anything that
> merely *coexists* can follow.**

So the cheap unifications are scheduled as **Phase 0 pre-work gates** in front of
each numbered step, not as a separate cleanup epic. Concretely:

```
Phase 0a  (pre-Step-5)   →  Step 5  (scene solver)
Phase 0b  (pre-Step-6)   →  Step 6  (step expansion)
Phase 0c  (pre-Step-7)   →  Step 7  (primitive refresh)
Phase H   (independent correctness — any time, no ordering dep)
```

---

## 4. Action plan

Each item is a small, independently shippable increment: **change → test →
done**. Check them off in order within a phase. `file:line` is the change site
(symbol names are the durable locator; line numbers were accurate 2026-06-11).
Keep the suite green at every check (currently **1025**).

### Phase 0a — pre-Step-5 seams (land before any solver work)

- [x] **P0a.1 — Promote the archetype→engine table to one source.** ✅ 2026-06-12.
  New leaf `layout/_archetype_plan.py` holds `_ARCHETYPE_PLAN: dict[Archetype,
  ArchetypePlan(engine, canvas_fn, label_fn, canvas_key, inject_canvas)]`.
  `panel_layout.ARCHETYPE_TO_LAYOUT` derives from it; `_override_subengine_canvas`
  reads it (duplicate if/elif deleted); `_dispatch_layout` / `_canvas_size` /
  `_label_requests_fn` read it (no more `_PATHWAY_COMPATIBLE_ARCHETYPES` membership
  tests in the compositor). Pure refactor, no golden diffs, +6 structural tests.
  Lift `ARCHETYPE_TO_LAYOUT` (`panel_layout.py:82`) into a single
  `_ARCHETYPE_PLAN: dict[Archetype, tuple[engine, canvas_fn, label_fn]]`. Make
  `_dispatch_layout` (`compositor.py:356`), `_canvas_size` (`:528`) and
  `_label_requests_fn` (`:510`) read it; **delete the duplicate `if/elif` at
  `panel_layout.py:210`** so REACTION_SCHEME is encoded once. Pure refactor.
  *Done when:* the 4 sites share one table; golden suite unchanged.

- [x] **P0a.2 — Introduce `LoweringPlan` + `_lowering_plan(ir)`.** ✅ 2026-06-12.
  `LabelStrategy` enum + `LoweringPlan(engine, canvas_fn, label_strategy,
  style_base, archetype_plan)` resolved once at the top of `render_figure`
  (container-mode-first). `render_figure` reads `plan.style_base` / `plan.canvas_fn`
  / `plan.label_strategy`; the PH.1 coercion stays a pre-plan normalise; the
  `_dispatch_layout` / `_canvas_size` signatures are untouched (pinned by tests).
  Behaviour identical (canvas_fn == _canvas_size verified for every mode).
  Add a small record `(engine, canvas_fn, label_strategy, style_base)` resolved
  once at the top of `render_figure`. Container-mode-first (`tiers` → `elif
  panels` → `else leaf`, archetype-second via P0a.1's table). Route
  `_dispatch_layout` and `_canvas_size` through the resolved plan instead of
  re-branching. The multi-step coercion (`compositor.py:172`) stays a *pre*-plan
  normalise — it sets archetype to PATHWAY before the plan resolves, so the
  resolver needs no second touch.
  *Done when:* dispatch + canvas read one plan; behaviour identical; tests green.

- [x] **P0a.3 — Extract `LabelCoordinator.place()` (minimum-viable, byte-identical).**
  ✅ 2026-06-12 (C2). New `render/label_coordinator.py` holds `LabelScope`
  (NamedTuple: entries-as-subset-AND-occupancy-seed, requests, canvas,
  style_dict, panel_chain, position, emit_leaders) + `LabelCoordinator.place()`
  dispatching container-mode-first (`if ir.tiers: return entries` inert seam;
  `ir.panels` → `_run_panels`; else `_run_leaf` via a shared `_place_scope`).
  Moved `_label_requests_fn` (re-exported from `compositor` so the
  `test_archetype_plan` import — added by C1, post-blueprint — still resolves)
  and `_panel_cell_bounds`; deleted `_place_labels_per_panel`. `render_figure`'s
  label step is now one `LabelCoordinator.place(...)` call under `if labels:`.
  One-directional import (coordinator imports nothing from compositor → no
  cycle). Zero golden diffs; +1 identity test (`place(tiers) is entries`).
  Move the inlined label `if/else` (`compositor.py:~192`) and
  `_place_labels_per_panel` (`:443`) into a `LabelCoordinator` keyed on a
  first-class `LabelScope = (entry-subset, canvas-bound, occupancy-seed)`.
  Leaf = one scope (current else-branch verbatim). Panels = one scope per panel
  (lift `_place_labels_per_panel`, reuse `_panel_cell_bounds`). **Tier captions
  stay byte-identical** (still emitted by `_caption_group`, `tier_layout.py:493`)
  — this cut does *not* change tier behaviour, it only builds the seam.
  *Done when:* 1025 tests still green; render output unchanged; the three label
  paths now live behind one `place()` dispatch.

- [x] **P0a.4 — Add `AnchorRegistry.copy()` (deep) + a `layer()` overlay.** ✅
  2026-06-12. `copy()` deep-copies `_anchors`+`_rails`; `layer(*, commit=True)` is
  a context manager that buffers `publish*` into an overlay and commits-or-drops
  on exit (drops on exception or `commit=False`); `resolve*`/`has`/`rail` read
  overlay-then-base. Not re-entrant. No-layer path byte-identical (5 unit tests:
  rollback, commit-merge, exception-drops, non-reentrant, copy-independence).
  Today `publish` is mutation-only (`anchors.py:94`, `self._anchors[k]=…`) with
  no versioning, so a re-running solver clobbers earlier writes
  non-deterministically. Add `copy()` (deep-copy both `_anchors` + `_rails`) and
  a `layer()` context that **buffers** `publish*` and commits-or-drops on exit;
  `resolve*` reads overlay-then-base. `layout_tiers` keeps building one base
  registry; the solver opts into a layer.
  *Done when:* a unit test proves publish-in-layer + rollback leaves base intact,
  and commit merges.

- [x] **P0a.5 — Aggregate anchor-ref validation in `layout_tiers`.** ✅ 2026-06-12.
  `AnchorRegistry.validate_refs(refs) -> list[str]` (unresolved subset, no raise);
  `tier_layout` aggregate-validates every intra-scene `connect` endpoint (before
  the `resolve_edge` loop in `_layout_scene`) and every non-rail `transition`
  endpoint (before the transitions loop), raising one `ValueError` that names the
  owning edge `ir_id` + each bad ref. `rail:` endpoints stay screened by the
  existing `NotImplementedError` guard. 2 tests (connect + transition aggregation).
  Add `AnchorRegistry.validate_refs(refs) -> list[str]` and call it after all
  `publish*` but **before** the first `resolve_edge` (`tier_layout.py`, in the
  tier loop ~`:640`). Aggregate every unresolved `from_ref`/`to_ref`/
  `from_anchor`/`to_anchor` into **one** error naming the owning edge `ir_id` —
  instead of dying on the first typo at `resolve` (`anchors.py:132`).
  *Done when:* a figure with two bad refs reports both in one error.

- [x] **P0a.6 — Validate the static slot token of anchor refs at IR-build time.**
  ✅ 2026-06-12 (C4, sign-off given). The **Scene** side already existed
  (`Scene._validate_scene` checks every `connect` ref's slot token) and `Tier`
  already validated the **scene** token of `transition` refs — so the only gap
  was the **slot** token of a `"scene.slot.anchor"` `TierEdge` ref. `Tier._validate_tier`
  now builds a static per-scene slot map (scenes + overlays; step_sequence scenes
  excluded — their slots arrive via deltas at expansion, so they stay a
  layout-time concern) and rejects a `scene.slot.anchor` transition whose slot
  token is unknown (`@`-frame refs have no slot token; the dynamic atom segment
  is still left for P0a.5 at layout). Purely **additive** — zero pre-existing
  lines changed, every test-matched error substring byte-preserved; new string
  "transition references unknown slot". +2 tests (reject nonexistent slot at
  build; known-slot + dynamic-anchor still builds). Adversarially verified
  (4-lens workflow → safe, 0 defects). 1060 green.
  *Done when:* a `TierEdge` naming a nonexistent slot fails at `Figure(...)`
  construction, not at render.

### Step 5 — Scene solver (plugs into the P0a seams)

Builds on P0a.3 (label seam), P0a.4 (registry rollback), P0a.5 (ref validation).
**Do not** grow a second placement/relaxation engine inside `tier_layout` — reuse
`place_labels`. (⚠️ verified: `tier_layout` imports nothing from
`label_placement`; that's the seam P0a.3 exists to close.)

- [x] **P5.1 — Topological attach/offset pass.** ✅ 2026-06-12 (C5).
  `_solve_slot_centers` rewritten: dependency-ordered (topological) attach solve
  with the child slide now using the *parent's* extent (new keyword-only
  `slot_extents`, uniform fallback → existing tests byte-identical), then a new
  `_deoverlap_coincident` pass that separates slots the solve landed on the SAME
  point (the His513-vs-ligand tangle) — *coincident* centres only, so the
  historic half-step `right` chain (distinct centres, overlapping boxes) and
  every single-slot scene are untouched (zero golden diffs). `_SLOT_EDGE_OFFSETS`
  gains `cavity_top/cavity_bottom/cavity_center` (quarter-extent inside the
  parent); `anchor`/`custom` still raise `NotImplementedError` (Step 7). Each
  scene's solve+publish now runs inside `registry.layer()` so a mid-scene
  failure rolls back partial publishes; a clean scene commits for the cross-cell
  transitions. `test_unsupported_attach_edge_raises` updated (`cavity_top` →
  `custom`); +4 tests (cavity resolves, MF-3 disjoint boxes, determinism,
  slot_extents widen-slide). 1050 green.
  *Done when:* the His513-vs-ligand tangle (**MF-3**, `V3_FEATURES.md`) cannot
  occur — a test with two center-attached slots produces non-overlapping boxes.

- [x] **P5.2 — Scene-local label placement via the coordinator.** ✅ 2026-06-12
  (C6). New `tier_layout.scene_label_requests` emits `LabelRequest`s for the
  scene caption (`scene.label`, one per `\n` line, ids preserved) plus the
  previously-unrendered non-TEXT `Slot.label` and `SceneEdge.label`. `_layout_scene`
  now places them through the shared `place_labels` pass (replacing the fixed
  `_caption_group` call — the fn stays for its direct test), with the caption
  gap carried over as the anchor gap. ⚠️ **Implementation note (deviates from
  the slice sketch):** placement is **engine-side** (wiring point A — where the
  per-scene cell/extent/boxes live), so the `LabelCoordinator` tier branch stays
  the inert `return entries` pass-through (its `BAKED` strategy = "engine places
  its own"); the "canvas = cell rect" clip in the sketch is geometrically wrong
  for the engine's *absolute* coords (cells have non-zero origins), so canvas is
  left unbounded and FR3 grows the frame as the fixed caption relied on. ids
  preserved → `label_scene_<id>_label` keeps matching token assertions; no tier
  pixel-goldens exist so nothing to regen. 1055 green.
  *Done when:* tier captions route through `place_labels`; scene-edge / slot
  labels render; no fixed-coordinate caption path remains.

- [x] **P5.3 — Seed the figure-level annotation pass with occupied bboxes.** ✅
  2026-06-12 (C6). `place_labels` gains a public `label_entry_bbox(entry)`;
  `render_figure` (tier path only) collects the placed scene-label bboxes and
  passes them as `occupied=` to `annotation_entries`. The annotation pass gains
  `occupied` + a `position_override`: LABEL/CAPTION annotations are nudged off
  the occupied boxes (and each other) via the reused `place_with_fallback`
  ladder; SCALE_BAR stays fixed. `occupied` None/empty (every non-tier path, and
  tier figures with no scene labels) → annotations render verbatim
  (byte-identical). +1 test.
  *Done when:* a regression figure that previously overlapped a scene label with
  a global annotation now separates them.

- [x] **P5.4 — Close the Step-4 deferred placement nits** ✅ 2026-06-12 (C7).
  **Nit-1** (non-molecule attach-parent extent): `_layout_scene` now threads
  per-slot extents (`_slot_bbox_size`, reusing `_slot_bbox`) into the solver, so
  a child slides by the *parent's* real box and de-overlaps by the *child's* —
  a TEXT parent no longer pushes a child a full molecule-width away. **Nit-2**
  (sub-pixel molecule centering): the molecule renders at `int(round(sw/sh))`
  and centres on that SAME rounded size (default `(180,140)` rounds to itself →
  no golden change; fractional sizes no longer drift by the `int()` floor).
  **Nit-3** (text `center` = midline not baseline): a TEXT slot's published
  `center` anchor is the visual midline and the rendered baseline drops 0.35 em
  (mirrors the `_badge_group` fix), so an edge to a text slot's centre meets its
  middle. +3 regression tests. 1058 green.
  *Done when:* each nit has a regression test.

### Phase 0b — pre-Step-6 seams (land before step expansion)

- [x] **P0b.1 — Apply `style_dict` inside `tier_layout`.** ✅ 2026-06-13.
  The base preset reached `layout_tiers` but was dropped ("unused in the slice").
  ⚠️ **Deviation (the literal sketch was a no-op-or-regression — verified by a
  cascade-design workflow):** `{**style_dict, **node.style}` is (a) a *no-op* for
  molecule slots (`slot.style` is mined only for `smiles`/`anchor_names` and never
  forwarded to the renderer) and band chrome (the preset carries no `band_*`
  keys), and (b) a *regression* for edges (the preset's bare `stroke`/`stroke_width`
  — set by acs/nature — would clobber the per-`SceneEdgeType` semantic colours,
  blackening every hbond). The real preset lever for tiers is the **params** dict.
  So P0b.1 projects the preset's text keys onto the tier params
  (`label_font_color → tier_text_color`, `label_font_family → tier_font_family`;
  `_preset_tier_params`), layered below explicit `layout_params`. Font **size** is
  deliberately not remapped (the engine owns title/subtitle/caption sizes; a single
  preset size flips the geometric legibility check). Hoisted one shared
  `merge_style()` (shallow, later-wins, None-safe) into `styles/loader` and reused
  it in `_resolve_preset`/`load_style` (pure refactor). cell_press maps
  byte-identically; acs (Times serif, `#000000`) visibly differs. No tier pixel
  golden exists; +1 test. 1061 green.

- [x] **P0b.2 — One additive style cascade for the chassis.** ✅ 2026-06-13.
  `merge_style` is the single merge implementation (P0b.1). ⚠️ **Deviation:** the
  cascade is **two channels**, because the base preset's vocabulary collides with
  chassis structure: **content channel** (molecules, text/captions) =
  `preset → tier.style → scene.style → slot.style`, with tier molecules now
  forwarding the merged style to `render_molecule_anchored` exactly as the leaf
  path does; **structural channel** (connect edges, tier transitions) =
  `tier.style → scene.style → edge.style` with **NO preset base** (so bare preset
  `stroke` can't recolour semantic edges). `scene.style` (was dead) is the scene
  layer; `Step.style` is the outermost layer and activates in Step 6 by folding
  into the expanded scene's `style` — no fourth path. Verified byte-identical
  under cell_press for both molecules and text; +4 tests incl. the edge-recolour
  regression guard. 1064 green.

- [x] **P0b.3 — Make `_build_panel_styles` dense.** ✅ 2026-06-13. Every
  `panel.id` is now keyed: panels matching the top-level preset reuse the SAME
  resolved base style object (preserving kwarg overrides + identity), differing
  panels get their own `load_style`. Downstream `.get(panel.id)` is uniform and
  matches the dense `smiles_map` broadcast. Behaviour-preserving (every consumer
  already fell back via `.get(panel.id, base_style)`; nested-grid recursion lands
  on the same value); the 2 sparse-asserting tests updated to the dense contract.
  1078 green.

- [x] **P0b.4 — Guardrail: no preset-NAME axis below `Figure`.** ✅ 2026-06-13.
  Chassis overrides are additive freeform `style` dicts only — never a second
  axis of preset *names*. `Panel.content.style_preset` stays the lone exception.
  Recorded in the §5 "Do not" list (now also naming the exception + the
  content/structural channel split from P0b.2). Step 6 honours it: `Step.style`
  is a freeform `dict`, folded into the expanded scene's `style` as the cascade's
  outermost layer — there is no per-step/per-scene preset *name* anywhere.

### Step 6 — Step expansion (slot-granular) — ✅ LANDED 2026-06-13

Built on P0b's single style-keying convention and the additive cascade.
`expand_step_sequence(seq)` (pure, in `tier_layout.py`) produces one validated
`Scene` per step; the SCENE_ROW loop and the canvas sizer both call it (via
`_tier_scene_list` / `_tier_scene_count`) so layout and viewport agree.

- [x] **P6.1 — Expand `StepSequence` → N concrete `Scene`s.** ✅ 2026-06-13.
  Replaced the `NotImplementedError` (`tier_layout.py:1007`, was the stale
  `:618`) with the expansion pass. Scene.id == step.id (so reserved transition
  tokens resolve and label/badge ir_ids keep `scene_<step.id>_*`); cumulative by
  default. ⚠️ **Deviation:** expansion runs at **layout time** (a pure pre-pass
  in the engine), not in `ir/builder.py` — verified that `semantic_check` /
  convention / glossary walk only `figure.panels`, never `figure.tiers`, so
  "builder-layer so verification sees real scenes" was moot; layout-time
  expansion also covers every Figure-construction path. Each expanded scene is a
  real validated `Scene` (re-runs `_validate_scene` → dangling refs fail loud).
  *Note:* extending `semantic_check` to walk tiers→scenes is a separable
  cross-cutting follow-up (affects all tier figures, not just expanded ones).

- [x] **P6.2 — Slot-granular deltas only** (`add`/`remove`/`replace`/`add_label`).
  ✅ 2026-06-13. REMOVE drops dependent attach/connect; REPLACE force-keeps
  `id=target`; any other op (GENERIC) raises. A target that resolves to a nested
  GROUP-slot id or a slot a prior cumulative step removed (both build-valid per
  the looser validator `known` set) **fails loud** at expansion rather than
  silently no-op'ing — hardened after the adversarial review.

- [x] **P6.3 — `ADD_LABEL` routes through the label coordinator.** ✅ 2026-06-13.
  An added label lands as a `Slot.label` on the expanded scene, so it flows
  through `scene_label_requests` → `place_labels` (the P5.2 pass) — no fourth
  placement path. `add_label` without `value['label']` raises (never silently
  erases an existing label).

- [x] **P6.4 — Per-step style via the additive cascade** (P0b.2). ✅ 2026-06-13.
  `step.style` folds into the expanded scene's `style` (outermost layer), so it
  rides the content cascade with zero new branches and no per-step preset name.

### Phase 0c — pre-Step-7 seams (land before primitive refresh)

- [x] **P0c.1 — Introduce `PrimitiveSpec` to collapse the 3-file table coupling.**
  ✅ 2026-06-13. New leaf `primitives/primitive_specs.py` holds one
  `PrimitiveSpec(name, render, bbox, shape|SKIP, icon_asset?)` per primitive in a
  single `PRIMITIVE_SPECS` list; `PRIMITIVE_REGISTRY`, `PRIMITIVE_TO_BBOX`,
  `PRIMITIVE_SHAPE`, `SKIP_SHAPE_PRIMITIVES` and `ICON_ASSETS` are all *derived*
  from it. `_geom` re-exports `PRIMITIVE_REGISTRY`/`PRIMITIVE_TO_BBOX` (its
  literal registry + `_PRIMITIVE_BBOX_OVERRIDE` + the inherit-via-`ENTITY_TO_PRIMITIVE`
  derivation deleted); `convention_check` aliases `PRIMITIVE_SHAPE`/`SKIP_SHAPE_PRIMITIVES`
  → its private `_PRIMITIVE_SHAPE`/`_SKIP_SHAPE_PRIMITIVES` (the two hand-kept
  literals deleted, dropping two dead `glyphs.flask`/`glyphs.centrifuge` shape
  entries that resolution never reached); `credits` reads `ICON_ASSETS` from the
  spec module (`entity_adapters.ICON_ASSETS` removed). The module is the lowest
  layer (imports only `primitives` sub-modules → no cycle); the per-spec bbox is
  explicit but byte-equal to what the old inheritance resolved to. Import-time
  uniqueness guard on name+callable. The coverage guard is now structural (new
  `test_primitive_specs.py` iterates the spec list); existing
  `test_primitive_shape_covers_registry` / `test_default_dispatch_shapes_covered`
  pass unchanged. +7 tests.
  *Done when:* registering a new spec is a single-site add; the coverage test
  becomes structural (iterates the spec list).

- [x] **P0c.2 — `list_style_keys()` discovery surface.** ✅ 2026-06-13.
  `styles/loader.list_style_keys(*, include_layout_params=False)` returns the
  sorted 192-key `KNOWN_STYLE_KEYS` vocabulary (the same set `load_preset_full`
  validates `overrides` against — authoritative, not a hand-kept list), with the
  13 aesthetic `KNOWN_LAYOUT_PARAMS` appended on request. New `python -m imageGen
  styles [--keys] [--layout-params] [--presets]` subcommand (sniffed in slot 0
  like `render-spec`; defaults to `--keys`) prints the inventory one item per
  line for clean grep/pipe. +6 tests.
  *Done when:* the full key inventory is printable from the CLI.

- [x] **P0c.3 — Fix the silent REACTION_SCHEME downgrade** (also in Phase H).
  ✅ 2026-06-13. The silent path was already closed by **PH.1** (fail-loud by
  default; the `pathway_fallback=True` opt-in always warns, ungated). This item
  *records the original archetype*: the compositor-local `LoweringPlan` gains a
  `coerced_from: Archetype | None` field, captured from `ir.archetype` **before**
  the PH.1 `model_copy(archetype=PATHWAY)` rebind erases it and threaded through
  `_lowering_plan`. It is `None` for every un-coerced figure and `REACTION_SCHEME`
  only on the coerced fallback, so a Step-7 primitive can distinguish a genuine
  PATHWAY from a coerced REACTION_SCHEME (whose chemistry layer was dropped) and
  refuse to silently no-op. No `schema.py` touch — the record lives on the plan
  (its documented home for "Step 6/7 adapters"), not the IR. +2 tests.
  *Done when:* a non-linear REACTION_SCHEME never silently degrades; PH.1 landed.

### Step 7 — Primitive refresh (aspirin/COX-1 acceptance) — the home stretch

Builds on P0c. Acceptance = the mechanism-figure fidelity criteria
(`V3_FEATURES.md` MF-1/2/3); Aspirin/COX-1 reproduction
(`references/aspirin_COX1_figure_spec.md`, proof `showcase/aspirin_cox1_anchored_proof.png`)
is **this** workstream's acceptance test, not a chassis milestone. This is the
**last** numbered step — when P7.4 lands, the V3 chassis is feature-complete.

> **Foundation already in place — verify, do NOT rebuild (scan 2026-06-13).**
> Step 7 is *targeted primitive gaps + the acceptance render*, not a from-scratch
> build. Confirmed present in the tree:
> - **Atom anchoring (MF-2 prerequisite):** `render_molecule_anchored`
>   (`primitives/_mol_render.py:316`) publishes per-atom anchors — `atom{idx}`,
>   `a{map}` (from `[O:1]` atom-maps), and human aliases via `anchor_names`. Molecule
>   **slots** already render through it and `registry.publish` their anchors
>   (`tier_layout.py:572`), so `AnchorRegistry.resolve("scene.slot.atom")` works **today**.
> - **Edge drawing:** `SceneEdgeType` already has `CURLY` / `HBOND` / `DASHED` /
>   `DEPARTS` / `TRANSITION` / `INHIBITS` (`ir/_enums.py:155`); `_edge_group`
>   (`tier_layout.py:273`) already draws a **curved arrow** between two resolved
>   anchors (quadratic Bézier + arrowhead, `bow` controllable). A point-to-point
>   curly arrow on real atoms is therefore *already expressible* — the gap is
>   richness (bond/lone-pair origins, handedness), not existence.
> - **MF-3 (placement):** the Step-5 scene solver + `_deoverlap_coincident`
>   (`tier_layout.py:330`) already prevents the His513-vs-ligand tangle.
> - **Single-site primitive registration (P0c.1):** every new glyph below is one
>   `PrimitiveSpec` append in `primitives/primitive_specs.py`.

> **Carry-over seam from P0c.3 — consume `LoweringPlan.coerced_from`.** P0c.3
> *records* the pre-coercion archetype on the plan but left it without a consumer.
> Step 7's chemistry primitives are REACTION-only, so a figure coerced
> REACTION_SCHEME→PATHWAY (`pathway_fallback`) has silently dropped its chemistry
> layer. Close it in **P7.1** (where chemistry dispatch is touched): read
> `plan.coerced_from` (it is `REACTION_SCHEME` exactly on the coerced path) and
> **fail loud / warn** rather than no-op'ing; a test asserts a coerced figure
> carrying a chemistry primitive does not silently render nothing.

**At a glance** (size = complexity × length; deps are hard ordering constraints):

| Item | What | Size | Depends on | Parallelisable? |
|---|---|---|---|---|
| **P7.0** | Extend `semantic_check` + `convention_check` to walk tiers→scenes→slots | **M** | — | yes (independent) |
| **P7.1** | Residue/heteroatom convention as real fragments (MF-1) + consume `coerced_from` | **M** | — | yes |
| **P7.2** | Arrow-pushing curly primitive: bond/lone-pair anchors + curvature (MF-2) | **M–L** | keystone (done) | yes |
| **P7.3** | Remaining north-star glyphs: blob, TS partial bond, tablet, PG cluster, ⊣ T-bar fix | **M** | — | yes (3 sub-glyphs independent) |
| **P7.4** | Aspirin/COX-1 acceptance render + MF-1∧2∧3 proof | **L** | **P7.0–P7.3 all** | no (integration) |

P7.0–P7.3 are mutually independent and can land in any order (or concurrently);
P7.4 is the integration gate that depends on all four. Recommended sequence:
**P7.0 → P7.1 → P7.2 → P7.3 → P7.4** (verification reach first so every later
primitive is acceptance-checkable as it lands).

- [x] **P7.0 — Extend verification reach to tier figures.** ✅ 2026-06-13.
  Both verifiers walked only `figure.entities` + `figure.panels`, so a **tier**
  figure (which the acceptance render is) was silently un-audited — a vacuous
  pass. Closed via one shared lockstep helper `tier_rendered_scenes(tier)`
  (`tier_layout.py`, reuses `_tier_scene_list` so it *cannot* drift from the
  engine's own scene list: SCENE_ROW scenes + expanded `step_sequence` steps +
  `overlays`; every other role draws none). **`semantic_check`** emits an expected
  id `"<scene.id>.<slot.id>"` (kind `"slot"`) per top-level non-GROUP slot of each
  rendered scene — over-listing leaf kinds is safe because an unsupported kind
  raises at layout and never reaches a rendered SVG; GROUP is skipped (no render /
  id scheme yet). **`convention_check`** gains `_SLOT_KIND_SHAPE` (BLOB→`<path>`,
  BOX→`<rect>` as forward seams for P7.3 primitives; molecule/residue/glyph/text/
  group/generic → skip, mirroring `_SKIP_SHAPE_PRIMITIVES`) + `_check_slot_shapes`
  (kind `"slot_shape"`). No `schema.py` touch; every existing error substring
  preserved (purely additive). +12 tests incl. a both-directions drift guard
  (engine-tagged slot ids == helper's slot-id set); CLI `--verify` now reports a
  genuine `semantic=OK convention=OK` on a tier render. 1108 green.
  *Done when:* a tier figure with a missing/mis-shaped slot fails the verifier; the
  aspirin IR is auditable end-to-end.

- [x] **P7.1 — Residue & heteroatom convention, one everywhere (MF-1).** ✅
  2026-06-13. Heteroatoms already render as coloured **letters** through the RDKit
  path (the "bare red dot" only ever lived in the hand-composed northstar, never
  in the IR-driven renderer), so MF-1 reduced to *routing residues through that
  same path*. `render_molecule_anchored` gains an opt-in `open_valence`/
  `attach_anchor` (default off → every existing depiction byte-identical): a dummy
  `*` atom has its label blanked so the bond to it renders as a **dangling stub**
  (open valence) instead of a `*` glyph, and its draw-coord is published as the
  attachment anchor. New `render_residue_anchored(residue, …)` wraps it + a
  `_RESIDUE_SMILES` convenience map (ser/his/tyr/cys/lys + COX-1 `ser530`/`his513`
  aliases; reactive atom mapped `:1` → `a1`); a capped fragment (no `*`) **fails
  loud**. `_layout_scene` renders RESIDUE slots through the shared molecule path
  (`style['residue']` or raw `smiles`), so the reactive O resolves as
  `scene.slot.a1` and the backbone as `scene.slot.attach` for H-bond/curly edges.
  **`coerced_from` consumed:** the PH.1 drop-warning now fires off the *resolved
  plan* (`plan.coerced_from`) and **names the dropped entities** (preserving the
  pinned "SMILES structures will not be drawn" substring) — the seam is no longer
  dead, and a coerced figure can't silently render its chemistry as nothing. No
  `PrimitiveSpec` added: residues are a slot-level axis, not the entity→glyph
  inference registry (the doc's "where a reusable glyph emerges" — it didn't, as
  an entity primitive). +10 tests; visual proof rendered (aspirin + Ser530 + curly
  edge on real atom anchors). 1118 green.
  > **Carry-forward:** the CURLY arrow still crosses the molecule (crude symmetric
  > bow) — **P7.2** owns handedness/arc. A 3-atom residue scaled to the full slot
  > box dwarfs a larger ligand's atoms — **P7.4** composition tunes per-slot scale
  > (or a future `fixedBondLength`), out of MF-1 scope.
  *Done when:* no bare-dot oxygen appears anywhere in the acceptance figure; Ser530
  and His513 are real fragments with named attachment anchors; a coerced-archetype
  figure with a chemistry primitive fails loud / warns instead of rendering nothing.

- [x] **P7.2 — Arrow-pushing curly primitive (MF-2 / V3-C4).** ✅ 2026-06-13.
  **(a) Anchors:** `render_molecule_anchored` now publishes (via
  `_bond_and_lone_pair_anchors`) a **bond-midpoint** anchor for every bond —
  `bond{lo}_{hi}` by atom index, plus `bond_a{m1}_a{m2}` / `bond_{name1}_{name2}`
  aliases in BOTH orderings for mapped/named endpoints — and a **lone-pair**
  anchor per N/O/S (`lp{idx}` / `lp_a{map}` / `lp_{name}`), offset outward along
  the direction away from the atom's neighbours. So a curly arrow can originate at
  a C=O π bond or an O lone pair, not only an atom centre; all shift with `center`.
  **(b) Rendering:** `_edge_group`'s curved branch gains `curl` (handedness — the
  control point's perpendicular side) and `arc='s'` (an S-shaped **cubic**, two
  controls bowing to opposite sides = electron flow), and the curly arrowhead is
  narrower (`head_w` via `_arrow_head(width_frac=…)`) for a pen-like organic head.
  **All default-off → every existing curved edge (hbond / curly) byte-identical**
  (the default still emits `Q 50,20`). Endpoints stay registry-resolved, so a head
  into void is impossible. +9 tests; visual proof rendered (lone-pair → carbonyl-C
  attack + C=O π → O, on real anchors). 1127 green.
  > **Carry-forward to P7.4:** the curly *primitive* is done; a clean short sweep
  > needs the residue placed *close* to its target (composition/scale), which is
  > P7.4's acceptance-layout tuning, not the primitive.
  *Done when:* a curly arrow originates on a real bond/lone-pair anchor and
  terminates on a real atom anchor; the Step-2 Ser530-O → carbonyl-C and C=O → O
  arrows render correctly; no eyeballed coordinate appears.

- [x] **P7.3 — Remaining north-star primitives.** ✅ 2026-06-14.
  - **7.3a — Organic protein blob with cavity** ✅ `proteins.protein_blob` — a
    deterministic smooth organic silhouette (`_blob_silhouette_path`: quadratics
    through wobbled ellipse vertices) with a centre-lighter highlight + a darker
    central cavity pocket; first shape is `<path>` (matches the P7.0 `_SLOT_KIND_SHAPE`
    seam). A BLOB slot publishes `center` + `cavity_center/top/bottom` anchors at
    the box centre/quarter-offsets, so a `cavity_*` attach lands a residue inside.
    **De-overlap fix:** `_deoverlap_coincident` now **exempts cavity-attached
    children** — they're deliberately co-located in the pocket, so MF-3's
    separation pass no longer pushes them out (the His513-vs-ligand *center*-tangle
    is unaffected). Verified: Ser530 renders inside the COX-1 pocket.
  - **7.3b — TS partial-bond** ✅ a `style={'partial':True}` edge draws a thin,
    finely-dashed straight half-bond between two atom anchors (no arrow/T-bar) —
    an anchor-pair overlay, no enum/schema change.
  - **7.3c — Minor glyphs + ⊣ fix** ✅ `glyphs.tablet` (scored disc) and
    `glyphs.pg_cluster` (dot cluster; `style['reduced']` → sparse depleted pool).
    `_EDGE_DEFAULTS['inhibits']` now draws a square-capped perpendicular **T-bar**,
    not an arrowhead; `convention_check` gains `_check_tier_inhibition_edges`
    (tier `connect`/`transition` INHIBITS edges audited for the T-bar — the
    P7.0-deferred edge convention).
  Three new `PrimitiveSpec`s (`protein_blob`→path, `tablet`/`pg_cluster`→circle);
  GLYPH slots render **any** registered primitive by `style['glyph']` (reuses the
  P0c.1 registry), unknown glyph fails loud. +21 tests; two visual proofs. 1148 green.
  *Done when:* each glyph renders from IR and registers as a single `PrimitiveSpec`;
  the blob's cavity anchors resolve; the inhibition edge draws a T-bar.

- [x] **P7.4 — Aspirin/COX-1 acceptance render.** ✅ 2026-06-14. **V3 is now
  feature-complete.** Authored the full 3-tier IR (title / 4-step mechanism row /
  summary bar) — `showcase/aspirin_cox1_v3_acceptance.{json,png,svg}`, a
  self-contained IR that renders + passes all three tier-aware checks (semantic,
  legibility, convention). The mechanism reads end-to-end: Step 1 aspirin enters
  with a red H-bond to Ser530; Step 2 the curly nucleophilic attack (origins on
  `ser.lp_a1` + `asp.bond_carbonylC_carbonylO` — real anchors); Step 3 the
  "breaking" TS partial bond + green salicylic-acid departure; Step 4 covalent
  acetyl–Ser530. The summary bar shows the physiological pathway and the
  aspirin-⊣-COX-1 inhibition (T-bar) → reduced PG. **MF-1** (Ser530/His513 are real
  fragments, coloured atom letters), **MF-2** (curly arrows on real bond/lone-pair
  anchors), **MF-3** (the solver spreads the active-site fragments — no overlap)
  all demonstrably met. **Key composition enabler:** a per-slot `style['scale']`
  (P7.4) so a small molecule/residue sits inside a full-size blob cavity without
  dwarfing it. Locked by `tests/test_acceptance_aspirin_cox1.py` (5 tests). 1153
  green. ⚠️ **Deviation:** the mechanism row is **4 authored scenes**, not a
  `StepSequence` — `StepDelta` is slot-granular (no per-step *edge* add/remove), so
  it cannot express "the curly arrow appears only in Step 2". Authored scenes give
  per-step edges and expand to the same 4-column row. (A `StepSequence` edge-delta
  op is a clean future extension if cross-panel slot continuity is wanted.)
  *Done when:* semantic + legibility + convention checks (now tier-aware, P7.0)
  pass on the IR-driven render; the three MF criteria are demonstrably met; the
  figure is committed to `showcase/` as the V3 acceptance artifact.

### Phase H — independent correctness hardening (no ordering dependency)

- [x] **PH.1 — Split classification from fallback on the multi-step downgrade.**
  ✅ 2026-06-12. `render_figure` now fails loud (`NotImplementedError`, matching
  `layout_reaction`) on a non-linear multi-step REACTION_SCHEME; the PATHWAY
  fallback is an explicit opt-in kwarg `pathway_fallback=True` (CLI:
  `--pathway-fallback`) that **always** warns (ungated; names original + coerced
  archetype). Two tests added (no-smiles-now-fail-loud + `A→B→C→A` cycle).
  ⚠️ `compositor.py:172` downgrades non-linear multi-step REACTION_SCHEME → PATHWAY;
  the `warnings.warn` is gated behind `if smiles_map:` (`:174`) so the no-smiles
  path is **silent**, and `render_figure` is fail-soft while `layout_reaction` is
  fail-loud for the identical condition. Flag non-linear REACTION_SCHEME, default
  **fail-loud** (match `layout_reaction`), make the PATHWAY fallback an explicit
  opt-in `render_figure` flag, and **always warn** when taken (ungate the
  `smiles_map` condition; name original + coerced archetype). Add the two missing
  tests: no-smiles silent path, and an `A→B→C→A` cycle.
  *Done when:* no silent downgrade path remains.

- [x] **PH.2 — Partition `_validate_structure`.** ✅ 2026-06-12 (sign-off given).
  `Figure._validate_structure` (`ir/_v2_models.py`) is now a thin dispatcher
  (exclusivity guard → dispatch by populated container) + `_validate_leaf` /
  `_validate_paneled` / `_validate_tiered`. Behaviour-preserving: every non-
  exclusivity error string + condition is byte-identical; conditional dispatch is
  equivalent to the monolith's run-all because the at-most-one guard runs first.
  ⚠️ IR change — needs sign-off.
  Split the 71-line monolith (`schema.py:622`) into a thin `@model_validator`
  dispatcher + `_validate_leaf` / `_validate_paneled` / `_validate_tiered`
  helpers, mirroring the chassis's node-type partitioning. Gives Steps 5/6/7 one
  obvious home for new cross-mode invariants (cross-tier `TierEdge` anchor
  existence; post-expansion scene-id collision, `:682`). **Preserve every
  test-matched error-string substring.**
  *Done when:* validators are per-mode; all `test_ir_schema*` pass unchanged.

- [x] **PH.3 — Correct the exclusivity error string.** ✅ 2026-06-12 (sign-off
  given). Figure exclusivity message now "Figure must use **at most one of**: …";
  the 3 tests that matched "exactly one of" (`test_ir_schema.py`,
  `test_ir_schema_tiers.py` ×2) updated to "at most one of". Tier's own message
  was already "at most one of" — unchanged.
  ⚠️ IR change — wording
  only. `schema.py:626` says "must use exactly one of" but the guard is
  `sum(...) > 1` (at-most-one; an all-empty figure validates). Soften to
  "at most one of". **Check `test_ir_schema_tiers` doesn't match the changed
  substring first.**
  *Done when:* the message matches the guard; tests green.

- [x] **PH.4 — Actionable overlap-warning text.** ✅ 2026-06-12. The overlap
  `UserWarning` (`label_placement.py`) now names the concrete escape hatches:
  larger canvas (`--canvas WxH`), split across panels, reduce entity count, or
  `--no-labels` — in addition to `strict_labels=True`.

- [x] **PH.5 — Externalise `_INFERENCE_RULES`.** ✅ 2026-06-12. The table is now
  checked-in declarative data (`layout/inference_rules.json`), loaded by
  `_geom._load_inference_rules()` into the same in-memory shape (behaviour-
  identical, order preserved). `infer_primitive` delegates to new
  `infer_primitive_explained` (returns matched keyword); `explain_entity_primitive`
  reports the basis (override / inferred-by-keyword / type default); CLI
  `--explain` prints it per entity. 4 tests added.
  ⚠️ Silent: `_geom.py:202` changes
  the rendered glyph on a bare label-keyword match with no IR trace and no warning
  (an *unknown* override warns; an *inferred* one doesn't). Step 6 multiplies
  entities, so one mis-tuned keyword propagates across N scenes. Promote the rule
  table to checked-in declarative data (json/toml) so it's diffable + unit-
  testable, and have `resolve_entity_primitive` (`:257`) optionally annotate the
  chosen entry with WHY (override vs inferred-by-keyword-X vs default) for a
  `--explain` pass. Control already exists via `style.primitive`; the gap is
  observability.
  *Done when:* the inference table is data, not code, and `--explain` reports the
  basis per entity.

---

## Phase R — module decomposition (independent; no ordering dependency)

**Motivation.** Six modules carry the bulk of the tree and force a full-file read
for any edit (token cost + weak concern-separation). This phase splits them into
focused sub-modules. It runs like **Phase H** — no dependency on Steps 5–7 — but
every extraction here *also* shrinks the seam files those steps edit, so landing
R1/R5 early pays compound interest.

**The invariant that makes this safe (read before touching anything):**
> Every name currently importable from a module **stays importable from that same
> module**. Each split leaves a thin **re-export shim** at the original path that
> imports the moved symbols back. No call site outside the split changes. The
> suite is the proof: **1025 green before and after every single extraction** —
> if a split drops the count, it's wrong, revert it.

This phase is **pure mechanical decomposition** — zero behaviour change. It does
**not** violate the §5 "do not merge engines" rule: these are *within-engine*
splits (R1 stays 100% pathway-engine code; it never touches `tier_layout`
placement). Private sub-modules take an `_`-prefixed sibling name so the
"internals of X" relationship is legible without a package conversion.

| Item | File (lines) | Split into | Public names to preserve (re-export) | Sign-off |
|---|---|---|---|---|
| **R1** | `layout/pathway_layout.py` (2494) | `_pathway_glyphs.py` · `_pathway_rings.py` · `_pathway_routing.py` · `_pathway_bands.py` · `_pathway_labels.py`; `pathway_layout.py` keeps the orchestrator + dispatch tables + re-exports | `layout_pathway`, `compute_pathway_canvas`, `pathway_label_requests`, `pathway_extlabel_leaders`, `phospho_badge_occupied_bbox`, `RELATION_TO_ARROW`, `_PATHWAY_COMPATIBLE_ARCHETYPES` | none |
| **R2** | `ir/schema.py` (709) | `_enums.py` · `_v2_models.py` · `_v3_models.py`; `schema.py` re-exports all | every model + enum + `_check_id_chars`/`_collect_slot_ids` | ⚠️ **REQUIRED** — load-bearing; preserve every test-matched error-string substring; keep the `model_rebuild()` block |
| **R3** | `primitives/chemistry.py` (801) | `_mol_render.py` (RDKit ingest/style) · `_reaction_render.py` (arrows/conditions/multistep); `chemistry.py` re-exports | `render_molecule`, `render_molecule_anchored`, `render_reaction`, `render_multistep_reaction`, `render_functional_group` | none |
| **R4** | `primitives/nucleic_acids.py` (796) | `_dna.py` (dna_segment, gene_helix, broken-DNA) · `_rna.py` (rna/mrna/primer helix, chromatin); `nucleic_acids.py` re-exports | all public segment/helix fns | none |
| **R5** | `render/compositor.py` (766) | `_svg_post.py` (autocrop, page bg, title group, frame box) · `compositor.py` keeps `render_figure` + dispatch | `render_figure` (+ any helper imported elsewhere) | none |
| **R6** | `styles/loader.py` (358) | `_palette.py` (`apply_palette_recipe`) · `loader.py` keeps preset I/O | `load_style`, `load_preset_full`, `load_layout_params`, `list_presets`, `apply_palette_recipe`, `DEFAULT_PRESET`, `KNOWN_STYLE_KEYS` | none |

**Deferred (do NOT split yet):** `layout/tier_layout.py` (654) — active V3 surface,
Steps 5/6 rewrite it; splitting mid-feature adds merge cost for zero gain. Revisit
after Step 6 lands. `primitives/lab_equipment.py` (747) — one cohesive primitive
family; low edit-frequency, low payoff.

**R1 internal seams (verified 2026-06-11 against the working tree):**
- The 7 public names above are the *entire* external surface (`compositor.py:57`
  imports 5; `label_placement.py:244`/`:300` lazy-import `RELATION_TO_ARROW` +
  `phospho_badge_occupied_bbox`; `panel_layout.py:50` imports `layout_pathway`).
- `_pathway_glyphs` is a true leaf: `_midpoint_of_path`/`_relation_glyph`/
  `_phospho_badge_geom`/`_phosphorylation_arrow`/`phospho_badge_occupied_bbox` +
  `_PHOSPHO_BADGE_DEFAULTS` call only each other; deps are `svgwrite`, `arrows`,
  `_centered_label`. Only inbound edge: `RELATION_TO_ARROW` → `_phosphorylation_arrow`
  (table stays in `pathway_layout.py`, imports the moved fn).
- `label_placement` ↔ `pathway_layout` already has a documented import cycle
  broken by lazy imports (`label_placement.py:236`). Keep all cross-`_pathway_*`
  imports module-top-level and one-directional (leaf modules import nothing from
  the orchestrator) so no new cycle is introduced.

**R1 LANDED in full — 2026-06-11.** `pathway_layout.py` 2494 → **652** lines
(orchestrator: `layout_pathway`, `compute_pathway_canvas`, `PATHWAY_DEFAULT_PARAMS`,
`_PATHWAY_COMPATIBLE_ARCHETYPES` + re-exports). A dependency-graph workflow
(3 readers + synthesis, 2026-06-11) proved the module import graph is a DAG and
forced one design refinement over the original sketch: a **`_pathway_common`**
leaf was added to hold the symbols shared by ≥2 sub-modules (`RELATION_TO_ARROW`,
`_LABEL_MARGIN`, `_RECEPTOR_FONT_SIZE`, `_IMPLICIT_COMPARTMENT_ID`), which breaks
the orchestrator↔labels cycle that `RELATION_TO_ARROW` would otherwise create.
Final verification: **1025 green** after every step; fresh-process import of all 7
modules (no cycle); all 7 public re-exports resolve; **AST pure-move proof** — all
46 functions + 20 constants present exactly once, byte-identical to git HEAD.

- [x] **R1.a — `_pathway_glyphs.py`** (141 ln) — phospho-badge glyph leaf.
- [x] **R1.b0 — `_pathway_common.py`** (53 ln) — shared constants + `RELATION_TO_ARROW` (DAG cycle-breaker).
- [x] **R1.b — `_pathway_rings.py`** (339 ln) — cycle/ring detection + ring geometry + band-height math.
- [x] **R1.c — `_pathway_bands.py`** (383 ln) — compartments, `_graph_positions`, membrane snap, arrow endpoints.
- [x] **R1.d — `_pathway_routing.py`** (702 ln) — port routing, fan-out, arch, bilayer/nuclear borders.
- [x] **R1.e — `_pathway_labels.py`** (487 ln) — ring-label declutter, `pathway_label_requests`, ext-label leaders (label_placement imports kept lazy).
- [x] **R3 — `primitives/chemistry.py`** (801 → 93 ln shim) — split into
  `_mol_render.py` (433 ln: RDKit ingest/style + `render_molecule`/
  `render_molecule_anchored`/`render_functional_group`) and `_reaction_render.py`
  (374 ln: arrows/conditions + `render_reaction`/`render_multistep_reaction`).
  One-directional dep (`_reaction_render` → `_mol_render` for `DEFAULT_STYLE`,
  `_smiles_to_mol`, `_inline_molecule`); no cycle. AST-verified pure move (all 17
  funcs/classes byte-identical to HEAD); shim re-exports every HEAD-defined name
  + the private surface the tree imports (`DEFAULT_STYLE`, `_arrow`,
  `_reversible_arrow`, `_FUNCTIONAL_GROUPS`, `_wrap_conditions`). **1025 green.**
- [x] **R4 — `primitives/nucleic_acids.py`** (796 → 78 ln shim) — split into
  `_dna.py` (470 ln: shared `DEFAULT_STYLE` + helix geometry helpers, `dna_segment`,
  `gene_helix`, `_broken_dna_segment`) and `_rna.py` (344 ln: `rna_segment`,
  `rna_helix`, `mrna_helix`, `primer_helix`, `chromatin`). One-directional dep
  (`_rna` → `_dna` for `DEFAULT_STYLE`, `_axis_frame`, `_sample_strand_on_path`,
  `_add_strand_polyline`, `dna_segment`); no cycle. AST-verified pure move (all 14
  funcs byte-identical to HEAD); shim re-exports every HEAD-defined name. **1025 green.**
- [x] **R5 — `render/compositor.py`** (766 → 615 ln orchestrator) — split the
  post-write SVG passes + figure-title chrome into `_svg_post.py` (193 ln:
  `_autocrop_svg`, `_expand_svg_to_content`, `_frame_box` + frame regexes,
  `_paint_page_background`, `_figure_title_group`, `_title_entry`). `render_figure`
  + dispatch/style/canvas/label helpers stay in `compositor.py`. One-directional dep
  (`compositor` → `_svg_post`); no cycle. The seam files Steps 5/6/7 edit
  (`_dispatch_layout`, `_canvas_size`, label coordinator) are untouched. Every
  externally-imported name still resolves from `compositor` (the moved private
  names are re-exported). AST-verified pure move (all 20 funcs/classes
  byte-identical to HEAD). **1025 green.**
- [x] **R6 — `styles/loader.py`** (358 → 318 ln) — extracted the palette→fill
  recipe (`PALETTE_RECIPE`, `apply_palette_recipe`) into `_palette.py` (55 ln);
  `loader.py` keeps all preset I/O (`load_style`, `load_preset_full`,
  `load_layout_params`, `list_presets`, `StylePreset`, key sets). One-directional
  dep (`loader` → `_palette`); no cycle. Both moved names re-exported so the full
  surface (incl. `PALETTE_RECIPE`/`apply_palette_recipe`) stays importable from
  `loader`. AST-verified pure move (all 11 funcs/classes byte-identical to HEAD).
  **1025 green.**
- [x] **R2 — `ir/schema.py`** (709 → 120 ln aggregator) — split into `_enums.py`
  (172 ln: all 14 kind enums), `_v2_models.py` (210 ln: `_IRBase` + Entity…Panel,
  `Figure`), `_v3_models.py` (374 ln: `_check_id_chars`/`_collect_slot_ids` +
  Slot…Tier). Pure DAG `_enums ← _v2_models ← _v3_models ← schema`; the real
  `Figure↔Tier` type cycle is resolved without an import cycle by keeping the
  12-call `model_rebuild()` block in the aggregator, where every model co-resides
  (exactly how the single-file version resolved forward refs at module end).
  **Sign-off given 2026-06-11.** AST-verified pure move (all 35 classes/functions
  byte-identical to HEAD); rebuild block verbatim; every model `__pydantic_complete__`;
  all test-matched error-string substrings preserved (validators moved byte-identical);
  full surface re-exported (incl. `_IRBase`/`_check_id_chars`/`_collect_slot_ids`).
  **1025 green.** Adversarially verified (4-lens workflow).

> **Dead code spotted during R1** (not fixed — pure-move discipline): `_label_extent_w`
> (`_pathway_rings.py`) is defined but referenced nowhere in the tree. Candidate for a
> follow-up removal pass.

---

## 5. Do NOT (verified failure modes)

- **Do not merge `tier_layout`'s anchor/solver placement with `pathway_layout`'s
  NetworkX placement.** Verified: they share zero primitives today (`pathway_layout`
  imports no anchors; `tier_layout` imports no `label_placement`). Steps 5/6/7
  only deepen the divergence. The win is collapsing the *4 precedence sites*, not
  unifying engines.
- **Do not grow a second relaxation engine inside `tier_layout` for Step 5** —
  that forks the `data-overlap=true` contract, the strict/lenient toggle and the
  warning path. Reuse `place_labels` via the P0a.3 seam.
- **Do not add a preset-NAME axis below `Figure`** (per-step or per-scene preset
  names) — additive freeform `style` dicts only. `Panel.content.style_preset` is
  the lone exception (already shipped). That's what prevents the panel×step matrix.
- **Do not fold the base preset into the chassis *structural* channel** (connect
  edges / tier transitions). The preset's primitive vocabulary sets bare
  `stroke`/`stroke_width` (acs/nature), which collide with `_edge_group`'s keys
  and would clobber the per-`SceneEdgeType` semantic colours (an hbond's red →
  black). The cascade (P0b.2) is two channels: **content** (molecules, text)
  takes the preset base; **structural** (edges) takes `tier.style → scene.style →
  edge.style` only. A journal preset must never recolour a semantic edge.
- **Keep chassis `style` keys flat scalars.** `merge_style` is shallow
  (later-wins, like preset `inherits`); a nested style sub-dict would be clobbered
  wholesale, not deep-merged. No preset/chassis layer sets a nested key today.
- **Do not touch `schema.py` without sign-off**, and **preserve every
  test-matched error-string substring** (`CONTRIBUTING.md`).
- **Do not remove the `model_rebuild()` block** — it's load-bearing under
  `from __future__ import annotations`.

---

## 6. What this supersedes / leaves intact

- **Supersedes:** the *sequencing* of `V3_IR_NODESHAPES_PROPOSAL.md §3` Steps 5–7
  and `V3_SCENE_CHASSIS_SCOPE.md §4` for unlanded work. The node-shape *schema*
  and the §2 design decisions in those docs **stand unchanged**.
- **Intact:** `V3_STATUS.md` Steps 1–4 record; `V3_FEATURES.md` MF-1/2/3
  acceptance criteria and the V3-C/L/I/O/S backlog (this plan only schedules
  V3-C4 into P7.2).
- **Cross-refs:** MF-1 → P7.1; MF-2 / V3-C4 → P7.2; MF-3 → P5.1; V3-L2
  (force-directed labels) remains deferred — P5.x is greedy-via-coordinator, not
  the L2 rewrite.

---

*Authored 2026-06-11 from the verified architecture scan. Update the checkboxes
as items land; when a step completes, fold its record into `V3_STATUS.md` and
tick it here.*
