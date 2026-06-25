# D6 — Molecule Orientation (pub-grade dimension 3): scoping doc

> **STATUS: IMPLEMENTED & CLOSED 2026-06-25.** This was the scoping doc; the
> feature landed as scoped (steps 1–4 below), suite 1190 → 1205. Two findings
> updated the plan during implementation: (1) the deadband had to be **80°**, not
> the proposed 30–45° — the corpus's "already-fine" control (fig 05) needs a 71°
> correction while the "must-fix" substrates need 85–96°, so a tight deadband
> re-posed 05 into a caption collision; 80° sits in the gap. (2) That fig-05
> collision is fundamentally a **containment** issue (a taller re-posed molecule
> overruns its caption) — logged as a dim-5 follow-up, with collision-aware
> orientation as the path to a tighter deadband. See `V3_STATUS.md` /
> `PUBGRADE_ROADMAP.md` for the landed summary. The design below is preserved as
> the rationale of record.

Scope/design only — **no feature code in this doc.** A fresh agent should be able
to implement D6 from this. Read `PUBGRADE_ROADMAP.md` (dim table, D1–D9) and
`V3_STATUS.md` (CURRENT FOCUS) first; this is the dim-3 deep-dive they defer to.

> Evidence base: this doc folds in a verified investigation (2026-06-25).
> RDKit-capability claims were **empirically run** against the installed RDKit
> 2026.03.1 (`~/Desktop/.venv`); corpus claims came from rendering all 11 figures
> and probing atom coordinates. Where a claim is *assumed* rather than verified it
> is marked **(unverified)**. The adversarial-critique pass that was planned for
> this scope was cut short by a session limit — §6 and §10 carry the skeptical
> review inline instead; treat §10 as the must-resolve list before coding.

---

## 1. Problem (D6)

Within a mechanism step, a substrate can be posed so the **attacked atom faces
away from the attacking residue**, so the curly arrow has to sweep across the
whole molecule and the step does not read left-to-right. This violates the
standing rule **cleanness before correctness gating** (`PUBGRADE_ROADMAP.md`): the
chemistry is correct but the figure reads wrong.

**It is real but focused** — a defect of the *residue-attack mechanism* archetype,
not corpus-wide. Eyeballing + coordinate probes across the 11-figure corpus:

| Figure | D6? | Why |
|---|---|---|
| `08_acetylcholinesterase_hydrolysis` | ✅ **worst** | ester carbonyl C at relX=0.17 (far left), its =O points straight **down**; Ser203 attacks from top-center over the *ammonium* (wrong) end → arrow sweeps full width and doubles back |
| `aspirin_cox1_v3_acceptance` | ✅ **highest impact** | byte-identical to corpus 01; the **flagship acceptance figure** carries the defect: acetyl carbonyl at relX=0.16 faces up-left, away from the top-center Ser530 |
| `01_aspirin_cox1_acetylation` | ✅ | same geometry as acceptance **plus** a cross-scene inconsistency: s1 H-bonds to `cooh` (far right) while s2/s3 attack the carbonyl (far left) → Ser's O appears to point two opposite ways across the sequence |
| `02_chymotrypsin_acylation` | ✅ moderate | scissile carbonyl at relX=0.33; its =O *does* point up toward Ser195, but Ser renders to its right and a closer **non-reactive** carbonyl sits between them → arrow swings past the wrong carbonyl |
| `05_imine_formation` | ❌ **control** | same archetype, but RDKit's canonical pose *coincidentally* puts the reactive carbonyl at relX=0.75, relY=1.0 — top-right, right under the amine. Reads fine. **This is the proof the fix only needs to guarantee that alignment.** |
| `03_sn2_substitution` | ❌ | too small — methyl bromide is a `Br` stub, carbon implicit; already reads L→R |
| `04 / 06 / 07 / 10` | ❌ | glyph/blob pathway or binding diagrams — no molecule with a reactive atom to mis-orient |
| `09_disulfide_redox` | ❌ | the two Cys are Attach'd vertically so the reactive S atoms already face each other |

