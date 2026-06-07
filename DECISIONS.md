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

---

## D5 — `cells` / `lab_equipment` wired via an adapter layer, not direct dispatch

**Decided:** 2026-06-06 (cleanup pass)
**Where enforced:** `primitives/entity_adapters.py`, `layout/_geom.py`,
`verify/convention_check.py`

The `cells` and `lab_equipment` modules were fully built and tested but
*unreachable*: `ENTITY_TO_PRIMITIVE` / `PRIMITIVE_REGISTRY` only referenced
`proteins`, `glyphs`, `nucleic_acids`, so the documented `cell` / `organelle`
/ `equipment` / `sample` entity types silently rendered as a generic protein
box. They are now wired:

- `CELL → cell`, `ORGANELLE → mitochondrion`, `EQUIPMENT → microscope`,
  `SAMPLE → tube` defaults, plus `primitive=` overrides for the full set
  (cell styles, 5 organelles, microscope/well_plate/tube/pipette/gel/mouse/
  human_figure).

**Why an adapter layer (`entity_adapters.py`) instead of editing those
modules:** the dispatch convention is
`(label, position_centre, *, size, color, style_dict)` with a fit-aware label.
`cells.cell_outline` returns `(group, curve)` with no label/position;
`lab_equipment` icons draw at a local origin at an intrinsic size and don't
scale. The adapters scale-to-fit each icon into the slot, add a wrap/shrink
label via `_text.fit_label` (so wide method labels don't spill — see the
scrnaseq workflow), and keep the underlying modules (and their tests)
untouched.

**Coupling note:** `convention_check._PRIMITIVE_SHAPE` must carry a shape tag
for every `PRIMITIVE_REGISTRY` entry, else it raises `KeyError` at verify
time. `tests/test_entity_adapters.py::test_primitive_shape_covers_registry`
now guards this.

**Not wired (deliberate):** the `membranes` standalone draw functions
(compartment-boundary primitives; `membranes.nuclear_envelope` is reached
transitively via the `nucleus` organelle). `render_molecule` and
`render_functional_group` were subsequently wired — see D6.

---

## D6 — chemistry-as-entity (`molecule`, `functional_group`) carries its input in `style`, and is skipped by `convention_check`

**Decided:** 2026-06-06 (EW1, EW2)
**Where enforced:** `primitives/entity_adapters.py`, `layout/_geom.py`,
`verify/convention_check.py`

A `metabolite` / `generic` entity with
`style={"primitive": "molecule", "smiles": "<SMILES>"}` now renders its 2-D
RDKit structure inline in a pathway (previously SMILES rendered only inside
`reaction_scheme` via `--smiles-map`). The `functional_group` primitive is the
same pattern: the group name comes from `style.functional_group` (or the entity
label), and `render_functional_group` supplies the structure + its own name
label, so the adapter adds no second label.

**Why SMILES rides in `style`, not a new IR field:** the dispatch convention
passes a *label*, not a structure string. `style` is already the per-entity
extension channel (`primitive`, `sublabel`, `dna_break`) and flows into the
primitive's `style_dict` untouched, so the adapter reads `style["smiles"]` with
no schema change — keeping D4's "SMILES is not an IR field" stance intact. (The
reaction `--smiles-map` kwarg path is unchanged and remains the route for full
schemes.)

**Why `convention_check` skips it:** that check verifies an entity renders with
its *EntityType's conventional shape*. A molecule is a composite RDKit drawing,
not a type glyph — exactly the case reactions are already skipped for. It is
listed in `_SKIP_SHAPE_PRIMITIVES` (not `_PRIMITIVE_SHAPE`), and the
registry-coverage guard test accepts either set. This also makes the
missing/invalid-SMILES fallback (warn + label-only) safe: no shape is required.

**Cost containment:** `chemistry` (hence RDKit) is imported lazily inside the
adapter, so the `_geom` import chain stays RDKit-free for figures with no
molecules.

---

## D7 — `liposome` surfaces the dead membrane primitives as a vesicle glyph (EW3)

**Decided:** 2026-06-07 (EW3)
**Where enforced:** `primitives/entity_adapters.py`, `layout/_geom.py`,
`verify/convention_check.py`, `primitives/membranes.py`

