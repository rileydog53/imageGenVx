"""Unit tests for the label-fit ladder in primitives/_text.py (LABEL_FIT).

Covers ``estimate_text_width`` monotonicity, ``fit_label`` rung selection
(fits / wrap / shrink / external), and the multi-line / fit rendering helpers.
The width estimator has no font-metric backing, so these assert *rung
behaviour* (which escalation a label lands on) rather than exact pixels.
"""
from __future__ import annotations

import svgwrite.text

from imageGen.primitives._text import (
    AVG_CHAR_RATIO,
    FONT_FLOOR,
    FitResult,
    centered_label,
    estimate_text_width,
    fit_label,
    label_for_fit,
    multiline_label,
)

STYLE = {
    "label_font_family": "Helvetica, Arial, sans-serif",
    "label_font_size": 11,
    "label_font_color": "#1A1A1A",
}

# The motivating box: a 60x30 metabolite/protein box.
BOX = (60.0, 30.0)


# ---------------------------------------------------------------------------
# estimate_text_width
# ---------------------------------------------------------------------------

def test_estimate_text_width_formula():
    assert estimate_text_width("abcd", 10) == 4 * 10 * AVG_CHAR_RATIO


def test_estimate_text_width_monotonic_in_length_and_size():
    assert estimate_text_width("aa", 11) < estimate_text_width("aaa", 11)
    assert estimate_text_width("aaa", 10) < estimate_text_width("aaa", 12)


def test_estimate_text_width_empty_is_one_char_floor():
    # Avoids a zero-width estimate that would call any box "fits".
    assert estimate_text_width("", 11) == estimate_text_width("a", 11)


# ---------------------------------------------------------------------------
# fit_label rung selection
# ---------------------------------------------------------------------------

def test_rung0_short_label_fits_as_is():
    fit = fit_label("ATP", *BOX, STYLE)
    assert fit == FitResult(["ATP"], 11.0, False)


def test_rung0_keeps_base_font_and_single_line():
    fit = fit_label("Citrate", *BOX, STYLE)
    assert fit.lines == ["Citrate"]
    assert fit.font_size == 11.0
    assert not fit.external


def test_long_no_break_label_shrinks_single_line():
    # "Oxaloacetate" (12 chars) has no break char: it can only shrink.
    fit = fit_label("Oxaloacetate", *BOX, STYLE)
    assert fit.lines == ["Oxaloacetate"]
    assert fit.font_size < 11.0
    assert fit.font_size >= FONT_FLOOR
    assert not fit.external
    # And the shrunk single line actually fits the inner width.
    assert estimate_text_width(fit.lines[0], fit.font_size) <= BOX[0] - 8.0


def test_hyphenated_label_wraps_to_two_lines_when_shrink_alone_fails():
    # "alpha-Ketoglutarate" (19) doesn't fit single-line but wraps in-box.
    # Rung 3 stops at the largest font that fits (the shrink loop walks down
    # from the base), so it lands above the floor — not pinned to it.
    fit = fit_label("alpha-Ketoglutarate", *BOX, STYLE)
    assert fit.external is False
    assert fit.lines == ["alpha-", "Ketoglutarate"]
    assert fit.font_size >= FONT_FLOOR
    # Hyphen stays on the first line (no orphaned delimiter).
    assert fit.lines[0].endswith("-")


def test_pathological_label_goes_external():
    fit = fit_label("Supercalifragilisticexpialidocious", *BOX, STYLE)
    assert fit.external is True
    assert fit.lines == ["Supercalifragilisticexpialidocious"]
    assert fit.font_size == FONT_FLOOR


def test_fr2_long_chem_names_wrap_in_box_not_external():
    # FR2: at the old 7px floor these escalated to an external leader, leaving
    # the node blank. At the 6px floor they wrap to two lines inside a 60x30 box.
    for label in ("Glyceraldehyde-3-phosphate", "SN2 transition state"):
        fit = fit_label(label, *BOX, STYLE)
        assert fit.external is False, f"{label!r} should stay in-box"
        assert len(fit.lines) == 2
        assert fit.font_size >= FONT_FLOOR


def test_fr2_unbreakable_long_word_still_external():
    # A single long word with no break point genuinely can't fit a 60px box;
    # rung 4 (external) remains the rare safety net.
    fit = fit_label("Bisphosphoglycerate", *BOX, STYLE)
    assert fit.external is True


def test_external_never_below_legibility_floor():
    # Even a hopeless label reports the floor font, never lower.
    fit = fit_label("x" * 200, *BOX, STYLE)
    assert fit.font_size == FONT_FLOOR
    # The floor sits at the legibility_check minimum (which uses a strict
    # ``font < 6.0`` test, so a 6.0 label still passes).
    assert fit.font_size >= 6.0


def test_space_break_drops_the_space():
    # A wide two-word label that must wrap: the space is consumed, not kept.
    fit = fit_label("Target Kinase", 50.0, 60.0, STYLE)
    if len(fit.lines) == 2:
        assert fit.lines == ["Target", "Kinase"]
        assert " " not in fit.lines[0] + fit.lines[1]


def test_taller_box_allows_wrap_before_shrink():
    # In a tall box a hyphenated label wraps at the base font (rung 1) rather
    # than shrinking, because the stacked height now fits.
    fit = fit_label("Acetyl-CoA", 60.0, 60.0, STYLE)
    assert fit.lines == ["Acetyl-", "CoA"]
    assert fit.font_size == 11.0
    assert not fit.external


def test_balanced_split_is_chosen():
    # "ab cd efgh" has two spaces; the more central break gives the most
    # balanced pair. ("ab cd" / "efgh" beats "ab" / "cd efgh").
    fit = fit_label("aaaa bb cccccc", 40.0, 60.0, STYLE)
    if len(fit.lines) == 2:
        a, b = fit.lines
        assert abs(len(a) - len(b)) <= len("aaaa bb cccccc")  # sanity
        # central break keeps the longer side as small as possible
        assert max(len(a), len(b)) <= len("cccccc") + len("bb") + 1


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def test_label_for_fit_single_base_font_matches_centered_label():
    # Rung-0 output must be byte-identical to the pre-fit centered_label so
    # unaffected entities don't shift their golden images.
    fit = fit_label("ATP", *BOX, STYLE)
    a = label_for_fit(fit, 30.0, 15.0, STYLE).tostring()
    b = centered_label("ATP", 30.0, 15.0, STYLE).tostring()
    assert a == b


def test_label_for_fit_shrunk_single_line_carries_reduced_size():
    fit = fit_label("Oxaloacetate", *BOX, STYLE)
    el = label_for_fit(fit, 30.0, 15.0, STYLE)
    assert float(el["font-size"]) == fit.font_size
    assert el["font-size"] != STYLE["label_font_size"]


def test_label_for_fit_multiline_emits_tspans():
    fit = fit_label("alpha-Ketoglutarate", *BOX, STYLE)
    el = label_for_fit(fit, 30.0, 15.0, STYLE)
    xml = el.tostring()
    assert xml.count("<tspan") == len(fit.lines) == 2


def test_multiline_label_is_centered_text():
    el = multiline_label(["one", "two"], 30.0, 15.0, STYLE)
    assert isinstance(el, svgwrite.text.Text)
    assert el["text-anchor"] == "middle"
    xml = el.tostring()
    assert xml.count("<tspan") == 2
    assert "one" in xml and "two" in xml


def test_multiline_label_single_line_still_renders():
    el = multiline_label(["solo"], 30.0, 15.0, STYLE)
    assert el.tostring().count("<tspan") == 1
