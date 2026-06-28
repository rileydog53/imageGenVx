# D6 / Orientation — rationale of record

> **Status: v1 IMPLEMENTED & CLOSED 2026-06-25** (pub-grade dim 3); **v2
> (cross-step consistency + H-bond drivers) LANDED 2026-06-28** — see *v2 — LANDED*
> below. Retained as the rationale-of-record because shipped code cites it
> (`primitives/_mol_render.py`, `layout/tier_layout.py`). The full scoping doc was
> pruned to git history 2026-06-26; remaining deferred items are below.

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

## v2 — LANDED 2026-06-28 (orientation-v2 branch)

- **Cross-step consistency — DONE.** Two cases: (A) a molecule recurring with the
  *same* SMILES across scenes now shares one pose — `_resolve_tier_orientations`
  groups by SMILES and propagates the single inferred orientation to unconstrained
  recurrences (aspirin `asp` no longer flips s1↔s2↔s3). (B) a *transforming*
  scaffold (different SMILES each scene) keeps its conserved core posed identically
  — `_resolve_tier_scaffold` finds the series' MCS and aligns each member's
  depiction to a shared reference via `GenerateDepictionMatching2DStructure`
  (`_align_to_reference`), threaded through both the size predictor and the renderer
  (β-lactamase thiazolidine core stable across s1–s4). Template = the
  most-constrained member, so the shared pose carries the common partner-facing.
- **H-bond / dashed drivers — DONE.** `_scene_orientations` drives off CURLY first,
  then HBOND / DASHED as a fallback, so a no-curly binding step aims its donor /
  acceptor (fig 01-s1). Still needs a direct parent-child Attach between the edge
  slots, so a pair bridged only through a shared substrate (fig 08-s1) stays
  canonical.

## Still deferred

- **Reflection (mirror) tie-break.** No driving case: a 2-D rotation always aims a
  single atom, and the inference is single-atom per slot, so there is no mirror
  ambiguity to resolve in the current corpus. The `reflect=` plumbing in
  `_orient_conformer` / `molecule_natural_size` is left in place for when a real
  2-point / wrong-mirror case appears. (Decided 2026-06-28.)
- **Collision-aware orientation** — a taller re-posed molecule can overrun its
  caption (the fig-05 containment finding); would let the 80° deadband tighten.
  The genuinely valuable remaining piece; distinct from reflection.

Tests: `tests/test_orientation_d6.py` (+15, incl. a geometric end-to-end check +
a deadband-window guard).
