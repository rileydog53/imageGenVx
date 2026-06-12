All four slices' ground-truth claims are verified. Final confirmations:

- `test_render_compositor.py:24-31` imports `_build_panel_styles`, `_is_multistep_reaction`, `_resolve_format`, `_resolve_style`, `render_figure`, `scoped_id` — **none of the three privates P0a.3 moves**. Safe to move.
- The three label privates have **zero importers outside `compositor.py`** — confirmed free to move.
- `tier_layout.py` currently imports **nothing** from `label_placement` — confirming the P0a.3 tier-seam-is-inert claim and the Step 5 `_overlaps` import is a new edge (flagged in the Step 5 risk list).

I have full verification. Writing the integrated blueprint.

---

# V3 Chassis Arc — Integrated Implementation Blueprint (Phase 0a seams + Step 5 scene solver)

**Working tree verified at HEAD `5cb0696` (post-R2/R5/PH).** Every file:line below is the *current* location. All four slices' ground-truth claims were re-verified against the tree; corrections and sign-off flags are called out inline.

## Verification corrections to the slices (read first)

| Claim in slice | Verified reality | Impact |
|---|---|---|
| P0a.1: `_PATHWAY_COMPATIBLE_ARCHETYPES` "imported into compositor at `:60`" | It is imported at **`compositor.py:57`** and used at `:420`, `:546`, `:568`. Defined at **`pathway_layout.py:324`**. | Cosmetic; the unification still works. |
| P0a.1: `pop` test raises `"...not yet wired in the compositor..."` | The `pop` test (`test_layout_panel.py:119-128`) exercises **`layout_panel`**, which raises **`"No layout engine registered for archetype"`** at `panel_layout.py:327-328` — NOT `_dispatch_layout`. | The `_dispatch_layout` `NotImplementedError` string is a *separate*, untested-by-`pop` path. Keep both strings verbatim; the `pop` test is satisfied purely by keeping `ARCHETYPE_TO_LAYOUT` a live mutable dict that `layout_panel` reads. |
| Step 5: `render_molecule_anchored` from `_mol_render.py:316` | True, but `tier_layout.py:57` imports it via the **`primitives.chemistry` re-export shim**. | The Nit-2 edit is at `tier_layout.py:361`; the renderer itself is untouched. |
| Step 5: current `_SLOT_EDGE_OFFSETS` | Confirmed 5 face edges only (`tier_layout.py:270-273`), no `cavity_*`. Edge-vocab guard at `:293-296` raises `match="attach edge"`. | `test_unsupported_attach_edge_raises` (`test_layout_tiers.py:159`, `edge="cavity_top"`) **will break** when P5.1 makes `cavity_*` resolvable — confirmed, must update. |
| `tier_layout` imports from `label_placement` | **None today.** | P5.2 (`LabelRequest`) and P5.1 (`_overlaps`) both add a *new* `tier_layout → label_placement` edge. Verified one-directional (no cycle): `label_placement` does not import `tier_layout`. |

**IR sign-off scan result:** Of all items below, **only P0a.6 touches `ir/_v2_models.py` / `ir/_v3_models.py`.** P0a.1–P0a.5 and P5.1–P5.4 are layout/render-layer only. I confirmed every Step-5 field already exists (`Attach.parent_anchor` `_v3_models.py:95`, `SceneEdge.label` `:113`, `Slot.label` `:76`, `AttachEdge.cavity_*` `_enums.py:131`), so **Step 5 needs no schema change**. Any drift into the schema by a non-P0a.6 item is a blueprint violation — none is planned.

---

## Dependency-ordered checklist

### P0a.1 — Unify the archetype→engine table (`_ARCHETYPE_PLAN`)

**Files + symbols (current file:line):**
- **NEW** `imageGen/layout/_archetype_plan.py` — leaf module holding `ArchetypePlan` (NamedTuple) + `_ARCHETYPE_PLAN` (mutable `dict`) + `_PATHWAY_PLAN_ARCHETYPES` (frozenset).
- `imageGen/layout/panel_layout.py:82-88` — `ARCHETYPE_TO_LAYOUT` literal → derived `{a: p.engine}` view.
- `imageGen/layout/panel_layout.py:202-211` — `_override_subengine_canvas` if/elif → `canvas_key`/`inject_canvas` read.
- `imageGen/render/compositor.py:420-433` (`_dispatch_layout`), `:546-550` (`_label_requests_fn`), `:568-572` (`_canvas_size`) — replace `in/==` pairs with `_ARCHETYPE_PLAN.get(...)`.
- **Keep** `compositor.py:575-585` `_compute_pathway_canvas` (test import target + wrapper).

