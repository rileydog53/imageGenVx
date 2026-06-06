"""Action-potential voltage trace (FR10).

Pins:
  1. voltage_trace returns a Group whose first shape is a <path> (the trace),
     matching its convention_check registration; axes + threshold render.
  2. The primitive is reachable via style.primitive="voltage_trace" and is
     registered in PRIMITIVE_REGISTRY / PRIMITIVE_TO_BBOX / _PRIMITIVE_SHAPE.
  3. The rendered figure passes all three verifiers (no overlap / off-canvas).
"""
from __future__ import annotations

import re

from imageGen.ir import builder as B
from imageGen.layout._geom import PRIMITIVE_REGISTRY, PRIMITIVE_TO_BBOX
from imageGen.primitives import glyphs
from imageGen.render.compositor import render_figure


def _first_shape_tag(group) -> str | None:
    svg = group.tostring()
    m = re.search(r"<(path|rect|polygon|ellipse|circle|polyline)\b", svg)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Primitive
# ---------------------------------------------------------------------------


def test_voltage_trace_returns_group_with_path_first():
    g = glyphs.voltage_trace("Vm", (100.0, 100.0))
    svg = g.tostring()
    assert _first_shape_tag(g) == "path"   # matches _PRIMITIVE_SHAPE registration
    assert "Vm" in svg                      # entity label
    assert "mV" in svg and "ms" in svg      # axis units
    assert "threshold" in svg               # default phases annotation


def test_voltage_trace_phases_toggle():
    assert "threshold" not in glyphs.voltage_trace("Vm", (100.0, 100.0), phases=False).tostring()


def test_voltage_trace_registered_everywhere():
    assert PRIMITIVE_REGISTRY["voltage_trace"] is glyphs.voltage_trace
    assert PRIMITIVE_TO_BBOX[glyphs.voltage_trace] == (150.0, 90.0)
    from imageGen.verify.convention_check import _PRIMITIVE_SHAPE
    assert _PRIMITIVE_SHAPE[glyphs.voltage_trace] == "path"


# ---------------------------------------------------------------------------
# Render + verifiers
# ---------------------------------------------------------------------------


def _vt_figure():
    return B.build(
        archetype="cellular_schematic", title="AP",
        entities=[("ap", "generic", "Membrane potential", None, "voltage_trace")],
        relations=[],
    )


def test_voltage_trace_figure_passes_all_verifiers(tmp_path):
    from imageGen.verify.convention_check import convention_check
    from imageGen.verify.legibility_check import legibility_check
    from imageGen.verify.semantic_check import semantic_check

    ir = _vt_figure()
    out = tmp_path / "ap.svg"
    render_figure(ir, out)
    semantic_check(ir, out)
    convention_check(ir, out)
    legibility_check(out)  # no overlap / off-canvas raise
