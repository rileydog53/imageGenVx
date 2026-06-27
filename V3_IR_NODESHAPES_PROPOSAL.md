# V3 IR Node-Shapes Proposal (Step 1)

> **Status (2026-06-26): SHIPPED.** The node shapes below were signed off and
> built — Steps 1–7 are feature-complete (`V3_STATUS.md`); the schema is
> authoritative in `imageGen/ir/schema.py` (cited from `ir/_enums.py`). This doc
> is **retained as the node-shape design + sign-off reference** (§0 keystone, §1
> node tables, §2 settled decisions, §4 sign-off log); its build-order narrative
> describes completed work. Active plan: `HANDOFF.md`.

Grounded in a full read of the real schema + layout/render path + authoring path,
then adversarially verified by three reviewers (schema-safety, render-feasibility,
target-coverage). This doc folds their fixes in.

Prereq doc: `V3_SCENE_CHASSIS_SCOPE.md` (agreed 3-layer plan).
Target figure: `references/aspirin_COX1_figure_spec.md`.

---

## 0. The keystone the review surfaced (read first)

The node shapes below are sound and additive. But the chassis depends on a piece
that is **not a node** and does **not exist today**:

> Every primitive in `PRIMITIVE_REGISTRY` (`imageGen/layout/_geom.py`) is
> `fn(label, position, size, color, style_dict) -> svgwrite.Group` — an **opaque
> group with geometry already baked in and no anchor map**. The scene graph
> (Layer A) needs to read back named points (`blob.cavity_top`,
> `ser530.terminal_O`, `aspirin.carbonyl_C`) to resolve `attach` and `connect`.
> Nothing produces those points.

**Consequences that reorder the build plan:**

1. **The true first deliverable is an anchor-return protocol**, not the node
   surface: `fn(...) -> tuple[Group, dict[str, tuple[float,float]]]` (group +
   named anchors in local coords), published into a figure-global anchor registry
   keyed by scoped id. Every slot primitive, the scene solver, rails, and
   cross-cell arrows speak this. Prove a **vertical slice** (1 blob + 1 residue +
   1 dashed connect + 1 midline rail + 1 cross-cell arrow) end-to-end before
   building the full enum surface.

2. **The aspirin figure cannot be the milestone-1 proof.** It is ~100% net-new
   chemistry/style primitives (protein blob, residue sticks, curly arrows, dashed
   H-bonds, dot clusters, tablet, ⊣ bar, green salicylate) — i.e. the deferred
   *primitive refresh* workstream. Milestone 1 proves the chassis on an example
   built from **primitives that exist today** (generic protein, SMILES molecule
   via `entity_adapters.molecule`, `reaction_arrow`, helix). Aspirin reproduction
   is the acceptance test for the *primitive refresh*, not the chassis.

3. **Step deltas cannot mutate sub-atoms** of an opaque RDKit molecule SVG
   (`SWAP –OH → acetyl`, "recolor that bond"). Restrict deltas to **slot-granular
   add / remove / replace** and **expand the step sequence to N concrete scenes
   at the builder layer** (so verification sees real scenes). No in-place
   sub-element mutation.

4. **"No renderer change" is overstated.** Per-tier band fill, band border, and
   the bottom-bar dashed divider are genuinely new (simple) draw calls; the verify
   layer (`semantic_check`/`convention_check`/`glossary_check`) walks
   entities/relations/panels and will silently give **zero coverage** on tiered
   figures unless extended to recurse tier→scene→slot.

None of this invalidates the node shapes — it sets the build order and trims the
milestone-1 claim to what actually renders.

---

## 1. The node shapes (additive to `schema.py`)

Framework parity (all confirmed against the real schema): subclass `_IRBase`
(`extra="forbid"`, `from_dict`/`to_json`); canonical `id`/`type`/`label` triple;
each kind is a `class XType(str, Enum)` with a GENERIC/CUSTOM escape member; every
field beyond the required core is optional with an explicit default
(`x: T | None = None` / `Field(default_factory=list)`); free-form visual intent
lives in a `style: dict` bag with glyph selection via `style["primitive"]`;
referential integrity in a `@model_validator(mode="after")`; synthetic `ir_id`
`@property` where there's no declared id.

