# Architectural Decisions

Durable record of design choices that span multiple phases. Each entry
captures the *why* — future agents and future-you should be able to
judge edge cases without re-deriving the decision. Add a new entry only
when the choice (a) was non-obvious, (b) affects code outside the
module where it's enforced, or (c) closes off an alternative someone
else might naturally try.

Entries are append-only. If a decision is reversed later, add a new
entry explaining the reversal — don't edit the old one.

---

## D1 — IR-id tagging uses both `id` and `data-ir-id`

**Decided:** 2026-05-11 (Phase 5 planning)
**Where enforced:** `render/compositor.py`

Every SVG element the compositor emits for an IR object carries two
attributes:

- `data-ir-id="<raw-ir-id>"` — the unprefixed IR id, always. This is
  what Phase 6's `semantic_check` parses to re-derive the IR from the
  rendered SVG.
- `id="<scoped-id>"` — a document-unique id, prefixed with the panel
  hierarchy when nested. Convention: `id = "__".join(panel_chain +
  [raw_ir_id])`. At depth 0 (no panel) this is just `raw_ir_id`.

**Why both:**

- SVG `id` must be unique per document. IR entity ids are unique only
  within a single `Figure`; a top-level `Figure` with panels contains
  nested sub-figures whose entity ids can collide. Prefixing with the
  panel id chain disambiguates without changing IR semantics.
- `data-ir-id` is namespaced and survives any future XML
  transformations (CSS hooks, manual edits in a vector editor) that
  might rewrite or strip the `id` attribute.
- Phase 6 verification reads `data-ir-id`; downstream tools (a future
  interactive viewer, deep linking) read `id`.

**Synthetic ids for IR objects without one:**

- `Relation` has no `id` field — synthesize as
  `rel_{source}_{type}_{target}` (collision-free given that `(source,
  target, type)` is effectively unique within a Figure; if a future
  validator allows duplicates, append a positional index).
- `Compartment` band entries: use the compartment's `id`.
- `Panel` chrome: use the panel's `id` with a `_chrome` suffix.
- Label primitives (from `place_labels`): use
  `label_{anchored-ir-id}` where the anchored id is the entity or
  relation the label points at.

---

## D2 — Demonstrative-data watermark — RETIRED (2026-06-06)

**Decided:** 2026-05-11 (Phase 5 planning) · **Retired:** 2026-06-06

Originally a v1 stub (`_needs_watermark` always `False`); briefly wired for
the FR10 `voltage_trace` glyph to auto-caption "Illustrative — not real data".
**Removed entirely** — the watermark mechanism (`_needs_watermark`,
`_inject_watermark`, the chart-like-primitive set) is gone from
`render/compositor.py`. Schematic figures don't plot real measurements, so the
caption was friction with no benefit; authors who want such a note can add a
plain `caption` annotation themselves.

---

## D3 — `place_labels` auto-invokes when a `*_label_requests` helper exists

**Decided:** 2026-05-11 (Phase 5 planning)
**Where enforced:** `render/compositor.py`

The compositor inspects the dispatched layout engine for a sibling
`*_label_requests` helper (e.g., `pathway_label_requests`). If found:
call it, pass its output to `place_labels`, append the resulting label
entries to the layout output before composing the SVG.

Caller opts out with `render_figure(..., labels=False)`. Defaults to
`True`.

**Why auto-invoke:**

Every call site that needs labels would otherwise have to chain
`layout_pathway → pathway_label_requests → place_labels` by hand. That
chain is mechanical and the renderer is the right place to hide it.
Reaction layouts (no labels in v1) and panels (no labels in v1) are
no-ops — the absence of a `*_label_requests` helper skips the pass.

**Escape hatch:** `labels=False` is for debugging the bare layout
output (you'll see entity primitives without their callouts). If
`place_labels` raises `LabelPlacementError`, the renderer surfaces it
— this is the "fail loudly" hard rule, not a reason to swallow.

---

## D4 — `smiles_map` is a `render_figure` kwarg, not an IR field

**Decided:** 2026-05-11 (Phase 5 planning)
**Where enforced:** `render/compositor.py::render_figure`

`render_figure(ir, output_path, *, smiles_map=None, ...)`. When the
dispatched layout engine is `layout_reaction` (or any future engine
that requires SMILES), the compositor passes `smiles_map` through.
Missing-when-required raises a clear `ValueError` listing the entity
ids that need SMILES strings.

**Why not an IR field:**

- The IR schema is load-bearing and changes require explicit approval
  (CLAUDE.md hard rule). Adding `entity.smiles` or `figure.smiles_map`
  is an additive change that *could* be defended later, but doing it
  *now* — before Phase 7 (LLM frontend) defines how SMILES enters the
  pipeline — risks designing the field for the wrong populator.
- Phase 7 will likely build `smiles_map` at prompt-parse time from a
  PubChem / RDKit lookup. That code can pass the map to
  `render_figure` directly without needing to round-trip through the
  IR.
- The pre-existing `layout_reaction(figure, smiles_map=...)` API is
  already shaped this way; the renderer just forwards.

**When to revisit:** Phase 7. If the LLM frontend always builds a
SMILES map and the round-trip through `render_figure`'s kwarg becomes
cumbersome, add `figure.smiles_map: dict[str, str] | None = None` to
the IR schema as a thin convenience layer (with the kwarg still
overriding).
