"""Entity-dispatch adapters for the cell and lab-equipment primitives.

The pathway / panel layout engines invoke every entity primitive with the
uniform signature ``(label, position, *, size, color=None, style_dict=None)``
where ``position`` is the *centre* of the slot and the drawing must fit inside
``size`` with a label below it (the same convention the ``glyphs`` module
follows).

The ``cells`` and ``lab_equipment`` modules predate that convention:

* ``cells.organelle`` already takes a centre + size, so it needs only a label.
* ``cells.cell_outline`` and the ``lab_equipment`` icons draw at a local origin
  at an intrinsic size and return (or imply) that size rather than fitting a box.

These thin adapters bridge the gap so both modules render as first-class
entities and via the ``primitive=`` override registry. They add no new drawing
logic — they translate/scale an existing primitive into the requested slot.
"""
from __future__ import annotations

import warnings

import svgwrite.container

from imageGen.primitives import _text, cells, lab_equipment, membranes
from imageGen.primitives.glyphs import DEFAULT_STYLE as _GLYPH_STYLE

# Fraction of the slot height reserved for the label strip beneath the icon.
_LABEL_FRAC = 0.22


def _label_style(style_dict: dict | None) -> dict:
    """Merge the caller's style over the shared label-font defaults so the
    label-font keys the text helpers read are always present."""
    return {**_GLYPH_STYLE, **(style_dict or {})}


def _emit_label(
    group: svgwrite.container.Group,
    label: str,
    cx: float,
    cy: float,
    box_w: float,
    box_h: float,
    style_dict: dict | None,
) -> None:
    """Render a wrap/shrink-fitted label in the bottom strip of the slot.

    Mirrors the fit behaviour of the ``proteins`` boxes (via ``_text.fit_label``)
    so wide labels wrap or shrink instead of spilling into a neighbouring slot —
    the icon sits in the upper region, the label in the lower ``_LABEL_FRAC``."""
    if not label:
        return
    s = _label_style(style_dict)
    base = float(s["label_font_size"])
    band_h = max(box_h * _LABEL_FRAC, 2.0 * base * 1.2)  # allow up to two lines
    fit = _text.fit_label(label, box_w, band_h, s)
    label_cy = cy + box_h * 0.40
    group.add(_text.label_for_fit(fit, cx, label_cy, s))


def _place_scaled(
    inner: svgwrite.container.Group,
    intrinsic: tuple[float, float],
    position: tuple[float, float],
    size: tuple[float, float],
    icon_frac: float = 1.0,
) -> svgwrite.container.Group:
    """Uniformly scale an origin-drawn ``inner`` (spanning ``[0,iw]×[0,ih]``) to
    fit ``icon_frac`` of the ``size`` box's height, centred horizontally and
    flush with the top of the slot. Adds no label."""
    iw, ih = intrinsic
    bw, bh = size
    fit_h = bh * icon_frac
    scale = min(bw / iw, fit_h / ih) if iw > 0 and ih > 0 else 1.0
    sw = iw * scale
    cx, cy = position
    ox = cx - sw / 2.0
    oy = cy - bh / 2.0  # icon sits flush with the top of the slot
    placed = svgwrite.container.Group(
        transform=f"translate({round(ox, 2)},{round(oy, 2)}) scale({round(scale, 4)})"
    )
    placed.add(inner)
    out = svgwrite.container.Group()
    out.add(placed)
    return out


def _fit_icon(
    inner: svgwrite.container.Group,
    intrinsic: tuple[float, float],
    label: str,
    position: tuple[float, float],
    size: tuple[float, float],
    style: dict,
) -> svgwrite.container.Group:
    """Scale an origin-drawn ``inner`` into the upper region of the ``size`` box
    centred at ``position``, then add a fitted label in the bottom strip."""
    bw, bh = size
    cx, cy = position
    out = _place_scaled(inner, intrinsic, position, size, icon_frac=1.0 - _LABEL_FRAC)
    _emit_label(out, label, cx, cy, bw, bh, style)
    return out


# ---------------------------------------------------------------------------
# Cell / organelle adapters
# ---------------------------------------------------------------------------

def _cell_adapter(style_name: str):
    def draw(label, position, size=(72.0, 56.0), color=None, style_dict=None):
        s = style_dict or {}
        inner, _curve = cells.cell_outline(style_name, size, style_dict)
        return _fit_icon(inner, size, label, position, size, s)
    draw.__name__ = f"cell_{style_name}"
    draw.__qualname__ = draw.__name__
    return draw


