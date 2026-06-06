# Proposal: FR8 — labels on parallel forward/back edges

**Status:** ✅ IMPLEMENTED (Option C, four-value enum — approved 2026-06-06).
`RelationLabelSide {above,below,left,right}` added to `Relation`; reciprocal
pairs auto-separate; explicit `label_side` overrides. See git history.
**Cross-ref:** BACKLOG FR8 (resolved), V3-L2 (force-directed placement).

---

## Problem (grounded)

When two entities are joined by both a forward and a back edge — e.g.
`A → B` "subunit dissociation" and `B → A` "GTP hydrolysis" — the two arrows
run between the same pair of boxes, roughly parallel. In
`pathway_label_requests` (`layout/pathway_layout.py:2188`) every
mostly-horizontal relation label is built with the **same** candidate order:

```python
priority = ("above", "below", "right", "left", "center")
```

So both labels try `above` first. `place_labels` then detects the collision and
bumps one to its next candidate, but the result reads as two labels stacked on
the same side of the edge pair — the FR8 symptom. The author has no way to say
"put the forward label above the edge and the back label below it."

There is currently **no** notion of an edge "side" anywhere in the IR or layout.

---

## Options

### Option A — Auto-detect reciprocal edges (no schema change)
Detect each `(A→B, B→A)` pair in `pathway_label_requests` and deterministically
flip one label's priority to `("below", ...)` while the other keeps
`("above", ...)`. Tie-break by `(source, target)` ordering for determinism.

- **Pros:** zero schema surface; no approval needed; fixes the common case
  (the FR8 examples are exactly reciprocal pairs) with no author effort.
- **Cons:** no author control over *which* label lands above vs below; only
  helps true reciprocal pairs, not two same-direction parallel edges.

### Option B — Add `label_side` to `Relation` (schema change)
Author pins each label explicitly:

```python
class RelationLabelSide(str, Enum):
    ABOVE = "above"
    BELOW = "below"

class Relation(_IRBase):
    source: str
    target: str
    type: RelationType
    label: str | None = None
    label_side: RelationLabelSide | None = None   # NEW — None = current behavior
    conditions: ReactionConditions | dict[str, Any] | None = None
```

`pathway_label_requests` reorders the priority tuple to lead with the requested
side:

```python
if relation.label_side is RelationLabelSide.ABOVE:
    priority = ("above", "below", "right", "left", "center")
elif relation.label_side is RelationLabelSide.BELOW:
    priority = ("below", "above", "right", "left", "center")
else:
    # unchanged: derive from arrow orientation as today
```

- **Pros:** explicit, predictable; works for any edge (not just reciprocal);
  matches the BACKLOG note.
- **Cons:** schema change (gated); `above/below` is meaningless for a vertical
  arrow (would need to also honor `left/right`, or document it as a hint that
  degrades to the orientation default).

### Option C — Hybrid (recommended)
Ship **Option A's auto-detection as the default**, and add **Option B's
`label_side` as an optional override**. Reciprocal pairs fix themselves; authors
who want control (or have non-reciprocal parallel edges) set `label_side`.

---

## Recommendation

**Option C**, but staged:

1. **Land Option A now — no schema, no approval.** It resolves the actual FR8
   figures (reciprocal pairs) immediately and is pure layout. I can do this
   under the existing "go" workflow.
2. **Defer Option B's schema field** until you've seen Option A's output and
   decide the explicit override is worth the schema surface. If you approve the
   field now, I'll land both together.

This keeps the load-bearing schema untouched unless the auto-heuristic proves
insufficient in practice.

---

## Details (applies to whichever option lands)

**`label_side` semantics (Option B/C):** a *hint*, not a guarantee — it leads the
priority tuple, so `place_labels` can still fall back to another side if the
preferred one is occupied. For a mostly-vertical arrow, `above/below` is
ambiguous; the value is honored as written but the orientation default already
prefers `left/right` there, so I'd document `label_side` as "for
mostly-horizontal edges; ignored where it doesn't apply." (Alternative: a
4-value enum `above/below/left/right` — more precise, more surface.)

**Validation:** none beyond the enum (Pydantic rejects unknown strings). No
cross-field rules needed; `label_side` with no `label` is harmless (ignored).

**Backward compatibility / goldens:** `label_side` defaults to `None` →
byte-identical to today. Option A changes output **only** for figures that have
a reciprocal edge pair with labels on both — none exist in the current fixtures
(verified: no golden has an `A→B`+`B→A` labeled pair), so **no golden regen
expected**. I'll confirm with a full run.

**Tests:**
- Auto-detect: a reciprocal labeled pair yields one `above`-led and one
  `below`-led `LabelRequest`; a single edge is unchanged.
- (Option B/C) `label_side="below"` leads the priority with `below`;
  `None` matches the orientation default; round-trips through `from_dict`/JSON.

**Short-term fallback (already available, no code):** authors can prefix labels
with ASCII arrows (`"→ GTP hydrolysis"` / `"← subunit dissociation"`) to
disambiguate direction without any side control.

---

## Decision needed

- [ ] **A only** — auto-detect reciprocal edges, no schema change (I proceed now).
- [ ] **C / B** — also approve the `label_side` schema field (I land both).
- [ ] **Two-value (`above/below`) vs four-value (`+left/right`)** enum, if B/C.
