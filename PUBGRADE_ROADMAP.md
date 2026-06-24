# Pub-grade Roadmap (Phase P)

Where the V3 chassis goes from *feature-complete* to *publication-grade by
default*. The engine renders correct tier figures (Steps 1–7); the skill door now
opens onto the chassis (P.1, 2026-06-15). What remains is **quality** — making a
cold skill call produce a *clean, readable* figure without hand-tuning.

> Read order: `V3_STATUS.md` → "CURRENT FOCUS" first, then this. This doc is the
> P.2 deliverable — it captures the 6-dimension scout report, the concrete defect
> list, and the render-critic + corpus plan that were previously only in chat.

---

## Two standing corrections (do not relitigate)

1. **Cleanness before correctness gating.** An unreadable-but-correct figure is
   worthless — you can't read the handwriting. Legibility/layout defects outrank
   chemical-correctness gating in priority.
2. **The defects are concrete and rule-fixable** — "sit it a little left", "the
   arrowhead needs ~1 cm clearance", "can't tell which arrowhead that is". They
   are **not** uncanny-valley. Rules can fix them; do not over-engineer.

---

## The missing instrument: render-critic + corpus

The reason "pub-grade by default" has been unmeasurable is there is **no quality
instrument** — only the three pass/fail verifiers (semantic / legibility /
convention), which catch *broken*, not *ugly*. Two pieces close that:

- **The corpus (P.3, next).** ~10 diverse figures authored **through the skill
  path** (mechanism, multi-step, a tier pathway, a binding event, …), added to
  the test/showcase set. This is the prerequisite for everything below: it makes
  overfitting to aspirin *visible* and turns "by default" into something measured
  rather than asserted. The current chassis corpus is effectively N≈3 (aspirin +
  the two P.1 verification figures); none are regression-pinned yet.
- **The render-critic (deferred).** A vision-scored pub-grade rubric — render the
  figure, score it on legibility / spacing / label placement / arrow clarity /
  overall polish, feed the score back. This is the missing closed loop. Scoped
  *after* the corpus exists, because the corpus defines what the rubric must
  reward.

**Order is load-bearing: corpus first, then critic.** A critic with no corpus
has nothing to score against; a corpus with no critic still surfaces defects by
eye (as P.1 already did).

---

## The 6 scout dimensions

Status keys: ✅ landed · ~ partial · ☐ not started. **All but `sizing` are
deferred until the corpus (P.3) confirms they still matter as scoped** — the
corpus is the bottleneck and will reprioritise this list.

