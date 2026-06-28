# Known Limitations (v1.0)

imageGen v1 produces journal-style figures for the five supported archetypes,
but it is deliberately scoped. The limitations below are known and accepted
for v1 — they are tracked for v2 in [BACKLOG.md](BACKLOG.md). If a figure
comes out wrong because of one of these, log it in [FEEDBACK.md](FEEDBACK.md).

## Label placement degrades gracefully on dense figures (v2)

Automatic label placement is greedy, but no longer fails loud by default. A
label that can't find a clear slot runs a **relax-and-retry ladder**: shrink
the font one step → nudge the anchor a few px → as a last resort, place it
anyway with `data-overlap="true"` (which `legibility_check` tolerates) and
emit a `UserWarning`. Dense fixtures (`graphical_abstract_mrna_vaccine`,
`mechanism_cartoon`, `western_blot_schematic`) now render with labels on.

Pass `strict_labels=True` (CLI: `--strict-labels`) to restore the v1
fail-loud `LabelPlacementError` contract. Force-directed placement and
leader lines remain a v2+ stretch (BACKLOG L2, L14).

*Workaround for a cluttered result:* render `--no-labels`, reduce entity
count, or split across panels.

## Large figures: dynamic canvas + band wrapping (v2)

The old ~20-entity ceiling is lifted. A band that holds more than
`pathway_max_per_row` entities (default 6) now **wraps to multiple rows**
instead of cramming into one line, and the canvas auto-sizes to fit the
content (clamped to an 800×600 floor so small figures are unchanged). Pin a
size with `--canvas WxH` if needed. Very large figures (dozens of entities,
many compartments) still read better split across panels, but they no longer
degrade into an unreadable single row.

Small figures still render on the 800×600 floor and so can sit in whitespace
(the floor preserves golden-image stability). To remove that margin, render
with `--crop`: it writes a `*_cropped` sibling reframed onto the content (a
wide pathway becomes a wide, short image). `--crop-keep-aspect` keeps the
canvas proportions but, because layouts fill a full dimension, usually crops
little.

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
