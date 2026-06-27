# HANDOFF — next session plan (β-lactamase mechanism figure)

**Authored 2026-06-26. Largely LANDED 2026-06-27 — see the landed log below.**
It consolidates a manual render-critic pass on the β-lactamase figure plus the
still-open V3 engine backlog. Read `V3_STATUS.md` for status and
`PUBGRADE_ROADMAP.md` for the standing corrections and the engine-can't-express
gaps; this doc is the active to-do.

## Landed 2026-06-27 (suite 1233 green)

- **A1–A4 (correctness) — DONE.** `betalactamase.json` rebuilt to **4 real
  species-scenes**: Michaelis → tetrahedral intermediate (proper `[O-]` oxyanion)
  → ring-opened acyl-enzyme (**Ser embedded as a real ester**, C=O restored, C–N
  broken) → inactive penicilloate. Penicilloate now actually appears (I/O closes,
  A3); proton-transfer curly drawn (A4); the dashed "new ester bond" cartoon is
  gone (B4 dissolved). Captions match structures.
- **C1 / G6 — RESOLVED, no schema change.** Charge renders via SMILES
  (`[O-]`/`[NH3+]` → proper ⊖/⊕ from RDKit; tofu only hits the *label-text* layer).
  - Engine: `_RESIDUE_SMILES` fixed to carry explicit H → residues render
    `-OH`/`-NH₂`/`-SH`, not a radical dot.
  - Engine: `_smiles_to_mol` now **warns** on any radical heteroatom (MF-1 lint) —
    catches the `[O:n]`-as-oxyanion class at parse time.
  - Corpus migrated off the radical idiom: 01 aspirin + acceptance (`[O:5]`→`[OH:5]`),
    02 chymotrypsin (`[O:2]`→`[O-:2]`), 03 SN2 + 05 imine (bracket atoms re-given
    H/charge). Suite is radical-warning-free. β-lactamase pinned as corpus member 11.
- **B1 (leader crosses caption) — FIXED generally.** Leader-eligible placement now
  rejects a slot whose tether would slice occupancy and re-picks a tether-clear
  slot (`label_placement._first_fit` `tether_from` + `_leader_ring` fallback).
  Pinned by `test_label_placement_fallback.py`. 0 caption crossings in all 4 scenes.
- **SKILL.md** gained a *Mechanism chemical correctness* checklist (structure↔caption,
  charge-via-SMILES, embed-residue-for-real-bond, arrow-every-claim, I/O closes).

**Still open (lower priority):** B3 band dead-space + B2 s1 arrow density (→
band-height/auto-fit + orientation-v2 backlog); D1 summary glyphs; A-minor
cosmetics; cross-step scaffold orientation; SN2/imine radical-fragment cleanup.

## Artifacts under review

- Spec: `~/Desktop/scratch/betalactamase.json` (archetype `mechanism_cartoon`, a
  tier figure: title / 3-scene mechanism row `mech` / summary bar `sum`).
- Render: `~/Desktop/scratch/betalactamase.png` (re-render at 300 dpi to inspect;
  crop each scene third — the defects below are visible only when zoomed).
- The mechanism row scenes are `s1`/`s2`/`s3`; slots are `sub`/`ti` (substrate),
  `ser` (Ser70), `lys` (Lys73). Summary glyphs are `drug`/`enz`/`prod`.

## Already closed — DO NOT re-litigate

Pub-grade dims **1 sizing, 2 leader-line labels, 3 orientation, 4 edge-colour
contrast, 5 arrow spacing/containment, 6 publication preset** are all closed
(`PUBGRADE_ROADMAP.md`). The findings below are issues those dimensions did **not**
cover: mechanism chemical-correctness, scene-band whitespace, charge semantics,
narrative clarity, and figure-level polish.

---

## A. Mechanism correctness, step count & I/O  *(highest priority — a reviewer would reject on these)*

