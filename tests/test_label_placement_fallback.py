"""Tests for the v2 relax-and-retry label-placement fallback ladder.

Covers each rung of `_place_with_fallback` (full → shrink → nudge → overlap),
the `data-overlap="true"` SVG marker, and that `legibility_check` tolerates a
deliberately-overlapping flagged label. Geometry is exercised through direct
`_place_with_fallback` calls with hand-built `occupied` boxes so the
collision math is precise and not coupled to entity-primitive sizing.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import svgwrite

from imageGen.layout.label_placement import (
    _FONT_SHRINK_FACTOR,
    LabelRequest,
    _label_primitive,
    _place_with_fallback,
    place_labels,
)
from imageGen.layout.types import LayoutEntry
from imageGen.primitives import proteins
from imageGen.verify.legibility_check import LegibilityCheckError, legibility_check

_GAP = 4.0
_MARGIN = 1.0
_FONT = 11.0


# ---------------------------------------------------------------------------
# Ladder rungs
# ---------------------------------------------------------------------------


def test_pass1_full_size_when_clear():
    """No obstruction → label lands at full font, no overlap flag."""
    req = LabelRequest(text="AAAA", anchor=(100, 100), anchor_size=(2, 2),
                       priority=("right",))
    _center, _bbox, font_used, overlap = _place_with_fallback(
        req, [], _GAP, _MARGIN, _FONT
    )
    assert font_used == _FONT
    assert overlap is False


def test_pass2_shrinks_font_when_full_blocked():
    """A blocker that clips the full-size slot but clears the shrunk slot
    forces a one-step font shrink (Pass 2)."""
    req = LabelRequest(text="AAAA", anchor=(100, 100), anchor_size=(2, 2),
                       priority=("right",))
    # Full 'right' bbox reaches x≈131.4; shrunk reaches x≈127.4. A blocker at
    # x≥130 collides with full but not shrunk.
    occupied = [(130.0, 90.0, 200.0, 110.0)]
    _center, _bbox, font_used, overlap = _place_with_fallback(
        req, occupied, _GAP, _MARGIN, _FONT
    )
    assert overlap is False
    assert font_used == pytest.approx(_FONT * _FONT_SHRINK_FACTOR)


def test_pass3_nudges_anchor_when_shrink_blocked():
    """A blocker covering both the full and shrunk in-place slot, but leaving
    a sliver clear 8px to one side, is escaped by an anchor nudge (Pass 3)."""
    req = LabelRequest(text="X", anchor=(100, 100), anchor_size=(2, 2),
                       priority=("right",))
    # Shrunk in-place 'right' bbox spans x≈[105,110.6]; this blocker overlaps
    # it, but a -8px x-nudge slides the label left to x≈[97,102.6], clearing.
    occupied = [(109.0, 94.0, 130.0, 106.0)]
    center, _bbox, font_used, overlap = _place_with_fallback(
        req, occupied, _GAP, _MARGIN, _FONT
    )
    assert overlap is False
    assert font_used == pytest.approx(_FONT * _FONT_SHRINK_FACTOR)
    # The rescuing nudge was to the left of the in-place 'right' slot.
    assert center[0] < 107.0


def test_pass3_5_large_nudge_escapes_wide_node(tmp_path=None):
    """A blocker that covers small nudges (±8 px) but clears at ±24 px is
    escaped by the L24 large-nudge rung (Pass 3.5) without overlap."""
    req = LabelRequest(text="at Ser", anchor=(200, 200), anchor_size=(2, 2),
                       priority=("above",))
    # Block the in-place and small-nudge slots: a rect from y=170 to y=210
    # that overlaps "above" at y≈189 and the ±8 nudge variants (y≈181–197),
    # but leaves the y≈176 region free for the ±24 nudge.
    occupied = [(150.0, 170.0, 260.0, 210.0)]
    center, _bbox, font_used, overlap = _place_with_fallback(
        req, occupied, _GAP, _MARGIN, _FONT
    )
    assert overlap is False
    # The center must be above the blocker (y < 170) — large nudge escaped it.
    assert center[1] < 170.0


def test_pass4_last_resort_overlap_when_boxed_in():
    """Everything around the anchor is occupied → last-resort placement with
    the overlap flag set (Pass 4)."""
    req = LabelRequest(text="boxed", anchor=(300, 300), anchor_size=(2, 2))
    occupied = [(0.0, 0.0, 600.0, 600.0)]  # the whole region is blocked
    _center, _bbox, font_used, overlap = _place_with_fallback(
        req, occupied, _GAP, _MARGIN, _FONT
    )
    assert overlap is True
    assert font_used == _FONT  # last resort renders at full size


# ---------------------------------------------------------------------------
# place_labels integration — overlap flag + warning
# ---------------------------------------------------------------------------


def test_place_labels_emits_overlap_kwarg_and_warns():
    """A boxed-in request placed leniently carries overlap=True and warns.

    L24 added _LARGE_NUDGES (±24, ±40 px) to the fallback ladder.  Passing a
    near-zero canvas forces every candidate position out-of-bounds so even the
    large-nudge rung cannot escape and the last-resort overlap path fires.
    """
    blocker = LayoutEntry(
        primitive=proteins.generic_protein,
        args=("Blk", (300, 300)),
        kwargs={},
        position=(0.0, 0.0),
    )
    req = LabelRequest(text="boxed", anchor=(300, 300), anchor_size=(2, 2))
    # canvas=(1, 1): anchor at (300, 300) is far outside [0,1]×[0,1], so
    # every candidate bbox is filtered as out-of-bounds → last-resort overlap.
    with pytest.warns(UserWarning, match="overlap"):
        out = place_labels([blocker], [req], canvas=(1.0, 1.0))
    label = next(e for e in out if e.primitive is _label_primitive)
    assert label.kwargs.get("overlap") is True


def test_strict_labels_raises_on_out_of_bounds_canvas():
    """strict_labels=True raises when every candidate is out of bounds."""
    from imageGen.layout.label_placement import LabelPlacementError
    blocker = LayoutEntry(
        primitive=proteins.generic_protein,
        args=("Blk", (300, 300)),
        kwargs={},
        position=(0.0, 0.0),
    )
    req = LabelRequest(text="label", anchor=(300, 300), anchor_size=(2, 2))
    with pytest.raises(LabelPlacementError):
        place_labels([blocker], [req], canvas=(1.0, 1.0), strict_labels=True)


# ---------------------------------------------------------------------------
# data-overlap SVG marker + legibility tolerance
# ---------------------------------------------------------------------------


def _strip(tag: str) -> str:
    return tag.split("}")[-1]


def test_label_primitive_emits_data_overlap_attribute():
    """_label_primitive(overlap=True) tags the rendered <text> with data-overlap."""
    group = _label_primitive("hi", (50.0, 50.0), overlap=True)
    dwg = svgwrite.Drawing(size=(100, 100), debug=False)
    dwg.add(group)
    xml = dwg.tostring()
    root = ET.fromstring(xml)
    texts = [el for el in root.iter() if _strip(el.tag) == "text"]
    assert texts and texts[0].get("data-overlap") == "true"


def test_label_primitive_no_marker_by_default():
    """Without overlap=True, no data-overlap attribute is emitted."""
    group = _label_primitive("hi", (50.0, 50.0))
    dwg = svgwrite.Drawing(size=(100, 100), debug=False)
    dwg.add(group)
    root = ET.fromstring(dwg.tostring())
    texts = [el for el in root.iter() if _strip(el.tag) == "text"]
    assert texts and texts[0].get("data-overlap") is None


def _write_two_label_svg(path: Path, *, flag_second: bool) -> None:
    """Write a minimal SVG with two overlapping <text> labels."""
    dwg = svgwrite.Drawing(str(path), size=(200, 200), debug=False)
    dwg.add(_label_primitive("alpha", (100.0, 100.0)))
    dwg.add(_label_primitive("alpha", (104.0, 102.0), overlap=flag_second))
    dwg.save()


def test_legibility_raises_on_unflagged_overlap(tmp_path):
    """Two genuinely-overlapping unflagged labels still raise."""
    svg = tmp_path / "unflagged.svg"
    _write_two_label_svg(svg, flag_second=False)
    with pytest.raises(LegibilityCheckError):
        legibility_check(svg)


def test_legibility_tolerates_flagged_overlap(tmp_path):
    """The same overlap is tolerated when one label carries data-overlap."""
    svg = tmp_path / "flagged.svg"
    _write_two_label_svg(svg, flag_second=True)
    result = legibility_check(svg)  # must not raise
    assert result is not None


# ---------------------------------------------------------------------------
# Leader-eligible rung: nearest-whitespace ring search (dim-2, second half)
# ---------------------------------------------------------------------------


def test_leader_request_parks_in_whitespace_instead_of_overlapping():
    """A `leader=True` request whose every adjacent + nudge slot is blocked
    parks in the nearest open whitespace (ring search) rather than landing on
    top of its anchor — the caller draws a leader line to restore the link."""
    import math

    # One big blocker covers the anchor and every nudge offset (±8/±24/±40);
    # only space beyond the inner ring radius is clear.
    occupied = [(150.0, 150.0, 250.0, 250.0)]
    req = LabelRequest(text="X", anchor=(200, 200), anchor_size=(0, 0),
                       priority=("below", "above", "right", "left"), leader=True)
    center, _bbox, _font, overlap = _place_with_fallback(
        req, occupied, _GAP, _MARGIN, _FONT
    )
    assert overlap is False, "leader request should find clear whitespace, not overlap"
    # Landed well outside the blocked core (in the widening ring), not snug.
    assert math.hypot(center[0] - 200, center[1] - 200) > 50.0


def test_non_leader_request_still_overlaps_in_same_scenario():
    """Identical scenario without `leader` falls to the last-resort overlap rung —
    proving the ring search is gated on the flag and the v1 ladder is unchanged."""
    occupied = [(150.0, 150.0, 250.0, 250.0)]
    req = LabelRequest(text="X", anchor=(200, 200), anchor_size=(0, 0),
                       priority=("below", "above", "right", "left"))
    _center, _bbox, _font, overlap = _place_with_fallback(
        req, occupied, _GAP, _MARGIN, _FONT
    )
    assert overlap is True


# ---------------------------------------------------------------------------
# Tether clearance: a leader label is not parked where its hairline would slice
# through other ink — the dim-2 'leader crosses the caption text' residual.
# ---------------------------------------------------------------------------

# Tall anchor (a residue chain) + a caption-like box centred straight below it:
# the snug "below" slot clears *past* the caption, but a vertical tether from the
# anchor to it would run through the caption.
_TETHER_ANCHOR = (100.0, 100.0)
_TETHER_ANCHOR_SIZE = (10.0, 80.0)
_CAPTION_BOX = (60.0, 120.0, 140.0, 140.0)  # centred under the anchor


def test_leader_label_skips_tether_crossing_slot():
    """A leader label rejects the below-the-caption slot (clear box, crossing
    tether) and takes the next priority whose tether stays off the caption."""
    from imageGen.layout.label_placement import _segment_intersects_bbox

    req = LabelRequest(text="AAAA", anchor=_TETHER_ANCHOR,
                       anchor_size=_TETHER_ANCHOR_SIZE,
                       priority=("below", "right", "above", "left"), leader=True)
    center, _bbox, _font, overlap = _place_with_fallback(
        req, [_CAPTION_BOX], _GAP, _MARGIN, _FONT
    )
    assert overlap is False
    # The straight tether back to the anchor clears the caption box.
    assert not _segment_intersects_bbox(_TETHER_ANCHOR, center, _CAPTION_BOX)
    # It went to the side, not straight down past the caption.
    assert center[1] < _CAPTION_BOX[1], "label should not sit below the caption"


def test_non_leader_label_keeps_tether_crossing_slot():
    """Same geometry without `leader`: the snug 'below' slot wins even though its
    tether crosses the caption — the tether gate is leader-only, v1 ladder intact."""
    from imageGen.layout.label_placement import _segment_intersects_bbox

    req = LabelRequest(text="AAAA", anchor=_TETHER_ANCHOR,
                       anchor_size=_TETHER_ANCHOR_SIZE,
                       priority=("below", "right", "above", "left"))
    center, _bbox, _font, overlap = _place_with_fallback(
        req, [_CAPTION_BOX], _GAP, _MARGIN, _FONT
    )
    assert overlap is False
    # Lands straight below, past the caption — its tether crosses (the old defect).
    assert center[1] > _CAPTION_BOX[3]
    assert _segment_intersects_bbox(_TETHER_ANCHOR, center, _CAPTION_BOX)