`membranes.cell_membrane_outline` + `membranes.lipid_bilayer` were built and
tested but unreachable (only `nuclear_envelope` was, transitively via the
`nucleus` organelle). They are now reachable through a new `liposome` entity
primitive — a closed phospholipid bilayer ring (two leaflets of head groups
around an empty lumen) — via `style={"primitive": "liposome"}`. The adapter
consumes `cell_membrane_outline`'s curve purely for anchoring and renders only
`lipid_bilayer`, so the first shape element is the bilayer tail `<polygon>`
(its `_PRIMITIVE_SHAPE` tag — it is *not* skipped, unlike the composite
molecule/functional_group of D6).

**Why a new name, not `vesicle`:** `glyphs.vesicle` already exists as a simple
filled-circle "membrane-bound sphere". `liposome` is the distinct textbook
bilayer-cross-section drawing; the two coexist in `PRIMITIVE_REGISTRY`.

**EW3's original premise was stale.** The backlog claimed `_compartment_band`
"draws a plain band" — it does not: it already renders a lipid-bilayer border
for `MEMBRANE` compartments (`_draw_bilayer_border`) and a nuclear-envelope
border for `NUCLEUS` (`_draw_nuclear_border`), as flat horizontal stripes.
Those inline stripe helpers are *deliberately separate* from `lipid_bilayer`
(top-anchored straight stripe vs. symmetric offset from a closed curve), so
compartment rendering was left untouched and no golden images shifted. EW3 was
therefore re-scoped from "wire into compartments" to "surface as an entity",
matching the EW1/EW2 adapter pattern.

**Seam fix:** surfacing `lipid_bilayer` exposed a latent bug — on a closed
curve its tail polygon (`outer_pts + reversed(inner_pts)`) never closed the
outer arc across the angle-0 seam, leaving a one-segment wedge gap in the fill.
Fixed by repeating each ring's first point so both radial bridges coincide at
the seam (the standard single-polygon annulus technique). Safe because
`lipid_bilayer` had no other call sites and the membrane tests assert only
"returns a Group / doesn't crash".

---

## D8 — label-keyword glyph inference for coarse entity types (EW4), via a resolver shared with `convention_check`

**Decided:** 2026-06-07 (EW4)
**Where enforced:** `layout/_geom.py` (`_INFERENCE_RULES`, `infer_primitive`,
`resolve_entity_primitive`), `layout/pathway_layout.py`,
`verify/convention_check.py`

CELL / ORGANELLE / EQUIPMENT / SAMPLE each had one label-agnostic default
(generic cell / mitochondrion / microscope / tube), so a `"Western blot"`
equipment drew as a microscope. When no explicit `style.primitive` is set, the
entity label is now matched against a per-type keyword table and, on a hit,
dispatched to the more specific registered glyph (blot/gel → `gel`, "Nucleus" →
`nucleus`, "T cell" → `cell_immune`, …). No match → the type default, exactly as
before.

**Chosen over the two alternatives in the backlog:** richer per-type defaults
don't help (still one glyph per type), and SKILL.md-only guidance ("always set
`style.primitive`") leaves the default dumb when the LLM frontend omits it.
Inference makes the out-of-the-box render correct while the override remains the
escape hatch.

**Why a single `resolve_entity_primitive` shared by layout and
`convention_check`:** the check verifies an entity's drawn shape against its
*resolved* primitive. If inference lived only in dispatch, inferring a
different-shaped glyph than the type default (e.g. `nucleus`=circle vs the
ORGANELLE default `mitochondrion`=polygon) would make `convention_check` expect
the wrong shape and raise. Both now call the same resolver
(override → inference → default), so they can never disagree.
`tests/test_entity_adapters.py::test_inferred_organelle_passes_convention_check`
guards this.

**Matching rule:** keywords match at a word-start boundary (`\b` + keyword) so
stems work (`"epitheli"` → *epithelial*) without firing mid-word (`\bplate`
does **not** match inside *template*). Only non-default glyphs are listed, so a
figure's rendering changes only when a label actually names a specific glyph —
this kept the golden blast radius to one intended image (`three_panel_workflow`,
"Western blot" microscope → gel).

**Sizing:** an inferred glyph keeps the *entity-type* bbox (not the glyph's
canonical bbox), so layout positions stay identical to the pre-inference
default; only an explicit override re-sizes to the chosen glyph. This is why
inference never perturbs spacing/collision, only the drawn icon.

