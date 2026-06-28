"""Superscript charges render font-independently through the tier pipeline.

LIMITATIONS "Superscript / special-glyph coverage": the system font may lack the
precomposed superscript glyphs (U+207B '⁻', U+00B2 '²', …), so a mechanism label
like "Nu⁻" / "Ca²⁺" rendered as a tofu box. The engine now typesets superscripts
from base glyphs raised via tspans, so the precomposed code point never reaches
the font. These pin that end-to-end for both tier label paths (title/caption text
via `_text_group` and scene/slot labels via `centered_label`).
"""
from __future__ import annotations

import warnings

from imageGen.ir import Figure
from imageGen.render.compositor import render_figure


def _charge_figure() -> Figure:
    return Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [
            {"id": "t", "role": "title", "height_frac": 0.16,
             "label": "Hydroxide Nu⁻ attacks", "subtitle": "forms Ca²⁺"},
            {"id": "row", "role": "scene_row", "height_frac": 0.84, "scenes": [
                {"id": "s1", "badge": "1", "label": "nucleophile Nu⁻",
                 "slots": [{"id": "m", "kind": "molecule", "label": "OH⁻",
                            "style": {"smiles": "[OH-]"}}]},
            ]},
        ],
    })


def test_superscript_labels_emit_tspans_and_no_precomposed_glyph(tmp_path):
    fig = _charge_figure()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = render_figure(fig, tmp_path / "charges.svg")
    svg = out.read_text()
    # The precomposed superscript code points must NOT survive into the output
    # (they would be tofu on a font that lacks them) — they are synthesized.
    for ch in ("⁻", "²", "⁺"):
        assert ch not in svg, f"precomposed {ch!r} leaked into the SVG"
    # Both the title-text path and the centered scene/slot label path synthesize
    # via raised tspans, so the figure carries several.
    assert svg.count("<tspan") >= 3
    # The charge is still present as its base glyph.
    assert ">-<" in svg or '>-</tspan' in svg.replace(" ", "")


def test_plain_tier_figure_has_no_synthesized_tspans(tmp_path):
    # A figure with no superscript keeps the byte-identical flat-text path:
    # no spurious tspans appear from the superscript machinery.
    fig = Figure.model_validate({
        "archetype": "mechanism_cartoon",
        "tiers": [
            {"id": "t", "role": "title", "height_frac": 0.2, "label": "p53 pathway"},
            {"id": "row", "role": "scene_row", "height_frac": 0.8, "scenes": [
                {"id": "s1", "badge": "1", "label": "step one",
                 "slots": [{"id": "m", "kind": "molecule", "label": "ATP",
                            "style": {"smiles": "C"}}]},
            ]},
        ],
    })
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        out = render_figure(fig, tmp_path / "plain.svg")
    svg = out.read_text()
    # "p53" must not be mis-subscripted, and the title/labels stay flat text.
    assert "p53" in svg
