"""P.3 — the tier-figure corpus gate.

The pub-grade phase's third finding: a skill call must produce a *tier* figure,
and "pub-grade by default" is unmeasurable while the chassis corpus is N = 1.
This test pins a corpus of diverse tier figures authored **through the skill
path** (IR JSON carrying ``tiers``, per ``SKILL.md`` → *Tier figures*), each
rendered through the same compositor and passing all three tier-aware verifiers.

Every figure under ``showcase/corpus/`` is:
  * a tier figure (``Figure.tiers`` populated, no leaf ``entities``);
  * authored as plain IR JSON — none is a one-off hand-written Python script;
  * rendered + checked here, so a regression in any of them fails the suite.

If a figure here regresses, fix the engine or re-author the JSON — do not delete
a corpus member to make the suite pass (that shrinks the very corpus this gate
exists to grow).
"""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import pytest

from imageGen.ir import Figure
from imageGen.render.compositor import render_figure
from imageGen.verify.convention_check import convention_check
from imageGen.verify.legibility_check import legibility_check
from imageGen.verify.semantic_check import semantic_check

CORPUS_DIR = Path(__file__).resolve().parent.parent / "showcase" / "corpus"
CORPUS = sorted(CORPUS_DIR.glob("*.json"))


def _figure(path: Path) -> Figure:
    return Figure.model_validate(json.loads(path.read_text()))


def test_corpus_has_at_least_ten_figures():
    # The acceptance bar for P.3: a real corpus, not N = 1.
    assert len(CORPUS) >= 10, (
        f"expected >=10 tier figures in {CORPUS_DIR}, found {len(CORPUS)}"
    )


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.stem)
def test_corpus_member_is_a_tier_figure(path: Path):
    fig = _figure(path)
    assert fig.tiers, f"{path.name} is not a tier figure (no Figure.tiers)"
    # tier figures carry no top-level leaf graph
    assert not fig.entities and not fig.relations, (
        f"{path.name} mixes a leaf graph with tiers"
    )
    # at least one scene_row tier with content (title-only is not a figure)
    assert any(t.scenes or t.step_sequence for t in fig.tiers), (
        f"{path.name} has no scene_row content"
    )


@pytest.mark.parametrize("path", CORPUS, ids=lambda p: p.stem)
def test_corpus_member_renders_and_passes_all_tier_checks(path: Path, tmp_path):
    fig = _figure(path)
    # Tolerated label-overlap warnings are a known pub-grade defect (D1–D4 in
    # PUBGRADE_ROADMAP.md), not a render failure — let them through here.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = render_figure(fig, tmp_path / f"{path.stem}.svg")
    assert out.exists() and out.stat().st_size > 0
    semantic_check(fig, out)     # every authored slot present
    legibility_check(out)        # no illegible overlap
    convention_check(fig, out)   # slot shapes + edge conventions
