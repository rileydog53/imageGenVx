"""Shared low-level SVG helpers for the primitive modules."""
from __future__ import annotations


def polyline_to_svg_points(
    points: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    """Round float coordinates to 2 decimal places for clean SVG output."""
    return [(round(x, 2), round(y, 2)) for x, y in points]
