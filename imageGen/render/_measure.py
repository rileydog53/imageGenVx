"""Shared text-measurement helper for the render-side box primitives.

Annotations, the legend, and the glossary all need a rough label-width
estimate to size their boxes. They share the same 0.6 char-width factor
(kept distinct from ``primitives/_text.estimate_text_width``'s 0.55, which
governs in-box label fitting — changing either would shift existing output).
"""
from __future__ import annotations


def estimate_text_w(text: str, font_size: float) -> float:
    """Rough text width (the 0.6 factor used across the renderer's boxes)."""
    return max(1, len(text)) * font_size * 0.6
