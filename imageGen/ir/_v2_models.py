"""IR v2 models (R2 split).

Internals of :mod:`imageGen.ir.schema`. Holds the shared model base (`_IRBase`)
and the original v2 figure models: `Entity`, `Compartment`, `ReactionConditions`,
`Relation`, `Annotation`, `GlossaryEntry`, `Panel`, and the top-level `Figure`.

`Figure` references `Panel` (here) and `Tier` (in the sibling `_v3_models`), and
`Panel.content` / `Scene.content` / `Tier.content` reference `Figure` — a true
type-graph cycle. It is resolved without an import cycle: this module imports
nothing from `_v3_models`; the forward refs are evaluated by the single
`model_rebuild()` block kept in `schema.py`, whose module namespace holds every
model (the same way the original single-file module resolved them at module end).
"""
from __future__ import annotations

from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from imageGen.ir._enums import (
    AnnotationType,
    Archetype,
    CompartmentType,
    EntityType,
    NamedSlot,
    RelationLabelSide,
    RelationType,
)


class _IRBase(BaseModel):
    model_config = ConfigDict(extra="forbid", use_enum_values=False)

    @classmethod
    def from_dict(cls, data: dict) -> Self:
        return cls.model_validate(data)

    def to_json(self, *, indent: int = 2) -> str:
        return self.model_dump_json(indent=indent)


class Entity(_IRBase):
    id: str
    type: EntityType
    label: str
    location: str | None = None
    style: dict[str, Any] | None = None


class Compartment(_IRBase):
    id: str
    type: CompartmentType
    label: str


class ReactionConditions(_IRBase):
    reagents: list[str] = Field(default_factory=list)
    yield_pct: float | None = None
    reversible: bool = False
    notes: str | None = None

    @field_validator("yield_pct")
    @classmethod
    def _yield_in_range(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 <= v <= 100.0):
            raise ValueError("yield_pct must be between 0 and 100")
        return v


class Relation(_IRBase):
    source: str
    target: str
    type: RelationType
    label: str | None = None
    label_side: RelationLabelSide | None = None
    conditions: ReactionConditions | dict[str, Any] | None = None

    @property
    def ir_id(self) -> str:
        """Synthetic IR id — relations have no declared id, so layout and
        verification derive one deterministically from the endpoints + type."""
        return f"rel_{self.source}_{self.type.value}_{self.target}"


class Annotation(_IRBase):
    type: AnnotationType
    text: str
    position: tuple[float, float] | NamedSlot


class GlossaryEntry(_IRBase):
    """One abbreviation → expansion pair for a figure's glossary box (FR9).

    Rendered as a bordered key (``render/glossary.py``); a non-empty
    ``Figure.glossary`` draws the box automatically. ``glossary_check`` (advisory)
    can flag acronyms in labels that lack a matching ``term``.
    """
    term: str
    definition: str


class Panel(_IRBase):
    id: str
    title: str | None = None
    content: Figure
    grid: tuple[int, int, int, int]

    @field_validator("grid")
    @classmethod
    def _grid_spans_positive(
        cls, v: tuple[int, int, int, int]
    ) -> tuple[int, int, int, int]:
        row, col, rowspan, colspan = v
        if row < 0 or col < 0:
            raise ValueError("grid row/col must be non-negative")
        if rowspan < 1 or colspan < 1:
            raise ValueError("grid rowspan/colspan must be >= 1")
        return v


class Figure(_IRBase):
    archetype: Archetype
    title: str | None = None
    caption: str | None = None
    style_preset: str = "cell_press"
    # LT1: optional layout override. "circular" forces a ring layout for a
    # compartment-free cyclic pathway; None lets the engine auto-detect (a pure
    # single cycle rings automatically). Other values are ignored by the engine.
    layout_hint: str | None = None
    entities: list[Entity] = Field(default_factory=list)
    compartments: list[Compartment] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)
    panels: list[Panel] = Field(default_factory=list)
    annotations: list[Annotation] = Field(default_factory=list)
    glossary: list[GlossaryEntry] = Field(default_factory=list)
    # V3 scene chassis: a third top-level container mode (vertical band stack),
    # mutually exclusive with leaf content and panels.
    tiers: list[Tier] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_structure(self) -> Self:
        leaf_populated = bool(self.entities or self.relations or self.compartments)
        if sum([leaf_populated, bool(self.panels), bool(self.tiers)]) > 1:
            raise ValueError(
                "Figure must use exactly one of: leaf content "
                "(entities/compartments/relations), panels, or tiers — "
                "not more than one"
            )

        entity_ids = [e.id for e in self.entities]
        if len(entity_ids) != len(set(entity_ids)):
            raise ValueError("Entity ids must be unique within a Figure")

        compartment_ids = [c.id for c in self.compartments]
        if len(compartment_ids) != len(set(compartment_ids)):
            raise ValueError("Compartment ids must be unique within a Figure")

        panel_ids = [p.id for p in self.panels]
        if len(panel_ids) != len(set(panel_ids)):
            raise ValueError("Panel ids must be unique within a Figure")

        entity_id_set = set(entity_ids)
        compartment_id_set = set(compartment_ids)

        for ent in self.entities:
            if ent.location is not None and ent.location not in compartment_id_set:
                raise ValueError(
                    f"Entity '{ent.id}' references unknown compartment '{ent.location}'"
                )

        for rel in self.relations:
            if rel.source not in entity_id_set:
                raise ValueError(
                    f"Relation references unknown source entity '{rel.source}'"
                )
            if rel.target not in entity_id_set:
                raise ValueError(
                    f"Relation references unknown target entity '{rel.target}'"
                )

        for i, a in enumerate(self.panels):
            ar0, ac0, arS, acS = a.grid
            ar1, ac1 = ar0 + arS, ac0 + acS
            for b in self.panels[i + 1 :]:
                br0, bc0, brS, bcS = b.grid
                br1, bc1 = br0 + brS, bc0 + bcS
                if ar0 < br1 and br0 < ar1 and ac0 < bc1 and bc0 < ac1:
                    raise ValueError(
                        f"Panel '{a.id}' grid overlaps with panel '{b.id}'"
                    )

        tier_ids = [t.id for t in self.tiers]
        if len(tier_ids) != len(set(tier_ids)):
            raise ValueError("Tier ids must be unique within a Figure")

        # Scene ids (including a step-sequence base and each expanded step) must
        # be unique across the whole figure: scene ids namespace slot anchors in
        # the 'scene.slot.anchor' registry grammar, so cross-tier refs need them
        # globally unambiguous. Slot ids stay scene-scoped (checked per Scene).
        all_scene_ids: list[str] = []
        for tier in self.tiers:
            all_scene_ids.extend(s.id for s in tier.scenes)
            all_scene_ids.extend(s.id for s in tier.overlays)
            if tier.step_sequence is not None:
                all_scene_ids.append(tier.step_sequence.base.id)
                all_scene_ids.extend(st.id for st in tier.step_sequence.steps)
        if len(all_scene_ids) != len(set(all_scene_ids)):
            raise ValueError("Scene ids must be unique across a Figure")

        return self
