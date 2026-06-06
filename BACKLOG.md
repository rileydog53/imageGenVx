# Backlog — rolling list of open issues

This file tracks **open, in-scope defects and small improvements** only. When
an item lands, its row is deleted — git history and each milestone's PLAN
write-up preserve the record.

- **Open defects / small improvements** → here.
- **Larger future features (out of scope for v2.x)** → `V3_FEATURES.md`.
- **Per-milestone implementation records** → git history.

Priority: high = blocks reading/using the tool; medium = shows up in real
figures soon; low = polish / advanced use.

> History note: V1.0 + V1.1 (orthogonal routing, reagent labels) and Waves 1–7
> (L1–L24, R1–R6, V1, P2–P3, ST1–ST5) are complete — see git history. V2.1
> (LT1–LT10: ring + layered DAG layout, ALAP rank tightening, RNA + broken-DNA
> primitives, the legibility trio, the `complex` entity type, SKILL.md sync +
> scope-guard) landed 2026-05-26 / 2026-05-27. **v2.2** (2026-05-27) is a
> maintenance milestone: package bumped to `2.2.0`, the two divergent SKILL.md
> docs reconciled onto the canonical repo reference, and a live-render
> verification sweep. Suite green at 658.

---

## Open issues

Source: live-render review of 10 figures, 2026-06-05 (see plan
`ok-write-the-plan-jazzy-bee`). Out-of-scope feature ideas live in
`V3_FEATURES.md`; wrong-figure reports go in `FEEDBACK.md`.

| ID | Priority | Issue |
|---|---|---|
| FR9 | low | **No abbreviation/acronym glossary** (item 4). Add `glossary:[{term,definition}]` to `Figure`, boxed legend via `render/legend.py`, verifier "every acronym defined". SCHEMA-GATED + V3-tier -- candidate for `V3_FEATURES.md`. Short-term: hand-authored `annotations` block (depends on FR1). |
| FR10 | low | **Domain-canonical idioms missing** (item G): action-potential voltage trace, antibody Y-shape (curved electron-pushing arrows already tracked as V3-C4). New primitives -- V3-tier; candidate for `V3_FEATURES.md`. |

---

## How to use this file

- **Open, in-scope issues only.** When an item lands, delete its row — git
  history keeps the record, and the implementation belongs in the milestone's
  PLAN write-up, not here.
- **New work:** add a row with a priority and a one-line source. If it's a
  larger future feature rather than a defect, put it in `V3_FEATURES.md`
  instead.
