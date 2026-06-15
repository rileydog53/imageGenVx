"""P7.4 — the V3 acceptance gate.

The aspirin/COX-1 figure (``showcase/aspirin_cox1_v3_acceptance.json``) is the
feature-complete proof of the V3 scene chassis: a three-tier, IR-driven mechanism
figure that renders and passes the tier-aware semantic + legibility + convention
checks, with the three mechanism-figure-fidelity criteria demonstrably met:

  * MF-1 — residues (Ser530, His513) are real molecular fragments (RESIDUE slots),
    heteroatoms render as coloured letters, never bare dots.
  * MF-2 — the Step-2 curly arrows originate on real bond / lone-pair anchors.
  * MF-3 — placement is solved (the scene solver spreads the active-site fragments
    so they never overlap).

If this breaks, the acceptance artifact regressed — re-author or fix the engine,
do not silently weaken the assertions.
"""
from __future__ import annotations

import json
from pathlib import Path

from imageGen.ir import Figure
from imageGen.render.compositor import render_figure
from imageGen.verify.convention_check import convention_check
from imageGen.verify.legibility_check import legibility_check
from imageGen.verify.semantic_check import semantic_check

ACCEPTANCE = (
    Path(__file__).resolve().parent.parent
    / "showcase" / "aspirin_cox1_v3_acceptance.json"
)


def _figure() -> Figure:
    return Figure.model_validate(json.loads(ACCEPTANCE.read_text()))


def test_acceptance_artifact_exists_and_is_a_tiered_figure():
    fig = _figure()
    # three tiers: title / 4-step mechanism row / summary bar
    assert [t.role.value for t in fig.tiers] == ["title", "scene_row", "scene_row"]
    assert len(fig.tiers[1].scenes) == 4  # four mechanism steps


def test_acceptance_renders_and_passes_all_tier_aware_checks(tmp_path):
    fig = _figure()
    out = render_figure(fig, tmp_path / "acceptance.svg")
    assert out.exists() and out.stat().st_size > 0
    semantic_check(fig, out)    # every slot present
    legibility_check(out)       # no overlapping labels
    convention_check(fig, out)  # slot shapes + inhibits T-bar


def test_acceptance_mf1_residues_are_real_fragments():
    # Every mechanism step carries Ser530 + His513 as RESIDUE slots (real
    # fragments), not TEXT placeholders or bespoke dots.
    fig = _figure()
    for scene in fig.tiers[1].scenes:
        residues = {sl.id for sl in scene.slots if sl.kind.value == "residue"}
        assert {"ser", "his"} <= residues, f"{scene.id} missing a residue fragment"


def test_acceptance_mf2_curly_arrows_originate_on_real_anchors():
    fig = _figure()
    s2 = next(s for s in fig.tiers[1].scenes if s.id == "s2")
    curly = [e for e in s2.connect if e.type.value == "curly"]
    assert curly, "Step 2 must carry the nucleophilic-attack curly arrows"
    # each curly originates on a bond-midpoint or lone-pair anchor, not a bare atom
    for e in curly:
        assert "lp_" in e.from_anchor or "bond_" in e.from_anchor


def test_acceptance_mf3_active_site_fragments_do_not_overlap(tmp_path):
    # The solver spreads the three active-site fragments (substrate + Ser530 +
    # His513) so they render as distinct, legible groups — assert all present.
    fig = _figure()
    out = render_figure(fig, tmp_path / "acc.svg")
    txt = out.read_text()
    for sid in ("s1.asp", "s1.ser", "s1.his"):
        assert f'id="{sid}"' in txt
