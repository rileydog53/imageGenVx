# Pub-grade Roadmap (Phase P)

Where the V3 chassis goes from *feature-complete* to *publication-grade by
default*. The engine renders correct tier figures (Steps 1–7) and the skill door
opens onto the chassis. All six scout dimensions are **closed**; what remains is
the optional render-critic, a set of dimension residuals, and the
engine-can't-express gaps. The landed dimension-by-dimension changelog (D1–D9
defect list, per-dim "landed" prose) was pruned to git history 2026-06-26.

> Active next-session work is in [`HANDOFF.md`](HANDOFF.md). Read this for the
> standing corrections, the gaps (G1–G5), and the render-critic plan.

---

## Two standing corrections (do not relitigate)

1. **Cleanness before correctness gating.** An unreadable-but-correct figure is
   worthless — you can't read the handwriting. Legibility/layout defects outrank
   chemical-correctness gating in priority.
2. **The defects are concrete and rule-fixable** — "sit it a little left", "the
   arrowhead needs ~1 cm clearance", "can't tell which arrowhead that is". They
   are **not** uncanny-valley. Rules can fix them; do not over-engineer.

---

## The 6 scout dimensions — all closed; live residuals only

| # | Dimension | Live residual / deferred-to-v2 |
|---|---|---|
| 1 | **sizing** | — (content-aware molecule + per-primitive glyph/blob natural box landed). |
| 2 | **labels** | **Residual:** a label with genuinely no whitespace in its band (a chain spanning the band) still overlaps — that's band-height (dim 1/5), not leaders. **Still open:** a leader that crosses unrelated caption text (corpus fig 05; **corpus-confirmed by the betalactamase figure — see `HANDOFF.md` §B1**). |
| 3 | **orientation** | **Deferred to v2:** H-bond/dashed edges as drivers (v1 = curly only); reflection tie-break; cross-step scaffold consistency. See `D6_ORIENTATION_SCOPE.md`. |
| 4 | **layering · contrast** | — (`hbond`→blue, `dashed`→gray, `curly`→auburn, `inhibits`→the only red T-bar). |
| 5 | **density · arrows / containment** | **Follow-up:** collision-aware orientation (a re-posed taller molecule can overrun its caption — fig 05) would let dim-3's 80° deadband tighten. |
| 6 | **pubgrade-defaults** | — (`publication` preset + routing flip: a cold **tier** skill call defaults to `publication`). |

---

## The missing instrument: render-critic + corpus

The reason "pub-grade by default" has been hard to measure is there is **no
quality instrument** — only the three pass/fail verifiers (semantic / legibility /
convention), which catch *broken*, not *ugly*.

- **The corpus** — 10 diverse tier figures authored through the skill path, pinned
  by `tests/test_corpus_tier_figures.py` (`showcase/corpus/`). Makes overfitting to
  aspirin visible and turns "by default" into something measured.
- **The render-critic (deferred, optional).** A vision-scored pub-grade rubric —
  render the figure, score it on legibility / spacing / label placement / arrow
  clarity / overall polish, feed the score back. The missing closed loop. Scoped
  *after* the corpus, because the corpus defines what the rubric must reward.

**Order is load-bearing: corpus first, then critic.** (The betalactamase critique
in `HANDOFF.md` is effectively a manual render-critic pass — the kind of rubric the
automated critic should encode.)

---

## Engine-can't-express gaps

The schema validates more than the renderer draws. The skill stays inside the
supported surface today; these are the candidate engine extensions if a figure
demands them. **Do not promise these in `SKILL.md` until the engine cashes them.**

- **G1 — slot kinds `box` / `group` / `generic`** validate but raise
  `NotImplementedError` at layout. Only `molecule`/`residue`/`glyph`/`blob`/`text`
  draw. (`group` nesting is validated but never laid out.)
- **G2 — tier roles `summary_bar` / `band`** render a band background only, no
  inner scenes. Any content band must use `scene_row` + `style.band_fill`.
- **G3 — `Tier.content`** (an embedded leaf `Figure` inside a band) is not laid
  out.
- **G4 — attach `edge` `anchor` / `custom`** are not solved (face + cavity edges
  only).
- **G5 — named residues are a fixed set** (`ser`/`his`/`tyr`/`cys`/`lys` +
  `ser530`/`his513` aliases). Others need a raw SMILES with a mapped reactive atom.
- **G6 — formal charge / protonation state has no render path (proposed, from the
  betalactamase critique).** Oxyanion `⊖` / ammonium `⊕` cannot be drawn on an
  atom; the corpus works around it with an ambiguous "·" that reads as a radical.
  Relates to the `U+207B` superscript-minus tofu gap (`LIMITATIONS.md`, V3-S2).
  Scoped in `HANDOFF.md` §C1.

---

*Authored 2026-06-15 (Phase P.2). Pruned to residuals + gaps 2026-06-26 — the
landed changelog is in git history; the active plan is `HANDOFF.md`.*
