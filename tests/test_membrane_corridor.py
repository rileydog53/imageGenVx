"""Clarity fix (#1a): cross-band arrow corridors must not ride the membrane.

A lipid bilayer is drawn at a MEMBRANE band's top edge. Because bands are
contiguous, a cross-band corridor routed at the band boundary lands exactly on
the bilayer stripe, so the horizontal leg of the elbow path visually rides
along the membrane (e.g. the Insulin -> INSR "binds" arrow). The fix lifts such
a corridor just above the stripe so the horizontal leg runs in the band above
the membrane and only the vertical legs cross it (perpendicular).

This pins:
  1. _lift_corridor_off_membrane lifts a corridor inside a keep-out to its top.
  2. _orthogonal_waypoints honours the keep-out for a real cross-band path.
  3. End-to-end: an extracellular->membrane edge's corridor clears the bilayer.
"""
from __future__ import annotations

from imageGen.ir.schema import (
    Archetype,
    Compartment,
    CompartmentType,
    Entity,
    EntityType,
    Figure,
    Relation,
    RelationType,
)
from imageGen.layout.pathway_layout import (
    RELATION_TO_ARROW,
    _compute_bands,
    _lift_corridor_off_membrane,
    _orthogonal_waypoints,
    layout_pathway,
)
from imageGen.primitives import membranes as _mem


# ---------------------------------------------------------------------------
# _lift_corridor_off_membrane
# ---------------------------------------------------------------------------

def test_lift_corridor_inside_keepout_moves_to_top():
    keep = [(112.0, 148.0)]
    assert _lift_corridor_off_membrane(116.0, keep) == 112.0


def test_lift_corridor_outside_keepout_unchanged():
    keep = [(112.0, 148.0)]
    assert _lift_corridor_off_membrane(90.0, keep) == 90.0   # above the stripe
    assert _lift_corridor_off_membrane(200.0, keep) == 200.0  # well below


def test_lift_corridor_no_keepouts_is_noop():
    assert _lift_corridor_off_membrane(116.0, None) == 116.0
    assert _lift_corridor_off_membrane(116.0, []) == 116.0


def test_lift_corridor_multiple_keepouts():
    keep = [(50.0, 80.0), (112.0, 148.0)]
    assert _lift_corridor_off_membrane(130.0, keep) == 112.0
    assert _lift_corridor_off_membrane(60.0, keep) == 50.0


# ---------------------------------------------------------------------------
# _orthogonal_waypoints honours the keep-out
# ---------------------------------------------------------------------------

def test_orthogonal_waypoints_lifts_corridor_off_membrane():
    # src band above (0..116), tgt band below (116..232); boundary at 116 carries
    # the bilayer keep-out [112, 148]. Without a keep-out the corridor sits at 116.
    src_band = (0.0, 116.0)
    tgt_band = (116.0, 232.0)
    keep = [(112.0, 148.0)]
    no_keep = _orthogonal_waypoints(
        (300.0, 60.0), (60.0, 30.0), src_band,
        (100.0, 160.0), (28.0, 60.0), tgt_band, gap=4.0,
    )
    assert no_keep[1][1] == 116.0  # rides the boundary (== membrane line)

    lifted = _orthogonal_waypoints(
        (300.0, 60.0), (60.0, 30.0), src_band,
        (100.0, 160.0), (28.0, 60.0), tgt_band, gap=4.0,
        membrane_keepouts=keep,
    )
    cy = lifted[1][1]
    assert cy == 112.0
    # Both elbow points share the lifted y (the horizontal leg).
    assert lifted[2][1] == cy
    # The horizontal leg is clear of the stripe interval.
    assert not (keep[0][0] < cy < keep[0][1])


# ---------------------------------------------------------------------------
# End-to-end
# ---------------------------------------------------------------------------

def test_extracellular_to_membrane_corridor_clears_bilayer(monkeypatch):
    import imageGen.layout.pathway_layout as PL

    captured: dict[str, tuple[float, float]] = {}
    _orig = PL._compute_bands

    def _spy(comps, canvas, origin, *, band_heights=None):
        result = _orig(comps, canvas, origin, band_heights=band_heights)
        captured.clear()
        captured.update(result)
        return result

    monkeypatch.setattr(PL, "_compute_bands", _spy)

    figure = Figure(
        archetype=Archetype.PATHWAY,
        entities=[
            Entity(id="lig", type=EntityType.LIGAND, label="Insulin", location="ec"),
            Entity(id="rec", type=EntityType.RECEPTOR, label="INSR", location="mem"),
            Entity(id="dwn", type=EntityType.KINASE, label="AKT", location="cyto"),
        ],
        compartments=[
            Compartment(id="ec", type=CompartmentType.EXTRACELLULAR, label="Extracellular"),
            Compartment(id="mem", type=CompartmentType.MEMBRANE, label="Membrane"),
            Compartment(id="cyto", type=CompartmentType.CYTOPLASM, label="Cytoplasm"),
        ],
        relations=[
            Relation(source="lig", target="rec", type=RelationType.BINDS),
            Relation(source="rec", target="dwn", type=RelationType.ACTIVATES),
        ],
    )
    entries = layout_pathway(figure)

    # The bilayer is drawn at the membrane band's top edge; its stripe spans
    # [top - r_head, top + thickness + r_head].
    mem_top = captured["mem"][0]
    ms = _mem.DEFAULT_STYLE
    thickness = float(ms["bilayer_thickness"])
    r_head = float(ms["bilayer_head_radius"])
    stripe_lo = mem_top - r_head
    stripe_hi = mem_top + thickness + r_head

    arrow_prims = frozenset(RELATION_TO_ARROW.values())
    lig_rec = next(e for e in entries
                   if e.primitive in arrow_prims
                   and e.ir_id and e.ir_id.startswith("rel_lig"))
    wps = lig_rec.kwargs.get("waypoints")
    assert wps is not None and len(wps) == 4
    corridor_y = wps[1][1]
    assert wps[2][1] == corridor_y, "horizontal corridor leg must be flat"

    # The horizontal corridor leg must not lie on the bilayer stripe; the lift
    # places it above the stripe (in the extracellular band).
    assert not (stripe_lo <= corridor_y <= stripe_hi), (
        f"corridor_y={corridor_y} rides the bilayer stripe "
        f"[{stripe_lo}, {stripe_hi}] at mem_top={mem_top}"
    )
    assert corridor_y < stripe_lo, "corridor should be lifted above the membrane"
