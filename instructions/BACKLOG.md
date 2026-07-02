# Backlog — rolling list of open issues

This file tracks **open, in-scope defects and small improvements** only. When
an item lands, its row is deleted — git history and each milestone's PLAN
write-up preserve the record.

- **Open defects / small improvements** → here.
- **Larger future features (out of scope for v2.x)** → `V3_FEATURES.md`.
- **Per-milestone implementation records** → git history.

Priority: high = blocks reading/using the tool; medium = shows up in real
figures soon; low = polish / advanced use.

> History note: all milestones through v2.2 and the V3 chassis (Steps 1–7,
> pub-grade dims 1–6) are complete — see git history, `V3_STATUS.md`, and the
> per-milestone PLAN write-ups.

---

## Open issues

| Priority | Issue | Source |
|---|---|---|
| Low | **β-lactamase summary glyphs (D1)** — `tablet`/`protein_blob`/`pg_cluster` misread without their labels (labels disambiguate today). | `HANDOFF.md` D1 |
| Medium | **1. Arrow-shaft/inter-node spacing too long** — leaf pathway/reaction/workflow figures spend 50-60%+ of canvas width on bare arrow shafts vs. content. | `NITPICK_FIXLIST.md` #1 |
| Medium | **2. Compartment/membrane crossings not perpendicular** — some cellular_schematic relations cross a band boundary at 10-25° instead of ~90°. | `NITPICK_FIXLIST.md` #2 |
| Medium | **3. Arrows crossing fixed captions + arrowhead pile-ups** — relation shafts cut through compartment/tier caption text; converging arrows overlap into a jumbled cluster at some targets. | `NITPICK_FIXLIST.md` #3 |
| Low | **4. Ring-layout arrowhead standoff inconsistent** — circular pathway arrowheads land flush on some targets, 20-53px short on others. | `NITPICK_FIXLIST.md` #4 |
| Low | **5. Legend band sized to a fixed fraction, not content** — legend key fills a small corner of a much larger reserved band. | `NITPICK_FIXLIST.md` #5 |
| Low | **6. `fit_label` over-shrinks when vertical room exists** — some labels wrap+shrink further than needed given available box height. | `NITPICK_FIXLIST.md` #6 |
| Low | **7. RDKit water/single-atom label sizing + reagent/notes font mismatch** — water renders as an oversized formula label; above/below condition text sizes can diverge. | `NITPICK_FIXLIST.md` #7 |
| Low | **8. Tier chassis: floating leader lines + curly-arrowhead/bond overlap** — a leader line can stop short of its atom; a short-radius curly arrowhead can overlap the bond stroke it points to. | `NITPICK_FIXLIST.md` #8 |
| Low | **9. Verify arrow-style "inconsistencies" aren't just different RelationTypes** — check before treating as a bug. | `NITPICK_FIXLIST.md` #9 |

The V3 engine backlog (deferred nits, orientation v2, render-critic, the
engine-can't-express gaps) is tracked in `V3_STATUS.md` → "Still open" and
`HANDOFF.md`. Larger future features remain in `V3_FEATURES.md`.

---

## How to use this file

- **Open, in-scope issues only.** When an item lands, delete its row — git
  history keeps the record, and the implementation belongs in the milestone's
  PLAN write-up, not here.
- **New work:** add a row with a priority and a one-line source. If it's a
  larger future feature rather than a defect, put it in `V3_FEATURES.md`
  instead.