**Concrete code shape (record + table):**
```python
# imageGen/layout/_archetype_plan.py
class ArchetypePlan(NamedTuple):
    engine: Callable[..., list[LayoutEntry]]
    canvas_fn: Callable[[Figure], tuple[float, float]]   # stores compute_pathway_canvas / _reaction_canvas
    label_fn: Callable[..., list] | None
    canvas_key: str          # "pathway" | "reaction"
    inject_canvas: bool      # True → set "<key>_canvas"; both set "<key>_origin"

_ARCHETYPE_PLAN: dict[Archetype, ArchetypePlan] = {
    Archetype.PATHWAY:            ArchetypePlan(layout_pathway, compute_pathway_canvas, pathway_label_requests, "pathway", True),
    Archetype.WORKFLOW:           ArchetypePlan(layout_pathway, compute_pathway_canvas, pathway_label_requests, "pathway", True),
    Archetype.CELLULAR_SCHEMATIC: ArchetypePlan(layout_pathway, compute_pathway_canvas, pathway_label_requests, "pathway", True),
    Archetype.MECHANISM_CARTOON:  ArchetypePlan(layout_pathway, compute_pathway_canvas, pathway_label_requests, "pathway", True),
    Archetype.REACTION_SCHEME:    ArchetypePlan(layout_reaction, _reaction_canvas, reaction_label_requests, "reaction", False),
}
```
Imports: `pathway_layout` (`layout_pathway`, `compute_pathway_canvas`, `pathway_label_requests`), `reaction_layout` (`layout_reaction`, `reaction_label_requests`, `REACTION_DEFAULT_PARAMS`), `ir.schema`, `types`. **All strictly below it in the DAG.**

`_override_subengine_canvas` body becomes:
```python
overrides = dict(base_params or {})
plan = _ARCHETYPE_PLAN.get(archetype)
if plan is not None:
    if plan.inject_canvas:
        overrides[f"{plan.canvas_key}_canvas"] = canvas
    overrides[f"{plan.canvas_key}_origin"] = origin
return overrides
```
`ARCHETYPE_TO_LAYOUT` becomes `{a: p.engine for a, p in _ARCHETYPE_PLAN.items()}` — **stays a plain mutable `dict`** (mandatory: `test_layout_panel.py:123` does `.pop`).

**Behaviour-preservation:** `_ARCHETYPE_PLAN.get(a) is None ⟺ a ∉ {5 archetypes}` (enum frozen at 5) ⟺ old fall-through. `plan.engine is layout_reaction ⟺ a == REACTION_SCHEME`. `_override_subengine_canvas` is case-exhaustive (proven in slice §3: pathway→`pathway_canvas`+`pathway_origin`; reaction→`reaction_origin` only; unmapped→untouched dict). The `"No layout engine..."` (panel) and `"...not yet wired..."`/`ValueError`/`NotImplementedError` (dispatch) strings are copied verbatim. Note `_canvas_size` keeps the `is compute_pathway_canvas` one-line check so the kept `_compute_pathway_canvas` wrapper still routes the pathway path (test import surface preserved).

**Test strategy:** Full `pytest` (1025) green, **zero golden updates** (pure dispatch refactor — any golden diff = bug). Targeted: `test_layout_panel.py:114-116` (identity), `:119-128` (`pop`/re-insert → `"No layout engine"`), `:131-143` (reaction-panel smiles). New structural unit: `{a: p.engine for a,p in _ARCHETYPE_PLAN.items()} == ARCHETYPE_TO_LAYOUT` and `frozenset(a for a,p in _ARCHETYPE_PLAN.items() if p.engine is layout_pathway) == _PATHWAY_COMPATIBLE_ARCHETYPES`. Import-cycle smoke: `python -c "import imageGen.layout._archetype_plan, imageGen.layout.panel_layout, imageGen.render.compositor"`.

---

### P0a.2 — `LoweringPlan` + `_lowering_plan(ir, style_name)` resolved once

**Depends on:** P0a.1 (`_ARCHETYPE_PLAN`).
**Files + symbols:**
- **NEW** in `compositor.py` (near `:98`): `LabelStrategy(Enum)`, `LoweringPlan(NamedTuple)`, `_lowering_plan(...)`, `_normalise_multistep_reaction(...)`.
- `compositor.py:171-234` (`render_figure` body) — route through `plan`.
- **Adopt slice option 1:** keep `_dispatch_layout(ir, style_dict, smiles_map, panel_styles=None)` and `_canvas_size(ir, entries)` **signatures unchanged** (pinned by `test_compositor_tiers.py:78,87`, `test_ir_schema_tiers.py:353`, `test_dynamic_canvas.py`).

