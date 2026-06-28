# V3 — Build Status

Orientation for any agent starting a V3 session. The V3 scene chassis is
**feature-complete** (numbered Steps 1–7) and all six pub-grade scout dimensions
are closed.

> **Tomorrow's work + the active plan live in [`HANDOFF.md`](HANDOFF.md). Read
> that first.**

**Suite:** 1239 passing (2026-06-28). This file is the lean status header; the
per-commit landed records were pruned 2026-06-26 (they live in git history).

> **2026-06-27:** β-lactamase mechanism rebuilt (4 real species-scenes) + three
> general engine fixes — residue protonation (no radical dot), MF-1 radical lint,
> and tether-aware leader placement (B1 caption-crossing fixed). G6 charge
> resolved via SMILES (no schema change). See `HANDOFF.md` → *Landed 2026-06-27*.

---

## What's done (full records in git history)

- **Engine, Steps 1–7** — anchor-return protocol + figure-global registry; schema
  (`Tier`/`Rail`/`TierEdge`/`Scene`/`Slot`/`Attach`/`SceneEdge`/`StepSequence`/
  `Step`/`StepDelta` + `Figure.tiers`); tier compositor + band chrome; scene
  solver (topological attach/offset + co-location de-overlap); step expansion;
  primitive refresh (curly arrows, TS partial bonds, organic shaded blobs,
  per-atom anchors). Aspirin/COX-1 acceptance render landed
  (`showcase/aspirin_cox1_v3_acceptance.{json,png,svg}`).
- **Pub-grade dims 1–6 — all closed** (details in `PUBGRADE_ROADMAP.md`): sizing
  (content-aware molecule + per-primitive glyph/blob natural box); labels (leader
  lines, both halves); orientation (D6 rigid pose); layering·contrast (semantic
  edge colours); density·arrows (ink-relative standoff + edge-to-edge attach
  spacing); publication preset + routing flip.
- **Phase R** — module decomposition R1–R6 (pathway_layout, schema, chemistry,
  nucleic_acids, compositor, loader split behind re-export shims; pure moves).
- **Skill door (Phase P.1–P.3)** — `SKILL.md` synced to the chassis; 10-figure
  tier corpus pinned (`showcase/corpus/`, `tests/test_corpus_tier_figures.py`).

---

## Still open — canonical list (carried into `HANDOFF.md`)

**Tomorrow's focus (betalactamase critique, 2026-06-26):** mechanism
chemical-correctness + figure polish on the β-lactamase figure. **Full plan in
[`HANDOFF.md`](HANDOFF.md).**

**Inherited engine backlog:**
- Deferred nits: duplicate-edge `ir_id` uniquifier; partial `height_frac`
  fallback; `rail:` bare endpoints in `TierEdge.from_ref`/`to_ref`.
- Phase-R deferred splits: `layout/tier_layout.py`, `primitives/lab_equipment.py`;
  dead-code `_label_extent_w` removal (`_pathway_rings.py`).
- `StepSequence` per-step **edge**-delta op — today `StepDelta` is slot-granular
  only, so it can't express "the curly arrow appears only in Step 2" (the aspirin
  + betalactamase mechanism rows are authored scenes for this reason).
- Overlay `TierEdge` → step_sequence `base.id` has no laid-out scene (fails loud);
  overlay gutter fraction (`tier_overlay_gutter_frac` = 0.3) is a first-cut heuristic.
- Orientation v2 — cross-step consistency (identical-SMILES + MCS scaffold) and
  H-bond/dashed drivers LANDED 2026-06-28. Still deferred: reflection tie-break
  (no driving case) and collision-aware orientation (lets the 80° deadband
  tighten). Rationale: `D6_ORIENTATION_SCOPE.md`.
- Leader residual: a label with no whitespace anywhere in its band still overlaps
  (band-height limit, dims 1/5).
- Archetype aspect-ratio capping (run10 critique #3) — tier-level concern.
  (Auto-fit / balanced reflow — B3 band dead-space — landed 2026-06-27: SCENE_ROW
  naturals measure real content via the scene solver; `height_frac` is now soft —
  naturals are floors, surplus splits by frac. See git history.)
- Render-critic (optional) — a vision-scored pub-grade rubric; corpus-first.
- Engine-can't-express gaps G1–G5 (+ proposed G6 charge rendering) →
  `PUBGRADE_ROADMAP.md`.
- Larger future features (V3-C/L/I/O/S track) → `V3_FEATURES.md`.

---

## Mechanism-figure fidelity — standing acceptance criteria (MF-1/2/3)

A naive reader must be able to trace a mechanism from the active sites alone:

| # | Requirement |
|---|---|
| MF-1 | One atom convention everywhere — heteroatoms render as coloured **letters**, never bare dots; residues are real molecular fragments. |
| MF-2 | Curly arrows terminate on atom anchors resolved from `AnchorRegistry.resolve("scene.slot.atom")` — never eyeballed coordinates. |
| MF-3 | Placement is solved, not guessed — the scene solver prevents co-located slots from overlapping. |

Evidence in `showcase/`; reference target `references/aspirin_COX1_figure_spec.md`.

---

## Doc map

- **`HANDOFF.md`** — active next-session plan (betalactamase mechanism figure +
  open backlog). **Start here.**
- **`PUBGRADE_ROADMAP.md`** — pub-grade dimensions, engine-can't-express gaps
  (G1–G5), render-critic + corpus plan, standing corrections.
- **`V3_EXECUTION_PLAN.md`** — architecture-decision reference (the dispatch /
  `LoweringPlan` model + the load-bearing "Do NOT" invariants). All action items
  landed; kept for the invariants.
- **`V3_FEATURES.md`** — deferred future-feature backlog (V3-C/L/I/O/S).
- **`V3_IR_NODESHAPES_PROPOSAL.md`** — node-shape schema tables + settled design
  decisions (Steps 1–7 shipped; cited by `ir/_enums.py`).
- **`V3_SCENE_CHASSIS_SCOPE.md`** — original 3-layer chassis rationale (shipped;
  retained for its §2 decisions).
- **`D6_ORIENTATION_SCOPE.md`** — orientation rationale-of-record (cited by code).
- **`DECISIONS.md`** — append-only architecture decision log.
  **`LIMITATIONS.md`** — known limitations.
  **`BACKLOG.md`** — open defects.
  **`FEEDBACK.md`** — figure-quality intake.
- **`masterhand/EDITOR_LOOP_HANDOFF.md`** — separate unstarted workstream (in-chat
  WYSIWYG figure editor).
