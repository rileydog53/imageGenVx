# V3 IR Node-Shapes Proposal (Step 1)

**Status: SHIPPED (2026-06-08–06-10), fully implemented.** Defined the V3 tier
chassis's IR node shapes: `Tier`/`Rail`/`TierEdge` (Layer B), `Scene`/`Slot`/
`Attach`/`SceneEdge` (Layer A), `StepSequence`/`Step`/`StepDelta` (Layer C), plus
the dedicated `SceneEdgeType` enum and `Figure.tiers`. All landed in
`imageGen/ir/schema.py` (authoritative — cited from `ir/_enums.py`), proven by
`tests/test_ir_schema_tiers.py`, `test_layout_tiers.py`, `test_compositor_tiers.py`.

No open items remain from this doc; it existed to scope and sign off the schema
before the `schema.py` edit (load-bearing per `CONTRIBUTING.md`). Superseded
build-order narrative and full decision log pruned to git history — see the
commits landing `ir/schema.py`'s tier models (2026-06-08 through 2026-06-10).

Active plan: `HANDOFF.md`. Status: `V3_STATUS.md`.
