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
| Low | **Archetype aspect-ratio capping (run10 #3).** A wide many-column SCENE_ROW produces an extreme landscape figure (run10: 03 ~5.4:1, 04 8:1 band, 06 11.5:1). Canvas width is content-driven (`_tier_block_width` = n·cell_w + gutters) with no cap on width-vs-height, so the more scenes a row has the wider/shorter the page. **B3 (landed 2026-06-27) slightly worsens the ratio** — packing bands to content shrank figure *height* (β-lactamase 807→711, aspirin 836→756), so the same width is now divided by a smaller height. Fix is tier-level: clamp the figure aspect to ~3:1–4:1 by **wrapping** an over-wide scene row onto multiple rows (reflow N columns into ⌈N/k⌉ rows) and/or raising band height to the cap — not by stretching content. Watch the two-channel cascade + the corpus as the guard; don't special-case per figure. | `V3_STATUS.md`, run10 #3 |
| Low | **β-lactamase summary glyphs (D1)** — `tablet`/`protein_blob`/`pg_cluster` misread without their labels (labels disambiguate today). | `HANDOFF.md` D1 |

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