**Concrete code shape:**
```python
class LabelStrategy(Enum):
    BAKED = "baked"; PER_PANEL = "panel"; LEAF = "leaf"

class LoweringPlan(NamedTuple):
    engine: Callable[..., list[LayoutEntry]]
    canvas_fn: Callable[[Figure], tuple[float, float]]
    label_strategy: LabelStrategy
    style_base: dict[str, Any]
    archetype_plan: ArchetypePlan | None
```
`render_figure` new control flow:
```python
ir = _normalise_multistep_reaction(ir, pathway_fallback)   # PH.1, BEFORE plan
plan = _lowering_plan(ir, style_name)
style_dict = plan.style_base
panel_styles = _build_panel_styles(ir, style_name) if ir.panels else {}
entries = _dispatch_layout(ir, style_dict, smiles_map, panel_styles=panel_styles)  # unchanged sig
computed_canvas = plan.canvas_fn(ir)                       # replaces _canvas_size(ir, entries) call
# label branch keys off plan.label_strategy (see P0a.3 for the extraction)
```
`_lowering_plan` is container-mode-first: `if ir.tiers → BAKED`; `if ir.panels → PER_PANEL`; else `_ARCHETYPE_PLAN.get(ir.archetype)` → `LEAF` (or unwired sentinel). `_normalise_multistep_reaction` extracts `compositor.py:188-207` **verbatim** (same `NotImplementedError`/`warnings.warn` strings, `model_copy(update={"archetype": PATHWAY})`).

**Behaviour-preservation:** PH.1 runs **before** `_lowering_plan` reads `ir.archetype`, so the archetype is final at resolution time (coercion routes everything through the pathway row in one decision). `_dispatch_layout`/`_canvas_size` keep signatures, so the three pinned test call sites are byte-identical. Schema's at-most-one-of-{leaf,panels,tiers} guard makes the `if/elif/else` provably unable to mis-route. `computed_canvas = plan.canvas_fn(ir)` returns the same value `_canvas_size(ir, entries)` did (canvas never depended on `entries` for any leaf/panel/tier path — verified: pathway uses `_compute_pathway_canvas(ir)`, reaction a constant, tiers `tier_canvas(ir)`, panels a constant).

**`stacklevel` caveat:** if the PH.1 warning is extracted into `_normalise_multistep_reaction`, bump `stacklevel=2 → 3` *only if* a test asserts warning origin. Verified: the PH.1 tests match the message substring, not the frame — so extraction is safe with `stacklevel=2` kept, OR keep the `warnings.warn` inline in `render_figure` before the plan call. **Recommend keeping the warn inline** to guarantee zero stacklevel risk.

**Test strategy:** Full suite green, zero golden updates. Targeted: PH.1 tests (multi-step coercion message + `pathway_fallback`), `test_compositor_tiers.py:76-87`, `test_ir_schema_tiers.py:350-353`, `test_dynamic_canvas.py`. New unit: `_lowering_plan(tier_fig).label_strategy is LabelStrategy.BAKED`, `(panel_fig)→PER_PANEL`, `(pathway_fig)→LEAF`.

---

### P0a.3 — `LabelCoordinator.place()` + `LabelScope`

**Depends on:** P0a.2 (`LabelStrategy`; the label branch is the `LEAF`/`PER_PANEL`/`BAKED` switch). Verified the three privates move freely (zero external importers).
**Files + symbols:**
- **NEW** `imageGen/render/label_coordinator.py` — `LabelScope(NamedTuple)`, `LabelCoordinator.place(...)`, `_run_leaf`, `_panel_scopes`, `_run_scopes_panel`; **moved** `_label_requests_fn` (from `compositor.py:535-550`) and `_panel_cell_bounds` (from `:436-465`); `_place_labels_per_panel` (`:468-532`) is **deleted/replaced**.
- `compositor.py:217-234` — replaced by a single `LabelCoordinator.place(...)` call.

**Concrete code shape:**
```python
class LabelScope(NamedTuple):
    entries: list[LayoutEntry]          # entry-subset AND occupancy-seed (same list)
    requests: list[LabelRequest]
    canvas: tuple[float, float] | None
    style_dict: dict[str, Any]
    panel_chain: tuple[str, ...] = ()
    position: tuple[float, float] | None = None   # None ⇒ no re-stamp (leaf)
    emit_leaders: bool = True
```
`place(ir, entries, style_dict, *, strict_labels, canvas, panel_styles)`: `if ir.tiers: return entries` (inert pass-through seam — P5.2 swaps it); `if ir.panels:` → `_panel_scopes`+`_run_scopes_panel`; else `_run_leaf`. Call site:
```python
if labels:
    from imageGen.render.label_coordinator import LabelCoordinator  # noqa: PLC0415
    entries = LabelCoordinator.place(ir, entries, style_dict,
        strict_labels=strict_labels, canvas=computed_canvas, panel_styles=panel_styles)
```

