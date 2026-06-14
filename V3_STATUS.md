# V3 — Current Build Status

Quick-read orientation for any agent starting a V3 work session. Read this
first, then dive into the detail docs linked below.

---

## Build order — where we are

| Step | What | Status |
|------|------|--------|
| 1 | **Anchor-return protocol + figure-global anchor registry** — `primitives/_anchors.py`, `render_molecule_anchored`, `layout/anchors.py` (`AnchorRegistry` + `Rail`) | ✅ LANDED (2026-06-08) |
| 2 | **Schema additions** — 7 enums + 10 models (`Tier`, `Rail`, `TierEdge`, `Scene`, `Slot`, `Attach`, `SceneEdge`, `StepSequence`, `Step`, `StepDelta`) + `Figure.tiers` + validators. Suite: 1000 green. | ✅ LANDED (2026-06-08) |
| 3 | **Vertical slice end-to-end** — `layout/tier_layout.py::layout_tiers`, proven with 11 tests. Suite: 1012 green. | ✅ LANDED (2026-06-08) |
| 4 | **Tier compositor + band chrome** — `render_figure` wired for tiered figures; band chrome, scene badges, content-gap arrow fix. Suite: 1025 green. | ✅ LANDED (2026-06-10) |
| 5 | **Scene solver** — topological attach/offset pass + co-location de-overlap (MF-3), scene-local label placement via `place_labels`, annotation occupancy seed, and the 3 placement nits. Suite: 1060 green. | ✅ LANDED (2026-06-12) |
| 0b | **Pre-Step-6 style seams** — tiered figures honour the journal preset; two-channel additive cascade (content vs structural); dense `_build_panel_styles`; preset-name-axis guardrail. Suite: 1064 → 1078. | ✅ LANDED (2026-06-13) |
| 6 | **Step expansion** — slot-granular `StepSequence` → N concrete validated `Scene`s (add/remove/replace/add_label), per-step style via the cascade, adversarially hardened. Suite: 1078 green. | ✅ LANDED (2026-06-13) |
| 0c | **Pre-Step-7 seams** — `PrimitiveSpec` single-site registry, `list_style_keys()` + `styles --keys` CLI, `LoweringPlan.coerced_from` record. Suite: 1082 → 1097. | ✅ LANDED (2026-06-13) |
| 7 | **Primitive refresh + expansion** — curly arrows (V3-C4), TS partial bonds, organic shaded blobs, per-atom anchors. **Aspirin/COX-1 reproduction is the acceptance test** (gated by MF-1/2/3). | ✅ LANDED (2026-06-14) — **V3 FEATURE-COMPLETE** |

**Current test count:** 1153 passing. **🎉 The V3 scene chassis is feature-complete
— all numbered steps (1–7) have landed.**

> **Chassis Phase 0a + Step 5 COMPLETE — landed 2026-06-12.** The chassis arc
> (`V3_CHASSIS_ARC_BLUEPRINT.md`) shipped in commit boundaries C1–C7:
> **C1** `_ARCHETYPE_PLAN` + `LoweringPlan` (P0a.1/P0a.2); **C2** `LabelCoordinator`
> seam (P0a.3); **C3** `AnchorRegistry.copy()`/`layer()` + `validate_refs`
> (P0a.4/P0a.5); **C5** topological attach/offset solver + co-location de-overlap
> (P5.1, MF-3); **C6** scene-local labels + annotation occupancy seed (P5.2/P5.3);
> **C7** the three placement nits (P5.4); **C4** build-time `TierEdge` slot-token
> validation (P0a.6, load-bearing IR, adversarially verified). The
> `LabelCoordinator` tier branch stays the inert pass-through by design — tiered
> figures place their scene labels in the tier engine (where the per-scene
> geometry lives), so `BAKED` means "the engine places its own."

