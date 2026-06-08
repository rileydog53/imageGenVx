"""Figure-global anchor + rail registry (V3 scene-chassis keystone).

The current layout pipeline has no addressable coordinate identity: each
sub-engine bakes absolute numbers into ``LayoutEntry`` args and the resolved
positions are discarded after the call, so nothing downstream can ask "where did
atom O of the aspirin in cell 3 end up?". The scene chassis needs that to draw a
``SceneEdge`` from one slot's anchor to another, and a cross-cell ``TierEdge``
that rides a shared rail.

This module is that missing piece. Slot primitives return an
:class:`~imageGen.primitives._anchors.AnchoredGroup`; the layout layer publishes
those local anchors here, offset by the cell/scene placement, into one
figure-global table keyed by ``"scoped_id.anchor"``. Rails publish a single
scalar on one axis. Edge endpoints are then resolved into absolute points so a
single arrow ``LayoutEntry`` can be emitted with baked coords and ``position=(0,
0)`` — exactly what ``_write_svg`` already knows how to draw.

Reference grammar (resolved by :meth:`AnchorRegistry.resolve`):
    ``"<scoped_id>.<anchor>"``  e.g. ``"s1.aspirin.carbonyl_C"`` — a point.
    ``"rail:<name>"``           e.g. ``"rail:midline"`` — a line, only usable to
                                clamp the cross-axis of another point (a line is
                                not a point on its own; see :meth:`resolve_on_rail`).

Determinism: this is a plain insertion-ordered table; no randomness. Ids must be
unique (the schema forbids ``.`` / ``__`` in scene/slot/rail ids so the
``"scoped.anchor"`` grammar and the compositor's ``__`` id-join never collide).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from imageGen.primitives._anchors import AnchoredGroup


def _inset_toward(
    a: tuple[float, float], b: tuple[float, float], dist: float
) -> tuple[float, float]:
    """Move point *a* toward *b* by *dist* pixels (no-op if dist<=0 or a==b).

    Used to pull an edge endpoint a few pixels short of the atom/glyph it
    references so the line or arrowhead does not render *inside* that glyph.
    """
    if dist <= 0:
        return a
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy)
    if length == 0:
        return a
    return (ax + dx / length * dist, ay + dy / length * dist)


@dataclass(frozen=True)
class Rail:
    """A named reference line resolved to one absolute scalar on its cross axis.

    axis='y' is a horizontal line at vertical position ``value`` (a midline);
    axis='x' is a vertical line at horizontal position ``value`` (a gutter).
    """

    name: str
    axis: str  # "x" or "y"
    value: float


class AnchorRegistry:
    """Figure-global table of resolved anchor points and rails.

    Anchors are stored absolute (already offset into figure space). Build one per
    figure render; publish every placed slot and declared rail; then resolve edge
    endpoints against it.
    """

    def __init__(self) -> None:
        self._anchors: dict[str, tuple[float, float]] = {}
        self._rails: dict[str, Rail] = {}

    # -- publish -----------------------------------------------------------
    def publish(
        self,
        scoped_id: str,
        anchors: dict[str, tuple[float, float]],
        offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        """Record *anchors* (local frame) under ``scoped_id``, shifted by *offset*.

        *offset* is the cell/scene placement — the same translate the renderer
        applies to the slot's Group — so the stored points are figure-absolute.
        """
        dx, dy = offset
        for name, (x, y) in anchors.items():
            self._anchors[f"{scoped_id}.{name}"] = (x + dx, y + dy)

    def publish_group(
        self,
        scoped_id: str,
        anchored: AnchoredGroup,
        offset: tuple[float, float] = (0.0, 0.0),
    ) -> None:
        """Convenience: publish an :class:`AnchoredGroup`'s anchors directly."""
        self.publish(scoped_id, anchored.anchors, offset)

    def publish_rail(self, name: str, axis: str, value: float) -> None:
        """Record a rail resolved to absolute *value* on its cross *axis*."""
        if axis not in ("x", "y"):
            raise ValueError(f"rail axis must be 'x' or 'y', got {axis!r}")
        self._rails[name] = Rail(name=name, axis=axis, value=value)

    # -- query -------------------------------------------------------------
    def has(self, ref: str) -> bool:
        """True if *ref* resolves (a known anchor or ``rail:<name>``)."""
        if ref.startswith("rail:"):
            return ref[len("rail:"):] in self._rails
        return ref in self._anchors

    def rail(self, name: str) -> Rail:
        """Return the named :class:`Rail` or raise KeyError-as-ValueError."""
        if name not in self._rails:
            raise ValueError(f"unknown rail {name!r} (known: {sorted(self._rails)})")
        return self._rails[name]

    def resolve(self, ref: str) -> tuple[float, float]:
        """Resolve a ``"scoped_id.anchor"`` reference to an absolute point.

        Raises:
            ValueError: *ref* is unknown, or is a bare ``rail:`` reference (a rail
                is a line, not a point — use :meth:`resolve_on_rail`).
        """
        if ref.startswith("rail:"):
            raise ValueError(
                f"{ref!r} is a rail (a line); resolve it against a point via "
                f"resolve_on_rail(point_ref, rail_name)"
            )
        if ref not in self._anchors:
            raise ValueError(
                f"unknown anchor {ref!r} (known: {sorted(self._anchors)})"
            )
        return self._anchors[ref]

    def resolve_on_rail(self, ref: str, rail_name: str) -> tuple[float, float]:
        """Resolve *ref* to a point, then clamp its cross-axis to *rail_name*.

        A horizontal transition arrow keeps each endpoint's x from its slot anchor
        but forces y onto the shared midline so the arrow is perfectly level.
        """
        x, y = self.resolve(ref)
        r = self.rail(rail_name)
        return (x, r.value) if r.axis == "y" else (r.value, y)

    def resolve_edge(
        self,
        from_ref: str,
        to_ref: str,
        *,
        from_standoff: float = 0.0,
        to_standoff: float = 0.0,
        on_rail: str | None = None,
    ) -> tuple[tuple[float, float], tuple[float, float]]:
        """Resolve both endpoints of an edge into draw-ready points.

        Returns ``(p0, p1)`` where each point is pulled toward the other by its
        standoff so the rendered line/arrowhead clears the atom or glyph it
        references — endpoint overlap avoidance. An arrowhead with a ``to_standoff``
        of ~12px points *at* the target atom from a few pixels away instead of
        landing inside it. When *on_rail* is given both endpoints are first clamped
        to that rail (a level transition arrow), then the standoff is applied along
        the clamped line.

        Note: this avoids *endpoint* overlap only. Full path-level routing that
        steers the shaft around intervening glyphs is the parked V3-L1 (orthogonal
        / curved routing with entity avoidance).
        """
        if on_rail is not None:
            p0 = self.resolve_on_rail(from_ref, on_rail)
            p1 = self.resolve_on_rail(to_ref, on_rail)
        else:
            p0 = self.resolve(from_ref)
            p1 = self.resolve(to_ref)
        return _inset_toward(p0, p1, from_standoff), _inset_toward(p1, p0, to_standoff)
