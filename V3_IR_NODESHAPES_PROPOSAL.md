# V3 IR Node-Shapes Proposal (Step 1 — for sign-off)

Status: **proposal, awaiting sign-off. No `schema.py` edits made.**
Grounded in a full read of the real schema + layout/render path + authoring path,
then adversarially verified by three reviewers (schema-safety, render-feasibility,
target-coverage). This doc folds their fixes in.

Prereq doc: `V3_SCENE_CHASSIS_SCOPE.md` (agreed 3-layer plan).
Target figure: `aspirin_COX1_figure_spec.md`.

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

1. **Scene/slot ids are figure-global-unique**, and `.`/`__` forbidden in them. (Registry + cross-tier refs need this.)
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
3. **Vertical slice end-to-end** on existing primitives: 1 blob-stand-in + 1 residue-stand-in + 1 dashed connect + 1 midline rail + 1 cross-cell `TierEdge` → real render.
4. **Tier compositor + band chrome** (band fill/border/divider draw calls).
5. **Scene solver** (topological attach/offset pass) + scene-local label placement.
6. **Step expansion** (builder-layer, slot-granular).
7. **→ Primitive refresh + expansion** (separate spec, #1 follow-on): the aspirin chemistry/style glyphs + per-atom anchors (RDKit conformer coords keyed by atom-map-number → anchor). **Aspirin/COX-1 reproduction is this workstream's acceptance test.**

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