> **Phase 0b + Step 6 COMPLETE — landed 2026-06-13.** Pre-Step-6 style seams
> (P0b.1/0b.2/0b.3/0b.4) then step expansion (P6.1–P6.4). The cascade is **two
> channels** (a verified correction to the plan's literal `{**preset, **node}`
> fold, which was a no-op for slots/chrome and a regression for edges): a
> **content** channel (molecules + text) takes the journal preset as its base —
> tier molecules now forward the merged style to `render_molecule_anchored` like
> the leaf path, closing the "tiers ignore their preset" gap — and a
> **structural** channel (connect edges / transitions) takes `tier→scene→edge`
> with NO preset base, so the preset's bare `stroke` can't recolour semantic
> edges. One shared `merge_style` helper (also reused in `loader`). `StepSequence`
> now expands to one validated `Scene` per step at layout time (a pure pre-pass;
> `semantic_check` walks only panels, so the "builder-layer" framing was moot);
> `step.style` rides the cascade as the outermost layer. The expansion was
> adversarially hardened (4-lens review): REPLACE keeps `id=target`, and
> REMOVE/REPLACE/ADD_LABEL fail loud on a nested or already-removed target
> instead of silently no-op'ing. **Now unblocked:** the deferred
> `tier_layout.py` Phase-R split (it said "revisit after Step 6").

> **Phase 0c COMPLETE — landed 2026-06-13.** The three pre-Step-7 seams.
> **P0c.1** collapses the primitive-registration coupling: a single
> `PRIMITIVE_SPECS` list (`primitives/primitive_specs.py`, one
> `PrimitiveSpec(name, render, bbox, shape|SKIP, icon_asset?)` per primitive)
> now *derives* `PRIMITIVE_REGISTRY` + `PRIMITIVE_TO_BBOX` (`_geom` re-exports),
> the `_PRIMITIVE_SHAPE` / `_SKIP_SHAPE_PRIMITIVES` convention maps
> (`convention_check` aliases), and `ICON_ASSETS` (`credits` reads it;
> `entity_adapters.ICON_ASSETS` removed) — registering a primitive is now a
> one-line append, and the coverage guard is structural (iterates the list). Two
> dead `glyphs.flask/centrifuge` shape entries fell out. **P0c.2** adds
> `list_style_keys()` + a `python -m imageGen styles --keys` subcommand to
> surface the 192-key style vocabulary before Step 7 inflates it. **P0c.3**
> finishes the REACTION_SCHEME→PATHWAY downgrade story: PH.1 already closed the
> *silent* path, so this records the pre-coercion archetype on
> `LoweringPlan.coerced_from` (captured before the `model_copy` rebind, no
> `schema.py` touch) so Step-7 primitives can refuse to no-op on a coerced
> archetype. +15 tests; 1097 green. **Step 7 is now unblocked.**

> **Step 7 P7.4 — aspirin/COX-1 acceptance render — landed 2026-06-14. V3 IS
> FEATURE-COMPLETE.** The full 3-tier IR (`showcase/aspirin_cox1_v3_acceptance.{json,png,svg}`)
> renders self-contained and passes all three tier-aware checks; a naive reader can
> trace the mechanism from the active sites alone (MF-1 ∧ MF-2 ∧ MF-3). A per-slot
> `style['scale']` lets a small molecule/residue sit inside a full-size blob cavity.
> Locked by `tests/test_acceptance_aspirin_cox1.py`. ⚠️ The mechanism row is 4
> *authored* scenes (not a StepSequence) — slot-granular deltas can't add per-step
> edges, so authored scenes give the per-step curly/TS edges. **All numbered steps
> 1–7 are done; 1153 green.**

> **Step 7 P7.3 — north-star primitives — landed 2026-06-14.** `proteins.protein_blob`
> (organic silhouette + centre highlight + cavity pocket; a BLOB slot publishes
> `cavity_*` anchors); `glyphs.tablet` + `glyphs.pg_cluster` (`reduced` → sparse);
> a `partial` edge style = TS half-bond; the tier `inhibits` edge now draws a
> **T-bar** (with a `convention_check` audit). GLYPH slots render any registered
> primitive via `style['glyph']`. Key fix: `_deoverlap_coincident` exempts
> cavity-attached children so a residue stays *inside* the pocket (MF-3's
> center-tangle separation is unaffected). 3 new PrimitiveSpecs; +21 tests; two
> visual proofs. 1148 green. **Next: P7.4 — the aspirin/COX-1 acceptance render
> (the final item; feature-complete when it lands).**

