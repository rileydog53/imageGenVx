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
| 2 | **labels** | ✅ | **Closed 2026-06-24** — D1/D2/D3/D4 all resolved. **Leader lines landed in full (both halves).** (a) `place_labels` gained a leader-eligible *whitespace ring search* — a `LabelRequest.leader` label whose adjacent + nudge slots are all blocked parks in the nearest open whitespace instead of landing on its anchor; (b) `tier_label_leaders` then tethers it (and any drifted label) back with a hairline dashed leader. Slot + edge labels set `leader=True`. Fixes **D1** (residue drift) and **D3** (`breaking`/`new bond` now park off the shaft + tether) across the corpus; snug labels stay leader-free. **Residual:** a label with genuinely no whitespace in its band (fig 01 `arachidonic acid`, a chain spanning the band) still overlaps — that's band-height (dim 1/5), not leaders. **Still open:** D2 caption clipping; a leader that crosses unrelated caption text (fig 05) is a minor aesthetic nit. |
| 3 | **orientation** | ✅ | **Closed 2026-06-25 (D6).** A rigid orientation pass poses each reactant so its reactive atom faces its partner. `_orient_conformer` (`_mol_render.py`) rotates the shared conformer about its centroid (verified rigid) before sizing/draw, gated to the tier path (leaf path byte-identical). `_scene_orientations` (`tier_layout.py`) infers `(reactive_atom, direction)` from each `CURLY` SceneEdge + the `Attach` placing the two reactants; threaded into both the size predictor and the renderer so the posed box matches. Fixes 08/02/01/aspirin-acceptance (carbonyl now faces the attacking Ser). An 80° deadband leaves already-readable structures (corpus 05) in their canonical pose. **Deferred to v2:** H-bond/dashed edges as drivers (v1 = curly only), reflection tie-break, cross-step scaffold consistency (fig 01's s1-vs-s2). See `D6_ORIENTATION_SCOPE.md`. |
| 4 | **layering · contrast** | ✅ | **Closed 2026-06-25 (dim-4).** Edge colour vocabulary made semantically distinct: `hbond` → blue `#1A6FC9` (biochem convention; resolves inhibits-red conflict); `dashed` → neutral gray `#888888` (partial/TS bond); `curly` (electron-flow) → dark auburn `#8B2500` (distinct from black bond ink so arrows don't merge with bonds on overlap). `hbond` also carries its own thinner `stroke_width=1.5` (delicate dash convention). `inhibits` T-bar stays red — now the **only** red edge. +6 tests. Suite 1205 → 1211. |
| 5 | **density · arrows / containment** | ~ | Landed: transition-arrow clearance (D5); **content-aware per-tier cell width** (scenes no longer overflow into neighbours); **content centering** in the cell (chains no longer hang out one side); **inter-tier band gap** + **content-aware band heights** (bands tall enough for their labels); **4-wall label containment** (labels can't spill out of their band onto the page). Still open: arrows are fixed-geometry not ink-relative; blob/cluster sizing is uneven (dim 1). |
| 6 | **pubgrade-defaults** | ✅ | **Closed 2026-06-25.** Shipped a first-class `publication` preset (`styles/publication.json`, inherits `cell_press`) that refines the content-channel keys reaching tier molecules/blobs/text: deeper CPK heteroatoms (pale amber S `#F9A825` → `#B07A0A`, orange P deepened), crisp near-black bonds + FG labels, and a lighter-fill/darker-stroke protein blob so a cavity residue stays legible. **Routing flip:** the schema default for `Figure.style_preset` is now `None` (was the literal `"cell_press"`), and `_resolve_style` falls a **tier** figure back to `publication` (leaf/panel keep `cell_press`) — so a cold skill call onto the chassis is the pub-grade call. Explicit preset (IR or `--style`) still wins. +9 tests. Suite 1211 → 1219. |

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

**Landed 2026-06-24 (both halves).** The feature is two cooperating pieces:

1. **Whitespace ring search** (`place_labels`). `LabelRequest` gained a `leader`
   flag. When a leader-eligible label exhausts the adjacent + nudge ladder, a new
   rung walks widening radii (`_LEADER_RING_RADII`) × 12 directions and parks it
   in the nearest clear whitespace instead of the last-resort *overlapping* slot.
   Default `leader=False` keeps the v1 ladder byte-identical for every other caller.
2. **Leader post-pass** (`tier_label_leaders`, sibling of the pathway
   `pathway_extlabel_leaders`). Tethers any slot/edge label whose placed edge is
   >`_TIER_LEADER_MIN_GAP` (22px) from its anchor box back with a hairline dashed
   connector, reusing the existing `_leader_line` primitive. Snug labels (gap <
   threshold) stay leader-free.

Slot + edge labels opt in (`leader=True`), so an otherwise-on-the-arrow label is
pushed into clear space *and* tethered. Closes **D1** and **D3**; suite 1177 →
1186. Residual: a label with no whitespace anywhere in its band still overlaps
(band-height, dim 1/5), and a leader can cross unrelated caption text (minor nit).

---

## Concrete defect list (observed)

Grounded in the aspirin acceptance artifact and the two P.1 verification renders
(chymotrypsin acylation + the doc skeleton). Each is concrete and rule-fixable.

- **D1 — residue labels float.** ✅ FIXED 2026-06-24. A residue attached
  `top`/`bottom` with an offset got its label placed far from the structure (e.g.
  "Ser530"/"Ser195" drifting to the band edge), reading as detached. The
  `tier_label_leaders` post-pass now draws a hairline dashed leader from the
  drifted label back to its slot box whenever the gap exceeds
  `_TIER_LEADER_MIN_GAP` (22px), so the association is visible; snug labels (e.g.
  His57 directly under its imidazole) get none. Confirmed across the corpus
  (figs 01/02/07/08). (dim 2)
- **D2 — scene captions clip / drop lines.** ✅ RESOLVED 2026-06-24 (superseded
  by D7). The cause was tight bands; the content-aware band-height work (D7)
  reserves enough headroom that every caption line now renders. Verified: all 20
  multi-line scene captions across the corpus render both lines (a token-presence
  sweep of the rendered SVGs found 0 dropped lines). No dedicated fix needed. (dim 2)
- **D3 — edge labels collide with arrows.** ✅ FIXED 2026-06-24. With both
  leader-line halves in place, an edge label (`H-bond` / `new bond` / `breaking`)
  that the nudge ladder can't clear now runs the `place_labels` whitespace ring
  search — it parks off the shaft in the nearest clear space and
  `tier_label_leaders` tethers it back to the edge midpoint. Confirmed: the
  aspirin `breaking` label moved up off the arrow with a leader, and the overlap
  warning for it is gone. (dim 2)
- **D4 — transition labels overlap the arrow shaft.** ✅ FIXED 2026-06-24. The
  real defect was worse than overlap: a `TierEdge.label` was **silently dropped** —
  the transition loop only drew the arrow, never the label (figs 04 `substrate`,
  09 `[O]`/`new S-S bond` rendered as bare arrows). Now the loop emits a
  `<tedge_id>_label` text entry placed by `_transition_label_pos` at the shaft
  midpoint, offset perpendicular onto the arrow's *upper* side (a near-vertical
  arrow offsets right instead), so the label rides above the arrow. Confirmed on
  figs 04/09. (dims 2, 5)
- **D5 — arrowhead clearance.** ✅ FIXED 2026-06-15. Cross-cell transition
  arrows now use a dedicated `tier_transition_standoff` (20px, ~one bond length),
  separate from the tight `tier_edge_standoff` that intra-scene atom edges need —
  so the arrowhead clears the next scene's structure without pulling curly/H-bond
  arrows off their atoms. Guarded by a behavioural test (the standoff moves the
  transition arrow but leaves intra-scene edges byte-identical). (dim 5)
- **D6 — reaction doesn't read directionally.** ✅ FIXED 2026-06-25. The substrate
  was posed (RDKit canonical) so the attacked atom faced away from the attacking
  residue, forcing the curly arrow to sweep across the structure (worst: fig 08
  ester carbonyl at relX=0.17 with =O pointing down while Ser203 attacks from the
  top). The dim-3 orientation pass now rigidly rotates the substrate's reactive
  atom (the `CURLY` SceneEdge `to_anchor`) toward the residue's `Attach` edge — and
  the residue's nucleophile back toward the substrate — *before* sizing and draw,
  so the box, depiction, and anchors move together. Confirmed on figs
  08/02/01/aspirin-acceptance; the curly arrow is now short and direct. An 80°
  deadband (a corpus finding — the proposed 30–45° was too tight and re-posed the
  already-fine fig 05 into a caption collision) leaves near-aligned structures
  untouched. (dim 3) — see `D6_ORIENTATION_SCOPE.md`.
- **D7 — content escapes its band ("out of the box").** ✅ FIXED 2026-06-15.
  Scenes overflowed their cell into neighbours (cells were sized for one slot),
  horizontal chains hung off one side (root pinned at cell centre), and labels
  spilled out of the gray band onto the white page. Fixed by content-aware
  per-tier cell width, post-solve content centring, content-aware band heights
  (small-frac bands keep a natural-height floor), an inter-tier band gap, and
  4-wall per-cell label containment. Confirmed on figs 06/10/01.
- **D9 — slot labels struck through by transition arrows.** ✅ FIXED 2026-06-24.
  A cross-cell transition (`s@right -> s@left`) runs horizontally through the
  scene's content vertical centre, but resolves at the *tier* level after each
  scene already placed its labels — so a side-by-side slot's label placed
  `right`/`left` at that height landed on the not-yet-drawn arrow and rendered
  struck-through (fig 03 "hydroxide"). `_layout_scene` now reserves two
  *transition lanes* (thin horizontal strips at `fcy` in the cell's side margins)
  as label occupancy, so such labels go above/below the row instead. Reserved
  unconditionally — a label in the mid-height gutter reads as detached regardless,
  so it's safe for transition-free scenes too. Confirmed fig 03; figs 06/08 side
  labels (off mid-height) unaffected. (dims 2, 5)
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
P.3 ✅ build the 10-figure corpus via the skill (makes "by default" measurable)
        │
        ├─► dim 1 (sizing) ✅   dim 2 (labels) ✅ closed 2026-06-24
        ├─► dim 3 (orientation/D6) ✅ closed 2026-06-25
        ├─► dim 5 (density/containment) ~ (D5/D7/D8 done; arrows + blob sizing open)
        └─► remaining: the (optional) render-critic
            [dim 4 (layering·contrast) ✅ closed 2026-06-25]
            [dim 6 (publication preset + routing flip) ✅ closed 2026-06-25]
```

**Corpus verdict (2026-06-25, updated):** dims 1 + 2 + 3 + 4 + 6 are all closed;
dim 5 is mostly done. The only remaining scout item is the **still-optional
render-critic** (a vision-scored pub-grade rubric closing the loop). With the
publication preset + routing flip landed, a cold tier skill call is now the
pub-grade call by default.
Two corpus-grounded follow-ups surfaced by dim 3, worth picking up alongside dim
4/5: (a) **orientation v2** — orient on H-bond/dashed edges too (fig 01-s1, 08-s1
still pose the H-bond step canonically) and keep a shared substrate posed
consistently across a step sequence (fig 01 s1-vs-s2); (b) the fig-05 finding that
a re-posed *taller* molecule can collide with its caption is really a **containment
gap (dim 5)** — collision-aware orientation would let the deadband be tighter.

---

*Authored 2026-06-15 (Phase P.2). Defect list and gaps grounded in the aspirin
acceptance artifact + the P.1 verification renders. Update as the corpus lands.*
