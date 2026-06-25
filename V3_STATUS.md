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

**Current test count:** 1205 passing. The V3 scene **engine** is feature-complete
(numbered steps 1–7). **But the work is NOT done** — see the pub-grade phase below.
Pub-grade dims closed: 1 (sizing), 2 (labels), 3 (orientation/D6), 4 (layering·contrast);
dim 5 mostly done; remaining dim 6 (publication preset) + optional render-critic.

> **Pub-grade dim-2 (leader lines) — landed in full 2026-06-24 (both halves).**
> (1) `place_labels` gained a leader-eligible *whitespace ring search*: a
> `LabelRequest.leader` label that exhausts the nudge ladder parks in the nearest
> open whitespace instead of overlapping its anchor. (2) `tier_label_leaders` (a
> post-pass, sibling of the pathway `pathway_extlabel_leaders`) tethers any drifted
> slot/edge label back to its glyph with a hairline dashed `_leader_line`. Slot +
> edge labels set `leader=True`. **Fixes D1** (residue/`Ser530` drift) **and D3**
> (`breaking`/`new bond` now park off the shaft + tether) across the corpus; snug
> labels stay leader-free. Residual: a label with no whitespace in its band still
> overlaps (band-height, dim 1/5). Suite 1177 → 1186. See `PUBGRADE_ROADMAP.md`
> dim 2.