---

## D9 — embedded Bioicons (faithful color) + unified info box + auto-credit

**Decided:** 2026-06-07 · **Where enforced:** `primitives/icon_loader.py`,
`assets/icons/`, `tools/ingest_icon.py`, `render/info_box.py`, `render/credits.py`,
`render/compositor.py`, `primitives/entity_adapters.py` (`ICON_ASSETS`)

The hand-drawn lab-equipment glyphs were crude box-art. We now embed real icons
from **Bioicons** (per-icon licensed; 2,818 SVGs). Investigation found they are
**flat multi-color illustrations**, not monochrome themeable glyphs, so the user
chose **embed-first with faithful color** (icons keep their own fills and do
*not* retheme with style presets), re-tracing only icons impractical to embed.

**Asset pipeline (dev-time):** `tools/ingest_icon.py` fetches a Bioicons SVG,
**cleans** it (strips Inkscape/sodipodi/RDF metadata), **inlines `<style>` CSS**
onto element attributes, **namespaces every id** with the asset name (so two
icons in one figure never collide on `defs`/clip ids), normalizes the viewBox,
and writes a namespace-free `assets/icons/<name>.svg` + an attribution record in
`assets/icons/credits.json` (license/author derived from the Bioicons path). It
also regenerates `THIRD_PARTY_ICONS.md`.

**Runtime:** `icon_loader.load_icon(name)` returns an origin-normalized
`svgwrite` Group + intrinsic `(w,h)`, embedding the cleaned shape subtree
*verbatim* via a tiny `_EmbeddedSVG` BaseElement (avoids lossily round-tripping
every attribute through svgwrite's shape classes; assets are namespace-free so
they inherit the Drawing's default SVG namespace). The Group is tagged
`data-icon-credit`. Entity adapters' `_build_*` helpers point at `load_icon`
(function names unchanged → registry/EW4/bbox wiring intact); embedded primitives
go in `convention_check._SKIP_SHAPE_PRIMITIVES` (multi-path composites, like
molecule/functional_group/liposome).

**Why faithful color (no theming):** recoloring a 12-color illustration to the
monochrome house palette is lossy; the user prefers the polished original look.
Embedded icons therefore intentionally ignore the style_dict palette. Trade-off:
they don't retheme under ACS/Nature/Cell-Press presets (documented limitation).

**Unified info box (`render/info_box.py`):** the former separate legend overlay
(top-right) and glossary strip (below) are consolidated into **one** bordered box
in the below-figure strip with stacked **Key / Abbreviations / Credits** sections
(each omitted when empty). The compositor emits a single `info_box` LayoutEntry;
the legend/abbreviation sub-groups keep `data-ir-id="legend"`/`"glossary"` so
existing checks still find them. Row/sample rendering is reused from `legend`
and `glossary` (single source of truth).

**Auto-credit (`render/credits.py`):** a figure's used icons are derived
deterministically from the IR (`resolve_entity_primitive` → `ICON_ASSETS`), never
by scanning output. **CC-BY** icons get a line in the info box's Credits section
(`render_figure(credits="auto")`, the default; `False` suppresses it); **every**
used icon (CC0/MIT included) is recorded in a per-figure `<output>.credits.txt`
sidecar. This keeps generated figures compliant by construction while leaving
CC0/MIT figures visually unencumbered.

**Re-trace fallback (`primitives/lab_icons.py`, Batch 2):** `pipette` and
`human_figure` had no clean simple Bioicons source (wrong instrument / 400 kB /
no good "person"), so they are hand-authored from a few svgwrite shapes — drawn
fresh, not copied, so they carry no license burden, stay themeable via
style_dict (unlike embedded icons), and keep real `_PRIMITIVE_SHAPE` tags
(pipette → rect, human_figure → circle). They flow through the same
`_equip_adapter` fit+label path the old `lab_equipment` icons used.

**Slot confinement:** embedded icons are clipped to their viewBox via a nested
`<svg>` viewport and tagged `data-icon-credit`, which `legibility_check._walk`
skips — necessary because `_walk` resolves only `translate`, not the `scale`
icons are placed with, so otherwise a loose asset (the centrifuge) was measured
at full intrinsic size and the auto-expand-to-content frame blew the canvas up.