### A1. Scene 3's molecule is the tetrahedral intermediate, mislabeled as the ring-opened acyl-enzyme
The `s3` slot `ti` SMILES is `CC1(C)S[C@@H]2[C@H](N)[C:1]([O:2])(O)N2[C@H]1C(=O)O`.
The reactive carbon `[C:1]` is tetrahedral (bears `[O:2]` = O⁻ **and** an `O`H)
**and is still bonded to the ring nitrogen `N2`** — the β-lactam C–N bond is
intact, so the ring is **not open**. A true ring-opened acyl-enzyme needs three
things this structure has none of: (a) the **C–N bond broken**, (b) the carbonyl
**C=O restored** (it's an ester now, not a gem-diol), (c) **Ser70's oxygen
covalently in the molecule** as that ester. As drawn, the only thing linking Ser
to the substrate is the gray dashed "new ester bond" leader — a cartoon line, not
a bond. **The caption ("ring-opened acyl-enzyme; β-lactam ring opened") contradicts
the molecule on the page.**

**Fix (authoring):** rewrite the `s3` substrate to the actual acyl-enzyme — break
`C1–N2`, restore `C1=O`, and put the Ser oxygen into the molecule so the ester is
a real bond (one combined Ser–O–C(=O)–substrate fragment, or keep them as two
slots but make the connecting edge a real bond, not a dashed leader). *Or* relabel
`s3` "tetrahedral intermediate" and add a 4th scene for the true acyl-enzyme (see
A2). Either way the structure and caption must agree.

### A2. The sequence is one beat short and the captions are off-by-one
`s2` still draws the **intact** carbonyl with the attack arrows on it; the
tetrahedral intermediate only appears in `s3` (mislabeled). So the genuine
"collapse → ring opens → acyl-enzyme" beat is missing, and `s3` is doing the work
of two different species. The honest minimal sequence is **four scenes**:

1. Penicillin bound; Ser70 activated.
2. Nucleophilic attack → **tetrahedral intermediate (oxyanion)**.
3. Collapse → **ring opens → acyl-enzyme** (ester formed, C–N broken).
4. Deacylation by water → **inactive penicilloate released + free enzyme**.

**Fix (authoring):** add the missing beat(s). Note the per-scene curly/TS edges
must be **authored scenes**, not a `StepSequence` — `StepDelta` is slot-granular
and can't add a per-step edge (this is the open engine gap below; the aspirin
acceptance row hit the same wall).

### A3. Input/output doesn't close — the summary promises a product the mechanism never makes
Title says "inactivates"; the `sum` band says "Net outcome: the antibiotic is
destroyed" with a `hydrolysis` edge → `inactive penicilloate`. But the mechanism
row stops at the (mis-drawn) acyl-enzyme — **deacylation by water is never shown
and no penicilloate is ever produced.** The covalent acyl-enzyme is an
*intermediate*, not the destroyed antibiotic.

**Fix (authoring):** either add the deacylation scene (A2 step 4) so the product
the summary claims actually appears, or soften the summary to "→ acyl-enzyme
(hydrolysis then releases inactive penicilloate)". Don't assert turnover the
scenes don't depict.

### A4. The proton transfer is claimed but never drawn
`s1` caption says "Lys73 deprotonates Ser70" and `s3` relabels it "Lys73-H+", but
no curly arrow ever moves that proton — `s2` shows only the O→C and C=O→O arrows.
The whole claim rests on the static Lys73→Ser70 H-bond arc.

**Fix (authoring):** add a curly arrow for the Ser–O–H → Lys73 proton transfer in
`s1` or `s2` (an H-bond/curly edge on the right atoms), so the "deprotonates" and
"Lys73-H+" labels are earned.

### A-minor (note, don't over-invest)
- The "penicillin core" is really **6-APA** — the free `NH2` on the ring carbon is
  a *spectator*, not the reactive amide. Make sure a reader can't mistake it for
  the nucleophile/leaving group; the reactive site is the β-lactam carbonyl.
- The Ser stub is drawn as ethoxide (2 carbons); serine's side chain is –CH₂OH
  (1 carbon). Cosmetic.
- Lys73-as-general-base is one of two hypotheses (Glu166/water is the other) —
  fine to keep, but it's a modelling choice worth a hedge in the caption.

---

## B. Layout, whitespace & crossing lines  *(visible craft defects)*

### B1. Lys73's leader runs straight through the caption text  *(corpus-confirmed dim-2 residual)*
In every scene the vertical dashed leader from the `lys` slot down to its "Lys73"
label passes **through** the two-line scene caption — clearest in `s2`, where it
slices "Nucleoph|ilic attack" and "by Ser70 |-OH". This is the exact
"leader crosses unrelated caption text" nit logged as *minor* in
`PUBGRADE_ROADMAP.md` dim 2 (fig 05) — **the betalactamase figure promotes it from
minor to a recurring defect.**