**Behaviour-preservation:** `_run_leaf` reproduces `compositor.py:224-234` exactly (same `_label_requests_fn` → `None`-guard → `place_labels` → `pathway_extlabel_leaders`). `_run_scopes_panel` is a line-by-line transcription of `_place_labels_per_panel:496-532`, with the **load-bearing invariant** `n = len(scope.entries)` and `scope.entries is bucket` (same list object) so the leader/label split `placed[:n]`/`placed[n:]` is preserved (leaders stay un-restamped, drifted labels get `_replace(panel_chain=(panel.id,), position=panel_offset)`). Dropping `and not ir.tiers` from the guard is byte-identical because `place()`'s first arm returns `entries` unchanged for tiers; `labels=False` short-circuit kept by the outer `if labels:`.

**Test strategy:** Golden suite (`test_golden_images.py`) is the primary guard — zero diffs. New unit: `LabelCoordinator.place(tier_fig, entries, …) is entries` (proves the tier seam is inert — pins the P5.2 swap as a deliberate change). Re-run `grep -rn` for the three privates over the full tree before deleting (verified empty now). Leave `place_labels`/`pathway_extlabel_leaders` imports in `compositor` if any out-of-tree importer relies on them (verified none in repo).

---

### P0a.4 — `AnchorRegistry.copy()` + `layer()`

**Independent of P0a.1–3.** Layout-layer only.
**Files + symbols (current file:line):**
- `anchors.py:30` — add `import copy`, `import contextlib`, `from collections.abc import Iterable`.
- `anchors.py:76-78` (`__init__`) — add `_overlay_anchors`/`_overlay_rails` (init `None`).
- `anchors.py` NEW methods — `copy()`, `layer(*, commit=True)` (contextmanager), `_write_anchors`/`_write_rails`, `_lookup_anchor`/`_lookup_rail`.
- `anchors.py:93-94` (`publish` loop) → write through `self._write_anchors()`.
- `anchors.py:109` (`publish_rail`) → write through `self._write_rails()`.
- `anchors.py:112-116` (`has`), `:120-122` (`rail`), `:136-140` (`resolve`) → route through `_lookup_*`, union known-set with overlay.

**Concrete shape:**
```python
def copy(self) -> "AnchorRegistry":
    clone = AnchorRegistry()
    clone._anchors = copy.deepcopy(self._anchors)
    clone._rails = copy.deepcopy(self._rails)
    return clone

@contextlib.contextmanager
def layer(self, *, commit: bool = True):
    if self._overlay_anchors is not None:
        raise RuntimeError("AnchorRegistry.layer() is not re-entrant")
    self._overlay_anchors, self._overlay_rails = {}, {}
    try:
        yield self; merged = True
    except BaseException:
        merged = False; raise
    finally:
        oa, orr = self._overlay_anchors, self._overlay_rails
        self._overlay_anchors = self._overlay_rails = None
        if merged and commit:
            self._anchors.update(oa); self._rails.update(orr)
```
Single overlay pair (not a stack); re-entrant `layer()` raises. `validate_refs` lands in P0a.5.

**Behaviour-preservation:** With no layer open, `_overlay_* is None` ⇒ `_lookup_anchor` reduces to `self._anchors.get(ref)`, `known` reduces to `sorted(self._anchors)` — byte-identical to current `resolve`/`rail`/`has` bodies and error strings. All new behaviour gated behind `with reg.layer():`. `copy()` independence: clone rebinds both dicts to deepcopies; `Rail` is `frozen` so deepcopy is value-equal. Existing tests never open a layer → unaffected.

**Test strategy:** Add 4 unit tests to `test_anchor_keystone.py` (imports `AnchorRegistry`, `Rail` at `:24`): rollback-leaves-base-intact, commit-merges, exception-always-drops-even-with-commit, copy-is-independent. Full suite green.

---

### P0a.5 — `validate_refs` aggregate + tier-loop wiring

