# Known Limitations (v1.0)

imageGen v1 produces journal-style figures for the five supported archetypes,
but it is deliberately scoped. The limitations below are known and accepted
for v1 — they are tracked for v2 in [BACKLOG.md](BACKLOG.md). If a figure
comes out wrong because of one of these, log it in [FEEDBACK.md](FEEDBACK.md).

## Label placement — ladder + leader lines (greedy, not force-directed)

*(v1.0 said leader lines were "a v2+ stretch" — that is stale; they landed.)*
Label placement is a multi-rung pipeline, not a naive greedy pass:

- **In-box fit ladder** — an entity label first fits to its box: as-is → wrap to
  two lines → shrink toward the 6px legibility floor → external leader
  (`primitives/_text.py:fit_label`). Long names wrap/shrink in place rather than
  spilling.
- **Relax-and-retry** for externally-placed labels — try priority slots → shrink
  one step → small anchor nudges → larger corridor nudges
  (`label_placement.py`).
- **Whitespace-ring + leader lines** — a label that still can't clear a slot is
  parked in nearby whitespace and **tethered back to its anchor with a leader
  line**, in *both* engines (`pathway_extlabel_leaders` / relation-label leaders;
  the tier engine's `tier_label_leaders`), with shaft-avoidance and receptor
  footprint awareness.
- **Graceful degradation** — only if all of the above fail does the label land
  with `data-overlap="true"` (tolerated by `legibility_check`) plus a
  `UserWarning`. `strict_labels=True` (CLI `--strict-labels`) restores the
  v1 fail-loud `LabelPlacementError`.

Covered by ~66 tests across `test_layout_label_placement`,
`test_label_placement_fallback`, `test_extlabel_leaders`,
`test_relation_label_leaders`, `test_tier_label_leaders`,
`test_label_shaft_avoidance`, `test_receptor_label_footprint`.

**Residual.** Placement is **greedy** (rung-by-rung), not a *global*
force-directed optimum — in a pathologically dense figure two labels may still
contend for the same whitespace, and a label whose band has **no** whitespace
anywhere still lands flagged (the band-height limit). A global force-directed
solver is deliberately not pursued: the ladder + leaders cover the real cases at
far lower risk than re-tuning 66 placement tests around a new optimiser.
*Workaround for a cluttered result:* `--no-labels`, fewer entities, or split
across panels.

## Large figures: dynamic canvas + wrapping (v2)

The old ~20-entity ceiling is lifted, on **both** layout axes:

- **Sibling wrap (within a band):** a band holding more than
  `pathway_max_per_row` entities (default 6) wraps to multiple rows instead of
  cramming into one line.
- **Column sizing (the DAG/rank axis):** a compartment-free graph is placed a
  column per topological rank, so the canvas is sized to the **real layered
  column count** (`_layered_grid_shape`), not the `min(len, max_per_row)`
  envelope. A deep chain (e.g. 30 nodes) used to squeeze 30 columns into
  6-columns-of-width and overlap the boxes; it now gets a column per rank and a
  single-row band height (no dead vertical padding). Covered by
  `tests/test_dynamic_canvas.py` (`test_deep_chain_sizes_canvas_to_columns_no_overlap`,
  `test_deep_chain_does_not_pad_vertical_whitespace`).

The canvas auto-sizes to fit content (clamped to an 800×600 floor so small
figures are unchanged); pin a size with `--canvas WxH`.

**Residual.** A very deep chain still produces a wide strip (it is not yet
*reflowed* onto multiple rows the way the tier engine's aspect-cap wraps a wide
scene row — that serpentine wrap is future work for this engine). The figure is
readable and non-overlapping, but for dozens of nodes a hand-authored **panel**
split (`Figure.panels`) still reads better; there is no automatic paneling.
Small figures render on the 800×600 floor and can sit in whitespace; `--crop`
reframes onto the content (`--crop-keep-aspect` keeps proportions).

## Arrow routing — covered; residual is dense-band lane exhaustion

*(v1.0 said "straight arrows only, no orthogonal routing" — that is stale.)*
Pathway relations are now routed, not drawn straight:

- **Ports + fan-out** spread co-sided arrows to distinct edge points and draw a
  shared Y-trunk for one source driving many targets (`_assign_ports`,
  `_route_fanout`).
- **Same-band arches** — a relation whose straight shaft would cross an
  intervening entity (or its label footprint) arches over the row instead, with
  a left-edge **lane** sweep so overlapping arches don't collapse onto one
  corridor (`_route_same_band_arrows` / `_arch_waypoints`).
- **Cross-band orthogonal corridors** — inter-compartment arrows route through
  the band gutter as elbows and lift off the membrane line
  (`_orthogonal_waypoints` / `_lift_corridor_off_membrane`).

Covered by `tests/test_layout_pathway.py` (`test_same_band_skip_arrow_arches`,
`test_overlapping_arches_get_distinct_lanes`, `test_cross_band_arrow_still_uses_corridor`)
and, for the tier engine's wrap seam, `test_cross_row_transition_routes_orthogonally_not_diagonally`.

**Residual.** Routing is orthogonal arches/elbows, not smooth-bezier
obstacle avoidance, and a *very* dense band can exhaust the alternating arch
lanes (the band has finite height) — at which point two arches may share a
corridor. The layered-DAG layout mitigates this by spreading nodes across rows
first. Smooth routed/curved avoidance remains a future polish item.

## No 3D structures

imageGen draws 2D schematic primitives only. Protein structures, ribbon
diagrams, and 3D molecular renderings are out of scope — a planned v2
stretch goal is a PyMOL handoff.

## Special-glyph coverage (arbitrary Unicode)

Labels are rendered with the system font via cairo, so a character the font
lacks renders as a missing-glyph box (tofu).

**Superscript charges / exponents are handled.** Precomposed superscript code
points (`⁻` U+207B, `⁺` U+207A, `²`/`³`/`⁰`–`⁹`, `ⁿ`, `ⁱ`, …) are no longer
sent to the font: each is mapped to a base glyph the font is guaranteed to have
and rendered raised + smaller via a `tspan` (the same cairosvg-safe `dy`
technique the chemical subscripts use). So `Nu⁻` / `LG⁻` / `Ca²⁺` typeset
correctly and font-independently — see `imageGen/primitives/_text.py`
(`superscript_runs` / `_emit_shifted_text`) and `tests/test_tier_superscript.py`.
The subscript rule stays confined to chemistry's `formula_text`, so a protein
name like `p53` is never mis-subscripted in a general label.

**Residual — arbitrary symbols still depend on font coverage.** A symbol that is
*neither* a superscript nor a chemical subscript (e.g. a literal `→`/`⇌` typed
into label text) still tofus if the system font lacks it, and a broad fallback
font in the family chain does not reliably back-fill it through cairo/fontconfig.
This is a font-bundling problem, not a rendering bug. In practice, draw reaction
arrows with the arrow **primitives** (not as text), and prefer ASCII or a known
covered glyph in label strings.

## Reaction schemes — per-molecule ids (composite, but verifiable)

A `REACTION_SCHEME` still renders under one composite `reaction_0` group, but
each molecule's sub-group is now **tagged with its entity id** (set inside
`render_reaction` / `render_multistep_reaction`), so `semantic_check` verifies
that *every* molecule of a top-level reaction is rendered — not just the single
`reaction_0` anchor. The tag adds no pixels, so golden images are unchanged.

