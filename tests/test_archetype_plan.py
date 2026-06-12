"""P0a.1 / P0a.2: the unified `_ARCHETYPE_PLAN` dispatch table + `LoweringPlan`.

These pin the single-source-of-truth invariants so a future edit that
re-introduces a duplicate archetype→engine encoding (or desyncs the derived
`ARCHETYPE_TO_LAYOUT` / `_PATHWAY_COMPATIBLE_ARCHETYPES` views) fails loudly.
"""
from __future__ import annotations

from imageGen.ir.schema import (
    Archetype, Entity, EntityType, Figure, Panel, Scene, Tier, TierRole,
)
from imageGen.layout._archetype_plan import _ARCHETYPE_PLAN
from imageGen.layout.panel_layout import ARCHETYPE_TO_LAYOUT
from imageGen.layout.pathway_layout import (
    _PATHWAY_COMPATIBLE_ARCHETYPES, layout_pathway,
)
from imageGen.layout.reaction_layout import layout_reaction
from imageGen.render.compositor import (
    LabelStrategy, _canvas_size, _label_requests_fn, _lowering_plan,
)


def test_archetype_plan_covers_every_leaf_archetype():
    assert set(_ARCHETYPE_PLAN) == set(Archetype)


def test_archetype_to_layout_derives_from_the_plan():
    assert ARCHETYPE_TO_LAYOUT == {a: p.engine for a, p in _ARCHETYPE_PLAN.items()}


def test_pathway_family_matches_compat_set():
    derived = frozenset(a for a, p in _ARCHETYPE_PLAN.items() if p.engine is layout_pathway)
    assert derived == set(_PATHWAY_COMPATIBLE_ARCHETYPES)
    assert _ARCHETYPE_PLAN[Archetype.REACTION_SCHEME].engine is layout_reaction


def test_label_requests_fn_reads_the_plan():
    for a in Archetype:
        assert _label_requests_fn(a) is _ARCHETYPE_PLAN[a].label_fn


def _leaf() -> Figure:
    return Figure(archetype=Archetype.PATHWAY,
                  entities=[Entity(id="a", type=EntityType.PROTEIN, label="A")])


def _paneled() -> Figure:
    return Figure(archetype=Archetype.WORKFLOW,
                  panels=[Panel(id="p", grid=(0, 0, 1, 1), content=_leaf())])


def _tiered() -> Figure:
    return Figure(archetype=Archetype.MECHANISM_CARTOON,
                  tiers=[Tier(id="t", role=TierRole.SCENE_ROW, scenes=[Scene(id="s")])])


def test_lowering_plan_label_strategy_is_container_first():
    assert _lowering_plan(_leaf(), None).label_strategy is LabelStrategy.LEAF
    assert _lowering_plan(_paneled(), None).label_strategy is LabelStrategy.PER_PANEL
    assert _lowering_plan(_tiered(), None).label_strategy is LabelStrategy.BAKED


def test_lowering_plan_canvas_matches_canvas_size():
    # plan.canvas_fn(ir) is what render_figure now uses; it must equal the
    # legacy _canvas_size(ir, entries) for every container mode.
    for fig in (_leaf(), _paneled(), _tiered()):
        assert _lowering_plan(fig, None).canvas_fn(fig) == _canvas_size(fig, [])
