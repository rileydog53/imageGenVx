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
| **5** | **Scene solver** — topological attach/offset pass + scene-local label placement. Acceptance: no overlapping slots (MF-3: His513-vs-ligand-tangle class of bug). | **← NEXT** |
| 6 | **Step expansion** — builder-layer slot-granular step delta expand to N concrete scenes. | Pending |
| 7 | **Primitive refresh + expansion** — curly arrows (V3-C4), TS partial bonds, organic shaded blobs, per-atom anchors. **Aspirin/COX-1 reproduction is the acceptance test** (gated by MF-1/2/3). | Pending |

**Current test count:** 1025 passing.

> **Phase R (module decomposition)** is now tracked in
> [`V3_EXECUTION_PLAN.md` → Phase R](V3_EXECUTION_PLAN.md). It splits the six
> largest modules (pathway_layout 2494 → 6 sub-modules, schema, chemistry,
> nucleic_acids, compositor, loader) into focused files behind re-export shims —
> pure mechanical, no behaviour change, 1025-green at every step. **R1 + R3–R6
> all landed 2026-06-11** (R1: `pathway_layout.py` 2494 → 652 ln into
> `_pathway_{glyphs,common,rings,bands,routing,labels}.py`; R3: `chemistry.py`
> 801 → `_mol_render`/`_reaction_render`; R4: `nucleic_acids.py` 796 → `_dna`/`_rna`;
> R5: `compositor.py` 766 → 615 + `_svg_post`; R6: `loader.py` 358 → 318 + `_palette`).
> Each is an AST-verified pure move (every moved fn/class byte-identical to HEAD),
> no import cycle, full public surface re-exported. **Only R2 (schema) remains —
> blocked on sign-off.** Runs independently of Steps 5–7.

> **Steps 5–7 are now planned in detail in [`V3_EXECUTION_PLAN.md`](V3_EXECUTION_PLAN.md).**
> That doc is the active forward plan: it folds in a verified 17-agent
> architecture scan (2026-06-11), schedules the dispatch/label/style unifications
> as Phase-0 gates *in front of* each step (seam-before-step), and lists ~30
> small action items with explicit `file:line` fixes. Read it before starting
> Step 5. The deferred nits below are now tracked as **P5.4** there.

---

## Deferred nits (from Step 4 review — revisit during Step 5/6)

- Sub-pixel molecule centering from `int()` render size.
- Non-molecule attach-parent extent (currently uses scene frame, not slot bbox).
- Text `center` anchor = baseline, not midline.
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
