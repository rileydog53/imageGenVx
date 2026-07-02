# V3 — Potential Features (out of scope for v2.x)

Everything here is **deliberately deferred** — out of scope for the current
v2.x line, parked for a possible v3. These are not bugs or open defects (those
live in `BACKLOG.md`); they are larger features or capability expansions, most
of which need a pipeline change rather than a localized fix.

Sourced from the old `BACKLOG.md` stretch goals (S1–S7), the v1 chemistry
stretch (P1), and the deferred items in `LIMITATIONS.md`.

Priority is rough intent, not commitment.

---

## Layout & routing

| # | Feature | Why deferred | Priority |
|---|---|---|---|
| V3-L1 | **Orthogonal / curved arrow routing** with entity avoidance. Pathway relations are straight bbox-edge-to-bbox-edge lines today, so an arrow can cross an unrelated node in a busy graph. | Needs a routing pass (channel/spline) in the layout engine. | Medium |
| V3-L2 | **Force-directed label placement** for dense pathways (replace the greedy relax-and-retry ladder). | Current placement degrades gracefully but isn't globally optimal. | Medium |
| V3-L3 | **Per-arrow conditional rendering in pathways** — different reagents/conditions per relation, as reaction layout already honors. | Schema supports `relation.conditions`; pathway layout doesn't draw them yet. | Low |

## Chemistry & molecular-structure rendering track (parked — not attempting in v2.x)

The whole chemistry-rendering deepening is deferred as one track. C3 is the
enabler the two arrow/structure items depend on; C1 is the pipeline rewrite at
the end.

| # | Feature | Why deferred | Priority |
|---|---|---|---|
| V3-C3 | **Per-element ids for `reaction_scheme`** groups so `convention_check` / `semantic_check` can audit each molecule, not just the composite `reaction_0` anchor. **Enabler** for C4/C5. | RDKit emits one composite SVG group today. | Medium |
| V3-C4 | **Curved mechanism arrows** (arrow-pushing) anchored on specific atoms. | ~~Needs precise atom anchoring → depends on C3's per-element ids.~~ **Atom anchoring now exists** (V3 keystone: `render_molecule_anchored` + `AnchorRegistry`, atom-map → anchor). Remaining work is the *curly-arrow primitive itself*, with endpoints taken from anchors (see MF-2 below). Promoted **High** — it is the #1 legibility blocker for mechanism figures. | High |
| V3-C5 | **Newman / chair projections** for conformational chemistry. | Specialized custom geometry outside the RDKit 2D path. | Low |
| V3-C1 | **True 3D ball-and-stick** chemistry rendering. Today `style="ball_stick"` is a 2D approximation (bigger atom labels, wider bonds, a visual lean). | Full 3D requires a rendering-pipeline rewrite; do last. | Low |
| V3-C2 | **3D protein structure integration** via a PyMOL handoff (ribbon/surface renders dropped into a panel). | Out of the vector-schematic scope; needs an external renderer bridge. | Low |

### Mechanism-figure fidelity — acceptance criteria (from the aspirin/COX-1 north-star read, 2026-06-10)

A hand-composed max-fidelity aspirin→COX-1 acetylation figure was built to scope
the gap between the placement chassis (Steps 1–4) and a *readable* mechanism
figure. Read cold, as a naive reader, the mechanism was **not derivable** from
the active sites — and the failures localised cleanly to three things the chassis
must **enforce**, not paint by hand. These are hard requirements (acceptance
criteria), not optional polish. Evidence (committed in `showcase/`):
`aspirin_cox1_northstar_handcomposed.png` (the failing hand-composed figure) vs
`aspirin_cox1_anchored_proof.png` (one panel done the right way — atom-anchored).
(Only the rendered evidence is committed; the figures were composed ad hoc with
workflow-authored glyph functions, so there is no durable repro script.)

The tell: every element rendered through the **real `render_molecule` primitive**
(aspirin, salicylate, arachidonic acid) read perfectly; every **hand-placed glyph**
(residue sticks, eyeballed curly arrows) was illegible. So the cure is to make the
mechanism elements first-class anchored primitives — not better hand-drawing.

| # | Requirement | Maps to |
|---|---|---|
| MF-1 | **One atom convention, everywhere.** Oxygen (and every heteroatom) must render through the *same* convention as the molecule renderer — a coloured atom **letter** (`O`), never a bespoke bare coloured **dot**. Residues / mechanism fragments are real rendered molecular fragments, not dot-glyphs. *(Reader defect: aspirin drew `O` letters while hand-glyphs drew red dots — two conventions in one figure read as ambiguous markers.)* | Primitive refresh (Step 7); supersedes the dot-based residue glyphs |
| MF-2 | **Curly arrows terminate on atom anchors.** The arrow-pushing primitive takes its endpoints from `AnchorRegistry.resolve("scene.slot.atom")` (the keystone already publishes atom-map → anchor), so every head lands on a *real* atom — never eyeballed coordinates pointing into empty space. *(Reader defect: a step-2 curly arrow pointed into the cavity void, connected to no atom.)* | **V3-C4** (now High); keystone done, primitive pending |
| MF-3 | **Placement is solved, not guessed — no overlaps.** The scene solver must keep co-located slots (e.g. His513 vs. the bound ligand) from overlapping; the keystone/scene-frame *content extent* must drive separation. *(Reader defect: in step 1 the His513 ring was drawn on top of the aspirin — one unreadable tangle.)* | **Scene solver — proposal §3 Step 5** (topological attach/offset pass); related to V3-L2 |

When Step 5 (solver) and Step 7 (primitive refresh) are planned, these three are
**gating acceptance tests** for "the aspirin/COX-1 reproduction is faithful":
a reader with no prior knowledge must be able to trace the mechanism from the
active sites alone.

## Input & interoperability

| # | Feature | Why deferred | Priority |
|---|---|---|---|
| V3-I1 | **Import standardized pathway formats** (BioPAX / SBML / SBGN) → IR. | Large parser surface; needs a format→IR mapping spec. | Low |
| V3-I2 | **LaTeX / TikZ export** for direct manuscript inclusion. | New exporter backend alongside SVG/PNG/PDF. | Low |

## Output & presentation

| # | Feature | Why deferred | Priority |
|---|---|---|---|
| V3-O1 | **Animated / multi-frame figures** (step-reveal builds for talks). | Needs a timeline/frame model on top of the static compositor. | Low |

## Styling & typography

| # | Feature | Why deferred | Priority |
|---|---|---|---|
| V3-S1 | **Automatic palette selection** keyed on entity-type mix. | Style presets are fixed today; auto-selection needs a heuristic. | Low |
| V3-S2 | **Extended glyph coverage** — superscript minus (U+207B) and other scientific glyphs the system cairo font lacks render as tofu; prefer ASCII today. | Font-embedding / glyph-substitution pass. | Low |

---

## How to use this file

- Items here are **future features**, not open bugs. A real defect in shipped
  behavior goes in `BACKLOG.md`.
- When v3 starts, promote chosen items into a `PLAN.md` for that milestone and
  delete their rows here as they land (git history keeps the record).
