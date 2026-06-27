# V3 Execution Plan — architecture reference

> **Status (2026-06-26): every action item in this plan has landed** — Steps 1–7
> (engine feature-complete), Phases 0a/0b/0c, Phase H, Phase R (R1–R6), and Phase
> P.1–P.3 (the skill door + corpus). The per-item checklists were pruned to git
> history. **This doc is retained for the durable architecture decisions below**
> — the one dispatch idea (§1), the scan corrections (§2), the sequencing rule
> (§3), and especially the **"Do NOT" invariants (§5)**. Active forward work is in
> [`HANDOFF.md`](HANDOFF.md); status in `V3_STATUS.md`.

The IR schema is load-bearing (`CONTRIBUTING.md`): **no `schema.py` edit lands
without explicit sign-off, and every test-matched error-string substring is
preserved.**

---

## 1. The one architectural idea this plan is built on

The V3 chassis did **not** create a 5-archetype × 3-container dispatch matrix.
The real shape is a **3-way container split** (tiers / panels / leaf) whose leaf
arm is a **2-engine split** (pathway-family vs reaction) wearing a 5-archetype
coat. The actual debt was that the same `tiers → panels → archetype` precedence
was **re-tested in four unsynchronised sites**, kept in sync only by golden tests:

| Site | File:line | What it re-decides |
|---|---|---|
| `_dispatch_layout` | `render/compositor.py` | container → engine |
| `_canvas_size` | `render/compositor.py` | container → canvas formula |
| render label branch | `render/compositor.py` | container → label strategy |
| `ARCHETYPE_TO_LAYOUT` + its twin if/elif | `layout/panel_layout.py` | archetype → engine (encoded **twice** in one file) |

**Every V3 pressure points the same way:** Steps 5/6/7 *deepen the tier engine's
internals* — they do **not** add container modes or archetypes (the `Archetype`
enum is frozen at 5). So the branch explosion the original plan feared only
materialises if the compositor keeps re-testing the container/archetype triple at
every concern.

**The move:** make container mode the single explicit dispatch axis, decided
**once**, via a small `LoweringPlan` record `(engine, canvas_fn, label_strategy,
style_base)`. Then Steps 5/6/7 land as *tier-engine-internal work + thin adapters
that plug into existing seams* — N-scene expansion produces more scopes/requests,
never more branches. **Net goal: the dispatch / label / style branch count stays
roughly flat while the feature set triples.**

The mutual-exclusion guard at `schema.py` (`sum([leaf, panels, tiers]) > 1`) is
what makes a container-mode-first `if/elif` *provably* unable to mis-route.

---

## 2. Corrections the scan forced (do not re-chase these)

| ⚠️ Old framing | Verified reality |
|---|---|
| label→glyph inference lives in `entity_adapters.py` | It's in `layout/_geom.py` — `_INFERENCE_RULES`, `infer_primitive`, `resolve_entity_primitive`. The adapter file is **not** the god-module. |
| a bad `TierEdge` ref raises `KeyError` at render | `AnchorRegistry.resolve` raises a **guarded `ValueError`**. The real gap was *loud-but-**late*** (layout time, not IR-build) — closed by build-time slot-token validation. |
| the multi-step downgrade **mutates** `ir.archetype` | it is a `model_copy(update=…)` rebind — the caller's IR is untouched. The real gap was that the downgrade was **silent** when `smiles_map` is falsy (closed by PH.1). |
| greedy label placement is O(n²) and will melt under V3 | Panels already collision-isolate per cell; tiers place per scene. The risk was the **tier seam doing zero overlap avoidance**, not algorithmic blow-up. |
| `style_dict` is dropped at the compositor for tiers | It **is** passed but was **never applied** inside `tier_layout` (closed by the two-channel cascade, P0b). |
| `model_rebuild()` block is redundant/fragile | **Load-bearing.** `from __future__ import annotations` makes the forward refs require it. Leave it. |

---

## 3. Sequencing rule

> **Anything a step will build *on a seam* must precede that step. Anything that
> merely *coexists* can follow.**

The cheap unifications were scheduled as **Phase 0 pre-work gates** in front of
each numbered step, not as a separate cleanup epic:

```
Phase 0a  (pre-Step-5)   →  Step 5  (scene solver)
Phase 0b  (pre-Step-6)   →  Step 6  (step expansion)
Phase 0c  (pre-Step-7)   →  Step 7  (primitive refresh)
Phase H   (independent correctness — any time, no ordering dep)
```

---

## 5. Do NOT (verified failure modes) — load-bearing invariants

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

## 6. What this supersedes / leaves intact

- **Supersedes:** the *sequencing* of `V3_IR_NODESHAPES_PROPOSAL.md §3` Steps 5–7
  and `V3_SCENE_CHASSIS_SCOPE.md §4` for unlanded work. The node-shape *schema*
  and the §2 design decisions in those docs **stand unchanged**.
- **Intact:** `V3_FEATURES.md` MF-1/2/3 acceptance criteria and the V3-C/L/I/O/S
  backlog.

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
