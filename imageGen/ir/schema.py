from __future__ import annotations

from enum import Enum
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class EntityType(str, Enum):
    PROTEIN = "protein"
    COMPLEX = "complex"
    LIGAND = "ligand"
    RECEPTOR = "receptor"
    KINASE = "kinase"
    GENE = "gene"
    RNA = "rna"
    METABOLITE = "metabolite"
    CELL = "cell"
    ORGANELLE = "organelle"
    EQUIPMENT = "equipment"
    SAMPLE = "sample"
    GENERIC = "generic"


class CompartmentType(str, Enum):
    EXTRACELLULAR = "extracellular"
    MEMBRANE = "membrane"
    CYTOPLASM = "cytoplasm"
    NUCLEUS = "nucleus"
    MITOCHONDRION = "mitochondrion"
    CUSTOM = "custom"


class RelationType(str, Enum):
    ACTIVATES = "activates"
    INHIBITS = "inhibits"
    BINDS = "binds"
    TRANSLOCATES = "translocates"
    PHOSPHORYLATES = "phosphorylates"
    TRANSCRIBES = "transcribes"
    CATALYZES = "catalyzes"
    CLEAVES = "cleaves"
    TRANSPORTS = "transports"
    RECRUITS = "recruits"
    GENERIC = "generic"


class RelationLabelSide(str, Enum):
    """Which side of its arrow a relation label should prefer (FR8).

    A *hint* that leads the label-placement priority — the greedy placer can
    still fall back to another side when the preferred one is occupied. Lets an
    author separate the two labels on a parallel forward/back edge pair (e.g.
    "subunit dissociation" above, "GTP hydrolysis" below). ``above``/``below``
    suit mostly-horizontal edges; ``left``/``right`` suit mostly-vertical ones.
    """
    ABOVE = "above"
    BELOW = "below"
    LEFT = "left"
    RIGHT = "right"


class Archetype(str, Enum):
    PATHWAY = "pathway"
    REACTION_SCHEME = "reaction_scheme"
    WORKFLOW = "workflow"
    CELLULAR_SCHEMATIC = "cellular_schematic"
    MECHANISM_CARTOON = "mechanism_cartoon"


class AnnotationType(str, Enum):
    LABEL = "label"
    CAPTION = "caption"
    SCALE_BAR = "scale_bar"


class NamedSlot(str, Enum):
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"
    TOP_LEFT = "top-left"
    TOP_RIGHT = "top-right"
    BOTTOM_LEFT = "bottom-left"
    BOTTOM_RIGHT = "bottom-right"
    CENTER = "center"


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

    @model_validator(mode="after")
    def _validate_structure(self) -> Self:
        leaf_populated = bool(self.entities or self.relations or self.compartments)
        if self.panels and leaf_populated:
            raise ValueError(
                "Figure must be either multi-panel (panels) or leaf "
                "(entities/compartments/relations), not both"
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

        return self


Panel.model_rebuild()
Figure.model_rebuild()