| # | Dimension | State | What's wrong / what it needs |
|---|---|---|---|
| 1 | **sizing** | ✅ | Content-aware molecule sizing landed (keystone `131a918`): every structure renders at one consistent bond length, no hand-set `scale`. **Generality unproven until P.3** — validated on one hand-authored figure. |
| 2 | **labels** | ~ | Label-occupancy seed landed; **leader lines are the real fix and are now confirmed REQUIRED** (see note ↓). Observed defects: scene captions clip, residue labels float far from their slot, edge labels (`H-bond`, `new bond`) crowd onto arrows. The single biggest readability gap. |
| 3 | **orientation** | ☐ | Molecules are posed as RDKit lays them out, not so the reaction *reads* left-to-right. A mechanism should flow with the nucleophile/electrophile oriented consistently across steps. |
| 4 | **layering · contrast** | ☐ | Band fills, slot colours, and arrow strokes are not tuned for figure-ground contrast; overlapping ink can lose the eye. Polish pass. |
| 5 | **density · arrows / containment** | ~ | Landed: transition-arrow clearance (D5); **content-aware per-tier cell width** (scenes no longer overflow into neighbours); **content centering** in the cell (chains no longer hang out one side); **inter-tier band gap** + **content-aware band heights** (bands tall enough for their labels); **4-wall label containment** (labels can't spill out of their band onto the page). Still open: arrows are fixed-geometry not ink-relative; blob/cluster sizing is uneven (dim 1). |
| 6 | **pubgrade-defaults** | ☐ | No first-class `publication` style preset, and `mechanism_cartoon` still defaults through the generic path. Needs a real preset + the routing flip so the *default* call is the pub-grade call. |

---

## Dimension 2 (labels): why a placement tweak isn't enough — leader lines required

**Experiment (2026-06-15).** The cheap hypothesis was that D1 is just a bad anchor
box: slot labels anchor to the uniform `tier_slot_size`, so a small residue/glyph
gets a big keep-away box and its label drifts. Two rule-only fixes were tried and
**both regressed the strict legibility gate**:

1. *Anchor the label to the slot's real drawn box* (`slot_extents`). Visibly fixed
   the common case (chymotrypsin residue labels snapped back beside their glyphs) —
   but regressed the **aspirin acceptance artifact**: a bottom-attached residue
   (`His513`), now anchored close, places its label *below* the glyph and spills
   across the tier boundary into the summary band, colliding with `arachidonic
   acid`. The uniform box had been silently acting as a keep-away margin.
2. *Reorder slot-label priority to prefer sides* (`right`/`left` first). Fixed the
   spill but cascaded: in dense active-site scenes the residue sits directly
   above/below a **wide** substrate, so the horizontal sides aren't clear either —
   broke `01`, `03`, `08`.

**Conclusion:** in a packed mechanism band there is often *no* clear position
adjacent to the glyph — neither vertical (spills out of the band) nor horizontal
(hits the substrate). The only correct fix is **leader lines**: place the label in
the nearest available whitespace and draw a thin connector back to the slot anchor,
with the connector itself seeded into `place_labels` occupancy. This is a real
feature (a new label-placement mode), not a parameter change — scope it as such.
The two rule tweaks were reverted; the suite stays at 1177.

---

## Concrete defect list (observed)

Grounded in the aspirin acceptance artifact and the two P.1 verification renders
(chymotrypsin acylation + the doc skeleton). Each is concrete and rule-fixable.

- **D1 — residue labels float.** A residue attached `top`/`bottom` with an offset
  gets its label placed far to the right of the structure (e.g. "Ser195" drifting
  to the band's right edge), reading as detached. (dim 2)
- **D2 — scene captions clip / drop lines.** Multi-line scene `label`s (`"\n"`)
  lose their second line in tight bands ("Tetrahedral" without "intermediate").
  *Fix:* reserve caption headroom from the measured label height. (dim 2)
- **D3 — edge labels collide with arrows.** `H-bond` / `new bond` / `breaking`
  land on top of the line they annotate (the warned "placed with overlap"). *Fix:*
  leader lines or a perpendicular offset off the edge midpoint. (dim 2)
- **D4 — transition labels overlap the arrow shaft.** A `TierEdge` label
  ("hydrolysis", "peptide substrate") sits across the arrow rather than above it.
  *Fix:* place at the arrow midpoint with a fixed above-shaft offset. (dims 2, 5)
- **D5 — arrowhead clearance.** ✅ FIXED 2026-06-15. Cross-cell transition
  arrows now use a dedicated `tier_transition_standoff` (20px, ~one bond length),
  separate from the tight `tier_edge_standoff` that intra-scene atom edges need —
  so the arrowhead clears the next scene's structure without pulling curly/H-bond
  arrows off their atoms. Guarded by a behavioural test (the standoff moves the
  transition arrow but leaves intra-scene edges byte-identical). (dim 5)
- **D6 — reaction doesn't read directionally.** Within a step the substrate may be
  posed so the attacked atom faces away from the attacking residue. *Fix:* the
  orientation pass (dim 3).
- **D7 — content escapes its band ("out of the box").** ✅ FIXED 2026-06-15.
  Scenes overflowed their cell into neighbours (cells were sized for one slot),
  horizontal chains hung off one side (root pinned at cell centre), and labels
  spilled out of the gray band onto the white page. Fixed by content-aware
  per-tier cell width, post-solve content centring, content-aware band heights
  (small-frac bands keep a natural-height floor), an inter-tier band gap, and
  4-wall per-cell label containment. Confirmed on figs 06/10/01.
- **D8 — steps don't separate / merge into one blob-chain.** ✅ FIXED 2026-06-15
  (same change): neighbouring scenes now sit in distinct, padded cells, so a row
  of steps reads as discrete steps instead of one continuous chain.

---

## Engine-can't-express gaps (logged during P.1)

The schema validates more than the renderer draws. The skill stays inside the
supported surface today; these are the candidate engine extensions if the corpus
demands them. **Do not promise these in `SKILL.md` until the engine cashes them.**

- **G1 — slot kinds `box` / `group` / `generic`** validate but raise
  `NotImplementedError` at layout. Only `molecule`/`residue`/`glyph`/`blob`/`text`
  draw. (`group` nesting is validated but never laid out.)
- **G2 — tier roles `summary_bar` / `band`** render a band background only, no
  inner scenes. Any content band must use `scene_row` + `style.band_fill`.
- **G3 — `Tier.content`** (an embedded leaf `Figure` inside a band) is not laid
  out — "every other role lays out no scenes today."
- **G4 — attach `edge` `anchor` / `custom`** are not solved (face + cavity edges
  only).
- **G5 — named residues are a fixed set** (`ser`/`his`/`tyr`/`cys`/`lys` +
  `ser530`/`his513` aliases). Others need a raw SMILES with a mapped reactive atom.

---

## Sequencing

```
P.1 ✅ sync SKILL.md to the chassis            (door opens onto the chassis)
P.2 ✅ this doc                                 (the plan, written down)
P.3 ☐ build the ~10-figure corpus via the skill (makes "by default" measurable)
        │
        └─► reassess dims 2–6 + the render-critic against what the corpus shows
```

After P.3, the corpus reprioritises dims 2–6 and tells us whether the
render-critic is worth building as scoped. **Do not start the deferred dimensions
or the critic before P.3.**

---

*Authored 2026-06-15 (Phase P.2). Defect list and gaps grounded in the aspirin
acceptance artifact + the P.1 verification renders. Update as the corpus lands.*