**Fix (engine):** `place_labels` / `tier_label_leaders` should treat scene-caption
text boxes as occupancy the leader must route around (or re-place the slot label so
its tether doesn't cross the caption band). Caption text is already laid out before
the leader post-pass — feed those boxes in as leader-avoidance occupancy.

### B2. Scene 1's H-bond arc is a tangle
The blue dashed H-bond arc sweeps from Lys73-N up across the molecule to Ser-O, and
the "H-bond" label's own dashed leader crosses *into* that arc near the `NH2`.
Three dashed elements (Ser70 leader, H-bond arc, H-bond label leader) converge in
the right third of `s1`.

**Fix (engine + authoring):** partly orientation-v2 (H-bond edges don't yet drive
pose, so the donor/acceptor aren't aimed at each other — `D6_ORIENTATION_SCOPE.md`
deferred item); partly edge routing (the arc bows across the structure instead of
taking the short path) and label placement (keep the "H-bond" label off the arc).

### B3. Tall vertical dead space in the mechanism band
The `Ser70` label floats ~¼-band above its residue on a long tether, and there's a
second large gap between the substrate and the `lys` chain. Content occupies maybe
60% of the band height.

**Fix (engine):** tighten the residue `Attach.offset`s and/or the band-height /
vertical-centering math so the column packs without the long tethers; this overlaps
the dim-5 containment work and the auto-fit/balanced-reflow backlog item.

### B4. Scene 3 stacks two near-collinear gray dashed verticals
The gray `Ser70` leader and the gray "new ester bond" leader sit almost on top of
each other, reading as one ambiguous element; "new ester bond" / "OH" / "O·" all
crowd the top-right of the bicyclic core.

**Fix (authoring + engine):** if A1 makes the ester a real bond, the "new ester
bond" dashed leader disappears (resolves most of this). Otherwise de-collide the
two gray verticals and give the top-right substituents room.

---

## C. Charge / colour semantics

### C1. The "·" reads as a radical, not a charge — and there's no formal charge anywhere
The alkoxide/oxyanion O is drawn red "O·". A chemist reads that dot as a lone
electron (radical), not a formal ⊖. The same glyph is used for the neutral Ser-OH
oxygen and the oxyanion, and "Lys73-H+" draws its N as "N:" — so **charge state is
asserted only in labels, never on the structure.**

**Fix (engine — proposed gap G6, see `PUBGRADE_ROADMAP.md`):** add a formal-charge
render path (⊖ on the oxyanion O, ⊕ on the ammonium N). There is currently **no**
way to draw this — it ties into the existing `U+207B` superscript-minus tofu gap
(`LIMITATIONS.md`, V3-S2). Until then, the spec should at least stop using "·" for
charge (it's misleading). This is the one finding that is a genuine new engine
feature, not an authoring fix.

---

## D. Summary band polish

### D1. All three glyphs misread
- `drug` = `tablet`: renders as a circle-with-minus, reads as a ⊘ prohibition sign
  / single bond, not a pill.
- `enz` = `protein_blob` with a concentric inner ring: reads as a **cell with a
  nucleus**, not an enzyme.
- `prod` = `pg_cluster`: a gray blob-cluster, reads as a blob, not a small molecule
  (penicilloate).

Plus the band is mostly empty vertical space under one caption.

**Fix (authoring first, maybe engine):** pick glyphs that read correctly (or label
them more explicitly); consider a tighter band height. Low priority relative to A–C.

---

## Priority order (propose-only — confirm before coding)

1. **A1** — fix `s3` to the real acyl-enzyme (or relabel as the tetrahedral
   intermediate). Internally contradictory as-is.
2. **A2 / A3** — reconcile step count with the stated I/O: add the deacylation
   beat (→ true penicilloate) or soften the summary.
3. **B1** — stop Lys73 leaders crossing the captions (engine; corpus-confirmed).
4. **B3 / B2 / B4** — tighten band dead-space; detangle `s1`'s H-bond arc;
   de-collide `s3`'s parallel gray verticals.
5. **A4** — draw the proton-transfer arrow.
6. **C1** — formal-charge rendering (engine gap G6); meanwhile drop the "·".
7. **D1** — reconsider the summary glyphs.

Items 1–2 are correctness (reviewer-reject); 3–4 are the visible craft defects;
5–7 are polish + one engine feature.

## Authoring vs engine, at a glance

| Finding | Authoring (edit the spec) | Engine (code) |
|---|---|---|
| A1 acyl-enzyme structure | ✅ rewrite `s3` SMILES / ester bond | — |
| A2 step count | ✅ add scene(s) | (relies on authored scenes; `StepSequence` edge-delta gap below) |
| A3 I/O close | ✅ add scene or soften summary | — |
| A4 proton arrow | ✅ add curly/H-bond edge | — |
| B1 leader↔caption | — | ✅ caption boxes as leader occupancy |
| B2 H-bond tangle | partial (offsets) | ✅ orientation-v2 H-bond driver + edge routing |
| B3 band dead-space | partial (offsets) | ✅ band-height / vertical packing |
| B4 parallel gray leaders | mostly via A1 | ✅ de-collide |
| C1 formal charge | drop "·" | ✅ **new gap G6** charge render path |
| D1 summary glyphs | ✅ glyph choice | maybe band height |

---

## Inherited V3 engine backlog (unchanged by this figure — pointers)

These are the still-open items from the pruned planning docs; the betalactamase
work touches several (noted). Full homes in parentheses.

- **`StepSequence` per-step edge-delta op** — `StepDelta` is slot-granular; can't
  add a per-step curly/TS edge. *Directly blocks authoring A2 as a step sequence.*
  (`V3_STATUS.md`)
- **Orientation v2** — H-bond/dashed edges as pose drivers (*B2*), reflection
  tie-break, cross-step scaffold consistency, collision-aware orientation.
  (`D6_ORIENTATION_SCOPE.md`, `PUBGRADE_ROADMAP.md`)
- **Leader residual** — a label with no whitespace anywhere in its band still
  overlaps (band-height). (`PUBGRADE_ROADMAP.md` dim 2)
- **Engine-can't-express gaps G1–G5 (+ proposed G6 charge).**
  (`PUBGRADE_ROADMAP.md`)
- **Deferred nits** — duplicate-edge `ir_id` uniquifier; partial `height_frac`
  fallback; `rail:` bare endpoints in `TierEdge`. (`V3_STATUS.md`)
- **Phase-R deferred splits** — `tier_layout.py`, `lab_equipment.py`; dead-code
  `_label_extent_w`. (`V3_EXECUTION_PLAN.md`)
- **Overlay** `TierEdge` → step_sequence `base.id` has no laid-out scene; overlay
  gutter 0.3 heuristic. (`V3_STATUS.md`)
- **Auto-fit / balanced reflow + aspect-ratio capping (run10 #3)** — tier-level
  (*overlaps B3*). (`V3_STATUS.md`)
- **Render-critic (optional)** — vision-scored rubric; this critique is a manual
  instance of it. (`PUBGRADE_ROADMAP.md`)
- **Future features** — V3-C/L/I/O/S track. (`V3_FEATURES.md`)
- **Separate workstream** — in-chat WYSIWYG figure editor
  (`masterhand/EDITOR_LOOP_HANDOFF.md`).

---

## Hard rules the next agent must respect

- **`imageGen/ir/schema.py` is load-bearing** — no edits without explicit sign-off;
  preserve every test-matched error-string substring (`CONTRIBUTING.md`,
  `V3_EXECUTION_PLAN.md` §5). G6 charge rendering may need a schema field — gate it.
- **Cleanness before correctness gating** — but here several A-findings are both:
  the figure is *internally contradictory* (A1) and *over-claims* (A3), which a
  reviewer reads as wrong, not just ugly. Fix them.
- The defects are **concrete and rule-fixable**, not uncanny-valley
  (`PUBGRADE_ROADMAP.md`).
- Don't re-open the six closed pub-grade dimensions.
- Keep the two-channel style cascade; a journal preset must never recolour a
  semantic edge (`V3_EXECUTION_PLAN.md` §5).

## First steps for the next agent

1. Re-render `betalactamase.json` at 300 dpi and crop the three scenes to confirm
   the defects (they're zoom-only).
2. Confirm the priority order above with the user, then start at **A1** (fix the
   `s3` structure) — it's pure spec authoring and unblocks B4.
3. Treat **B1** (leader↔caption) as the first *engine* change — it's
   corpus-confirmed and small.