> **Pub-grade D4 (transition labels) — fixed 2026-06-24.** A `TierEdge.label` was
> silently dropped (the transition loop drew only the arrow). It now lowers to a
> `<tedge_id>_label` text entry placed above the shaft midpoint via
> `_transition_label_pos` (perpendicular offset onto the arrow's upper side).
> Confirmed on corpus figs 04 (`substrate`) and 09 (`[O]`/`new S-S bond`), which
> previously rendered bare arrows. Suite 1186 → 1189.

> **Pub-grade D9 (labels struck through by transition arrows) — fixed 2026-06-24.**
> A cross-cell transition runs through the scene's content vertical centre but
> resolves at the tier level after each scene placed its labels, so a side-by-side
> slot label could land on the not-yet-drawn arrow (fig 03 "hydroxide"
> struck-through). `_layout_scene` now reserves transition lanes (strips at `fcy`
> in the cell side margins) as label occupancy, pushing such labels above/below
> the row. Suite 1189 → 1190.

> **Pub-grade dim 4 — layering · contrast — CLOSED 2026-06-25.** Edge colour
> vocabulary now semantically distinct: `hbond` → blue `#1A6FC9` (biochem
> H-bond convention; resolves conflict with inhibits red); `dashed` → neutral
> gray `#888888` (partial/TS bonds); `curly` (electron-flow arrows) → dark
> auburn `#8B2500` so they don't merge with black bond ink when arrows cross
> structures. `hbond` also gets its own thinner `stroke_width=1.5` (delicate
> dash). `inhibits` T-bar stays red — now the **only** red edge.
> Per-type `stroke_width` in `_EDGE_DEFAULTS` is now honoured by `_edge_group`
> (caller can still override). +6 tests. Suite 1205 → 1211.

> **Pub-grade dim 3 — orientation (D6) — CLOSED 2026-06-25.** Molecules were posed
> in RDKit's canonical pose with no aiming, so a substrate's attacked atom could
> face away from the attacking residue (worst: fig 08; also 02/01/aspirin
> acceptance). New: `_orient_conformer` (`primitives/_mol_render.py`) rigidly
> rotates the *shared* conformer about its centroid so a chosen atom faces a
> chosen direction, applied before `_natural_box`/draw so box + depiction +
> anchors move together; **gated to the tier path** (`target_bond_px` set) so the
> leaf/panel path is byte-identical. `_scene_orientations` (`layout/tier_layout.py`)
> infers `(reactive_atom, direction)` from each `CURLY` SceneEdge + the `Attach`
> placing the two reactants, threaded into **both** the size predictor
> (`molecule_natural_size`) and the renderer so the posed box matches the drawn
> box. An **80° deadband** leaves already-readable structures in canonical pose
> (corpus 05 — the proposed 30–45° was too tight and re-posed it into a caption
> collision). v1 = curly attack edges only; H-bond-driver, reflection tie-break,
> and cross-step scaffold consistency are deferred (logged in
> `PUBGRADE_ROADMAP.md`). +15 tests (`tests/test_orientation_d6.py`, incl. a
> geometric end-to-end check + a deadband-window guard). Suite 1190 → 1205. See
> `D6_ORIENTATION_SCOPE.md`.

---

## ← CURRENT FOCUS: the pub-grade phase (post-feature-complete)

The engine is feature-complete; the **output is not yet publication-grade**, and a
review (2026-06-14) found the real reason: **`SKILL.md` is out of sync with the V3
engine.** It still documents the pre-chassis leaf IR and classifies
`mechanism_cartoon` as a **Leaf** figure, with zero authoring guidance for
Tier/Scene/Slot/residue/blob/content-sizing. The **entire Steps 1–7 arc never
updated the skill.** Consequences:

- A **skill call cannot produce a tier figure** — it emits leaf IR (entities +
  relations) → boxes-and-arrows, not the chassis. So the chassis is unreachable
  through the front door.
- Every tier figure to date — **including the aspirin acceptance artifact** — was
  hand-authored in a Python script. The chassis corpus is therefore **N = 1**
  (the ~10 fixture figures are all *leaf*, testing the old engine), and
  "pub-grade by default via a skill call" is currently **structurally impossible**.

> **Leaf vs tier:** a *leaf* figure is the V2 model — flat `entities` + `relations`
> → graph-laid boxes-and-arrows (mapk_cascade, gpcr_signaling, …). A *tier* figure
> is the V3 chassis — `tiers` → `scenes` → `slots` (molecules/residues/blobs)
> placed by relative anchoring, with atom-anchored edges (the aspirin figure).
> `render_figure` dispatches on which container is populated.

**Three findings, in priority order — everything else waits behind these:**

1. ✅ **DONE (2026-06-15) — `SKILL.md` synced to the chassis.** Added a full
   *Tier figures (the V3 scene chassis)* section (Tier/Scene/Slot/Attach/
   SceneEdge/TierEdge/Rail/StepSequence + the slot-kind anchor grammar);
   reclassified `mechanism_cartoon` as a **tier** archetype routing to JSON
   authoring; pointed its fixture at `showcase/aspirin_cox1_v3_acceptance.json`;
   noted molecule sizing is automatic. **Verified by authoring + rendering two
   *new* tier figures through the documented `render-spec` path** (a chymotrypsin
   acylation mechanism and the doc's own worked skeleton) — both render through
   the chassis (not boxes-and-arrows) and pass semantic/legibility/convention.
   **Engine-can't-express gaps logged for P.2** (see below).
2. ✅ **DONE (2026-06-15) — `PUBGRADE_ROADMAP.md` written.** Folds in the
   6-dimension scout report, the concrete observed-defect list (D1–D6, grounded
   in the aspirin artifact + the P.1 renders), the engine-can't-express gaps
   (G1–G5, carried over from P.1), and the render-critic + corpus plan
   (**corpus-first, critic-after**). The 6 dims: sizing ✅ / labels ~ /
   orientation ☐ / layering·contrast ☐ / density·arrows ☐ / pubgrade-defaults ☐
   — all but sizing deferred until the corpus reprioritises them.
2. **Write the pub-grade roadmap doc** (`PUBGRADE_ROADMAP.md`). Capture the
   6-dimension scout report (sizing ✓ / labels ~ / orientation / layering·contrast
   / density·arrows / pubgrade-defaults), the concrete defect list, and the
   **critic + corpus** plan — currently trapped in chat.
3. ✅ **DONE (2026-06-15) — corpus is real (N = 10).** 10 diverse tier figures
   authored as IR JSON through the skill path under `showcase/corpus/` (see its
   README), pinned by `tests/test_corpus_tier_figures.py` (suite 1156 → **1177**).
   None is a one-off Python script. **Finding:** all 10 render clean, and the
   label defects (D1 residue/glyph labels drift, D2 caption clipping, D4
   transition labels overlap arrows) **recur across figures** — so they are
   general chassis behaviour, not aspirin tuning. **Dimension 2 (labels / leader
   lines) is the corpus-confirmed top pub-grade priority.**

**Once #1–#3 land, reassess whether the remaining scout dimensions** (orientation,
leader-line labels, density/arrows, the publication preset + routing flip, the
render-critic) are still needed as scoped — the corpus will tell us.

**Corrections logged (2026-06-14):**
- **Correctness gating comes AFTER cleanness** — an unreadable-but-correct figure
  is worthless (you can't read the handwriting). Cleanness first.
- The current defects are **concrete and fixable** ("that should sit a little
  left", "the arrowhead needs ~1cm clearance", "can't tell which arrowhead that
  is") — **not** uncanny-valley. Rules can fix them.

**Pub-grade keystone (content-aware molecule sizing + label-occupancy seed)** landed
2026-06-14 (commit `131a918`) — but validated on the one hand-authored figure;
its generality is **unproven until the corpus exists** (finding 3).

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
