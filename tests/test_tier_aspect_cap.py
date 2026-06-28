"""Archetype aspect-ratio cap (run10 #3).

A wide many-column ``SCENE_ROW`` used to drive the canvas width unbounded
(``width = n * cell_w + gutters``) with no width-vs-height ceiling, so the more
scenes a row carried the wider+shorter the page (B3's height-packing made the
divisor smaller still). The fix is tier-level: when the content-sized figure
exceeds ``tier_aspect_max`` the engine **wraps** the widest over-wide scene row
onto multiple rows (reflow N columns into ``ceil(N/k)`` per row), shrinking width
and growing height at once; a residual height-raise pins the cap when wrapping
can't reach it (a single intrinsically-wide scene, an all-1-column figure).

The cap sits at the top of the cited 3:1-4:1 publication band, so the pinned
corpus (widest ~3.7:1) is untouched — these tests pin that promise *and* the
wrap behaviour on synthetic wide figures, since no real corpus figure trips it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from imageGen.ir import Figure
from imageGen.render.compositor import render_figure
from imageGen.layout.tier_layout import (
    TIER_DEFAULT_PARAMS,
    _tier_wrap_map,
    _wrap_grid,
    _wrapped_cell_rects,
    layout_tiers,
    tier_canvas,
)
from imageGen.verify.convention_check import convention_check
from imageGen.verify.legibility_check import legibility_check
from imageGen.verify.semantic_check import semantic_check

CAP = float(TIER_DEFAULT_PARAMS["tier_aspect_max"])
CORPUS_DIR = Path(__file__).resolve().parent.parent / "showcase" / "corpus"


def _wide_chain(n: int) -> Figure:
    """A single-band mechanism row of ``n`` molecule scenes — the shape that,
    un-capped, balloons into a landscape strip."""
    scenes = [
        {"id": f"s{i}", "badge": str(i + 1), "label": f"step {i + 1}",
         "slots": [{"id": "m", "kind": "molecule", "label": "aspirin",
                    "style": {"smiles": "CC(=O)OC1=CC=CC=C1C(=O)O"}}]}
        for i in range(n)
    ]
    return Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [
            {"id": "t", "role": "title", "height_frac": 0.14, "label": "Wide chain"},
            {"id": "row", "role": "scene_row", "height_frac": 0.86, "scenes": scenes},
        ],
    })


# --- _wrap_grid / _wrapped_cell_rects unit ------------------------------------

@pytest.mark.parametrize("n,k,expected", [
    (6, 1, (6, 1)),   # no wrap
    (6, 2, (3, 2)),   # 3 per row, 2 rows
    (6, 3, (2, 3)),
    (5, 2, (3, 2)),   # ceil(5/2)=3 cols, ceil(5/3)=2 rows
    (3, 2, (2, 2)),   # short last row
    (1, 4, (1, 1)),   # can't wrap a single scene
    (0, 2, (0, 0)),
])
def test_wrap_grid_shapes(n, k, expected):
    assert _wrap_grid(n, k) == expected


def test_wrapped_cell_rects_is_byte_identical_at_wrap_1():
    from imageGen.layout.tier_layout import _row_cell_rects
    rect = (10.0, 20.0, 600.0, 300.0)
    assert (_wrapped_cell_rects(rect, 4, 1, 24.0, 18.0, 120.0)
            == _row_cell_rects(rect, 4, 24.0, 120.0))


def test_wrapped_cell_rects_lays_a_real_grid():
    rect = (0.0, 0.0, 600.0, 300.0)
    cells = _wrapped_cell_rects(rect, 6, 2, 24.0, 18.0, 120.0)
    assert len(cells) == 6
    ys = sorted({round(c[1], 3) for c in cells})
    xs = sorted({round(c[0], 3) for c in cells})
    assert len(ys) == 2, "6 scenes wrapped onto 2 rows -> 2 distinct row y's"
    assert len(xs) == 3, "ceil(6/2)=3 columns -> 3 distinct x's"
    # rows partition the band height (with a gap between), no overlap
    assert ys[1] > ys[0]


# --- wrap map -----------------------------------------------------------------

def test_wrap_map_engages_only_when_over_cap():
    assert _tier_wrap_map(_wide_chain(2), TIER_DEFAULT_PARAMS)["row"] == 1
    assert _tier_wrap_map(_wide_chain(6), TIER_DEFAULT_PARAMS)["row"] >= 2


def test_wrap_map_respects_min_cols_floor():
    # A wrapped row never collapses below tier_wrap_min_cols (no 1-wide strip).
    floor = int(TIER_DEFAULT_PARAMS["tier_wrap_min_cols"])
    for n in (5, 6, 8, 10):
        k = _tier_wrap_map(_wide_chain(n), TIER_DEFAULT_PARAMS)["row"]
        cols, _ = _wrap_grid(n, k)
        assert cols >= floor


# --- canvas-level cap ---------------------------------------------------------

@pytest.mark.parametrize("n", [5, 6, 8, 10])
def test_wide_row_is_capped_by_wrapping(n):
    fig = _wide_chain(n)
    w_un, h_un = tier_canvas(fig, {"tier_aspect_max": None})
    assert w_un / h_un > CAP, "the un-capped figure should genuinely exceed the cap"
    w, h = tier_canvas(fig)
    assert w / h <= CAP + 1e-6, f"capped aspect {w / h:.2f} must be <= {CAP}"
    assert _tier_wrap_map(fig, TIER_DEFAULT_PARAMS)["row"] >= 2


def test_cap_disabled_restores_precap_behaviour():
    fig = _wide_chain(6)
    w, h = tier_canvas(fig, {"tier_aspect_max": None})
    assert w / h > CAP
    assert _tier_wrap_map(fig, {**TIER_DEFAULT_PARAMS, "tier_aspect_max": None})["row"] == 1


def test_residual_height_raise_pins_an_unwrappable_wide_scene():
    # One intrinsically-wide scene (5 spread glyphs) has no columns to reflow;
    # the residual lever raises height so the aspect is still capped.
    slots = [{"id": c, "kind": "glyph", "style": {"glyph": "tablet"}} for c in "abcde"]
    attach = [{"child": c, "parent": p, "edge": "right", "offset": [260, 0]}
              for p, c in zip("abcd", "bcde")]
    fig = Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [
            {"id": "t", "role": "title", "height_frac": 0.1, "label": "T"},
            {"id": "row", "role": "scene_row", "height_frac": 0.9,
             "scenes": [{"id": "s", "slots": slots, "attach": attach}]},
        ],
    })
    assert _tier_wrap_map(fig, TIER_DEFAULT_PARAMS)["row"] == 1  # nothing to wrap
    w, h = tier_canvas(fig)
    assert w / h == pytest.approx(CAP, abs=1e-3)


# --- corpus promise + verifier health ----------------------------------------

@pytest.mark.parametrize(
    "path", sorted(CORPUS_DIR.glob("*.json")), ids=lambda p: p.stem)
def test_corpus_is_untouched_by_the_cap(path):
    # The cap is a guard for wider rows than the corpus carries: every member
    # stays at wrap=1 and already sits under the cap, so its bytes don't move.
    fig = Figure.model_validate(json.loads(path.read_text()))
    assert all(k == 1 for k in _tier_wrap_map(fig, TIER_DEFAULT_PARAMS).values())
    w, h = tier_canvas(fig)
    assert w / h <= CAP + 1e-6


def test_wrapped_figure_still_passes_all_three_verifiers(tmp_path):
    # A reflowed figure is still a well-formed figure — the wrap must not strand
    # an anchor or co-locate slots. Render + run the tier-aware verifiers (each
    # raises on failure).
    import warnings
    fig = _wide_chain(6)
    layout_tiers(fig)  # must not raise (anchors resolve in the grid)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = render_figure(fig, tmp_path / "wrapped.svg")
    assert out.exists() and out.stat().st_size > 0
    semantic_check(fig, out)
    legibility_check(out)
    convention_check(fig, out)