> **Step 7 P7.2 — arrow-pushing curly primitive (MF-2) — landed 2026-06-13.**
> `render_molecule_anchored` now publishes **bond-midpoint** anchors (`bond_a1_a2`
> + index/name aliases) and **lone-pair** anchors (`lp_a{map}`) so a curly arrow
> can originate at a C=O π bond or an O lone pair, not only an atom centre.
> `_edge_group` gained `curl` (handedness) and `arc='s'` (S-shaped cubic =
> electron flow) plus a narrower organic arrowhead — all default-off, so every
> existing curved edge is byte-identical. Endpoints stay registry-resolved (a head
> into void is impossible). +9 tests; visual proof rendered. 1127 green. **Next:
> P7.3** (blob/TS-bond/tablet/PG-cluster glyphs + the inhibits T-bar fix).

> **Step 7 P7.1 — residues as real fragments (MF-1) — landed 2026-06-13.**
> Heteroatoms already rendered as coloured letters in the IR-driven path, so MF-1
> meant *routing residues through it*. `render_molecule_anchored` gained an opt-in
> `open_valence` (dummy `*` → blanked label = dangling-bond stub + published
> `attach` anchor; default off → existing depictions byte-identical);
> `render_residue_anchored` + a `_RESIDUE_SMILES` map (ser530/his513/… reactive
> atom → `a1`) wrap it, and RESIDUE slots now render through the shared molecule
> path so `scene.slot.a1`/`scene.slot.attach` resolve for H-bond/curly edges. The
> P0c.3 `coerced_from` seam is consumed: the coercion drop-warning fires off the
> resolved plan and names the dropped entities. +10 tests; visual proof rendered.
> 1118 green. **Next: P7.2** (curly-arrow handedness/arc — the arrow still bows
> crudely across the molecule).

