"""Semantic verification — Phase 6 Step 1.

Re-parses a rendered SVG and verifies that every IR-defined element is
present in the output. The compositor tags every emitted ``<g>`` with
``id="<scoped-id>"`` (D1) precisely so this check has something to grep
for; ``semantic_check`` enforces that contract.

Scope:
  For PATHWAY-family figures, every IR-*declared* element is verified —
  entities, compartments, and relations (relations have no declared id,
  so their synthetic ``Relation.ir_id`` is used). Panel chrome ids are
  layout artifacts and are ignored.

  REACTION_SCHEME figures render the whole reaction as one composite
  group (molecules are drawn from SMILES as a unit, not per-entity), so
  the only semantic anchor is the ``reaction_0`` group — that is what
  gets verified for a reaction (sub-)figure.

  A panel's presence is verified implicitly — its content's elements
  carry the panel-chain prefix, so a mis-scoped or missing panel
  surfaces as missing/mismatched child ids.

  A TIER figure (mutually exclusive with entities/panels) exposes its
  geometry as scene slots — every laid-out slot is tagged
  ``"<scene.id>.<slot.id>"`` (D1, no panel chain). ``semantic_check`` walks
  the scenes the engine actually draws (``tier_rendered_scenes`` — SCENE_ROW
  scenes, expanded ``step_sequence`` steps, and overlays) so a missing or
  mis-scoped slot is caught. Without this a tier figure passes vacuously.

Failure mode:
  Raises ``SemanticCheckError`` on the first missing element. This
  matches the fail-loud precedent of ``LabelPlacementError`` in
  ``layout/label_placement.py``.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Literal

from imageGen.ir.schema import Archetype, Figure, SlotKind
from imageGen.layout.reaction_layout import REACTION_GROUP_IR_ID
from imageGen.layout.tier_layout import tier_rendered_scenes
from imageGen.render.compositor import scoped_id

_Kind = Literal["entity", "compartment", "relation", "reaction", "annotation", "slot"]


class SemanticCheckError(RuntimeError):
    """Raised when an IR-defined element is missing from the rendered SVG.

    Attributes:
        ir_id: The raw IR id of the missing element (e.g. ``"ras"``).
        kind: One of ``"entity"``, ``"compartment"``, ``"relation"``.
        scoped_id: The panel-scoped SVG id that was expected but not
            found (e.g. ``"p1__ras"``; equals ``ir_id`` at depth 0).
    """

    def __init__(self, ir_id: str, kind: _Kind, expected_id: str) -> None:
        self.ir_id = ir_id
        self.kind = kind
        self.scoped_id = expected_id
        super().__init__(
            f"Missing {kind} in rendered SVG: ir_id={ir_id!r} "
            f"(expected scoped id {expected_id!r})"
        )


def _expected_ids(
    figure: Figure, panel_chain: tuple[str, ...]
) -> list[tuple[str, _Kind, str]]:
    """Walk an IR Figure and return (scoped_id, kind, raw_ir_id) triples.

    Recurses into panels, extending ``panel_chain`` by the panel id so
    nested elements get the same prefix the compositor applies. A
    REACTION_SCHEME (sub-)figure contributes a single ``reaction_0``
    anchor instead of per-entity ids — see module docstring.
    """
    expected: list[tuple[str, _Kind, str]] = []
    if figure.archetype == Archetype.REACTION_SCHEME:
        expected.append(
            (scoped_id(REACTION_GROUP_IR_ID, panel_chain), "reaction", REACTION_GROUP_IR_ID)
        )
    else:
        for entity in figure.entities:
            expected.append((scoped_id(entity.id, panel_chain), "entity", entity.id))
        for compartment in figure.compartments:
            expected.append(
                (scoped_id(compartment.id, panel_chain), "compartment", compartment.id)
            )
        for relation in figure.relations:
            expected.append(
                (scoped_id(relation.ir_id, panel_chain), "relation", relation.ir_id)
            )
    # FR6/FR1: annotations are drawn once at the top level (the compositor reads
    # only ``ir.annotations``), tagged ``annotation_0``, ``annotation_1``, …
    # Verifying each guards against the FR1 regression where annotations were a
    # silent no-op. Gated on the top-level call so panel-content annotations —
    # which the compositor does not draw — aren't falsely required.
    if not panel_chain:
        for i, _annotation in enumerate(figure.annotations):
            aid = f"annotation_{i}"
            expected.append((aid, "annotation", aid))
    for panel in figure.panels:
        expected.extend(_expected_ids(panel.content, (*panel_chain, panel.id)))
    # P7.0: a tier figure's geometry lives in scene slots, each tagged
    # "<scene.id>.<slot.id>" by the engine. Walk only the scenes the engine
    # actually lays out (tier_rendered_scenes) so we never demand an id that was
    # never drawn. GROUP slots nest further but neither render nor define an id
    # scheme yet (Step 7) — and a GROUP slot raises at layout, so it can never
    # reach a rendered SVG — so they are skipped. Every other leaf kind is safe
    # to require: an unsupported kind aborts the render before this check runs.
    for tier in figure.tiers:
        for scene in tier_rendered_scenes(tier):
            for slot in scene.slots:
                if slot.kind == SlotKind.GROUP:
                    continue
                raw = f"{scene.id}.{slot.id}"
                expected.append((scoped_id(raw, panel_chain), "slot", raw))
    return expected


def semantic_check(ir: Figure, svg_path: str | Path) -> None:
    """Verify every IR-defined element is present in the rendered SVG.

    Args:
        ir: The IR Figure that was rendered.
        svg_path: Path to the SVG produced by ``render_figure``.

    Raises:
        SemanticCheckError: On the first IR element whose scoped id is
            absent from the SVG.
    """
    root = ET.parse(str(svg_path)).getroot()
    present = {el.get("id") for el in root.iter() if el.get("id") is not None}

    for expected_id, kind, raw_id in _expected_ids(ir, ()):
        if expected_id not in present:
            raise SemanticCheckError(raw_id, kind, expected_id)
