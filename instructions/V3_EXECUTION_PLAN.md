# V3 Execution Plan — architecture reference

**Status: every scheduled action item landed** — Steps 1–7 (engine
feature-complete), Phases 0a/0b/0c, Phase H, Phase R1–R6, Phase P.1–P.3 (skill
door + corpus). The dispatch-unification idea, the scan corrections, and the
sequencing rule that drove that work are done; full narrative pruned to git
history. What remains below is still load-bearing: the **"Do NOT" invariants**
(permanent constraints, not a to-do list) and **Phase R's two deferred
splits** (genuinely not done).

The IR schema is load-bearing (`CONTRIBUTING.md`): **no `schema.py` edit lands
without explicit sign-off, and every test-matched error-string substring is
preserved.**

Active forward work is in [`HANDOFF.md`](HANDOFF.md); status in `V3_STATUS.md`.

---

## Do NOT (verified failure modes) — load-bearing invariants

- **Do not merge `tier_layout`'s anchor/solver placement with `pathway_layout`'s
  NetworkX placement.** They share zero primitives today (`pathway_layout` imports
  no anchors; `tier_layout` imports no `label_placement`). The win is collapsing
  the *4 precedence sites*, not unifying engines.
- **Do not grow a second relaxation engine inside `tier_layout`** — that forks the
  `data-overlap=true` contract, the strict/lenient toggle and the warning path.
  Reuse `place_labels` via the `LabelCoordinator` seam.
- **Do not add a preset-NAME axis below `Figure`** (per-step or per-scene preset
  names) — additive freeform `style` dicts only. `Panel.content.style_preset` is
  the lone exception (already shipped). That's what prevents the panel×step matrix.
- **Do not fold the base preset into the chassis *structural* channel** (connect
  edges / tier transitions). The preset's primitive vocabulary sets bare
  `stroke`/`stroke_width` (acs/nature), which collide with `_edge_group`'s keys
  and would clobber the per-`SceneEdgeType` semantic colours (an hbond's blue →
  black). The cascade is two channels: **content** (molecules, text) takes the
  preset base; **structural** (edges) takes `tier.style → scene.style → edge.style`
  only. A journal preset must never recolour a semantic edge.
- **Keep chassis `style` keys flat scalars.** `merge_style` is shallow (later-wins,
  like preset `inherits`); a nested style sub-dict would be clobbered wholesale,
  not deep-merged.
- **Do not touch `schema.py` without sign-off**, and **preserve every test-matched
  error-string substring** (`CONTRIBUTING.md`).
- **Do not remove the `model_rebuild()` block** — it's load-bearing under
  `from __future__ import annotations`.

---

## Phase R — remaining deferred splits (not done)

Module decomposition R1–R6 landed (pure re-export-shim moves). Two splits were
deliberately deferred and are still open:

- `layout/tier_layout.py` — the active V3 surface; splitting mid-feature added
  merge cost for zero gain. Revisit now that Steps 5/6 have landed.
- `primitives/lab_equipment.py` — one cohesive primitive family; low edit-frequency,
  low payoff.
- Dead-code follow-up: `_label_extent_w` (`_pathway_rings.py`) is defined but
  referenced nowhere — candidate for a removal pass.
