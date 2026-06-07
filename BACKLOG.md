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

_No open defects._ The 2026-06-06 cleanup-pass follow-ups (DECISIONS D5) are all
landed: the `cells`/`lab_equipment` wiring, then **EW1** (molecule-as-entity) and
**EW2** (functional-group entity) on 2026-06-06 (DECISIONS D6), and **EW3**
(liposome entity, DECISIONS D7) + **EW4** (label-keyword glyph inference for the
coarse entity types, DECISIONS D8) on 2026-06-07. The earlier FR1–FR10
live-render defects and the Phase 7 LLM frontend (now the skill in `SKILL.md`,
including the reaction `--smiles-map` path) were already done.

Larger future features remain in `V3_FEATURES.md`.

---

## How to use this file

- **Open, in-scope issues only.** When an item lands, delete its row — git
  history keeps the record, and the implementation belongs in the milestone's
  PLAN write-up, not here.
- **New work:** add a row with a priority and a one-line source. If it's a
  larger future feature rather than a defect, put it in `V3_FEATURES.md`
  instead.
