# Tier-figure corpus (Phase P.3)

Diverse `mechanism_cartoon` **tier** figures, authored as IR JSON **through the
skill path** documented in `SKILL.md` → *Tier figures (the V3 scene chassis)* —
not hand-written Python scripts. Each is rendered and checked by
`tests/test_corpus_tier_figures.py` (render + semantic/legibility/convention).
This is the corpus that makes "pub-grade by default" measurable and overfitting
to the aspirin acceptance artifact visible (Phase P, see `PUBGRADE_ROADMAP.md`).

Render any one through the same path a skill call uses:

```bash
~/Desktop/.venv/bin/python -m imageGen render-spec \
    showcase/corpus/03_sn2_substitution.json -o /tmp/out.png --verify --autocrop
```

| # | File | Exercises |
|---|---|---|
| 01 | `01_aspirin_cox1_acetylation.json` | the acceptance artifact — 4-step mechanism, residues, curly arrows, summary band |
| 02 | `02_chymotrypsin_acylation.json` | catalytic-triad acylation; ser/his residues, H-bond, curly arrows, rail transitions |
| 03 | `03_sn2_substitution.json` | `departs` leaving-group arrow; small-molecule nucleophile + substrate |
| 04 | `04_enzyme_substrate_binding.json` | `blob` slot + `cavity_center` attach (ligand seated in a pocket) |
| 05 | `05_imine_formation.json` | amine→carbonyl nucleophilic addition; curly arrows on a non-enzymic substrate |
| 06 | `06_egfr_erk_signaling.json` | glyph-only "tier pathway": `protein_blob`/`tablet` glyphs, `activates`/`inhibits` edges, two bands |
| 07 | `07_kinase_phosphorylation_steps.json` | `step_sequence` expansion — `add_label` / `replace` / `remove` deltas across 3 states |
| 08 | `08_acetylcholinesterase_hydrolysis.json` | ester-hydrolysis mechanism; charged substrate, acyl-enzyme + leaving group |
| 09 | `09_disulfide_redox.json` | redox/structural change; `cys` residues, a forming S–S bond |
| 10 | `10_competitive_inhibition.json` | competition cartoon; `binds` vs `inhibits` to a shared enzyme, blob cavity |

**What the corpus confirms (2026-06-15):** the chassis renders all ten cleanly
(every verifier green), and the label defects catalogued in `PUBGRADE_ROADMAP.md`
(D1 residue/glyph labels drift, D2 multi-line caption clipping, D4 transition
labels overlapping arrows) **recur across figures** — i.e. they are general
chassis behaviour, not aspirin-specific tuning. Dimension 2 (**labels** /
leader lines) is the top pub-grade priority the corpus surfaces.
