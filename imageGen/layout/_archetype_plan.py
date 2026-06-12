"""Single source of truth for the archetype → engine / canvas / label dispatch.

Phase 0a (P0a.1). The "which leaf archetypes are pathway-family vs reaction"
decision was previously encoded in four unsynchronised sites — the
``ARCHETYPE_TO_LAYOUT`` table here, ``_override_subengine_canvas``'s if/elif in
``panel_layout``, and the ``_PATHWAY_COMPATIBLE_ARCHETYPES`` / ``== REACTION_SCHEME``
membership tests in the compositor's ``_dispatch_layout`` / ``_canvas_size`` /
``_label_requests_fn``. This module collapses them into one ``_ARCHETYPE_PLAN``
table that every site reads, so adding/retiring an archetype is a single edit.

Container modes (tiers / panels) are decided *before* any archetype lookup
(container-mode-first); this table maps the five **leaf** archetypes only.

DAG position: a leaf below ``panel_layout`` and ``compositor``. It imports only
the two leaf engines (``pathway_layout``, ``reaction_layout``) plus ``ir.schema``
and ``layout.types`` — none of which import this module — so no cycle is created.
"""
from __future__ import annotations

from typing import Any, Callable, NamedTuple

from imageGen.ir.schema import Archetype, Figure
from imageGen.layout.pathway_layout import (
    compute_pathway_canvas,
    layout_pathway,
    pathway_label_requests,
)
from imageGen.layout.reaction_layout import (
    REACTION_DEFAULT_PARAMS,
    layout_reaction,
    reaction_label_requests,
)
from imageGen.layout.types import LayoutEntry


def _reaction_canvas(figure: Figure) -> tuple[float, float]:
    """Static reaction canvas — the reaction engine lays out within a fixed envelope."""
    return REACTION_DEFAULT_PARAMS["reaction_canvas"]


class ArchetypePlan(NamedTuple):
    """How one leaf archetype lowers.

    Fields:
        engine: the layout engine callable (``layout_pathway`` / ``layout_reaction``).
        canvas_fn: ``figure -> (w, h)`` SVG viewport for a top-level figure of
            this archetype (``compute_pathway_canvas`` for pathway-family, a
            constant for reaction).
        label_fn: the ``*_label_requests`` sibling, or ``None``.
        canvas_key: the ``*_canvas`` / ``*_origin`` style-key prefix the panel
            sub-engine uses ("pathway" | "reaction").
        inject_canvas: when True a panel sub-engine receives ``"<key>_canvas"``;
            both prefixes always receive ``"<key>_origin"``.
    """
    engine: Callable[..., list[LayoutEntry]]
    canvas_fn: Callable[[Figure], tuple[float, float]]
    label_fn: Callable[..., list] | None
    canvas_key: str
    inject_canvas: bool


_ARCHETYPE_PLAN: dict[Archetype, ArchetypePlan] = {
    Archetype.PATHWAY:            ArchetypePlan(layout_pathway, compute_pathway_canvas, pathway_label_requests, "pathway", True),
    Archetype.WORKFLOW:           ArchetypePlan(layout_pathway, compute_pathway_canvas, pathway_label_requests, "pathway", True),
    Archetype.CELLULAR_SCHEMATIC: ArchetypePlan(layout_pathway, compute_pathway_canvas, pathway_label_requests, "pathway", True),
    Archetype.MECHANISM_CARTOON:  ArchetypePlan(layout_pathway, compute_pathway_canvas, pathway_label_requests, "pathway", True),
    Archetype.REACTION_SCHEME:    ArchetypePlan(layout_reaction, _reaction_canvas, reaction_label_requests, "reaction", False),
}