def _organelle_adapter(organelle_type: str):
    def draw(label, position, size=(56.0, 46.0), color=None, style_dict=None):
        s = style_dict or {}
        cx, cy = position
        bw, bh = size
        icon_size = (bw, bh * (1.0 - _LABEL_FRAC))
        # organelle() draws centred on the point we pass; shift up so the label
        # strip clears the bottom of the slot.
        icon_center = (cx, cy - bh * _LABEL_FRAC / 2.0)
        g = svgwrite.container.Group()
        g.add(cells.organelle(organelle_type, icon_center, icon_size, style_dict))
        _emit_label(g, label, cx, cy, bw, bh, s)
        return g
    draw.__name__ = organelle_type
    draw.__qualname__ = organelle_type
    return draw


# ---------------------------------------------------------------------------
# Lab-equipment adapters
# ---------------------------------------------------------------------------

def _equip_adapter(name, build_inner, intrinsic, default_size):
    """Wrap an origin-drawn lab-equipment icon as an entity primitive.

    ``build_inner(style_dict)`` returns the icon Group drawn at the local origin
    (any negative-coordinate parts already normalised), ``intrinsic`` is its
    ``(w, h)`` footprint used for the fit scale.
    """
    def draw(label, position, size=default_size, color=None, style_dict=None):
        s = style_dict or {}
        inner = build_inner(style_dict)
        return _fit_icon(inner, intrinsic, label, position, size, s)
    draw.__name__ = name
    draw.__qualname__ = name
    return draw


def _normalised(inner: svgwrite.container.Group, dx: float, dy: float):
    """Wrap ``inner`` in a translate so a primitive that draws into negative
    coordinates starts at the local origin."""
    if dx == 0.0 and dy == 0.0:
        return inner
    g = svgwrite.container.Group(transform=f"translate({dx},{dy})")
    g.add(inner)
    return g


def _build_well_plate(style_dict):
    return lab_equipment.well_plate(style_dict=style_dict)


def _build_microscope(style_dict):
    return lab_equipment.microscope(position=(0.0, 0.0), style_dict=style_dict)


def _build_pipette(style_dict):
    return lab_equipment.pipette(position=(0.0, 0.0), style_dict=style_dict)


def _build_gel(style_dict):
    return lab_equipment.gel_lane(position=(0.0, 0.0), style_dict=style_dict)


def _build_tube(style_dict):
    return lab_equipment.tube(position=(0.0, 0.0), style_dict=style_dict)


def _build_mouse(style_dict):
    # mouse() draws its tail to x≈-18; shift right so the icon starts at x=0.
    return _normalised(lab_equipment.mouse(position=(0.0, 0.0), style_dict=style_dict), 18.0, 0.0)


def _build_human(style_dict):
    return lab_equipment.human_figure(position=(0.0, 0.0), style_dict=style_dict)


# ---------------------------------------------------------------------------
# Chemical-structure adapter (EW1)
# ---------------------------------------------------------------------------

def molecule(label, position, size=(120.0, 96.0), color=None, style_dict=None):
    """Render a 2-D chemical structure for any entity carrying ``style.smiles``.

    Lets a ``metabolite`` / ``generic`` entity draw its RDKit structure inline
    in a pathway (previously SMILES only rendered inside ``reaction_scheme``).
    Usage: ``style={"primitive": "molecule", "smiles": "<SMILES>"}``.

    ``chemistry`` (and thus RDKit) is imported lazily so figures that use no
    molecules never pay the import cost. A missing/invalid SMILES warns and
    falls back to a label-only render rather than crashing the figure;
    ``convention_check`` skips this primitive, so the absent shape is fine.
    """
    s = style_dict or {}
    cx, cy = position
    bw, bh = size
    g = svgwrite.container.Group()
    smiles = s.get("smiles")
    if smiles:
        from imageGen.primitives import chemistry  # lazy: avoid RDKit import for non-molecule figures
        icon_h = bh * (1.0 - _LABEL_FRAC)
        mol_style = {k: v for k, v in s.items() if k != "smiles"}
        try:
            g.add(chemistry.render_molecule(
                str(smiles),
                size=(int(bw), int(icon_h)),
                center=(cx, cy - bh * _LABEL_FRAC / 2.0),
                style_dict=mol_style,
            ))
        except ValueError as exc:
            warnings.warn(
                f"molecule primitive: SMILES {smiles!r} did not render ({exc}); "
                f"drawing label only.",
                UserWarning, stacklevel=2,
            )
    else:
        warnings.warn(
            "molecule primitive requires style['smiles']; drawing label only.",
            UserWarning, stacklevel=2,
        )
    _emit_label(g, label, cx, cy, bw, bh, s)
    return g


