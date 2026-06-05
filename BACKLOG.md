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
| FR4 | medium | **GPCR/transmembrane glyph doesn't span the bilayer.** `primitives/proteins.py:399 gpcr()` anchors at the membrane boundary, not piercing both leaflets. ~30-line primitive change, no schema. |
| FR5 | medium | **Cyclic graphs render as flat L->R DAGs** (diabetes, action potential, carbon cycle) while rock-cycle rings correctly. Cross-links defeat ring detection; add auto-detect (`layout/`, `_dispatch_layout`); `layout_hint`/`--layout circular` already wired. |
| FR6 | medium | **`--verify` passed all 10 despite FR1/FR2/FR3.** Add legibility/semantic rules to catch empty-box overflow, off-canvas text, and undrawn annotations (`verify/legibility_check.py`). |
| FR7 | medium | **`style.primitive` unreachable from tuple shorthand** (blocked the antibody glyph in IgG). Add optional 5th tuple element in `ir/builder.py` `_normalize_entity`; dict-form entities already expose it. |
| FR8 | medium | **Stacked labels on parallel fwd/back edges** (item 2: subunit dissociation / GTP hydrolysis). Add `label_side: above\|below` to `Relation`; offset in `layout/label_placement.py`. SCHEMA-GATED -- needs approval (CONTRIBUTING rule 5). Cross-ref V3-L2. Short-term: ASCII arrow prefixes in labels. |
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
