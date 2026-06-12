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

- [ ] **P0a.1 — Promote the archetype→engine table to one source.**
  Lift `ARCHETYPE_TO_LAYOUT` (`panel_layout.py:82`) into a single
  `_ARCHETYPE_PLAN: dict[Archetype, tuple[engine, canvas_fn, label_fn]]`. Make
  `_dispatch_layout` (`compositor.py:356`), `_canvas_size` (`:528`) and
  `_label_requests_fn` (`:510`) read it; **delete the duplicate `if/elif` at
  `panel_layout.py:210`** so REACTION_SCHEME is encoded once. Pure refactor.
  *Done when:* the 4 sites share one table; golden suite unchanged.

- [ ] **P0a.2 — Introduce `LoweringPlan` + `_lowering_plan(ir)`.**
  Add a small record `(engine, canvas_fn, label_strategy, style_base)` resolved
  once at the top of `render_figure`. Container-mode-first (`tiers` → `elif
  panels` → `else leaf`, archetype-second via P0a.1's table). Route
  `_dispatch_layout` and `_canvas_size` through the resolved plan instead of
  re-branching. The multi-step coercion (`compositor.py:172`) stays a *pre*-plan
  normalise — it sets archetype to PATHWAY before the plan resolves, so the
  resolver needs no second touch.
  *Done when:* dispatch + canvas read one plan; behaviour identical; tests green.

- [ ] **P0a.3 — Extract `LabelCoordinator.place()` (minimum-viable, byte-identical).**
  Move the inlined label `if/else` (`compositor.py:~192`) and
  `_place_labels_per_panel` (`:443`) into a `LabelCoordinator` keyed on a
  first-class `LabelScope = (entry-subset, canvas-bound, occupancy-seed)`.
  Leaf = one scope (current else-branch verbatim). Panels = one scope per panel
  (lift `_place_labels_per_panel`, reuse `_panel_cell_bounds`). **Tier captions
  stay byte-identical** (still emitted by `_caption_group`, `tier_layout.py:493`)
  — this cut does *not* change tier behaviour, it only builds the seam.
  *Done when:* 1025 tests still green; render output unchanged; the three label
  paths now live behind one `place()` dispatch.

- [ ] **P0a.4 — Add `AnchorRegistry.copy()` (deep) + a `layer()` overlay.**
  Today `publish` is mutation-only (`anchors.py:94`, `self._anchors[k]=…`) with
  no versioning, so a re-running solver clobbers earlier writes
  non-deterministically. Add `copy()` (deep-copy both `_anchors` + `_rails`) and
  a `layer()` context that **buffers** `publish*` and commits-or-drops on exit;
  `resolve*` reads overlay-then-base. `layout_tiers` keeps building one base
  registry; the solver opts into a layer.
  *Done when:* a unit test proves publish-in-layer + rollback leaves base intact,
  and commit merges.

- [ ] **P0a.5 — Aggregate anchor-ref validation in `layout_tiers`.**
  Add `AnchorRegistry.validate_refs(refs) -> list[str]` and call it after all
  `publish*` but **before** the first `resolve_edge` (`tier_layout.py`, in the
  tier loop ~`:640`). Aggregate every unresolved `from_ref`/`to_ref`/
  `from_anchor`/`to_anchor` into **one** error naming the owning edge `ir_id` —
  instead of dying on the first typo at `resolve` (`anchors.py:132`).
  *Done when:* a figure with two bad refs reports both in one error.

- [ ] **P0a.6 — Validate the static slot token of anchor refs at IR-build time.**
  ⚠️ IR change — needs sign-off. Extend `Tier._validate_tier` (`schema.py:~561`)
  and `Scene._validate_scene` (`:374`) to also check the **slot** token of
  `"scene.slot.anchor"` refs (slot ids are known at build), leaving only the
  truly-dynamic atom segment for layout time. Catches a whole typo class early;
  matters more once Step 7 explodes anchor cardinality. Preserve existing
  error-string substrings.
  *Done when:* a `TierEdge` naming a nonexistent slot fails at `Figure(...)`
  construction, not at render.

### Step 5 — Scene solver (plugs into the P0a seams)

Builds on P0a.3 (label seam), P0a.4 (registry rollback), P0a.5 (ref validation).
**Do not** grow a second placement/relaxation engine inside `tier_layout` — reuse
`place_labels`. (⚠️ verified: `tier_layout` imports nothing from
`label_placement`; that's the seam P0a.3 exists to close.)

- [ ] **P5.1 — Topological attach/offset pass.** Replace the current
  dependency-ordered attach solve with a real topological offset solver over the
  `Attach` graph; resolve co-located slots so they do not overlap. Run it inside
  a registry `layer()` (P0a.4) so iterations can roll back.
  *Done when:* the His513-vs-ligand tangle (**MF-3**, `V3_FEATURES.md`) cannot
  occur — a test with two center-attached slots produces non-overlapping boxes.

- [ ] **P5.2 — Scene-local label placement via the coordinator.** Add a
  `scene_label_requests(scene, scene_entries)` in `tier_layout` that emits
  `LabelRequest`s for `scene.label` (replacing the fixed `_caption_group`),
  **plus the currently-unrendered `SceneEdge.label` (`schema.py:338`) and
  non-TEXT `Slot.label` (`schema.py:301`)**. Swap *only* the tier branch of
  `LabelCoordinator` from emit-caption to a per-scene scope whose canvas bound is
  the scene cell rect. `place_labels`' existing canvas-clip enforces
  scene-locality for free.
  *Done when:* tier captions route through `place_labels`; scene-edge / slot
  labels render; no fixed-coordinate caption path remains.

- [ ] **P5.3 — Seed the figure-level annotation pass with occupied bboxes.** After
  scene scopes place, hand their bboxes to the annotation pass
  (`compositor.py:~216`) as occupancy so a scene-local label and a global
  annotation can no longer silently overlap.
  *Done when:* a regression figure that previously overlapped a scene label with
  a global annotation now separates them.

- [ ] **P5.4 — Close the Step-4 deferred placement nits** (from `V3_STATUS.md`):
  non-molecule attach-parent extent (use slot bbox, not scene frame); sub-pixel
  molecule centering from `int()` render size; text `center` anchor = midline not
  baseline. These are now in-scope because the solver owns extents.
  *Done when:* each nit has a regression test.

### Phase 0b — pre-Step-6 seams (land before step expansion)

- [ ] **P0b.1 — Apply `style_dict` inside `tier_layout`.** ⚠️ The base preset
  reaches `layout_tiers` but is never layered onto nodes. Merge it as the base
  under each per-node dict: `{**style_dict, **(tier.style or {})}` (`:578`),
  `{**style_dict, **(slot.style or {})}` (`:355`), `{**style_dict, **(edge.style
  or {})}` (`:416`/`:647`). Remove the "unused in the slice" note at
  `tier_layout.py:552`.
  *Done when:* a tiered figure rendered under two presets visibly differs;
  regression golden per preset.

- [ ] **P0b.2 — One additive style cascade for the chassis.** Establish
  `base preset → tier.style → scene.style → step.style`, reusing
  `_resolve_preset`'s inherits-merge idiom (`styles/loader.py:259`) — **not** a
  second merge implementation. `Step.style` (`schema.py:432`, currently **dead** —
  consumed nowhere) becomes the last additive layer.
  *Done when:* a `Step.style` override changes only that step's render.

- [ ] **P0b.3 — Make `_build_panel_styles` dense.** ⚠️ `smiles_map` is broadcast
  dense `{p.id: …}` (`compositor.py:388`) while `panel_styles` is sparse/
  differ-only (`:318`). Resolve every panel's effective style eagerly so
  downstream `.get(panel.id)` is uniform and Step 6 inherits **one** keying
  convention.
  *Done when:* both broadcasts use the same dense shape; panel tests green.

- [ ] **P0b.4 — Guardrail: no preset-NAME axis below `Figure`.** Document (and
  enforce in review) that chassis overrides are additive freeform `style` dicts
  only — never a second axis of preset *names*. `Panel.content.style_preset`
  stays the lone exception (already shipped). This is what prevents a panel×step
  matrix.
  *Done when:* the rule is in this doc's "Do not" list and Step 6 honours it.

### Step 6 — Step expansion (builder-layer, slot-granular)

Builds on P0b's single style-keying convention and the additive cascade.

- [ ] **P6.1 — Expand `StepSequence` → N concrete `Scene`s at the builder layer.**
  Replace the `NotImplementedError` (`tier_layout.py:618`) by expanding deltas at
  build time so verification sees real scenes (per `proposal §2.4`). Cumulative
  deltas apply in order.
  *Done when:* a 3-step sequence renders as 3 scenes; `semantic_check` audits each.

- [ ] **P6.2 — Slot-granular deltas only** (`add`/`remove`/`replace`/`add_label`)
  — no sub-atom mutation of opaque groups. `delta.target` resolves in `base` or a
  prior `add` when cumulative.
  *Done when:* an out-of-scope delta op fails loud at build.

- [ ] **P6.3 — `ADD_LABEL` deltas route through the label coordinator** as *more
  `LabelRequest`s in the expanded scene's scope* (P5.2) — **not** a fourth
  placement path.
  *Done when:* a step-added label is placed by the same solver as scene labels.

- [ ] **P6.4 — Per-step style via the additive cascade** (P0b.2) — `Step.style`
  is the last layer; no per-step preset name.
  *Done when:* per-step restyle works with zero new branches in the cascade.

### Phase 0c — pre-Step-7 seams (land before primitive refresh)

- [ ] **P0c.1 — Introduce `PrimitiveSpec` to collapse the 3-file table coupling.**
  ⚠️ Adding a primitive today needs synchronized edits across: the
  `entity_adapters` callable + icon assets; `_geom.PRIMITIVE_REGISTRY` (`:69`) +
  `_PRIMITIVE_BBOX_OVERRIDE` (`:128`); and `convention_check._PRIMITIVE_SHAPE`
  (`:56`) / `_SKIP_SHAPE_PRIMITIVES` (`:103`) — guarded by **one** test. Define a
  single `PrimitiveSpec(name, callable, bbox, shape_tag|SKIP, icon_asset?)`
  registered once; derive `PRIMITIVE_REGISTRY`, the bbox table, the convention
  shape map and icon assets from that one list.
  *Done when:* registering a new spec is a single-site add; the coverage test
  becomes structural (iterates the spec list).

- [ ] **P0c.2 — `list_style_keys()` discovery surface.** The 192-key vocabulary
  (`KNOWN_STYLE_KEYS`, `loader.py:81`) is code-only; SKILL.md lists 3 preset
  names. Add `list_style_keys()` + a `python -m imageGen styles --keys` path
  before Step 7 inflates the key set with curly-arrow primitives.
  *Done when:* the full key inventory is printable from the CLI.

- [ ] **P0c.3 — Fix the silent REACTION_SCHEME downgrade** (also in Phase H — do
  it here at the latest). Step 7's curly arrows / per-atom anchors are
  REACTION-only; once a mechanism is a non-linear multi-arrow graph the downgrade
  to PATHWAY (`compositor.py:172`) erases the chemistry layer **silently** when
  `smiles_map` is falsy. See **PH.1**. Record the original archetype so Step-7
  primitives can refuse to no-op on a coerced archetype.
  *Done when:* a non-linear REACTION_SCHEME never silently degrades; PH.1 landed.

### Step 7 — Primitive refresh (aspirin/COX-1 acceptance)

Builds on P0c. Acceptance = the mechanism-figure fidelity criteria
(`V3_FEATURES.md` MF-1/2/3). Aspirin/COX-1 reproduction is **this** workstream's
acceptance test, not a chassis milestone.

- [ ] **P7.1 — One atom convention everywhere (MF-1).** Heteroatoms render as
  coloured **letters** via the molecule renderer's convention, never bespoke bare
  dots. Residue fragments are real rendered molecular fragments. Register them as
  `PrimitiveSpec`s (P0c.1).
  *Done when:* no bare-dot oxygen appears; a figure mixing aspirin + a residue
  uses one atom convention.

- [ ] **P7.2 — Curly arrow-pushing primitive (MF-2 / V3-C4).** Endpoints come
  from `AnchorRegistry.resolve("scene.slot.atom")` (the keystone already
  publishes atom-map → anchor) — never eyeballed coords.
  *Done when:* every arrowhead lands on a real atom anchor; a head pointing into
  void is impossible by construction.

- [ ] **P7.3 — TS partial-bond glyph + organic shaded blobs + tablet/⊣ glyphs**
  (the remaining aspirin north-star primitives), each a `PrimitiveSpec`.
  *Done when:* the aspirin/COX-1 figure renders from IR with these primitives.

- [ ] **P7.4 — Aspirin/COX-1 acceptance render.** A naive reader can trace the
  mechanism from the active sites alone (MF-1 ∧ MF-2 ∧ MF-3). Compare against
  `showcase/aspirin_cox1_anchored_proof.png`; target spec
  `references/aspirin_COX1_figure_spec.md`.
  *Done when:* semantic + legibility + convention checks pass on the IR-driven
  render and the three MF criteria are demonstrably met.

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
  names) — additive freeform `style` dicts only. That's what prevents the
  panel×step matrix.
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
