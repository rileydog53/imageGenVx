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

## Straight pathway arrows only

Pathway relations are drawn as straight arrows between entity bbox edges.
There is no orthogonal routing or curved-arrow avoidance, so an arrow can
cross an unrelated entity in a busy layout. Curved/routed arrows are a v2
item.

## No 3D structures

imageGen draws 2D schematic primitives only. Protein structures, ribbon
diagrams, and 3D molecular renderings are out of scope — a planned v2
stretch goal is a PyMOL handoff.

## Superscript / special-glyph coverage

Entity labels are rendered with the system font via cairo. Characters the
font lacks render as a missing-glyph box (tofu). Notably **superscript minus
(U+207B)** — common in mechanism labels like `Nu⁻` / `LG⁻` — is not covered;
the en-dash (U+2013) and most common scientific symbols are. Prefer ASCII
(`Nu-`, `LG-`) or a covered Unicode minus where possible.

## Reaction schemes are composite

A `REACTION_SCHEME` renders as one composite `reaction_0` SVG group with no
per-element ids. The `convention_check` verifier therefore skips per-entity
shape checks for reactions, and `semantic_check` verifies the single
composite anchor rather than each molecule.

## Aspect-cap wrap seam (cross-row transition arrows)

The archetype aspect-ratio cap (`tier_aspect_max`, default 4.0) reflows an
over-wide `SCENE_ROW` onto multiple rows. Cross-cell transition arrows resolve
from the `AnchorRegistry`, so they follow scenes to their wrapped positions —
but a transition chained **across the wrap seam** (e.g. the step 3 → step 4 arrow
when a 6-step row wraps 3+3) draws as a single long diagonal rather than snaking.
Within-row arrows are unaffected. The cap is a guard for pathologically wide
rows; for an authored multi-row mechanism, prefer not to chain a transition over
the seam (or wrap deliberately in the JSON). Boustrophedon / orthogonal seam
routing is a future item.