**Common failure signature:** `Attach` puts the partner residue on an **edge** of
the substrate's bounding box (almost always `top`), but the reactive atom named in
the `SceneEdge.to_anchor` lands **elsewhere** in the box (far-left for aspirin/ACh).
`Attach` controls only where the partner sits relative to the substrate *bbox* — it
has no influence on where the reactive atom is *inside* that bbox.

---

## 2. Current behavior — the single posing seam

Every molecule (and every residue) is posed in exactly one place,
`imageGen/primitives/_mol_render.py`:

- `_natural_box` ([:402](imageGen/primitives/_mol_render.py:402)) calls
  `rdDepictor.Compute2DCoords(mol)` ([:414](imageGen/primitives/_mol_render.py:414))
  — RDKit's **canonical 2D pose, used as-is. No rotation/reflection is ever
  applied to orient a reaction.**
- The conformer from that one `Compute2DCoords` is **shared**: `_natural_box`
  measures the bbox from it for sizing, and `_inline_molecule_anchored`
  ([:327](imageGen/primitives/_mol_render.py:327)) draws from it.
- `render_molecule_anchored` ([:447](imageGen/primitives/_mol_render.py:447))
  reads **anchors straight off the draw coords** (`atom_coords`,
  [:550–571](imageGen/primitives/_mol_render.py:550)) — atom/`a{map}`/named/
  `attach`/bond-midpoint/lone-pair. So **any rigid transform applied to the
  conformer before [:546](imageGen/primitives/_mol_render.py:546) moves draw and
  anchors together, automatically and consistently.** This is the load-bearing
  property D6 stands on.
- Residues route through the same path: `render_residue_anchored`
  ([:590](imageGen/primitives/_mol_render.py:590)) → `render_molecule_anchored`
  ([:630](imageGen/primitives/_mol_render.py:630)).

**`proteins.py`'s `group.rotate` is NOT reusable** ([:97–104](imageGen/primitives/proteins.py:97)):
it rotates the *SVG group* after coords are read, so anchors stay un-rotated. D6
must transform the **conformer**, not the group.

The directional intent the posing site lacks lives in the IR
(`imageGen/ir/_v3_models.py`): `SceneEdge.from_anchor → to_anchor`
([:109–110](imageGen/ir/_v3_models.py:109)) names the nucleophile→electrophile
atoms; `Attach.edge` ([:94](imageGen/ir/_v3_models.py:94)) names where the partner
sits; `TierEdge.from_ref/to_ref` ([:287–288](imageGen/ir/_v3_models.py:287)) names
cross-scene L→R flow.

---

## 3. The core challenge — a dependency cycle

In `_layout_scene` (`imageGen/layout/tier_layout.py`
[:699](imageGen/layout/tier_layout.py:699)) the order is:

1. `_solve_slot_centers` ([:741](imageGen/layout/tier_layout.py:741)) computes slot
   positions — and to do so it needs each slot's **size**, which it gets from the
   predictor `molecule_natural_size` ([:1138](imageGen/layout/tier_layout.py:1138)).
2. the slot render loop ([:787](imageGen/layout/tier_layout.py:787) residue /
   [:793](imageGen/layout/tier_layout.py:793) molecule) draws and publishes anchors.
3. `SceneEdge`s resolve against those anchors
   ([:906](imageGen/layout/tier_layout.py:906)).

The cycle: **orientation** changes a molecule's **bbox** (a wide molecule rotated
90° becomes tall) → bbox feeds **sizing** → sizing feeds **placement** → placement
is what would tell us the partner's solved position → which is what "face the
partner" needs. So orientation appears to need a position that only exists after
orientation.

Two consequences that the design must respect:

