# V3 Scene Chassis — Scoping Doc

Status: **scope only, no code.** Kicks off the v3 line. Decisions taken with the
user 2026-06-08:

- **General chassis** — new IR-expressible layout layers any figure can use, not
  a bespoke template for one figure class.
- **v3 full** — accepted as a pipeline change; schema changes are on the table
  (require explicit sign-off before `imageGen/ir/schema.py` is touched).
- **Chassis only** here — the chemistry/style primitives (curly arrows, shaded
  blobs, TS partial bonds, icons) are **the #1 follow-on workstream**, specced
  separately, after the placement chassis is proven.

Reference target: `references/aspirin_COX1_figure_spec.md` + `ChatGPT Image Jun 8, 2026 …`
— the "perfect figure" we are building toward.

---

## 1. Why a new chassis

The shipped layout engine (`imageGen/layout/panel_layout.py`) is a **depth-1
grid** that dispatches each cell to a *whole-figure* sub-engine
(`layout_pathway`, `layout_reaction`). The target figure is a **composed
multi-tier scene** that this model cannot express. Concrete gaps:

| Target need | Current reality |
|---|---|
| A cell holding an arbitrary composed scene (blob + sticks + residues + arrows, mutually anchored) | A cell can only be one archetype's whole output; primitives land at absolute (x,y), no relative anchoring |
| Cross-panel arrows / shared rails | Each cell's coordinates are offset-isolated; nothing spans the gutter |
| An element that persists/mutates across cells (His513 dashed line identical across all 4 steps; –OH → covalent acetyl) | No element identity carried between panels |
| Tier-specific internal layout (centered title vs equal-column row vs two-section bar) | Single global `style_dict`, one layout language |
| Nesting (scene-in-cell) | Depth > 1 explicitly raises `NotImplementedError` |
| Auto-fit + balanced reflow | Deferred Phase-2 item, still open |

This is squarely a pipeline change → v3, not a localized fix.

---

## 2. The three chassis layers (bottom-up)

### Layer A — Relative-anchor scene graph (the core)

The new placement unit is a **slot**: a primitive (or sub-scene) placed
*relative to another slot* rather than at an absolute coordinate.

- Slots expose **named anchor points** (`blob.cavity_top`, `ring.C1`,
  `residue.terminal_O`).
- Relations between slots: `attach(a, to=b.anchor, offset=…)`,
  `connect(edge, a.anchor → b.anchor)`.
- A scene is a **small constraint solve** (anchors + offsets — not a physics
  engine) that resolves to absolute positions.

This is what lets one cell hold a heterogeneous, self-consistent composition. It
also subsumes the deferred **V3-L2** (force-directed label placement) — greedy
relax becomes one anchoring strategy among several.

### Layer B — Tier / band compositor (above the grid)

Replace the flat grid with **stacked tiers**. Each tier declares its own
internal layout strategy:

- `centered-title`, `equal-columns`, `two-section-bar`, `free-scene`, …

Tiers expose **rails** — named horizontal/vertical reference lines (e.g. the
"mechanism midline") that *both* child cells and cross-gutter arrows anchor to.
Rails are what make the transition arrows and the between-panel "salicylate
departure" element work — they live in tier space, not cell space.

This layer also owns auto-fit / balanced reflow (the open Phase-2 item) and
archetype aspect-ratio capping (run10 critique #3), since those are tier-level
concerns now.

### Layer C — Step / state model (half the figure's storytelling power)

Author **one scene**, plus a list of **per-step deltas**:

- mutate a bond style (dashed → solid), swap a substituent (–OH → acetyl),
  add/remove an element (curly arrow appears in step 2; ring gone in step 4),
  add a label.

The chassis renders N copies applying cumulative deltas. This gives **cross-
panel continuity** (His513 unchanged) *and* the **state-diff story** for free,
and is the natural substrate for the deferred **V3-O1** (animated / step-reveal
builds for talks).

---

## 3. IR impact (load-bearing — needs sign-off)

New node concepts, names TBD: `scene` (Layer A), `tier` (Layer B), `step`
(Layer C). The IR schema is load-bearing per CONTRIBUTING; **no edits to
`schema.py` until the node shapes are reviewed and approved.** The schema
proposal is the first deliverable of the build phase, not part of this scoping
doc.

---

## 4. Sequencing

1. **Scene graph (Layer A)** — slots, anchors, constraint solve. Prove on a
   single static composed scene with existing plain primitives.
2. **Tier compositor (Layer B)** — stacked tiers + rails + auto-fit. Prove a
   2-tier figure (title + one row) end to end, plain primitives.
3. **Cross-tier arrows** — transition arrows + gutter elements anchored to
   rails.
4. **Step/state model (Layer C)** — deltas, cumulative render.
5. **→ Primitive refresh + expansion (separate spec, #1 priority).** Curly
   arrow-pushing (V3-C4), TS partial-bond glyph, organic shaded blobs,
   tablet / dot-cluster icons, named-palette + page-bg design system. This is
   what closes the remaining gap to a pixel-faithful aspirin/COX-1 reproduction.

Each step is independently verifiable on a real render before the next starts.

---

## 5. Quality bar — what "perfect" requires (from the target)

The chassis must make these expressible; the primitive refresh makes them
beautiful:

1. Tiered page composition (title / step-row / summary-bar). — Layers B
2. Rich heterogeneous mutually-anchored scenes per cell. — Layer A
3. Cross-panel continuity + shared midline rail + between-panel departure. — Layer B rails
4. State-diff storytelling (same scene mutated step to step). — Layer C
5. Real design system (cool-gray bg, named palette, shaded blobs, icons, callouts). — primitive refresh
6. Chemistry rendering (curly arrow-pushing, TS partial bonds). — primitive refresh

---

## 6. Out of this doc / open

- Exact IR node shapes (next deliverable, needs approval).
- The primitive-refresh spec (separate doc, follows chassis).
- Whether Layer C ships in the first v3 milestone or a second one (defer until
  Layers A+B land).
