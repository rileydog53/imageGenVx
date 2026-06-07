"""Hand-authored, themeable lab glyphs re-traced for the house style (D9).

Where Bioicons had no clean, simple source (the micropipette options were either
the wrong instrument or 400 kB; no good single "person"), these are drawn from
scratch as a handful of svgwrite shapes — license-clean and fully recolorable
via ``style_dict`` (unlike the embedded Bioicons, which keep their flat color).

Each function is **origin-drawn** at a fixed intrinsic ``(w, h)`` (no label) so
``entity_adapters._equip_adapter`` can scale-to-fit it into a slot and add the
fitted label, exactly like the older ``lab_equipment`` icons it replaces. The
first emitted shape matches the primitive's ``convention_check`` tag
(pipette → ``rect``, human_figure → ``circle``).
"""
from __future__ import annotations

import svgwrite.container
import svgwrite.path
import svgwrite.shapes

# Intrinsic drawing boxes (px) — kept in sync with the _equip_adapter intrinsics.
PIPETTE_SIZE = (26.0, 96.0)
HUMAN_SIZE = (44.0, 56.0)

DEFAULT_STYLE: dict[str, object] = {
    "lab_outline_stroke": "#2C3E50",
    "lab_outline_stroke_width": 1.6,
    "pipette_body_fill": "#D7E3EF",      # pale instrument blue-grey
    "pipette_accent_fill": "#5B8DB8",    # plunger / tip accent
    "pipette_window_fill": "#FFFFFF",
    "human_fill": "#7A8A99",             # neutral figure grey
    "human_stroke": "#2C3E50",
    "human_stroke_width": 1.4,
}


def _rrect(insert, size, rx, **kw):
    r = svgwrite.shapes.Rect(insert=insert, size=size, rx=rx, ry=rx, **kw)
    return r


def pipette(style_dict: dict | None = None) -> svgwrite.container.Group:
    """An adjustable micropipette: plunger button, tapered body with a volume
    window, and a thin tip cone. Origin-drawn in ``[0,26]×[0,96]``."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    stroke = str(s["lab_outline_stroke"])
    sw = float(s["lab_outline_stroke_width"])
    body = str(s["pipette_body_fill"])
    accent = str(s["pipette_accent_fill"])
    g = svgwrite.container.Group()

    # Plunger button (first shape → "rect").
    g.add(_rrect((9, 0), (8, 8), 2.0, fill=accent, stroke=stroke, **{"stroke-width": sw}))
    # Plunger shaft.
    g.add(_rrect((11, 8), (4, 8), 1.0, fill=body, stroke=stroke, **{"stroke-width": sw}))
    # Tapered body (shoulders down to the tip holder).
    body_poly = svgwrite.shapes.Polygon(
        points=[(4, 16), (22, 16), (17, 62), (9, 62)],
        fill=body, stroke=stroke,
    )
    body_poly["stroke-width"] = sw
    g.add(body_poly)
    # Volume window.
    g.add(_rrect((9, 26), (8, 10), 1.0, fill=str(s["pipette_window_fill"]),
                 stroke=stroke, **{"stroke-width": sw}))
    # Tip holder + thin tip cone.
    g.add(_rrect((9, 62), (8, 8), 1.0, fill=body, stroke=stroke, **{"stroke-width": sw}))
    tip = svgwrite.shapes.Polygon(
        points=[(9, 70), (17, 70), (14, 96), (12, 96)],
        fill=accent, stroke=stroke,
    )
    tip["stroke-width"] = sw
    g.add(tip)
    return g


def human_figure(style_dict: dict | None = None) -> svgwrite.container.Group:
    """A clean person silhouette: round head above rounded shoulders — the
    universal "subject / participant" glyph. Origin-drawn in ``[0,44]×[0,56]``."""
    s = {**DEFAULT_STYLE, **(style_dict or {})}
    fill = str(s["human_fill"])
    stroke = str(s["human_stroke"])
    sw = float(s["human_stroke_width"])
    g = svgwrite.container.Group()
    cx = 22.0

    # Head (first shape → "circle").
    head = svgwrite.shapes.Circle(center=(cx, 12), r=10, fill=fill, stroke=stroke)
    head["stroke-width"] = sw
    g.add(head)
    # Shoulders / torso: a rounded bust hump rising to the neck.
    torso = svgwrite.path.Path(
        d=("M 4,56 "
           "C 4,38 12,30 22,30 "
           "C 32,30 40,38 40,56 Z"),
        fill=fill, stroke=stroke,
    )
    torso["stroke-width"] = sw
    g.add(torso)
    return g
