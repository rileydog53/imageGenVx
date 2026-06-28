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
    SUBSCRIPT_SIZE_FACTOR,
    SUPERSCRIPT_SIZE_FACTOR,
    FitResult,
    centered_label,
    chemical_runs,
    estimate_text_width,
    fit_label,
    formula_text,
    has_superscript,
    label_for_fit,
    multiline_label,
    superscript_runs,
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


# ---------------------------------------------------------------------------
# Chemical-formula subscripts (chemical_runs + formula_text)
# ---------------------------------------------------------------------------

FORMULA_STYLE = dict(font_family="Helvetica, Arial, sans-serif", fill="#000")


def test_chemical_runs_subscripts_digits_after_a_letter():
    # H2SO4 → H, ₂, SO, ₄ — only the digit runs that follow a letter subscript.
    assert chemical_runs("H2SO4") == [
        ("H", False), ("2", True), ("SO", False), ("4", True)
    ]
    assert chemical_runs("CO2") == [("CO", False), ("2", True)]
    assert chemical_runs("Na2CO3") == [
        ("Na", False), ("2", True), ("CO", False), ("3", True)
    ]


def test_chemical_runs_leaves_locants_and_plain_text_on_baseline():
    # Leading/standalone numbers are locants/coefficients, never subscripts.
    assert chemical_runs("2-DG") == [("2-DG", False)]
    assert chemical_runs("NAD+") == [("NAD+", False)]
    assert chemical_runs("reflux") == [("reflux", False)]
    assert chemical_runs("100 °C") == [("100 °C", False)]


def test_chemical_runs_roundtrips():
    for s in ("H2SO4", "2-DG", "CO2 + H2O", "G6P", "CH3COOH", ""):
        assert "".join(seg for seg, _ in chemical_runs(s)) == s


def test_formula_text_plain_when_no_subscripts_is_a_flat_text():
    # No letter-then-digit → a plain <text>, no tspans, anchor preserved.
    el = formula_text("reflux", (10.0, 20.0), font_size=11, anchor="middle",
                      **FORMULA_STYLE)
    xml = el.tostring()
    assert "<tspan" not in xml
    assert 'text-anchor="middle"' in xml
    assert ">reflux<" in xml


def test_formula_text_emits_subscript_tspans():
    el = formula_text("H2SO4", (100.0, 20.0), font_size=12, anchor="middle",
                      **FORMULA_STYLE)
    xml = el.tostring()
    # One tspan per run after the leading baseline run (2, SO, 4) = 3 tspans.
    assert xml.count("<tspan") == 3
    # Subscript digits render smaller; the baseline run between them does not.
    assert f'font-size="{12 * SUBSCRIPT_SIZE_FACTOR}"' in xml
    # The whole formula text is recoverable from the rendered element.
    import xml.etree.ElementTree as ET
    assert "".join(ET.fromstring(xml).itertext()) == "H2SO4"


def test_formula_text_uses_start_anchor_for_subscripts_cairosvg_safe():
    # cairosvg only lays out multi-tspan text under text-anchor="start"; the
    # requested middle anchor is emulated by offsetting x, not by the attribute.
    el = formula_text("H2SO4", (100.0, 20.0), font_size=12, anchor="middle",
                      **FORMULA_STYLE)
    xml = el.tostring()
    assert 'text-anchor="middle"' not in xml
    # x is shifted left of the requested centre by ~half the text width.
    assert float(el.attribs["x"]) < 100.0


# ---------------------------------------------------------------------------
# Superscript charges / exponents (font-independent typesetting)
#
# The system font may lack the precomposed superscript glyphs (U+207B '⁻',
# U+00B2 '²', …) and render them as tofu boxes, so charge notation in mechanism
# labels is synthesized from base glyphs raised via tspans instead.
# ---------------------------------------------------------------------------

def test_superscript_runs_maps_precomposed_to_base_glyphs():
    # ⁻ → '-', ² → '2', ⁺ → '+', each as a raised 'super' run.
    assert superscript_runs("Nu⁻") == [("Nu", "base"), ("-", "super")]
    assert superscript_runs("Ca²⁺") == [("Ca", "base"), ("2+", "super")]


def test_superscript_runs_leaves_ascii_and_baseline_digits_alone():
    # No precomposed superscript → one base run (digits are NOT subscripted here,
    # so a protein name like "p53" and an ASCII charge "NAD+" are untouched).
    assert superscript_runs("p53") == [("p53", "base")]
    assert superscript_runs("NAD+") == [("NAD+", "base")]
    assert superscript_runs("reflux") == [("reflux", "base")]


def test_superscript_runs_roundtrips_with_glyph_substitution():
    for s in ("Nu⁻", "Ca²⁺", "e⁻ transfer", "x²", "R⁺ then OH⁻"):
        rebuilt = "".join(seg for seg, _ in superscript_runs(s))
        # base segments verbatim; superscripts swapped for their base glyph.
        assert "⁻" not in rebuilt and "²" not in rebuilt and "⁺" not in rebuilt


def test_has_superscript():
    assert has_superscript("Nu⁻")
    assert has_superscript("Ca²⁺")
    assert not has_superscript("NAD+")
    assert not has_superscript("p53")


def test_centered_label_superscript_emits_raised_tspan():
    el = centered_label("Nu⁻", 50.0, 20.0, STYLE)
    xml = el.tostring()
    assert xml.count("<tspan") == 1
    # raised run is smaller and lifts (negative dy); the precomposed glyph is gone.
    assert f'font-size="{11 * SUPERSCRIPT_SIZE_FACTOR}"' in xml
    assert "⁻" not in xml
    assert 'dy="-' in xml
    import xml.etree.ElementTree as ET
    assert "".join(ET.fromstring(xml).itertext()) == "Nu-"


def test_centered_label_plain_label_is_byte_identical():
    # No superscript → the exact pre-change centered_label element.
    a = centered_label("p53", 30.0, 15.0, STYLE).tostring()
    assert "<tspan" not in a and ">p53<" in a


def test_formula_text_handles_superscript_charge():
    el = formula_text("Ca²⁺", (100.0, 20.0), font_size=12, anchor="middle",
                      **FORMULA_STYLE)
    xml = el.tostring()
    assert "<tspan" in xml and "²" not in xml
    import xml.etree.ElementTree as ET
    assert "".join(ET.fromstring(xml).itertext()) == "Ca2+"