- **The predictor and the renderer must apply the *same* orientation.**
  `molecule_natural_size` ([_mol_render:437](imageGen/primitives/_mol_render.py:437))
  re-depicts the molecule **independently** of the actual render (separate `Mol`
  instance, separate `Compute2DCoords`). Both poses are *deterministic and
  identical* (see §4), so applying the same orientation rule to both keeps the
  predicted box equal to the drawn box. If only one is oriented, the box mismatches
  the drawing and layout breaks.
- **The orientation must be computable *before* the solve** (it feeds sizing at
  step 1). This is the key to cutting the cycle, next.

### Cutting the cycle: orient toward the *Attach edge*, not the solved partner

Do **not** orient toward the partner's *solved* position (that is what creates the
cycle). Orient toward the **`Attach.edge` direction**, which is static IR known
before any solving. "The residue is Attach'd to my `top` edge → my reactive atom
should point toward `top`." This is exactly the corpus failure signature (§1) and
is cycle-free. The solved partner position is never needed for v1.

(Within a scene, `_solve_slot_centers` at [:741](imageGen/layout/tier_layout.py:741)
*does* expose intra-scene centers before the render loop, so a future v2 could
refine toward the real partner center. Cross-scene partners are not resolved until
TierEdge time ([:~1506](imageGen/layout/tier_layout.py:1506)), so cross-scene must
use static `from_ref/to_ref` intent regardless. v1 sticks to the static edge.)

---

## 4. Design

### 4a. The reorientation primitive (verified)

A **manual rigid transform of the existing shared conformer**, applied via
`rdMolTransforms.TransformConformer(conf, M)` with a numpy 4×4
`M = T(c)·R(θ)·T(−c)` about the atom centroid `c`. Optionally compose a mirror
(`diag(−1,1)` left/right, `diag(1,−1)` up/down about `c`) to flip which side the
rest of the molecule falls on.

**Verified against RDKit 2026.03.1** (probes on aspirin
`CC(=O)Oc1ccccc1[C:1](=O)O`):
- Rotating the mapped carbonyl C onto +x: after-angle = −4.2e-16° (exact); max
  bond-length change 4.44e-16; centroid moved 2.9e-16 → **rigid, no distortion.**
- Reflection: max bond-length change 0.0; bond angle at the mapped atom
  120.0000…° before and after → **rigid.**
- `Compute2DCoords` is **deterministic**: 4 runs on aspirin, max coord diff 0.0;
  toggling `SetPreferCoordGen` and back restores byte-identical coords. → the
  angle the engine derives from the canonical pose is reproducible, and the
  predictor/renderer agree.

