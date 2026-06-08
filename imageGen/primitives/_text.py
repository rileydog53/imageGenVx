"""Shared text-rendering helpers for primitive modules.

Promoted from ``proteins._centered_label`` (V2 / P3) so any primitive
module — and layout helpers such as ``label_placement`` — can build
centered text labels without coupling to ``proteins.py``.

The function is intentionally minimal: it wraps svgwrite's Text element
with the three standard centering attributes and honours the master-preset
``label_*`` style keys. All label styling in the codebase flows through
this single entry point so a preset change propagates everywhere.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import svgwrite.text


# ---------------------------------------------------------------------------
# Label-fit estimation (LABEL_FIT plan)
#
# Entity boxes are a fixed size per type (ENTITY_BBOX) and labels were rendered
# dead-center with no measurement, so any label longer than the box spilled past
# its border. These helpers give primitives a pragmatic way to fit text to the
# box: estimate the rendered width, then escalate through a fixed ladder
# (fit-as-is → wrap to 2 lines → shrink font → external label).
#
# There is no font-metric library at this stage (svgwrite has no measurement
# API), so width is approximated as ``n_chars * font_size * AVG_CHAR_RATIO``.
# The estimator is monotonic in both inputs; it is deliberately a hair generous
# so we under-fill rather than overflow.
# ---------------------------------------------------------------------------

AVG_CHAR_RATIO = 0.55     # em/char for the sans default (matches the plan)
# Smallest shrink size — set to the 6.0 legibility floor (``legibility_check``
# uses a strict ``font < 6.0`` test, so 6.0 still passes). FR2: long chemistry
# names like "Glyceraldehyde-3-phosphate" and "SN2 transition state" overflow a
# 60px box at the old 7px floor and escalated to an external leader, leaving the
# node visibly blank. At 6px they wrap to two lines and sit *inside* the box, so
# rung 4 (external) stays the rare safety net the plan intends. Lowering the
# floor only rescues labels that previously went external: the shrink loop still
# finds 7px (and any larger size) first, so every label that already fit at >=7px
# renders byte-identically.
FONT_FLOOR = 6.0
INNER_PAD = 4.0           # px — padding inside the box on each side
LINE_HEIGHT_RATIO = 1.15  # multiple of font size between stacked tspan baselines
_BREAK_CHARS = " /-"      # natural wrap points: space, slash, hyphen
_MIN_FRAGMENT = 3         # Bug 6: avoid orphaning a <3-char wrap fragment ("a-")


@dataclass(frozen=True)
class FitResult:
    """Outcome of fitting a label to a box.

    Attributes:
        lines:     The text split into render lines (1 line = no wrap).
        font_size: The font size (px) the lines should render at.
        external:  True when even the floor font overflows — the caller
                   should render the box without the label and place the
                   full text outside on a leader (rung 4).
    """
    lines: list[str]
    font_size: float
    external: bool


def estimate_text_width(text: str, font_size: float) -> float:
    """Estimate the rendered width (px) of ``text`` at ``font_size``.

    ``n_chars * font_size * AVG_CHAR_RATIO``. Used only to choose a fit rung;
    Phase 6 ``legibility_check`` validates the final output independently.
    """
    return max(1, len(text)) * font_size * AVG_CHAR_RATIO


# ---------------------------------------------------------------------------
# Chemical-formula text: numeric subscripts in reagent / condition strings.
#
# A flat <text> node renders "H2SO4" with full-size baseline digits — wrong on a
# publication-grade scheme. Stoichiometric subscripts in a formula are exactly
# the digit runs that immediately follow an element symbol (a letter), so that
# is the rule: a digit run is set as <tspan baseline-shift="sub"> only when the
# preceding character is a letter. Leading/standalone numbers stay on the
# baseline — locants and coefficients ("2-DG", "100 °C", "50%") are not
# subscripts. Shared by ``arrows.reaction_arrow`` and ``chemistry`` condition
# text so both render formulas identically.
# ---------------------------------------------------------------------------

SUBSCRIPT_SIZE_FACTOR = 0.75  # subscript digits render at 75% of the base size
SUBSCRIPT_DROP_FACTOR = 0.22  # subscript baseline drops 22% of the base size


def chemical_runs(text: str) -> list[tuple[str, bool]]:
    """Split *text* into ``(segment, is_subscript)`` runs by the formula rule.

    A digit run is flagged subscript only when the immediately preceding
    character is a letter (an element symbol), so ``"H2SO4"`` →
    ``[("H", False), ("2", True), ("SO", False), ("4", True)]`` while ``"2-DG"``
    stays a single baseline run. Concatenating every segment reproduces *text*.
    """
    runs: list[tuple[str, bool]] = []
    i, n = 0, len(text)
    while i < n:
        if text[i].isdigit() and i > 0 and text[i - 1].isalpha():
            j = i
            while j < n and text[j].isdigit():
                j += 1
            runs.append((text[i:j], True))
            i = j
        else:
            j = i + 1
            while j < n and not (text[j].isdigit() and text[j - 1].isalpha()):
                j += 1
            runs.append((text[i:j], False))
            i = j
    return runs


def formula_text(
    text: str,
    insert: tuple[float, float],
    *,
    font_family: str,
    font_size: float,
    fill: str,
    anchor: str = "middle",
) -> svgwrite.text.Text:
    """A ``<text>`` for *text* with chemical numeric subscripts rendered.

    When *text* has no subscript digits the result is a plain ``<text>`` node,
    byte-identical to a direct ``svgwrite.text.Text`` (so non-formula labels and
    existing goldens are unchanged). When it does, each run is a nested
    ``<tspan>``; subscript runs drop via a relative ``dy`` and a reduced font
    size, with the next baseline run carrying the inverse ``dy`` to return.

    Three deliberate rendering choices, all forced by cairosvg (the PNG/PDF
    rasteriser), which only lays out a multi-``<tspan>`` ``<text>`` correctly
    when it is ``text-anchor="start"``:

    * ``dy`` is used rather than ``baseline-shift`` (cairosvg mis-advances x
      after a ``baseline-shift`` tspan, overlapping the next glyph);
    * the requested ``anchor`` is *emulated* by pre-offsetting x and emitting a
      start-anchored element — ``middle``/``end`` directly on a multi-tspan
      element makes cairosvg overlap the runs;
    * the leading baseline run is the ``<text>`` body, not a first ``<tspan>``.

    The x offset uses :func:`estimate_text_width` (the same approximate metric
    the layout/legibility code uses), counting subscript runs at their reduced
    size, so a centred formula sits visually centred.
    """
    runs = chemical_runs(text)
    has_sub = any(sub for _seg, sub in runs)
    if not has_sub:
        t = svgwrite.text.Text(
            text, insert=insert, font_family=font_family,
            font_size=font_size, fill=fill,
        )
        t["text-anchor"] = anchor
        return t

    # Emulate the anchor with start positioning (see docstring).
    total_w = sum(
        estimate_text_width(
            seg, font_size * (SUBSCRIPT_SIZE_FACTOR if sub else 1.0)
        )
        for seg, sub in runs
    )
    ix, iy = insert
    if anchor == "middle":
        x0 = ix - total_w / 2.0
    elif anchor == "end":
        x0 = ix - total_w
    else:
        x0 = ix

    # Leading baseline run as the <text> body; remaining runs as tspans. ``dy``
    # is relative, so track the current vertical offset and emit the delta to
    # reach each run's target (drop for subscripts, 0 for baseline). debug off so
    # svgwrite's strict validator accepts the float font-size on the tspans.
    t = svgwrite.text.Text(
        runs[0][0], insert=(x0, iy), font_family=font_family,
        font_size=font_size, fill=fill,
    )
    t._parameter.debug = False
    drop = font_size * SUBSCRIPT_DROP_FACTOR
    current = 0.0
    for seg, sub in runs[1:]:
        target = drop if sub else 0.0
        span = svgwrite.text.TSpan(seg, dy=[target - current])
        if sub:
            span._parameter.debug = False
            span["font-size"] = font_size * SUBSCRIPT_SIZE_FACTOR
        t.add(span)
        current = target
    return t


def _best_two_line_split(label: str) -> Optional[tuple[str, str]]:
    """Split ``label`` into two balanced lines at the most central break point.

    Breaks on space, ``/`` or ``-``. A space is consumed (dropped); ``/`` and
    ``-`` stay on the first line so "Succinyl-CoA" → "Succinyl-" / "CoA" and a
    fragment is never orphaned from its delimiter. Returns the split whose two
    lines are most balanced (smallest longer side), or None when there is no
    usable break.

    Bug 6: among the available breaks, prefer those that leave *both* fragments
    at least ``_MIN_FRAGMENT`` chars, so a lopsided break like "a-Ketoglutarate"
    → "a-" / "Ketoglutarate" is skipped when a more balanced break exists. When
    every break is lopsided (e.g. the hyphen is the only break point), the guard
    falls back to the full candidate set so the label still wraps rather than
    escalating to an external leader.
    """
    candidates: list[tuple[str, str]] = []
    for i, ch in enumerate(label):
        if ch not in _BREAK_CHARS:
            continue
        if ch == " ":
            a, b = label[:i].rstrip(), label[i + 1:].lstrip()
        else:  # keep the delimiter on the first line
            a, b = label[:i + 1], label[i + 1:]
        if a and b:
            candidates.append((a, b))
    if not candidates:
        return None
    balanced = [
        ab for ab in candidates
        if len(ab[0]) >= _MIN_FRAGMENT and len(ab[1]) >= _MIN_FRAGMENT
    ]
    pool = balanced or candidates
    return min(pool, key=lambda ab: max(len(ab[0]), len(ab[1])))


def fit_label(
    label: str,
    box_w: float,
    box_h: float,
    style: dict,
    *,
    pad: float = INNER_PAD,
    floor: float = FONT_FLOOR,
) -> FitResult:
    """Fit ``label`` inside a ``box_w`` × ``box_h`` box via the escalation ladder.

    Rungs, in order, returning the first that fits:
      0. Fits as-is at the base font → single centered line.
      1. Wrap to 2 lines at a natural break → both lines fit width and the
         stacked height fits the box.
      2. Shrink the single line toward ``floor`` until it fits the width.
      3. Shrink the 2-line wrap toward ``floor`` until both lines + stacked
         height fit.
      4. None of the above → ``external=True`` (caller renders a leader label).

    Args:
        label:  The entity label text.
        box_w:  Box width in px.
        box_h:  Box height in px.
        style:  Merged style dict; ``label_font_size`` is the base size.
        pad:    Inner padding per side (default ``INNER_PAD``).
        floor:  Smallest shrink font (default ``FONT_FLOOR``).

    Returns:
        A ``FitResult``. Width comparisons use ``estimate_text_width``.
    """
    base = float(style.get("label_font_size", 11))
    inner_w = max(box_w - 2 * pad, 1.0)
    inner_h = max(box_h - 2 * pad, 1.0)

    def fits_w(text: str, fs: float) -> bool:
        return estimate_text_width(text, fs) <= inner_w

    def stack_fits_h(fs: float) -> bool:
        return 2 * fs * LINE_HEIGHT_RATIO <= inner_h

    # Rung 0 — fits as-is.
    if fits_w(label, base):
        return FitResult([label], base, False)

    split = _best_two_line_split(label)

    # Rung 1 — wrap to 2 lines at the base font.
    if split is not None and stack_fits_h(base):
        a, b = split
        if fits_w(a, base) and fits_w(b, base):
            return FitResult([a, b], base, False)

    # Rung 2 — shrink the single line toward the floor.
    fs = base
    while fs > floor:
        fs = max(floor, fs - 1.0)
        if fits_w(label, fs):
            return FitResult([label], fs, False)

    # Rung 3 — shrink the 2-line wrap toward the floor.
    if split is not None:
        a, b = split
        fs = base
        while fs >= floor:
            if stack_fits_h(fs) and fits_w(a, fs) and fits_w(b, fs):
                return FitResult([a, b], fs, False)
            if fs == floor:
                break
            fs = max(floor, fs - 1.0)

    # Rung 4 — external label on a leader.
    return FitResult([label], floor, True)


def centered_label(
    text: str,
    cx: float,
    cy: float,
    style: dict,
    *,
    weight: str = "normal",
    color: Optional[str] = None,
    size_override: Optional[float] = None,
) -> svgwrite.text.Text:
    """Build a horizontally + vertically centered SVG text element.

    Args:
        text:          The string to render.
        cx, cy:        Centre-point of the text element.
        style:         Merged style dict; must contain ``label_font_family``,
                       ``label_font_size``, and ``label_font_color``.
        weight:        CSS ``font-weight`` value; omitted when ``"normal"``.
        color:         Fill color override; defaults to ``style["label_font_color"]``.
        size_override: Font-size override in px; defaults to ``style["label_font_size"]``.

    Returns:
        An ``svgwrite.text.Text`` with ``text-anchor: middle`` and
        ``dominant-baseline: central`` so callers only need to supply the
        centre-point — no manual offset arithmetic required.
    """
    t = svgwrite.text.Text(
        text,
        insert=(cx, cy),
        font_family=style["label_font_family"],
        font_size=float(size_override or style["label_font_size"]),
        fill=color or style["label_font_color"],
    )
    t["text-anchor"] = "middle"
    t["dominant-baseline"] = "central"
    if weight != "normal":
        t["font-weight"] = weight
    return t


def multiline_label(
    lines: list[str],
    cx: float,
    cy: float,
    style: dict,
    *,
    weight: str = "normal",
    color: Optional[str] = None,
    size_override: Optional[float] = None,
) -> svgwrite.text.Text:
    """Build a centered multi-line label as stacked ``<tspan>`` rows.

    Each line is one ``<tspan>`` re-anchored at ``cx`` (so every row centers
    independently) and offset vertically so the whole block is centered on
    ``cy``. With a single line this is equivalent to ``centered_label`` but
    via a tspan; callers that want byte-identical single-line output should
    use ``label_for_fit`` which delegates to ``centered_label`` for one line.

    Args:
        lines:         The text rows, top to bottom.
        cx, cy:        Centre-point of the stacked block.
        style:         Merged style dict; same keys as ``centered_label``.
        weight:        CSS ``font-weight``; omitted when ``"normal"``.
        color:         Fill override; defaults to ``style["label_font_color"]``.
        size_override: Font-size override in px; defaults to the style size.
    """
    fs = float(size_override or style["label_font_size"])
    line_h = fs * LINE_HEIGHT_RATIO
    n = len(lines)
    t = svgwrite.text.Text(
        "",
        insert=(cx, cy),
        font_family=style["label_font_family"],
        font_size=fs,
        fill=color or style["label_font_color"],
    )
    t["text-anchor"] = "middle"
    t["dominant-baseline"] = "central"
    if weight != "normal":
        t["font-weight"] = weight
    first_dy = -(n - 1) / 2.0 * line_h
    for i, line in enumerate(lines):
        dy = first_dy if i == 0 else line_h
        t.add(svgwrite.text.TSpan(line, x=[cx], dy=[dy]))
    return t


def label_for_fit(
    fit: FitResult,
    cx: float,
    cy: float,
    style: dict,
    *,
    weight: str = "normal",
    color: Optional[str] = None,
    halo: bool = False,
) -> svgwrite.text.Text:
    """Render a ``FitResult`` as a centered label at (``cx``, ``cy``).

    A single line at the base font produces the exact ``centered_label``
    element the engine emitted before label-fitting existed, so unaffected
    entities stay byte-identical (golden-image safe). A shrunk single line
    passes the reduced size through; multiple lines render as stacked tspans.

    When ``halo=True`` the (single) text element is given a white stroke painted
    *behind* its fill (``paint-order: stroke``), forming a legibility halo for
    labels that cross a busy/overlapping background (e.g. a complex's two
    subunits + their borders). This stays one ``<text>`` element — not a
    duplicate — so the legibility audit still sees exactly one label. Off by
    default so every other entity is byte-identical. Halo color/width come from
    ``label_halo_color`` / ``label_halo_width`` (default white, ~22% of font).

    Callers must check ``fit.external`` first — an external result carries no
    in-box text and should not be passed here.
    """
    base = float(style.get("label_font_size", 11))
    if len(fit.lines) == 1:
        override = None if fit.font_size == base else fit.font_size
        t = centered_label(
            fit.lines[0], cx, cy, style,
            weight=weight, color=color, size_override=override,
        )
    else:
        t = multiline_label(
            fit.lines, cx, cy, style,
            weight=weight, color=color, size_override=fit.font_size,
        )
    if halo:
        halo_color = style.get("label_halo_color", "#FFFFFF")
        halo_width = float(
            style.get("label_halo_width", max(1.0, fit.font_size * 0.06))
        )
        halo_opacity = float(style.get("label_halo_opacity", 0.55))
        t["stroke"] = halo_color
        t["stroke-width"] = halo_width
        t["stroke-opacity"] = halo_opacity
        t["stroke-linejoin"] = "round"
        # paint-order isn't in svgwrite's attribute allowlist; disable this
        # element's validation (it is a valid SVG2 / CSS attribute) and set it so
        # the stroke renders behind the fill (a halo, not an outline over glyphs).
        t._parameter.debug = False
        t.attribs["paint-order"] = "stroke"
    return t
