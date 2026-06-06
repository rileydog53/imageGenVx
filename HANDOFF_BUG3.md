# Handoff — resume at Bug 3 (receptor label overlaps arrows)

## Where things stand (read this first)

- **Repo:** `~/Desktop/imageGen-v2.5/`  • **venv:** `~/Desktop/.venv` (Python 3.12)
- **Branch:** `fix/layout-overlaps-bug1-bug2` (NOT pushed — local only, no PR yet)
- **Last commit:** `9f18253` fix(layout): stop entity-box overlap and labels-on-arrow-shafts
- **Working tree:** clean
- **Test baseline:** `~/Desktop/.venv/bin/python -m pytest tests/ -q` → **765 passed**
- **Run a figure:** `~/Desktop/.venv/bin/python -m imageGen <IR.json> -o <out.png> --dpi 96`
- **Test specs live in:** `~/Desktop/scratch/labelfit_test/` (safe1_mapk.json, stress2_hub.json, etc.)

## What's already fixed (commit 9f18253)

- **Bug 1** — entity boxes overlapped / arrows drew backwards inside a box. Root
  cause: the LT4 position clamp in `_graph_positions` (`pathway_layout.py`) sized
  the horizontal clamp by *centered-label* width, pulling wide-labeled neighbours
  until their boxes collided. Fixed: clamp by box width only (`half_x = ew/2`),
  both call sites.
- **Bug 2** — relation labels landed on arrow shafts. Root cause: arrows were
  zero-footprint to the greedy label engine. Fixed: `_shaft_bboxes()` in
  `label_placement.py` samples small collision boxes along each shaft polyline
  and adds them to `place_labels`' `occupied` set. New tests in
  `tests/test_label_shaft_avoidance.py`.

## The full bug list (from LAYOUT_BUGS_PLAN.md)

1. ✅ Arrow endpoints inside boxes (DONE)
2. ✅ Relation labels on shafts (DONE)
3. ⏭️ **Receptor label overlaps arrows (THIS TASK)**
4. ⬜ ATM→p53 same-band arrow doesn't arch (passes through CHK2)
5. ⬜ External-label boxes have no leader lines + entity/relation labels collide
6. ⬜ Ring label crowding + unbalanced wrap ("a-" / "Ketoglutarate")

The full root-cause analysis + recommended fixes for all six are in
**`LAYOUT_BUGS_PLAN.md`**. Bug-1 deep-dive is in **`BUG1_FINDINGS.md`**.

---

## Bug 3 — the task

### Symptom
In `safe1_mapk` (`~/Desktop/scratch/labelfit_test/safe1_mapk.json`), the receptor
entity EGFR renders its "EGFR" label and the binding arrow between EGF and EGFR
passes straight through the text (struck through). Bug 2's shaft-corridor fix did
NOT solve this, because the EGFR label is the *receptor primitive's own
left-anchored label*, not a `place_labels`-managed relation label — so the
placement engine never sees it.

### Root cause
`proteins.receptor()` (`imageGen/primitives/proteins.py`, ~line 334) draws its
label to the LEFT of the hourglass body with a `text-anchor: end` `<text>`
element. But `ENTITY_BBOX[RECEPTOR] = (28, 60)` (`layout/_geom.py`) covers only
the body. So:
- `label_placement._entry_bbox()` reserves only the 28x60 body — the label is
  invisible to other labels.
- `pathway_layout._arrow_endpoints` / `_bbox_exit_point` exit the body's left
  edge and route straight through where the label sits.

### Recommended fix (from LAYOUT_BUGS_PLAN.md, Bug 3)
Two parts:
1. In `label_placement._entry_bbox()`, detect receptor entries
   (`entry.primitive is proteins.receptor`) and extend the collision bbox
   LEFTWARD by the estimated label width — same pattern already used for the
   generic entity-label-extent widening a few lines below in that function.
2. In `pathway_layout._arrow_endpoints` (or where it calls `_bbox_exit_point`),
   use the extended footprint (body + label width) as the effective half-width
   for receptor source/target entities, so the arrow exits past the label.

Explicitly OUT OF SCOPE (file as a separate ticket if you want it): moving the
receptor label to above/below the body like `gpcr` does. The fix above is the
narrow, safe one.

### Verify
- `~/Desktop/.venv/bin/python -m pytest tests/ -q` stays green (765+).
- Re-render safe1 and confirm the binding arrow no longer crosses "EGFR":
  `~/Desktop/.venv/bin/python -m imageGen ~/Desktop/scratch/labelfit_test/safe1_mapk.json -o /tmp/safe1_bug3.png --dpi 110`
  then Read /tmp/safe1_bug3.png.
- Add a regression test (e.g. in tests/test_layout_pathway.py or a new file):
  an entity using the receptor primitive contributes a collision/exit footprint
  wider than its 28px body on the label side.

### Workflow notes / gotchas from the last session
- The shell tool occasionally lags or garbles output (stale stdout, a stray
  `inspect.py` in scratch once shadowed the stdlib). Trust pytest exit codes and
  Read-the-PNG over eyeballed terminal text. If output looks wrong, re-run the
  single command from the repo root with absolute paths.
- Don't commit `tests/figures/*.png` — those are rewritten every run and are not
  goldens. `git checkout -- tests/figures/` before committing.
- Golden images are `tests/golden/`; only regen with `IMAGEGEN_REGEN_GOLDEN=1`
  after visual inspection, and only if a fix legitimately changes them.
- Commit on the existing branch `fix/layout-overlaps-bug1-bug2` (or a new one) —
  do not commit to `main`. End commit messages with the Co-Authored-By line.
- CONTRIBUTING.md hard rules still apply (svgwrite objects only, every primitive
  gets a golden test, don't touch ir/schema.py without approval).