### Layer B — Tier (band compositor) + Rail

| Model | Fields |
|---|---|
| `Tier` | `id`(req) · `role: TierRole`(req) · `label?` · `subtitle?` · `layout: TierLayout = equal_columns` · `height_frac?` (0<f≤1) · `scenes: list[Scene]` · `step_sequence: StepSequence?` · `sections: list[str]` · `rails: list[Rail]` · `transitions: list[TierEdge]` · `overlays: list[Scene]` · `content: Figure?` · `style?` |
| `Rail` | `name`(req, unique-in-tier) · `axis: RailAxis = y` · `at: float = 0.5` (0..1 fraction) |
| `TierEdge` | `from_ref`(req) · `to_ref`(req) · `type: SceneEdgeType = transition` · `on_rail?` · `label?` · `style?` |

- `TierRole`: `title · scene_row · summary_bar · band`
- `TierLayout`: `centered_title · equal_columns · two_section_bar · free_scene · custom`
- Tier validator: **at most one of** {`scenes`, `step_sequence`} **+ optional `overlays`** (overlays are free/gutter scenes that coexist with a step_sequence — this is the home for the departing salicylate); rail names unique; every `transitions`/`on_rail` ref resolves.
- `ref` grammar: `"scene_id.slot.anchor"` · `"rail:NAME"` · `"scene_id@edge"`.

### Layer A — Scene + Slot + Attach + SceneEdge

| Model | Fields |
|---|---|
| `Scene` | `id`(req) · `label?` (multi-line via `\n`) · `badge?` · `slots: list[Slot]` · `attach: list[Attach]` · `connect: list[SceneEdge]` · `content: Figure?` · `style?` |
| `Slot` | `id`(req) · `kind: SlotKind`(req) · `label?` · `anchors: list[str]` (author-declared, beyond kind built-ins) · `slots: list[Slot]` (group recursion) · `style?` |
| `Attach` | `child`(req) · `parent?` (None = scene frame) · `edge: AttachEdge = center` · `parent_anchor?` · `offset: tuple = (0,0)` |
| `SceneEdge` | `from_anchor`(req `"slot.anchor"`) · `to_anchor`(req) · `type: SceneEdgeType = generic` · `label?` · `style?` |

- `SlotKind`: `blob · molecule · residue · glyph · text · box · group · generic`
- `AttachEdge`: `top · bottom · left · right · center · cavity_top · cavity_bottom · cavity_center · anchor · custom`
- Scene validator: slot ids unique in scene; every attach/connect ref resolves to a slot; `content` XOR `slots`.

### Layer C — StepSequence + Step + StepDelta

| Model | Fields |
|---|---|
| `StepSequence` | `id`(req) · `base: Scene`(req) · `steps: list[Step]` · `cumulative: bool = True` |
| `Step` | `id`(req) · `badge?` · `label?` · `deltas: list[StepDelta]` · `style?` |
| `StepDelta` | `op: StepOp`(req) · `target`(req) · `value: dict?` |

