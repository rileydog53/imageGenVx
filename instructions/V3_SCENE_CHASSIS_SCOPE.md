# V3 Scene Chassis — Scoping Doc

**Status: SHIPPED, fully implemented.** Scoped and kicked off the V3 line: a
3-layer chassis — Layer A (relative-anchor scene graph: slots/attach/connect),
Layer B (tier/band compositor with rails), Layer C (step/state model with
cumulative deltas) — replacing the old depth-1 grid so a cell can hold a
heterogeneous, mutually-anchored, multi-step composition. All three layers are
built and feature-complete (Steps 1–7; `V3_STATUS.md`).

No open items remain from this doc; the sequencing it proposed is superseded
by completed work, and its IR node shapes were finalized in
`V3_IR_NODESHAPES_PROPOSAL.md` (now itself a shipped-status stub). Full
scoping rationale pruned to git history — see the commits landing
`layout/tier_layout.py` and `render/compositor.py`'s tier dispatch
(2026-06-08 through 2026-06-10).

Active plan: `HANDOFF.md`. Status: `V3_STATUS.md`.