def functional_group(label, position, size=(110.0, 96.0), color=None, style_dict=None):
    """Render a named functional-group callout (structure + group name).

    The group is chosen by ``style.functional_group`` (e.g. ``"carboxyl"``);
    when that key is absent the entity ``label`` is used as the group name, so
    ``label="amine"`` works with no extra key. ``render_functional_group`` draws
    its own name label below the structure, so no second label is added.

    ``chemistry``/RDKit is imported lazily. An unknown/missing group warns and
    falls back to a label-only render; ``convention_check`` skips this primitive.
    """
    s = style_dict or {}
    cx, cy = position
    bw, bh = size
    name = s.get("functional_group") or (label or "")
    if name:
        from imageGen.primitives import chemistry  # lazy: avoid RDKit import for non-molecule figures
        icon_w = max(1, int(bw))
        icon_h = max(1, int(bh * 0.6))
        fg_style = {k: v for k, v in s.items() if k not in ("functional_group", "smiles")}
        try:
            inner = chemistry.render_functional_group(
                str(name), size=(icon_w, icon_h), style_dict=fg_style,
            )
            # render_functional_group draws its name label ~18px below `size`.
            return _place_scaled(inner, (icon_w, icon_h + 18.0), position, size)
        except (ValueError, KeyError) as exc:
            warnings.warn(
                f"functional_group primitive: {name!r} did not render ({exc}); "
                f"drawing label only.",
                UserWarning, stacklevel=2,
            )
    else:
        warnings.warn(
            "functional_group primitive requires style['functional_group'] or a "
            "label naming the group; drawing label only.",
            UserWarning, stacklevel=2,
        )
    g = svgwrite.container.Group()
    _emit_label(g, label, cx, cy, bw, bh, s)
    return g


# ---------------------------------------------------------------------------
# Membrane adapter (EW3) — closed lipid-bilayer vesicle
# ---------------------------------------------------------------------------

# Intrinsic drawing box for the liposome. Only the thickness/radius *ratio*
# matters (it survives the fit scale); 160 px gives a textbook bilayer with a
# clean head-group cadence before being scaled into the entity slot.
_LIPOSOME_INTRINSIC = (160.0, 160.0)


def liposome(label, position, size=(96.0, 96.0), color=None, style_dict=None):
    """Render a closed phospholipid-bilayer vesicle (liposome cross-section).

    Surfaces the otherwise-unreachable ``membranes.cell_membrane_outline`` +
    ``membranes.lipid_bilayer`` pair as a first-class entity glyph: a ring of
    two leaflets with phospholipid head groups around an empty lumen — the
    textbook liposome / transport-vesicle drawing. Distinct from the simpler
    filled-circle ``glyphs.vesicle``; reach it via
    ``style={"primitive": "liposome"}``.

    Only the bilayer is drawn (the membrane midline outline is consumed solely
    for its anchor curve), so the first shape element is the bilayer tail
    ``<polygon>`` — matching its ``_PRIMITIVE_SHAPE`` tag.
    """
    s = style_dict or {}
    _outline, curve = membranes.cell_membrane_outline(
        "circle", _LIPOSOME_INTRINSIC, style_dict
    )
    inner = svgwrite.container.Group()
    inner.add(membranes.lipid_bilayer(curve, style_dict=style_dict))
    return _fit_icon(inner, _LIPOSOME_INTRINSIC, label, position, size, s)


# ---------------------------------------------------------------------------
# Public, convention-conforming primitives
# ---------------------------------------------------------------------------

cell = _cell_adapter("generic")
cell_neuron = _cell_adapter("neuron")
cell_epithelial = _cell_adapter("epithelial")
cell_immune = _cell_adapter("immune")

mitochondrion = _organelle_adapter("mitochondrion")
nucleus = _organelle_adapter("nucleus")
endoplasmic_reticulum = _organelle_adapter("er")
golgi = _organelle_adapter("golgi")
lysosome = _organelle_adapter("lysosome")

microscope = _equip_adapter("microscope", _build_microscope, (50.0, 60.0), (60.0, 64.0))
well_plate = _equip_adapter("well_plate", _build_well_plate, (138.0, 98.0), (96.0, 70.0))
tube = _equip_adapter("tube", _build_tube, (22.0, 50.0), (40.0, 58.0))
pipette = _equip_adapter("pipette", _build_pipette, (12.0, 96.0), (28.0, 74.0))
gel = _equip_adapter("gel", _build_gel, (24.0, 100.0), (40.0, 74.0))
mouse = _equip_adapter("mouse", _build_mouse, (93.0, 30.0), (84.0, 46.0))
human_figure = _equip_adapter("human_figure", _build_human, (40.0, 52.0), (44.0, 60.0))
