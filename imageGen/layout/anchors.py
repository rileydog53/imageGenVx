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

import contextlib
import copy
import math
from collections.abc import Iterable, Iterator
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
        # P0a.4: when a ``layer()`` is open these hold buffered writes that
        # resolve* reads on top of the base; they are None when no layer is open.
        self._overlay_anchors: dict[str, tuple[float, float]] | None = None
        self._overlay_rails: dict[str, Rail] | None = None

    # -- snapshot / overlay (P0a.4) ---------------------------------------
    def copy(self) -> "AnchorRegistry":
        """Return an independent deep copy of the *committed* registry.

        Copies the base ``_anchors`` / ``_rails`` only (not any open overlay), so
        a solver can snapshot a known-good state and rebuild from it. Mutating the
        clone never touches the original.
        """
        clone = AnchorRegistry()
        clone._anchors = copy.deepcopy(self._anchors)
        clone._rails = copy.deepcopy(self._rails)
        return clone

    @contextlib.contextmanager
    def layer(self, *, commit: bool = True) -> Iterator["AnchorRegistry"]:
        """Open a write overlay: ``publish*`` buffers, ``resolve*`` reads overlay-then-base.

        On clean exit the overlay is merged into the base (when ``commit``); on an
        exception — or ``commit=False`` — it is dropped, leaving the base exactly
        as it was. Lets a placement solver try a tentative set of publishes and
        roll them back if the attempt fails. Not re-entrant.
        """
        if self._overlay_anchors is not None:
            raise RuntimeError("AnchorRegistry.layer() is not re-entrant")
        self._overlay_anchors, self._overlay_rails = {}, {}
        merged = True
        try:
            yield self
        except BaseException:
            merged = False
            raise
        finally:
            overlay_a, overlay_r = self._overlay_anchors, self._overlay_rails
            self._overlay_anchors = self._overlay_rails = None
            if merged and commit:
                self._anchors.update(overlay_a)
                self._rails.update(overlay_r)

    def _write_anchor(self, key: str, value: tuple[float, float]) -> None:
        target = self._anchors if self._overlay_anchors is None else self._overlay_anchors
        target[key] = value

    def _write_rail(self, rail: Rail) -> None:
        target = self._rails if self._overlay_rails is None else self._overlay_rails
        target[rail.name] = rail

    def _lookup_anchor(self, key: str) -> tuple[float, float] | None:
        if self._overlay_anchors is not None and key in self._overlay_anchors:
            return self._overlay_anchors[key]
        return self._anchors.get(key)

    def _lookup_rail(self, name: str) -> Rail | None:
        if self._overlay_rails is not None and name in self._overlay_rails:
            return self._overlay_rails[name]
        return self._rails.get(name)

    def _known_anchor_keys(self) -> Iterable[str]:
        if self._overlay_anchors is None:
            return self._anchors.keys()
        return self._anchors.keys() | self._overlay_anchors.keys()

    def _known_rail_keys(self) -> Iterable[str]:
        if self._overlay_rails is None:
            return self._rails.keys()
        return self._rails.keys() | self._overlay_rails.keys()

    def validate_refs(self, refs: Iterable[str]) -> list[str]:
        """Return the subset of *refs* that do NOT resolve, without raising (P0a.5).

        Lets a caller aggregate every unresolved endpoint into one error instead
        of dying on the first typo. A ``"rail:<name>"`` ref counts as resolved
        when that rail is declared.
        """
        return [r for r in refs if not self.has(r)]

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
            self._write_anchor(f"{scoped_id}.{name}", (x + dx, y + dy))

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
        self._write_rail(Rail(name=name, axis=axis, value=value))

    # -- query -------------------------------------------------------------
    def has(self, ref: str) -> bool:
        """True if *ref* resolves (a known anchor or ``rail:<name>``)."""
        if ref.startswith("rail:"):
            return self._lookup_rail(ref[len("rail:"):]) is not None
        return self._lookup_anchor(ref) is not None

    def rail(self, name: str) -> Rail:
        """Return the named :class:`Rail` or raise KeyError-as-ValueError."""
        r = self._lookup_rail(name)
        if r is None:
            raise ValueError(
                f"unknown rail {name!r} (known: {sorted(self._known_rail_keys())})"
            )
        return r

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
        point = self._lookup_anchor(ref)
        if point is None:
            raise ValueError(
                f"unknown anchor {ref!r} (known: {sorted(self._known_anchor_keys())})"
            )
        return point

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
        # Clamp the standoffs so they never cross past each other on a short edge
        # (which would draw the segment / arrowhead reversed). When the combined
        # standoff would consume the whole span, scale both down to leave ~20%
        # of the span as the drawn edge. Long edges are unaffected.
        fs, ts = from_standoff, to_standoff
        total = fs + ts
        length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
        if total > 0 and total >= length:
            scale = (length * 0.8) / total
            fs, ts = fs * scale, ts * scale
        return _inset_toward(p0, p1, fs), _inset_toward(p1, p0, ts)