- `StepOp` (slot-granular only): `add · remove · replace · add_label · generic` *(no `set_style`/`swap` of sub-atoms — opaque groups can't be mutated post-build)*
- Validator: step ids unique; every `delta.target` resolves in `base` (or a prior `add` when cumulative).
- **Expanded to N concrete `Scene`s at the builder layer** so verification sees real scenes.

### New dedicated edge enum (do NOT overload `RelationType`)

`SceneEdgeType`: `dashed · hbond · curly · transition · departs · binds · activates · inhibits · generic` — gives the mechanism vocabulary a home without editing the load-bearing `RelationType`.

### Change to existing `Figure` (one field + additive validator clauses)

- ADD `tiers: list[Tier] = Field(default_factory=list)`.
- EXTEND `_validate_structure` additively: leaf-XOR-panel becomes **at most one of** {leaf-content, panels, tiers}; tier ids unique; **scene ids and slot ids figure-global-unique**; **forbid `.` and `__` in scene/slot/rail ids** (so the `scene.slot.anchor` registry grammar and `scoped_id`'s `__` join can't collide).
- When `tiers` is non-empty, **suppress `Figure.title`/`caption`** (the TITLE tier owns titling) — gate `_title_entry` with `not ir.panels and not ir.tiers` to avoid double-render.

---

## 2. Decisions settled by recommendation (object if you disagree)

1. **Scene ids are figure-global-unique; slot ids are scene-scoped** (unique within their scene), and `.`/`__` forbidden in scene/slot/rail ids. *Refinement of the original §2.1 ("slot ids figure-global-unique") made at implementation: the scene id already namespaces slot anchors in the `scene.slot.anchor` registry key, so global slot uniqueness is unnecessary and would block natural id reuse (a `blob`/`mol` slot in every scene). Scene-scoped is sufficient for unambiguous refs and `__` scoping.*
2. **Dedicated `SceneEdgeType`** rather than overloading `RelationType`.
3. **`RailAxis` enum** (`x`/`y`) for full convention parity (not a free str).
4. **Step expansion at the builder layer**, deltas slot-granular only.
5. **Tier carries `step_sequence` + optional `overlays`** (departing salicylate lives as an overlay scene + a `TierEdge`, not a step delta).
6. **`Figure.title` suppressed under tiers**; title tier owns it.
7. **Verify layer extended** to recurse tier→scene→slot (or the gap is documented in the PR, not silent).
8. **`builder.build()` gets a `tiers` param** (it has an explicit signature, no `**kwargs`) and `_spec_to_figure` forwards it — this is a real edit to an existing function, acknowledged.
9. **All new models `model_rebuild()`'d unconditionally at module end** after `Figure` is defined (order-insensitive; avoids the forward-ref brittleness).

---

## 3. Revised build order (supersedes the scope doc's sequencing)

1. **Anchor-return protocol + figure-global anchor registry** — the keystone.
   **✅ LANDED 2026-06-08.** `primitives/_anchors.py` (`AnchoredGroup` contract),
   `primitives/chemistry.py::render_molecule_anchored` (RDKit atom-precise anchors
   via `GetDrawCoords`, atom-map naming, map labels cleared), `layout/anchors.py`
   (`AnchorRegistry` + `Rail`, `resolve`/`resolve_on_rail`). Proven end-to-end by
   `tests/test_anchor_keystone.py` (10 tests): two anchored molecules across a
   cell-offset boundary, an intra-scene dashed bond, and a cross-cell transition
   arrow clamped to a midline rail — all resolving to correct coords and
   rendering (`tests/figures/anchor_keystone_slice.png`). Full suite 964 green.
2. **Schema additions** (this doc) — additive IR; `layout_tiers` stub raising `NotImplementedError` for unimplemented `SlotKind`s (mirrors the existing unregistered-archetype pattern).
   **✅ LANDED 2026-06-08.** `ir/schema.py`: 7 enums (`TierRole`, `TierLayout`,
   `SlotKind`, `AttachEdge`, `StepOp`, `SceneEdgeType`, `RailAxis`) + 10 models
   (`Tier`, `Rail`, `TierEdge`, `Scene`, `Slot`, `Attach`, `SceneEdge`,
   `StepSequence`, `Step`, `StepDelta`) + `Figure.tiers` + three-way leaf/panels/
   tiers exclusivity + id-uniqueness/reserved-char/ref-resolution validators +
   all-at-module-end `model_rebuild()`. `ir/__init__.py` exports; `builder.py`
   gains a `tiers` passthrough; `compositor._dispatch_layout` raises a clear
   `NotImplementedError` for tiered figures (engine is Step 4–5). `StepDelta.target`
   made optional (required for remove/replace/add_label, optional for ADD).
   Tested by `tests/test_ir_schema_tiers.py` (33 tests). Full suite **1000** green.
3. **Vertical slice end-to-end** on existing primitives: 1 blob-stand-in + 1 residue-stand-in + 1 dashed connect + 1 midline rail + 1 cross-cell `TierEdge` → real render.
   **✅ LANDED 2026-06-08.** `layout/tier_layout.py::layout_tiers` lowers a tiered
   `Figure` to `LayoutEntry`s through the `AnchorRegistry` (TITLE + SCENE_ROW tiers,
   MOLECULE/TEXT slots, dependency-ordered attach solver, intra-scene `SceneEdge`
   + cross-cell `TierEdge` with rail clamp + standoff). Proven by the IR-driven
   aspirin→salicylic render in `tests/test_layout_tiers.py` (11 tests). Adversarially
   reviewed (3 lenses, all "sound"); fixes applied: dependency-ordered/cycle-safe
   attach solver, loud errors for unsupported attach edges & `rail:` endpoints,
   `resolve_edge` standoff clamp on short edges, curved-arrow tangent. Full suite
   **1012** green. *Deferred review nits (out of slice scope): sub-pixel molecule
   centering from int() render size; non-molecule attach-parent extent; text
   `center` anchor = baseline; duplicate-edge ir_id uniquifier; partial-`height_frac`
   fallback — revisit with the Step-4/5 compositor + solver.*
4. **Tier compositor + band chrome** (band fill/border/divider draw calls).
   **✅ LANDED 2026-06-10.** `render/compositor.py` wires `layout_tiers` into the
   normal `render_figure` pipeline/CLI: `_dispatch_layout` lowers tiered figures
   through the engine (the Step-3 `NotImplementedError` stub is gone), `_canvas_size`
   sizes via the new `tier_layout.tier_canvas` (content-aware: cols×cell width +
   per-tier natural heights; pinnable) so the SVG viewport matches the engine's
   baked coords, the pathway label pass + `Figure.title` are suppressed under tiers
   (the TITLE tier owns titling), and autocrop/expand/page-bg flow unchanged. New
   engine work: unified `_band_chrome` (fill/border + solid/dashed top divider),
   scene `_badge_group` (corner step number) + `_caption_group` (centred multi-line
   `scene.label`), `_tier_rects` weighted by `height_frac`-or-role-natural-height,
   and the **cell-vs-content extent fix** — scene-frame anchors now publish from the
   union of slot boxes (content extent) so cross-cell transition arrows span the
   visible molecule gap, not the narrow inter-cell gutter. Title/subtitle baselines
   reworked to a fixed-separation centred block so a thin TITLE band no longer trips
   a legibility false-positive (canonical figure verifies semantic+legibility+
   convention clean via the CLI). Proven by `tests/test_compositor_tiers.py` (13
   tests: end-to-end render, canvas match, title suppression, autocrop, content-gap
   arrow, chrome/badge/caption goldens) + updated `test_ir_schema_tiers` dispatch
   test. Full suite **1025** green. *Deferred (Step 5): topological attach solver +
   scene-local label collision; non-molecule attach-parent extent; sub-pixel molecule
   centering; `rail:` bare endpoints; step_sequence (Step 6).*
5. **Scene solver** (topological attach/offset pass) + scene-local label placement.
   *Acceptance: no overlapping slots (V3_FEATURES MF-3) — His513-vs-ligand-tangle class of bug.*
6. **Step expansion** (builder-layer, slot-granular).
7. **→ Primitive refresh + expansion** (separate spec, #1 follow-on): the aspirin chemistry/style glyphs + per-atom anchors (RDKit conformer coords keyed by atom-map-number → anchor). **Aspirin/COX-1 reproduction is this workstream's acceptance test** — gated by the mechanism-figure fidelity criteria (V3_FEATURES **MF-1** one atom convention / no bare-dot oxygens, **MF-2** curly arrows terminate on atom anchors / V3-C4) so the mechanism is *readable*, not just placed. Scoped 2026-06-10 from a hand-composed north-star read.

---

## 4. Decisions resolved (sign-off 2026-06-08)

- **Sign-off: APPROVED.** Build order = **keystone first** (anchor-return protocol
  + figure-global registry, proven on a vertical slice) then the schema additions.
- **Atom-level anchoring: RDKit atom-precise NOW.** The molecule slot publishes
  per-atom anchors from RDKit 2D conformer coords keyed by atom-map-number →
  anchor name, in the first slice. Mechanism bonds/curly arrows hit real atoms.
- **Edge vocabulary: dedicated `SceneEdgeType`** (RelationType untouched).
- **Aspirin reproduction** = acceptance test for the primitive-refresh workstream,
  not a chassis milestone (consistent with "chassis only, primitives next").

All §2 recommendation-settled decisions stand unless revisited.