> **Step 7 P7.0 — tier-aware verification — landed 2026-06-13.** Both
> `semantic_check` and `convention_check` walked only entities/panels, so a tier
> figure (the acceptance render's shape) passed *vacuously*. A shared
> `tier_rendered_scenes(tier)` helper (`tier_layout.py`, reuses `_tier_scene_list`
> → cannot drift from the engine) enumerates the scenes a tier actually draws
> (SCENE_ROW scenes + expanded `step_sequence` steps + overlays). `semantic_check`
> now requires every rendered slot's `"<scene.id>.<slot.id>"` id; `convention_check`
> audits shape-bearing slot kinds against `_SLOT_KIND_SHAPE` (BLOB→path, BOX→rect
> as forward seams for P7.3; composite/text kinds skipped). Purely additive — no
> `schema.py` touch, every error substring preserved. +12 tests incl. a
> both-directions engine/verifier drift guard. 1108 green. **Next: P7.1.**

> **`Tier.overlays` now render — landed 2026-06-13.** A follow-up to the Step 6
> review (overlays were accepted by the schema + promised in the docstring but
> never laid out). A SCENE_ROW tier with `overlays` carves a bottom gutter strip
> (`tier_overlay_gutter_frac`, default 0.3 of the band — first-cut heuristic);
> overlays lay out there via the same `_layout_scene` path + cascade and publish
> anchors before transitions resolve, so a `TierEdge` (e.g. a `departs` arrow)
> connects a row scene to an overlay (the aspirin/COX-1 departing-fragment
> shape). Overlay-free tiers keep the full band (byte-identical). +4 tests; 1082
> green. Remaining pre-existing note: a `TierEdge` to the step_sequence
> `base.id` validates but has no laid-out scene (fails loud at layout).

> **Phase R (module decomposition)** is now tracked in
> [`V3_EXECUTION_PLAN.md` → Phase R](V3_EXECUTION_PLAN.md). It splits the six
> largest modules (pathway_layout 2494 → 6 sub-modules, schema, chemistry,
> nucleic_acids, compositor, loader) into focused files behind re-export shims —
> pure mechanical, no behaviour change, 1025-green at every step. **Phase R
> COMPLETE — R1–R6 all landed 2026-06-11** (R1: `pathway_layout.py` 2494 → 652 ln
> into `_pathway_{glyphs,common,rings,bands,routing,labels}.py`; R2: `schema.py`
> 709 → 120 aggregator + `_enums`/`_v2_models`/`_v3_models`; R3: `chemistry.py`
> 801 → `_mol_render`/`_reaction_render`; R4: `nucleic_acids.py` 796 → `_dna`/`_rna`;
> R5: `compositor.py` 766 → 615 + `_svg_post`; R6: `loader.py` 358 → 318 + `_palette`).
> Each is an AST-verified pure move (every moved fn/class byte-identical to HEAD),
> no import cycle, full public surface re-exported. R2 (load-bearing IR) was
> signed off and adversarially verified (4-lens workflow) — the `model_rebuild()`
> block kept in the aggregator resolves the `Figure↔Tier` forward-ref cycle.
> Runs independently of Steps 5–7. **Remaining Phase-R deferrals:** `tier_layout.py`
> (after Step 6) and `lab_equipment.py` (low payoff).

> **Steps 5–7 are now planned in detail in [`V3_EXECUTION_PLAN.md`](V3_EXECUTION_PLAN.md).**
> That doc is the active forward plan: it folds in a verified 17-agent
> architecture scan (2026-06-11), schedules the dispatch/label/style unifications
> as Phase-0 gates *in front of* each step (seam-before-step), and lists ~30
> small action items with explicit `file:line` fixes. Read it before starting
> Step 5. The deferred nits below are now tracked as **P5.4** there.

---

## Deferred nits (from Step 4 review — revisit during Step 5/6)

- ✅ ~~Sub-pixel molecule centering from `int()` render size.~~ (P5.4 / C7)
- ✅ ~~Non-molecule attach-parent extent (currently uses scene frame, not slot bbox).~~ (P5.4 / C7 — now per-slot `_slot_bbox_size`)
- ✅ ~~Text `center` anchor = baseline, not midline.~~ (P5.4 / C7)
- Duplicate-edge `ir_id` uniquifier.
- Partial `height_frac` fallback.
- `rail:` bare endpoints in `TierEdge.from_ref`/`to_ref`.

---

## Mechanism-figure fidelity — Step 7 acceptance criteria (MF-1/2/3)

When Step 7 lands, a naive reader must be able to trace the mechanism from the
active sites alone. Three hard requirements:

| # | Requirement |
|---|---|
| MF-1 | **One atom convention everywhere.** Heteroatoms (O, N, …) render as coloured **letters**, never bare dots. Residue fragments are real rendered molecular fragments. |
| MF-2 | **Curly arrows terminate on atom anchors.** Arrow endpoints come from `AnchorRegistry.resolve("scene.slot.atom")` — never eyeballed coordinates. |
| MF-3 | **Placement is solved, not guessed.** The scene solver (Step 5) prevents co-located slots from overlapping. |

Evidence committed in `showcase/`: `aspirin_cox1_northstar_handcomposed.png`
(the failing hand-composed figure) vs `aspirin_cox1_anchored_proof.png` (one panel
done the right way). Reference target spec: `references/aspirin_COX1_figure_spec.md`.

---

## Detail docs

- **`V3_IR_NODESHAPES_PROPOSAL.md`** — node shapes, all §2 decisions, full annotated build order. Source of truth for what each step entails.
- **`V3_SCENE_CHASSIS_SCOPE.md`** — agreed 3-layer plan (scene graph / tier compositor / step model) and the motivating gaps.
- **`V3_FEATURES.md`** — full deferred-feature backlog including the chemistry track (V3-C1 through V3-C5) and all other non-chassis features.
