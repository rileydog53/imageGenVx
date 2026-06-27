# D6 / Orientation — rationale of record

> **Status: IMPLEMENTED & CLOSED 2026-06-25** (pub-grade dim 3). Retained as the
> rationale-of-record because shipped code cites it
> (`primitives/_mol_render.py`, `layout/tier_layout.py`). The full scoping doc was
> pruned to git history 2026-06-26; deferred-v2 items are tracked in
> `PUBGRADE_ROADMAP.md`.

## What shipped

A rigid orientation pass poses each reactant so its reactive atom faces its
partner. `_orient_conformer` (`_mol_render.py`) rotates the shared RDKit conformer
about its centroid **before** sizing/draw (so box + depiction + anchors move
together), gated to the tier path (`target_bond_px` set → leaf/panel byte-identical).
`_scene_orientations` (`tier_layout.py`) infers `(reactive_atom, direction)` from
each `CURLY` SceneEdge `to_anchor` + the `Attach` placing the two reactants, and
threads it into both the size predictor and the renderer so the posed box matches.

## Locked decisions

- **Atom + direction inference:** the CURLY `to_anchor` selects the reactive atom;
  the residue's `Attach.edge` selects the direction it should face.
- **Per-scene**, not per-figure (each step poses independently).
- **Curly edges only** drive orientation in v1.
- **80° deadband** — structures already within 80° of aligned stay in canonical
  pose. (The proposed 30–45° was too tight: the corpus's already-fine control
  (fig 05) needs a 71° correction while the must-fix substrates need 85–96°, so a
  tight deadband re-posed 05 into a caption collision. 80° sits in the gap.)
- **Angle sign:** mind RDKit y-up vs SVG y-down (handled in `_orient_conformer`).

## Deferred to v2 (tracked in `PUBGRADE_ROADMAP.md`)

- H-bond / dashed edges as orientation drivers (v1 = curly only; fig 01-s1, 08-s1
  still pose the H-bond step canonically).
- Reflection (mirror) tie-break when rotation alone can't aim the atom.
- Cross-step scaffold consistency — keep a shared substrate posed the same across
  a step sequence (fig 01 s1-vs-s2 drift).
- Collision-aware orientation — a taller re-posed molecule can overrun its caption
  (the fig-05 containment finding); would let the deadband tighten.

Tests: `tests/test_orientation_d6.py` (+15, incl. a geometric end-to-end check +
a deadband-window guard).
