# Nitpick fix list — capability-test visual QA pass

Source: a meticulous per-figure visual QA pass (11 figures, one independent
review agent per figure, several spot-checked against the raw pixels) run
after the 5 defects in the original capability-test handoff were assumed
fixed. 34 new findings, grouped into 9 fix items by root cause rather than by
figure — several individual findings share one underlying cause. Ordered by
dependency: earlier items change canvas size/node position/routing that later
items should be re-verified against, so do them in order and re-render the
affected figures before starting the next item.

Each item lists: the figures/findings it resolves, the concrete file(s) to
change, and a fix instruction grounded in the actual code (function/constant
names below were confirmed by reading the source, not guessed) — but treat
"the fix" as a starting point, not a blind numeric edit: re-render the
affected figure and compare before/after each time.

When an item lands, delete its row from `BACKLOG.md` and delete this item's
section here (or strike it) — same convention as the rest of the repo's docs.

---

## 1. Systemic: arrow-shaft / inter-node spacing too long [Medium]

**Resolves:** `01` (shafts = 61% of canvas width vs 36% for boxes), `02`
(pathway row + 62%-empty legend band), `05` (shaft:box ≈ 5:1), `06` (shafts
~350px vs boxes ~150px), `07` (each panel's content is a thin ~6%-ink band),
`09` (one arrow shaft alone ≈ 40% of canvas width). Partially also the
`horizontal_sprawl`/`whitespace` notes on `08` and `11`.

**Why first:** every other pathway/cellular_schematic fix below (#2–#5)
changes arrow *routing*, not node *spacing* — but routing math is computed
from final node positions. Land this first so #2–#5 are tested against the
real, tightened geometry instead of the current overlong one.

**Where:** `imageGen/layout/pathway_layout.py`
- `DEFAULT_PARAMS["pathway_edge_margin"] = 8.0` (~line 193) and
  `DEFAULT_PARAMS["pathway_arrow_gap"] = 4.0` (~line 173) — the base
  clearance constants.
- `inter_gap = max(2.0 * edge_margin, 20.0)` (~lines 317 and 473, duplicated
  for the two sizing paths) — the column-to-column gap for a layered
  DAG/chain layout. This is the direct lever for shaft length in a linear
  chain.
- Row width formula: `row_w = 2.0*padding + n_cols*max_entity_w + (n_cols-1)*inter_gap`
  (~line 325 and ~483).

**Fix instruction:** the `20.0` floor in `max(2.0 * edge_margin, 20.0)` is
almost certainly not what's producing the huge visual gaps seen in the PNGs —
the PNG pixel dimensions (e.g. `2500×110`) are DPI-scaled from a smaller
logical SVG canvas (300dpi export ≈ 3.1x a ~96dpi-equivalent logical size), so
before changing constants, instrument `_size_bands`/whichever function builds
`row_w` (search `pathway_layout.py` for `inter_gap` — 4 call sites) to print
the logical (pre-DPI) column gap and entity width for `tests/fixtures/mapk_cascade.json`
rendered plain (no compartments, 4 nodes) — confirm empirically what the real
gap-to-box ratio is at the SVG/logical level, not the exported PNG level, then
tune `inter_gap`'s multiplier/floor down (or make it a function of
`max_entity_w` — e.g. `min(inter_gap, 0.6 * max_entity_w)` so long shafts
can't exceed a fraction of node width) until a plain 4-node chain lands close
to a 3–4:1 aspect ratio instead of 22:1. Re-render `01`, `02`, `05`, `06`,
`09` and re-check aspect ratios after.

**Fallback if root cause differs:** if instrumenting shows `inter_gap` isn't
actually the dominant term (e.g. it's `_LABEL_MARGIN`, `edge_margin`
canvas-clamping, or a downstream auto-crop/floor step scaling final canvas
up), the same print-and-compare approach will surface which term dominates —
don't guess past that point, measure it.

---

## 2. Compartment/membrane boundary crossings not perpendicular [Medium]

**Resolves:** `08` — three arrows (dendrite→nucleus "Signal input" arrows,
nucleus→myelin "Action potential", myelin→terminal "Saltatory conduction")
cross their compartment divider at shallow 10–25° angles instead of ~90°.

**Where:** `imageGen/layout/_pathway_routing.py`
- `_lift_corridor_off_membrane` (~line 472) and `_orthogonal_waypoints`
  (~line 495) — existing logic whose own docstring says a cross-band
  corridor should be "perpendicular, as a membrane crossing should read."
  This logic exists and is *supposed* to cover exactly this case.

**Fix instruction:** the perpendicular-forcing logic exists but these three
arrows aren't going through it — find the call site that decides whether a
relation gets routed via `_orthogonal_waypoints`/`_lift_corridor_off_membrane`
vs. a plain straight/diagonal line (search callers of
`_lift_corridor_off_membrane` in `_pathway_routing.py` and `pathway_layout.py`
around the `_route_same_band_arrows`/dispatch logic at ~line 371). The
dendrite and terminal arrows in `08` connect entities that are diagonally
offset (not directly stacked in the same column) across a compartment
boundary — the dispatch condition likely only engages orthogonal routing for
same-column crossings and falls through to a straight line for diagonal
ones. Fix: widen the condition so *any* relation whose endpoints sit in
different compartment bands gets routed through the corridor/orthogonal path
(with the corridor's horizontal offset absorbing the diagonal displacement),
not just same-column ones. Re-render `08` and `09` (which shares this engine)
and check crossing angles.

---

## 3. Arrows crossing over fixed text (captions/labels), and arrowhead pile-ups [Medium]

**Resolves:**
- `02`: dashed feedback-leader line bisects the "RAF" label; feedback edge's
  ERK-end diagonal cuts the ERK hexagon corner.
- `07`: Panel-1 delivery arrow cuts through "Cytoplasm".
- `08`: "Signal input" and "Action potential" edge-caption text crossed by
  their own arrow shafts; two separate arrowhead clusters (at the nucleus, at
  the synaptic terminal) overlap into a jumbled shape where multiple arrows
  converge on nearly the same point.
- `09`: translocation arrow's tail/arrowhead sits on top of "Nucleus".
- `10`: two dashed bond-indicator lines ("H-bond", "breaking" captions) are
  crossed by their own indicator line.

**Where:**
- Movable relation-*label* collisions (edge captions like "Signal input",
  "Action potential", the feedback leader in `02`) are the domain of
  `imageGen/layout/label_placement.py`, which LIMITATIONS.md documents as
  already having shaft-avoidance. Search for the shaft-avoidance check
  (`label_shaft_avoidance` / `tests/test_label_shaft_avoidance.py` names the
  function under test) and confirm it's actually being invoked for pathway
  *relation* labels, not just entity labels — the gap is likely that
  relation-label placement doesn't run the same avoidance pass entity labels
  get.
- Fixed structural captions (compartment names like "Cytoplasm"/"Nucleus",
  tier scene captions like "H-bond"/"breaking") are **not** part of the
  movable label system at all — they're placed by
  `_compartment_band` (`_pathway_routing.py` ~line 556) and by the tier
  caption renderer (`imageGen/layout/tier_layout.py`) independently of arrow
  routing, so arrows have no knowledge of them.
- Arrowhead pile-ups at a shared target: `_assign_ports`/`_diverging_fanouts`
  in `_pathway_routing.py` (~lines 64–166) — this is the fan-in spreading
  logic that's supposed to prevent exactly this ("covers fan-in (many
  entries)").

**Fix instruction:**
1. For relation-label-over-own-shaft: confirm `label_placement.py`'s
   shaft-avoidance runs for pathway relation captions (not just entity
   labels); if it's entity-only, extend it to relation labels.
2. For arrow-over-fixed-caption (compartment/tier captions): add the fixed
   caption's rendered bounding box to the same obstacle set the arrow router
   already avoids for entities (check what obstacle list `_route_same_band_arrows`
   / the corridor router consults in `_pathway_routing.py`, and add
   compartment-label and tier-caption boxes to it).
3. For arrowhead pile-ups: `_assign_ports` takes a target entity and spreads
   incoming edges to distinct ports — confirm it's actually being called for
   the nucleus/synaptic-terminal fan-in cases in `08`'s cellular_schematic
   dispatch path (cellular_schematic shares `layout_pathway`, confirmed
   earlier in this session) — if the fan-in threshold or a diagonal-only
   guard is excluding these, widen it the same way as item #2.

Do this after #1 and #2 since both label positions and routed paths shift
with those fixes — re-verify these specific crossings still exist before
touching this item's code.

---

## 4. Ring-layout arrowhead standoff inconsistency [Low]

**Resolves:** `03` — arrowheads land flush on some target nodes, 20–53px
short on others, with no correlation to target shape (confirmed by direct
pixel inspection).

**Where:** `imageGen/layout/_pathway_bands.py` `_bbox_exit_point` (~line 379)
and `_inset_relation_endpoints` (~line 407), reused by the ring layout via
`pathway_ring_node_gap` (`pathway_layout.py` DEFAULT_PARAMS ~line 207).

**Fix instruction:** `_bbox_exit_point` computes the arrow's exit/entry point
from a **rectangular bounding box**, then applies a fixed `gap` outward along
the line direction. For a hexagon entity (e.g. `CDK4/6`, `CDK2` in `03`), the
bbox edge and the hexagon's actual visible outline diverge at non-cardinal
angles (the ring places nodes at angles around a circle, so most edges hit a
hexagon corner region, not its flat side) — the fixed `gap` is measured from
the invisible bbox, not the visible shape, so the *visual* standoff varies
with how far the hexagon's outline is inset from its bbox at that particular
angle. Fix: for hexagon (and any non-rectangular) entity shapes, compute the
true shape-outline intersection point (not the bbox) before applying `gap`,
or increase `gap` specifically for hexagon targets to compensate for the
average inset. Re-render `03` and measure standoff on all 6 edges for
consistency.

---

## 5. Legend band sizing tied to canvas height, not content [Low]

**Resolves:** `02` — legend band occupies 62% of canvas height but the key
itself fills only its top-left corner (~78% of the band's width and much of
its height unused).

**Where:** `imageGen/render/legend.py` — `legend_box_size(keys)` (~line 133)
computes the legend's *own* content box correctly, but the containing band
height that gets reserved on the canvas is set elsewhere (search
`pathway_layout.py`/`compositor.py` for where legend space is reserved on the
canvas — likely a fixed fraction or a separate constant, not
`legend_box_size`'s return value).

**Fix instruction:** find the call site that reserves vertical canvas space
for the legend and confirm it uses `legend_box_size(keys)`'s actual height
(plus a small margin) rather than a fixed band fraction. Do this after #1
lands, since #1 changes the pathway row's own height/width and the legend
band should size relative to the final canvas, not the current oversized one.

---

## 6. `fit_label` wrap-rung sometimes shrinks further than needed [Low]

**Resolves:** `05` — "N-Phenylbenzamide" wraps as orphaned "N-" / "Phenylbenzamide"
at an extra-small font despite the box having ~30px of unused vertical margin
top and bottom (i.e. a larger single-line or better-balanced 2-line font
would still fit).

(Note: `05`'s other finding — "Aniline" rendering larger than "Benzoic Acid"/
"N-Boc-Aniline" in same-size boxes — is very likely **not a defect**: shorter
text legitimately gets to stay at a larger font than longer text in the same
box width under `fit_label`'s designed behavior (LIMITATIONS.md: "long names
wrap/shrink in place"). No action recommended there; don't spend time on it.)

**Where:** `imageGen/primitives/_text.py` `fit_label` (~line 348), rungs 2–3
(~lines 401–420): shrink single-line toward `floor`, then shrink the 2-line
wrap toward `floor`.

**Fix instruction:** read the rung-2/rung-3 transition condition — it likely
falls through to the 2-line wrap-and-shrink rung as soon as the single line
doesn't fit at full size, without checking whether a *taller* single-line
font (shrunk less aggressively, using the box's actual available height, not
just width) would fit instead of wrapping. For a box with real vertical slack
like this one, prefer the option that reads better (fewer, larger lines) when
both fit within the floor. Low priority — cosmetic only, no legibility
failure.

---

## 7. RDKit reaction rendering: water/single-atom sizing + reagent/notes font consistency [Low]

**Resolves:**
- `04`: water renders as a large red "H2O" formula label (~6x the text scale
  of the other three molecules' skeletal-structure heteroatom labels).
- `04`: "H2SO4, heat" (reagents, above arrow) renders visibly larger than
  "reflux, -H2O" (notes, below arrow) despite both being reaction-condition
  text on the same arrow.

**Where:**
- `imageGen/primitives/_mol_render.py` — `render_molecule`/`_natural_box`
  (~lines 384, 424). Water (`O`, or `[H]O[H]`) has 1 heavy atom and no bonds;
  confirm whether there's a distinct code path for a single-heavy-atom
  molecule that falls back to a bare-formula label at a different (larger)
  font scale than the small heteroatom labels drawn inside a skeletal
  structure — RDKit's own 2D depiction typically has no interesting skeleton
  to draw for water, so imageGen (or RDKit) is likely choosing a
  formula-label fallback without matching it to the heteroatom-label font
  size used elsewhere in the same scheme.
- `imageGen/layout/reaction_layout.py` ~line 653:
  `cond_size = int(_CHEM_STYLE["chem_conditions_font_size"])` — a single
  style constant is used for condition text sizing. If reagents (above) and
  notes (below) genuinely render at different sizes despite sharing this
  constant, the divergence is in `imageGen/primitives/chemistry.py`'s
  `_wrap_conditions` or wherever "above" vs "below" condition blocks are
  drawn — check for two separate call sites that might each apply their own
  font math (e.g. one path passing `cond_size` directly, another recomputing
  it from a different constant like the compound-name label size).

**Fix instruction:** for water, add an explicit check: when a molecule has
≤1 heavy atom (or renders via the formula fallback), size its label to match
the *heteroatom label font*, not a full compound-name font. For the
condition-font divergence, trace both the reagents (above) and notes (below)
render call sites back to confirm they both actually read
`chem_conditions_font_size` — unify if one doesn't. Fully independent of
items #1–#6 (different engine entirely); safe to do any time, no ordering
dependency.

---

## 8. Tier chassis: leader lines that don't reach their target, curly-arrow-over-bond overlap [Low–Medium]

**Resolves:** `11` — Scene 3's dashed leader line under the alkoxide product
label stops ~170px short of the atom it's meant to indicate (floating,
disconnected — a different defect from the already-fixed wrong-molecule label
pointing); the small "carbonyl collapse" curly-arrow head renders directly on
top of the molecule's own C=O bond stroke rather than sitting cleanly beside
it. Also `10`: a summary-band arrow meets the cell membrane at a shallow
~35–40° angle instead of pointing in perpendicular (same *category* of issue
as item #2, but in the tier engine, not the pathway engine — separate code).

**Where:** `imageGen/layout/tier_layout.py` — the curly-arrow pose/orientation
solving functions (~lines 600–660, the `curly_only`/pose-driver logic
referenced when I fixed context around this area earlier), and whatever
function computes a slot's external-label leader-line endpoint (search for
`leader` near tier label placement).

**Fix instruction:**
1. Leader-line-too-short: the leader's endpoint is likely computed once at
   label-placement time based on an *estimated* atom position, but the
   molecule's final layout (after per-scene restyling / bond-length
   normalization mentioned in the original `11` gen report) shifts the atom
   afterward without the leader endpoint being recomputed. Find where the
   leader endpoint is captured relative to the molecule's anchor system
   (`a{map}`/`atom{N}` anchors, per SKILL.md's tier-figure anchor docs) and
   make sure it's read *after* final molecule placement, not before.
2. Curly-arrowhead-over-bond: this is likely the same short-distance-pose
   degenerate case flagged as a hypothesis in the original handoff for `11`'s
   *other* (already-fixed) curly-arrow defect — when the curly arrow's
   `bow`/curvature parameter is small (a tight collapse over a short C=O
   bond), the computed arrowhead position doesn't offset far enough from the
   bond's own stroke. Increase the minimum offset/clearance for short-radius
   curly arrows so the head clears the bond line it's pushing electrons onto.
3. `10`'s shallow membrane-crossing angle: unrelated code path (this is a
   `mechanism_cartoon` summary `scene_row`, not a pathway compartment) — if
   worth fixing at all (it's minor/cosmetic, arguably acceptable for a
   schematic "entering the cell" illustration), the fix is in whatever
   attach/anchor logic placed that arrow's endpoint on the cell glyph;
   otherwise leave as-is.

Independent of items #1–#7 (separate archetype/engine). Do last among the
"real" fixes since it's the most specialized code path and benefits least
from bundling with anything above.

---

## 9. Verify-only: arrow style differences that may be intentional, not bugs [Low]

**Findings to check, not blindly "fix":**
- `08`: "ATP supply" arrow (thin single-stroke, solid triangle, orthogonal
  routing) looks different from the other relations (thick double-line
  outlined shaft, open chevron, diagonal).
- `07`: one connector ends in a bare open circle, the next in the same chain
  ends in a filled triangle.
- `10`: summary-band "COX-1→prostaglandins" arrow is bold/solid, the
  adjacent "COX-1→reduced PG" arrow is thin/gray.

**Why verify first:** imageGen deliberately gives different `RelationType`s
distinct visual conventions (T-bars for inhibition, etc. — this is enforced
by `imageGen/verify/convention_check.py`). A grep for a relation-style
dispatch table in `pathway_layout.py`/`compositor.py` didn't surface an
obvious single lookup during this session's investigation — so before
"fixing" any of these three, check what `RelationType` each arrow in the pair
actually is (read the source IR/spec, e.g. `08`'s ATP-supply relation is
probably `transports` while the others are `activates`/`generic`/etc.). If
the two arrows in a pair are genuinely different relation types, this is
correct-by-design and **no fix is needed** — just note it. Only treat it as a
bug if two arrows of the *identical* `RelationType` render with different
styling in the same figure.