**Ruled out** (also verified):
- `StraightenDepiction` / `NormalizeDepiction` — rigid but snap to a bond-angle
  grid / principal inertial axis; **cannot aim a *chosen* atom.** Normalize also
  rescales bonds by default. Not the primitive. (If `Straighten` were ever chained
  *after* the aim it would override it — don't.)
- `SetPreferCoordGen` / `GenerateDepictionMatching2DStructure` (hard mode) —
  **regenerate coordinates** (CoordGen vs default differ by max 4.48 on aspirin),
  so they'd change the depiction shape and break byte-identity. Not for orientation.
- **2D chirality is a genuine non-concern:** reflecting a conformer leaves graph
  stereo tags and the SMILES unchanged, and skeletal depictions emit zero wedge
  bonds — a mirror has no visible chirality effect.

### 4b. Computing the angle

1. Resolve the **target atom index** from the IR intent: the reactive atom is the
   `SceneEdge.to_anchor` atom (the electrophile being attacked). The
   anchor-name/map-num → RDKit-index map already exists inside
   `render_molecule_anchored` ([:513–517, 550–562](imageGen/primitives/_mol_render.py:513));
   the transform must run *after* that map is built but *before* `_inline_molecule_anchored`.
2. Resolve the **desired direction** in the **SVG frame** from `Attach.edge`
   (top → up, bottom → down, left → left, right → right).
3. `θ = desired_angle − atan2(target − c)`; build `M`; `TransformConformer(conf, M)`.
4. **Reflection (secondary, optional for v1):** if a second reference atom (e.g.
   the `from_anchor` side, or the bulk of the molecule) ends up overlapping the
   incoming partner, compose a mirror and re-apply. Rotation alone fixes the
   primary "atom faces the right way" defect; reflection is a tidiness enhancement.

> **Frame gotcha (verified risk):** RDKit's conformer y points **up**; the
> rendered SVG y points **down**. `+x` ("right") is unaffected, but every up/down
> aim and the choice of mirror axis must be expressed in the **SVG** frame or the
> molecule flips the wrong way. The rigid math is frame-agnostic; only the
> angle/axis fed to it carries the sign.

### 4c. The seam (call-site contract)

Add the orientation as **new defaulted kwargs on `render_molecule_anchored`**, with
`render_residue_anchored` forwarding them. Recommended shape:

```
render_molecule_anchored(..., *, orient_to_atom: str | None = None,
                         orient_direction: str | None = None,  # 'up'|'down'|'left'|'right'
                         orient_reflect: bool = False, ...)
```

- The angle is computed *inside* `_mol_render` from its own conformer (so the
  predictor and renderer — which each build their own conformer — compute the
  **same** θ from the same deterministic pose; no need to pass a precomputed angle
  and risk a desync).
- `orient_to_atom` is an anchor name (`'a1'`, `'carbonyl_C'`, an atom index) the
  function already knows how to map to an index.
- **Hard gate:** the whole transform runs only when `target_bond_px is not None`
  (the V3 tier path). When `None` (leaf/panel), **early-return before constructing
  any matrix** — not a no-op identity matrix (float roundoff at ε could still
  perturb coords; see §6).

### 4d. Where the pre-pass lives

`_layout_scene` ([:699](imageGen/layout/tier_layout.py:699)) computes, per oriented
molecule/residue slot, the `(orient_to_atom, orient_direction)` pair by:
- scanning `scene.connect` ([SceneEdge](imageGen/ir/_v3_models.py:103)) for an edge
  whose `to_anchor` slot-token is this slot → its atom = `orient_to_atom`;
- finding the `Attach` ([:86](imageGen/ir/_v3_models.py:86)) whose `parent` is this
  slot → its `edge` → `orient_direction` (partner on my top → aim `up`, etc.).

Thread that pair into **both** the `molecule_natural_size` call
([:1138](imageGen/layout/tier_layout.py:1138)) and the `render_molecule_anchored`/
`render_residue_anchored` calls ([:787/:793](imageGen/layout/tier_layout.py:787)).
Because both recompute θ from identical deterministic poses, the predicted box
equals the drawn box.

---

## 5. Alternatives considered & rejected

- **New IR field `Slot.orient` (explicit author hint).** `Slot.style` already
  exists ([:78](imageGen/ir/_v3_models.py:78)) and could carry an `orient` hint
  additively. Rejected for v1: the corpus shows the direction is *derivable* from
  `SceneEdge` + `Attach` that authors already write — an explicit field is
  redundant and pushes layout decisions onto authors. Keep it as a v2 **override**
  for the rare case inference gets it wrong (additive, no schema break).
- **Template / scaffold alignment (`GenerateDepictionMatching2DStructure`, soft
  `alignOnly=True`).** Verified to pose a shared core *identically* across
  molecules (benzene core landed byte-identical across two molecules). Genuinely
  useful for a **secondary** goal — keeping a scaffold posed the same across
  mechanism steps (fig 01's cross-scene inconsistency) — and it *composes* with
  the rigid rotate. But it aligns a *core*, not an *arbitrary atom's direction*, so
  it is not the primary primitive. **Deferred to a follow-up** (cross-step
  consistency, §7 OUT).
- **Layout-time fix: choose the `Attach` attachment point nearest the reactive
  atom** instead of rotating the molecule. Rejected: `Attach.edge` is coarse
  (4 edges); it can't put the partner at the carbonyl if the carbonyl is mid-edge,
  and it doesn't make the *molecule* read directionally — only moves the partner.

---

## 6. Risks & invariants (adversarial pass)

- **Byte-identity guarantee (leaf path).** Only `target_bond_px is None` must stay
  byte-identical. **All corpus/tier figures set `target_bond_px`, so they are
  *allowed* to change** — the constraint is purely the leaf/panel path. The gate
  must be a **hard early-return**, because even a 0° `TransformConformer` call can
  perturb coords at the ε level. Add a regression test that a leaf render is
  byte-identical before/after the feature.
- **Pin tests are behavioral, not snapshot** (verified). `test_acceptance_aspirin_cox1.py`
  asserts tier roles, scene count, render-exists, `legibility_check` (no
  overlapping labels), residues present, curly arrows on `lp_`/`bond_` anchors,
  fragment ids present — **no geometry/pixel hash.** `test_corpus_tier_figures.py`
  is the same shape (renders + `legibility_check`, tolerates label-overlap
  warnings). **So D6 won't break them by re-posing** *as long as legibility still
  passes and curly anchors stay valid.* No snapshot re-baselining needed. The real
  risk is **introducing new label overlaps** when a molecule rotates and its
  leader/label placement shifts (dim 2 interaction) — re-run the corpus and eyeball.
- **The control figure (05) will change pose.** It's a tier figure, so legal, but
  the rule must not make it *worse*. Mitigation: a **deadband** — if the reactive
  atom is already within ±θ_tol (e.g. 30°) of the desired edge, **skip the
  rotation** (θ≈0 → no-op). Keeps already-good figures stable and bounds churn.
- **Sizing must read the POST-transform bbox.** `_natural_box` re-measures the
  bbox from the transformed conformer, so this is automatic *iff* the transform
  runs before the bbox measurement. Order inside `_mol_render` matters.
- **Single-shared-conformer is load-bearing.** Anchors stay consistent only because
  the transform runs on the exact conformer `_inline_molecule_anchored` draws from.
  Any future refactor that re-depicts between sizing and drawing would desync
  orientation from anchors. Note this in the code.
- **Centroid choice** (unweighted atom centroid) is fine for aiming; for very
  asymmetric molecules the visual center shifts post-rotation, but since the bbox
  is re-measured, sizing stays correct.

**Claims to verify before/while coding (were not adversarially re-checked):**
- That `_solve_slot_centers` size predictor path ([:1138](imageGen/layout/tier_layout.py:1138))
  is the *only* place a tier molecule's size is predicted (grep for other
  `molecule_natural_size` / `_slot_bbox_size` callers).
- That `render_residue_anchored`'s open-valence dummy-atom handling
  ([_mol_render:518–529](imageGen/primitives/_mol_render.py:518)) doesn't fight a
  rotation (the `attach` anchor is just another atom, so it should rotate with the
  rest — confirm).
- Exact SVG-frame sign for each `Attach.edge` → direction mapping (the y-flip).

---

## 7. Scope boundaries

**IN (v1):**
- Rigid **rotation** of a molecule/residue conformer so its `SceneEdge.to_anchor`
  reactive atom faces the `Attach.edge` direction, on the tier path only.
- Deadband no-op when already aligned.
- Predictor + renderer apply the identical rule.

**OUT (explicitly deferred):**
- **Reflection** beyond the optional secondary tie-break (can land in v1 if cheap,
  but rotation is the contract).
- **Cross-step scaffold consistency** (fig 01's s1-vs-s2 inconsistency) — needs
  template alignment + a per-step-sequence "pose once" decision. Separate feature.
- **Explicit author override** (`Slot.style['orient']`) — v2, additive.
- 3D / stereochemistry / wedge-bond aware posing — not applicable to these
  schematic skeletal depictions.
- Orienting toward the *solved* partner position (refinement; v1 uses the static
  Attach edge).

---

## 8. Test plan

Acceptance set, chosen to cover the archetype and guard against overfitting to
aspirin:
- **Fixes (must improve):** `08_acetylcholinesterase` (worst), `01_aspirin` +
  `aspirin_cox1_v3_acceptance` (flagship), `02_chymotrypsin` (moderate).
- **Control (must NOT regress):** `05_imine_formation` — already correct; assert
  the deadband leaves it effectively unchanged / still legible.
- **Untouched (must be byte-identical or unaffected):** a **leaf** figure
  (e.g. an existing mapk/gpcr fixture) → byte-identical assertion guarding the
  `target_bond_px is None` gate; `03/04/06/07/09/10` → still render + pass
  `legibility_check`.

Assertions (behavioral, matching the existing test style):
- **New positive assertion:** for each fixed figure, after layout the oriented
  slot's reactive-atom vector (centroid→`to_anchor` atom, in figure space) points
  toward the partner's `Attach.edge` within N° (e.g. 45°). This is the direct D6
  check and is overfitting-resistant (it's a geometric property, not a pixel hash).
- `legibility_check` still passes on the whole corpus (no new label overlaps).
- Acceptance MF-2 still holds (curly arrows originate on `lp_`/`bond_` anchors) —
  rotation preserves anchor names, so this should be free; assert it.
- Leaf byte-identity test (new).

Avoid overfitting: the positive assertion is a per-figure geometric invariant, and
the control + untouched sets ensure the rule is general, not aspirin-tuned.

---

## 9. Incremental landing plan (suite-green at each step)

1. **Primitive + gate.** Add `orient_to_atom`/`orient_direction`/`orient_reflect`
   kwargs to `render_molecule_anchored` (forwarded by `render_residue_anchored`),
   implement the rigid `TransformConformer` transform, **hard-gate on
   `target_bond_px is not None`**. Default-off → entire suite byte-identical. Add
   the leaf byte-identity test + a unit test that a given atom lands on a given
   direction (the verified probe, as a test).
2. **Predictor parity.** Thread the same kwargs through `molecule_natural_size` so
   the predicted box matches the oriented draw box. Unit-test predicted == drawn
   bbox under orientation.
3. **Inference pre-pass in `_layout_scene`.** Derive `(to_atom, direction)` from
   `SceneEdge` + `Attach`; thread into both call sites; add the deadband. Re-render
   the corpus; add the positive geometric assertion for the 4 fixed figures.
4. **Corpus verification + re-pin docs.** Confirm 05 + the untouched set still pass
   `legibility_check`; eyeball all 11; update `PUBGRADE_ROADMAP.md` (dim 3 → ✅,
   D6 → fixed) and `V3_STATUS.md`.
5. *(optional, may split out)* secondary reflection tie-break if a fixed figure
   still overlaps after rotation.

---

## 10. Open questions for the human

1. **Driver precedence.** When `SceneEdge.to_anchor` and `Attach.edge` both touch a
   molecule and *disagree*, which wins? (Proposed: `to_anchor` selects the atom,
   `Attach.edge` selects the direction — they're orthogonal, so no conflict in the
   common case. Confirm.)
2. **Multiple `SceneEdge`s on one slot** (fig 01: s1 H-bond to `cooh`, s2 attack to
   carbonyl). Per-scene orientation, or pose a shared slot once across the whole
   step sequence? v1 proposes **per-scene** (simplest, fixes the active arrow);
   cross-step consistency is the deferred follow-up. OK?
3. **H-bond / dashed edges as orientation drivers?** v1 proposes orienting to the
   **curly nucleophilic-attack** edge only; H-bond-only scenes (09 already works by
   stacking) are left alone. OK, or should dashed `SceneEdge`s also drive?
4. **Deadband angle** (skip-if-already-aligned tolerance). Proposed ±30–45°. Pick.
5. **Reflection in v1 or deferred?** Proposed: rotation in v1, reflection optional.

---

*Authored 2026-06-25 (pub-grade Phase P, dim 3). RDKit claims verified against
2026.03.1; corpus claims grounded in rendered figures + coordinate probes.
Supersedes the dim-3 row stub in `PUBGRADE_ROADMAP.md` once dim 3 lands.*