**Depends on:** P0a.4 (`_lookup_*`-aware `has`, so `validate_refs` is overlay-correct).
**Files + symbols:**
- `anchors.py` NEW — `def validate_refs(self, refs: Iterable[str]) -> list[str]: return [r for r in refs if not self.has(r)]`.
- `tier_layout.py` — insert intra-scene aggregate **before** `:411` (`for edge in scene.connect`), after the scene-frame publish at `:387-391`.
- `tier_layout.py` — insert transitions aggregate **between** the rails loop (ends `:631`) and the transitions loop (`:634` `for te in tier.transitions`), inside the `if tier.role == TierRole.SCENE_ROW:` block (`:617`).

**Concrete shape (transitions; intra-scene is symmetric):**
```python
te_unresolved: list[str] = []
for te in tier.transitions:
    if te.from_ref.startswith("rail:") or te.to_ref.startswith("rail:"):
        continue  # screened by the NotImplementedError guard at :636
    for raw in (te.from_ref, te.to_ref):
        if registry.validate_refs([_ref_to_key(raw)]):
            te_unresolved.append(f"{te.ir_id}: {raw!r}")
if te_unresolved:
    raise ValueError(f"Tier '{tier.id}' has unresolved transition endpoints: "
                     + "; ".join(te_unresolved))
```
Uses `_ref_to_key` (`tier_layout.py:534`) for the lookup (so `scene@edge`→`scene.edge`) but prints the author's `raw` ref; tags with `te.ir_id` / `edge.ir_id`.

**Behaviour-preservation:** On valid figures, `validate_refs` returns `[]` for every endpoint (same `has`-backed keys `resolve_edge` would use) ⇒ no raise ⇒ falls through to the unchanged `resolve_edge` loops. On invalid figures it raises `ValueError` slightly earlier with an aggregated message (still `ValueError`; no test asserts the old single-ref unknown-anchor string for tiers). The `rail:` `continue` preserves the existing `NotImplementedError` ordering (`test_rail_endpoint_transition_not_supported`, `match="rail.*endpoint"`).

**Test strategy:** Full suite green. New unit: a tier with two bad transition refs → one `ValueError` naming **both** `tedge_*` ids (the P0a.5 done-criterion). Confirm `test_rail_endpoint_transition_not_supported` still raises `NotImplementedError` (not shadowed).

---

### P0a.6 — **IR change, NEEDS SIGN-OFF** (out of this blueprint's edit scope)

Not detailed in the four slices beyond references. **This is the only item that touches `ir/_v2_models.py` / `ir/_v3_models.py`.** The slices note P0a.6 handles build-time ref validation that the dynamic (layout-time) P0a.5 deliberately leaves alone (`_v3_models.py:169-176` `Scene._validate_scene`). **Do not begin P0a.6 until the IR owner signs off on the schema delta.** P5.1–P5.4 do **not** depend on P0a.6 (Step-5 fields all already exist), so the rest of the arc proceeds without it.

---

### P5.1 — Topological attach/offset solver + co-location de-overlap

**Depends on:** **P0a.4 `layer()`/`copy()`** (the scene solve runs inside one `registry.layer()` so a failed solve rolls back partial publishes). If P0a.4 slips, P5.1 can ship the solver *without* the wrapper (greedy solver has no multi-pass rollback need yet) — but the gate is sequenced first; prefer it.
**Files + symbols:**
- `tier_layout.py:276-329` — **rewrite** `_solve_slot_centers` (same name; keyword-only new params with defaults so `test_layout_tiers.py:140/154/161` 3-positional calls are unaffected).
- `tier_layout.py:270-273` — extend `_SLOT_EDGE_OFFSETS` with `cavity_*` rows.
- `tier_layout.py` NEW — `_SlotBox(NamedTuple)`, `_attach_point`, `_slide_off_parent`, `_deoverlap`, `_box`; import `_overlaps` from `label_placement` (NEW edge — flagged in RISK).
- `tier_layout.py:348` — `_layout_scene` call wrapped in `with registry.layer() as scene_layer:`.

**Concrete signature:**
```python
def _solve_slot_centers(scene, rect, slot_size, *,
    slot_extents: dict[str, tuple[float, float]] | None = None,
    parent_anchors: dict[str, dict[str, tuple[float, float]]] | None = None,
) -> dict[str, tuple[float, float]]:
```
Kahn topological sort over the attach DAG; per-child `parent_center + edge_unit·PARENT_size + offset` (the historic `:321` formula, using parent extent for the slide); then `_deoverlap` pushes co-located boxes perpendicular to the attach axis deterministically (`+1,−1,+2,−2,…`), reusing `label_placement._overlaps` (the shared AABB test — reuse, not engine-merge).

