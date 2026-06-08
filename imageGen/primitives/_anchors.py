"""Anchor-return protocol for scene-graph primitives (V3 keystone).

Today every primitive returns a bare ``svgwrite.container.Group`` whose geometry
is baked in and opaque: a caller cannot ask "where did the carbonyl oxygen
land?". The V3 scene chassis needs exactly that. A ``SceneEdge`` draws a dashed
H-bond from ``ser530.terminal_O`` to ``aspirin.carbonyl_C``; resolving those
endpoints into coordinates means the primitive must publish named points in its
own local frame.

This module defines the small dataclass contract the primitive layer and the
layout layer talk through, following the project rule "decouple via protocols,
not imports" (cf. ``MembraneCurve.anchor_at`` in ``membranes.py``). The contract
lives under ``primitives/`` so the established ``layout -> primitives`` import
direction is preserved — layout consumes ``AnchoredGroup``; primitives never
import layout.

An anchor-aware primitive returns an :class:`AnchoredGroup`: the Group exactly as
before, plus ``{anchor_name: (x, y)}`` in the Group's LOCAL coordinate frame
(i.e. as the content renders when the Group's origin sits at ``(0, 0)``). The
layout layer offsets those points into figure-global space and resolves edge
references against them via the ``AnchorRegistry`` in ``layout/anchors.py``.

Design notes / future-phase coupling:
- Anchors are LOCAL, not absolute, so an ``AnchoredGroup`` is position-independent
  and reusable wherever the layout drops it (mirrors how every chemistry Group is
  overlay-composable). The single source of absolute truth is the registry.
- ``AnchoredGroup`` is intentionally a plain value object (frozen dataclass) with
  no svgwrite behaviour beyond carrying the Group — so a primitive can return it
  and a non-anchor-aware caller can still ``.group`` it and ignore anchors.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import svgwrite.container


@dataclass(frozen=True)
class AnchoredGroup:
    """A rendered primitive plus its named anchor points (local frame).

    Attributes:
        group: The svgwrite Group, identical to what a non-anchored primitive
            would return — drop it on a Drawing as usual.
        anchors: ``{name: (x, y)}`` in the Group's local coordinate frame
            (pre-placement). Names are primitive-defined (e.g. atom-map numbers
            for molecules, ``cavity_top`` for a future protein blob).
    """

    group: svgwrite.container.Group
    anchors: dict[str, tuple[float, float]] = field(default_factory=dict)

    def shifted(self, dx: float, dy: float) -> dict[str, tuple[float, float]]:
        """Return the anchors translated by ``(dx, dy)``.

        Local frame -> parent frame: the layout layer passes the cell/scene
        placement offset so anchors land in the same space the renderer will
        translate the Group into. Returns a new dict; ``self`` is unchanged.
        """
        return {name: (x + dx, y + dy) for name, (x, y) in self.anchors.items()}