Residual: `convention_check` still does no per-molecule *shape* check — a
skeletal molecule is a composite structure with no single conventional glyph
(the same reason `MOLECULE`/`RESIDUE` slots are shape-exempt in the tier engine),
so there is nothing to shape-check. And the per-molecule ids are not panel-scoped,
so for a reaction nested inside a panel the per-molecule audit is skipped (the
composite `reaction_0` anchor is still checked); only top-level reactions get the
per-molecule check.

## Aspect-cap wrap seam (cross-row transition arrows) — routed

The archetype aspect-ratio cap (`tier_aspect_max`, default 4.0) reflows an
over-wide `SCENE_ROW` onto multiple rows. A transition chained **across the wrap
seam** (e.g. the step 3 → step 4 arrow when a 6-step row wraps 3+3) is now routed
**orthogonally** through the inter-row gap — a Z that drops from the upper anchor
into the empty gap, runs horizontally across it, then drops into the lower anchor
(`_seam_route` / `_edge_group(..., waypoints=…)`) — instead of slashing
diagonally across the scenes between them. Within-row arrows stay straight.
Residual: the route is a simple Z (not a margin-hugging boustrophedon sweep), so
on a very wide wrapped row its horizontal run is long; acceptable for what is a
guard against pathologically wide auto-laid rows.