**Behaviour/new-behaviour:** With `slot_extents=None`, `parent_anchors=None`, face edges, and non-overlapping boxes, the formula and order are byte-identical to current `:319-322` → the 3 existing solver tests (`a=(150,50) b=(175,50) c=(200,50)`, cycle `ValueError` `"cyclic or unresolvable attach chain"`) pass unchanged. **New behaviour:** two `center`-attached children of one parent now get disjoint boxes (fixes MF-3). **Breaking:** `cavity_top` becomes resolvable → `test_unsupported_attach_edge_raises` (`test_layout_tiers.py:159`) **must be updated** (keep a `custom`-with-no-`parent_anchor` case for the `NotImplementedError` contract). Recommend the **symmetric pre-seed** for `center`/`cavity_center` co-location (split `±(child_w/2+margin)`) for legibility, with relaxation as fallback.

**Test strategy:** Preserve the 3 solver tests (edge-vocab one updated). New: MF-3 acceptance (two boxes disjoint `his.maxx ≤ lig.minx`); determinism (solve twice → identical dict); diamond DAG resolves `a` first / `d` last, 2-cycle raises; Nit-1 extent test. Full suite green; flag any tier pixel-golden shift.

---

### P5.2 — Scene-local labels via `LabelCoordinator` tier branch

**Depends on:** **P0a.3** (`LabelCoordinator` seam — the tier arm flips from inert `return entries` to a real per-scene scope) **and P5.1** (de-overlapped `boxes`/`centers`/`edge_midpoints` feed the requests).
**Files + symbols:**
- `tier_layout.py` NEW — `scene_label_requests(scene, centers, boxes, content_extent, edge_midpoints, params)` (sibling of `pathway_label_requests`; imports `LabelRequest` from `label_placement` — NEW edge).
- `tier_layout.py:401-407` — retire the fixed-coordinate `_caption_group` **call** (keep `_caption_group` the function — directly tested at `test_compositor_tiers.py:220`).
- `tier_layout.py:540` `layout_tiers` — add `place_scene_labels: bool = True`; run `place_labels` per scene with `canvas = scene cell rect` (scene-locality via the engine's existing canvas-clip at `_first_fit`).
- `compositor.py:208` (`_dispatch_layout` tier branch) — pass `place_scene_labels=labels`.

**Concrete shape:** `scene_label_requests` emits one `LabelRequest` per `\n`-line of `scene.label` ( id `f"scene_{scene.id}_label"` — **preserved**), one per non-TEXT `Slot.label`, one per `SceneEdge.label`; TEXT slots skipped (already rendered as body). **Recommend wiring point (A)** — emit+place inside `_layout_scene` where cell rect/extent/boxes already exist.

**Behaviour/golden risk:** `place_labels` tags the emitted entry `label_{ir_id}` → `label_scene_s_aspirin_label`, so `test_tiered_figure_renders_end_to_end`'s substring assertion `scene_s_aspirin_label` (`test_compositor_tiers.py:96`) **still matches**; `scene_s_aspirin_badge` is untouched chrome. **The caption's (x,y) changes** (greedy vs fixed `maxy+gap+font`) → any tier pixel-golden shifts (**HIGH-severity intended change** — refresh goldens or switch to placement-invariant assertions: "caption below content extent").

**Test strategy:** New: `scene_label_requests` emits exactly the right count (TEXT skipped, ids preserved); end-to-end SVG contains `label_scene_<id>_<edge.ir_id>_label`; scene-locality (scene-2 caption bbox stays in scene-2 cell rect). Token-preservation + legibility tests stay green.

---

### P5.3 — Seed annotation pass with scene bboxes

**Depends on:** **P5.2** (the placed scene-label boxes are the occupancy seed).
**Files + symbols:**
- `tier_layout.py` `layout_tiers` — add `return_occupancy: bool = False`; when True, return `(entries, placed_label_boxes)`.
- `annotations.py:218` `annotation_entries` — add `occupied: list[Bbox] | None = None`; route `LABEL`/`CAPTION` through `place_labels`/first-fit seeded with `occupied` when present; `SCALE_BAR` stays fixed.
- `compositor.py:241-243` — pass `occupied=scene_label_boxes if ir.tiers else None`.

**Behaviour-preservation:** `occupied=None` (default, **every non-tier path**) → `annotation_entries` runs its current fixed-coordinate code verbatim. `return_occupancy=False` default keeps the single-list return for every existing `layout_tiers` caller. Only tiered figures with both scene labels and annotations get the collision-aware path.

**Test strategy:** Regression: tiered figure + global `CAPTION` annotation positioned where a scene caption sits → after the seed, bboxes disjoint. Confirm non-tier annotation goldens untouched.

---

### P5.4 — Deferred placement nits (3 independent edits)

**Depends on:** P5.1 (`slot_extents` thread for Nit 1). Nits 2–3 are isolated `_layout_scene`/`_text_group` edits, any order.
**Files + symbols:**
- **Nit 1** (`tier_layout.py:321` slide / `:377` extent) — thread `slot_extents={slot.id: _slot_bbox_size(slot, params)}` into the solver; use child extent for de-overlap half-size, parent extent for slide. `_slot_bbox_size` reuses `_slot_bbox` (`:512`) per-kind logic.
- **Nit 2** (`tier_layout.py:361`) — `rw, rh = int(round(sw)), int(round(sh))`; render at `(rw, rh)`; `top_left = (center[0]-rw/2, center[1]-rh/2)`; publish anchors with that same `top_left`. (Default `(180.0,140.0)` rounds to the same `int()` already produces → **no golden change for default preset**.)
- **Nit 3** (`tier_layout.py:366-372`, `_text_group` `:421`) — publish TEXT `center` anchor at the visual midline; render baseline at `center_y + 0.35·fs` (mirror the `_badge_group:486` `cy + r*0.35` fix).

**Behaviour-preservation:** Each nit is a no-op for the default-preset/molecule-only fixtures (Nit 1 absent `slot_extents` ⇒ old formula; Nit 2 `round(180.0)==int(180.0)`; Nit 3 only moves the text-slot anchor that nothing currently resolves an edge to in the goldens). New behaviour appears only for fractional presets / TEXT parents / edges-to-text.

**Test strategy:** One regression each — Nit 1: TEXT parent slide uses text bbox; Nit 2: fractional `(181,141)` slot, anchor within 0.5px of center; Nit 3: published text `center` == midline, rendered `y == center_y + 0.35·fs`. Full suite green (verify fractional-preset claim with a full run).

---

## Cross-item dependency graph (explicit)

```
P0a.1 ─► P0a.2 ─► P0a.3 ──────────────┐
P0a.4 ─► P0a.5                         │
P0a.4 ──────────────► P5.1 ─► P5.2 ◄──┘   (P5.2 needs BOTH P0a.3 LabelCoordinator AND P5.1 boxes)
                              P5.2 ─► P5.3
                              P5.1 ─► P5.4 (Nit1; Nits 2-3 independent)
P0a.6  (IR sign-off gate — blocks nothing in P5.x; parallel track)
```
- **P5.1 needs P0a.4** `layer()`/`copy()` (degradable: solver can ship without the wrapper if P0a.4 slips).
- **P5.2 needs P0a.3** `LabelCoordinator` (the tier arm it flips) **and P5.1** (de-overlapped geometry for requests).
- **P5.3 needs P5.2** (the occupancy seed is P5.2's placed boxes).
- **P0a.2 needs P0a.1** (`_ARCHETYPE_PLAN`). **P0a.3 needs P0a.2** (`LabelStrategy`). **P0a.5 needs P0a.4** (`_lookup_*`-aware `has`).

---

## Consolidated RISK list

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| R1 | **P5.2 caption position changes** (greedy vs fixed `maxy+gap+font`) → every tier pixel-golden shifts; SVG text `y` differs. | **HIGH (intended)** | Token assertions survive via preserved `ir_id`. Refresh image goldens or replace exact-y with placement-invariant assertions. |
| R2 | `test_unsupported_attach_edge_raises` (`test_layout_tiers.py:159`, `cavity_top`) breaks when P5.1 makes `cavity_*` resolvable. | Med | Update the test; keep a `custom`-no-`parent_anchor` case for the `NotImplementedError` contract. |
| R3 | **P0a.1/P0a.3 must produce zero golden diffs** (pure dispatch/label-extraction refactors). | Med | `test_golden_images.py` is the tripwire — any diff = bug, revert. |
| R4 | **Import-cycle hazard:** new `_archetype_plan` leaf (P0a.1) and new `tier_layout → label_placement` edge (P5.1 `_overlaps`, P5.2 `LabelRequest`). | Med | `_archetype_plan` sits in `panel_layout`'s exact DAG slot (imports only `pathway_layout`/`reaction_layout`/`ir.schema`/`types`); both engines verified to import neither each other nor anything above them. `label_placement` verified to NOT import `tier_layout` → one-directional. Smoke-test with a fresh-process import after each. |
| R5 | `ARCHETYPE_TO_LAYOUT` must stay a **mutable importable `dict`** (P0a.1) — `MappingProxyType`/property breaks `test_layout_panel.py:123` `.pop`. | Med | Derive as a plain `dict` snapshot `{a: p.engine}`; `layout_panel` keeps reading it. |
| R6 | Panel-offset re-stamp + leader split (P0a.3) — `placed[:n]/[n:]` relies on `scope.entries is bucket` (same object, anchoring `n`). A future copy breaks it. | Med | Document in `LabelScope` docstring: `entries` must be the same list object whose length anchors the split. |
| R7 | De-overlap non-determinism (P5.1). | High-if-wrong | Algorithm is fully deterministic (Kahn order + declaration tiebreak + fixed `+/−` alternation, no set iteration over coords). Add a determinism test. |
| R8 | Nit-2 `int(round)` vs `int()` shifts molecule render by 1px for fractional presets. | Low–Med | Default `(180.0,140.0)` rounds identically → no change for default preset; no fractional fixtures exist. Verify with full-suite run. |
| R9 | `_normalise_multistep_reaction` extraction changes warning `stacklevel` (P0a.2). | Low | Keep `warnings.warn` inline in `render_figure` before the plan call (zero stacklevel risk); PH.1 tests match message substring only. |
| R10 | **IR drift:** any non-P0a.6 item touching `ir/_v2_models.py`/`ir/_v3_models.py`. | **Blocker if it happens** | **None planned.** Only P0a.6 touches the schema (sign-off gated). Step-5 fields all pre-exist. If any other item drifts into `ir/`, STOP and get sign-off. |

---

## Commit boundary suggestion

| Commit | Items | Rationale |
|---|---|---|
| **C1** | P0a.1 + P0a.2 | The table unification and the `LoweringPlan` that consumes it are one conceptual change (single source of truth → resolved once). Tight coupling; one "no golden diff" verification. |
| **C2** | P0a.3 | Label extraction is self-contained (new module + one compositor block); the inert tier seam is its own reviewable unit. Separate so the `LabelCoordinator.place(tiers) is entries` identity test pins it before P5.2 moves it. |
| **C3** | P0a.4 + P0a.5 | `copy()`/`layer()`/`validate_refs` are all `anchors.py` + the tier-loop wiring; one cohesive registry-capability commit with its 4+1 new unit tests. |
| **C4** | P0a.6 | **Separate commit, gated on IR sign-off.** The only schema-touching change; must be isolable/revertible. |
| **C5** | P5.1 (+ P5.4 Nit 1) | Solver rewrite + the `slot_extents` thread (Nit 1 is the natural fold). One acceptance criterion (MF-3 disjoint boxes) + the edge-vocab test update. |
| **C6** | P5.2 + P5.3 | The scene-label tier-branch flip and its annotation occupancy seed are the same user-visible behaviour change (scene-local labels that also de-conflict with annotations); commit together so the golden refresh happens once. |
| **C7** | P5.4 Nits 2 + 3 | Isolated sub-pixel/baseline fixes, no cross-dependency; small cleanup commit. |

Recommended landing order: **C1 → C2 → C3 → C5 → C6 → C7**, with **C4 (P0a.6)** slotted whenever IR sign-off lands (it blocks nothing in the P5 arc).

**Files touched across the whole arc (all absolute):**
- NEW `/Users/josephardizzone/Desktop/imageGen-v2.6/imageGen/layout/_archetype_plan.py` (P0a.1)
- NEW `/Users/josephardizzone/Desktop/imageGen-v2.6/imageGen/render/label_coordinator.py` (P0a.3)
- `/Users/josephardizzone/Desktop/imageGen-v2.6/imageGen/render/compositor.py` (P0a.1/2/3, P5.2/5.3)
- `/Users/josephardizzone/Desktop/imageGen-v2.6/imageGen/layout/panel_layout.py` (P0a.1)
- `/Users/josephardizzone/Desktop/imageGen-v2.6/imageGen/layout/anchors.py` (P0a.4/5)
- `/Users/josephardizzone/Desktop/imageGen-v2.6/imageGen/layout/tier_layout.py` (P0a.5, P5.1/5.2/5.4)
- `/Users/josephardizzone/Desktop/imageGen-v2.6/imageGen/render/annotations.py` (P5.3)
- Tests: `tests/test_anchor_keystone.py`, `tests/test_layout_tiers.py`, `tests/test_layout_panel.py`, `tests/test_compositor_tiers.py` (+ new structural/unit tests per item)
- **Schema (`ir/_v2_models.py`, `ir/_v3_models.py`): touched by P0a.6 ONLY — sign-off required.**