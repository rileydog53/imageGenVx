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


# ---------------------------------------------------------------------------
# V3 scene-chassis enums (Tier / Scene / Step layers). Each kind enum carries a
# GENERIC/CUSTOM escape-hatch member, matching the existing schema convention.
# See V3_IR_NODESHAPES_PROPOSAL.md for the design and sign-off.
# ---------------------------------------------------------------------------

class TierRole(str, Enum):
    """What a Tier (a full-width horizontal band) is — drives band chrome."""
    TITLE = "title"              # pure-typography band: title + subtitle
    SCENE_ROW = "scene_row"      # a row of mutually-anchored scenes
    SUMMARY_BAR = "summary_bar"  # bordered band, optional internal divider
    BAND = "band"                # escape hatch: any other banded content


class TierLayout(str, Enum):
    """A Tier's internal layout strategy."""
    CENTERED_TITLE = "centered_title"
    EQUAL_COLUMNS = "equal_columns"
    TWO_SECTION_BAR = "two_section_bar"
    FREE_SCENE = "free_scene"
    CUSTOM = "custom"


class SlotKind(str, Enum):
    """Kind of a Slot — one placeable primitive (or sub-scene) inside a Scene."""
    BLOB = "blob"          # organic protein-surface container (cavity_* anchors)
    MOLECULE = "molecule"  # stick/skeletal structure (atom anchors)
    RESIDUE = "residue"    # side-chain stick + terminal atom
    GLYPH = "glyph"        # icon (tablet, dot-cluster, COX-1 blob, ...)
    TEXT = "text"          # free label / callout text
    BOX = "box"            # bordered callout / aspirin box
    GROUP = "group"        # nested sub-scene: holds its own slots (recursion)
    GENERIC = "generic"    # escape hatch


class AttachEdge(str, Enum):
    """Which anchor of the PARENT slot a child binds to (relative placement)."""
    TOP = "top"
    BOTTOM = "bottom"
    LEFT = "left"
    RIGHT = "right"
    CENTER = "center"
    CAVITY_TOP = "cavity_top"
    CAVITY_BOTTOM = "cavity_bottom"
    CAVITY_CENTER = "cavity_center"
    ANCHOR = "anchor"      # use the named anchor in Attach.parent_anchor
    CUSTOM = "custom"


class StepOp(str, Enum):
    """A per-step delta operation. Slot-granular only — no in-place sub-atom
    mutation (opaque primitive Groups can't be edited post-build)."""
    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"
    ADD_LABEL = "add_label"
    GENERIC = "generic"


class SceneEdgeType(str, Enum):
    """Visual kind of an intra-scene (SceneEdge) or cross-cell (TierEdge) edge.
    Dedicated so the load-bearing RelationType is not overloaded."""
    DASHED = "dashed"
    HBOND = "hbond"
    CURLY = "curly"            # arrow-pushing (primitive-refresh territory)
    TRANSITION = "transition"  # plain step-to-step arrow
    DEPARTS = "departs"        # leaving-group departure arrow
    BINDS = "binds"
    ACTIVATES = "activates"
    INHIBITS = "inhibits"
    GENERIC = "generic"


class RailAxis(str, Enum):
    """A rail's orientation: a horizontal (y) line or a vertical (x) line."""
    X = "x"
    Y = "y"


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


# ---------------------------------------------------------------------------
# V3 scene-chassis models. Additive: existing leaf/panel figures are unchanged.
# Layer A = relative-anchor scene graph (Scene/Slot/Attach/SceneEdge);
# Layer B = tier compositor + rails (Tier/Rail/TierEdge);
# Layer C = step/state deltas (StepSequence/Step/StepDelta).
# Forward refs to Figure are resolved by the model_rebuild() block at module end.
# ---------------------------------------------------------------------------

def _check_id_chars(value: str, what: str) -> str:
    """Reject '.' and '__' in ids — both are reserved separators.

    '.' delimits the anchor-registry 'scene.slot.anchor' grammar; '__' is the
    compositor's scoped-SVG-id join. Keeping them out of ids means neither can
    ever collide.
    """
    if "." in value or "__" in value:
        raise ValueError(
            f"{what} {value!r} must not contain '.' or '__' (reserved "
            "separators for the anchor registry and SVG-id scoping)"
        )
    return value


def _collect_slot_ids(slots: list[Slot]) -> list[str]:
    """Flatten slot ids, descending into group (nested) slots."""
    ids: list[str] = []
    for s in slots:
        ids.append(s.id)
        if s.slots:
            ids.extend(_collect_slot_ids(s.slots))
    return ids


class Slot(_IRBase):
    """One placeable primitive (or nested sub-scene) inside a Scene.

    Exposes named anchor points the scene solver and edges resolve against.
    Built-in anchors per kind are engine-provided (e.g. a blob's
    cavity_top/cavity_center); ``anchors`` declares extra author-named points
    (e.g. a molecule's atom-map names). kind=GROUP nests further ``slots``.
    """
    id: str
    kind: SlotKind
    label: str | None = None
    anchors: list[str] = Field(default_factory=list)
    slots: list[Slot] = Field(default_factory=list)
    style: dict[str, Any] | None = None

    @field_validator("id")
    @classmethod
    def _id_chars(cls, v: str) -> str:
        return _check_id_chars(v, "Slot id")


class Attach(_IRBase):
    """A relative-placement constraint: place ``child`` at ``parent``'s edge.

    parent=None attaches to the scene frame. ``offset`` is a small relative
    (dx, dy) nudge — the only explicit numbers; absolute positions are solved.
    """
    child: str
    parent: str | None = None
    edge: AttachEdge = AttachEdge.CENTER
    parent_anchor: str | None = None
    offset: tuple[float, float] = (0.0, 0.0)

    @property
    def ir_id(self) -> str:
        return f"att_{self.parent}_{self.child}"


class SceneEdge(_IRBase):
    """An intra-scene edge between two named anchors ('slot_id.anchor').

    A dashed interaction line, H-bond, or curly mechanism arrow — the visual
    form comes from ``type`` + ``style['primitive']``.
    """
    from_anchor: str
    to_anchor: str
    type: SceneEdgeType = SceneEdgeType.GENERIC
    label: str | None = None
    style: dict[str, Any] | None = None

    @property
    def ir_id(self) -> str:
        return f"edge_{self.from_anchor}_{self.to_anchor}"


class Scene(_IRBase):
    """A heterogeneous composition of slots placed by relative anchoring.

    The geometry-bearing leaf of the chassis: a blob + sticks + residues +
    interaction lines, mutually anchored. Either a slot-graph
    (slots/attach/connect) OR an embedded leaf Figure (content), never both.
    Slot ids are unique within the scene; the scene id namespaces them so the
    'scene.slot.anchor' registry key is unambiguous.
    """
    id: str
    label: str | None = None
    badge: str | None = None
    slots: list[Slot] = Field(default_factory=list)
    attach: list[Attach] = Field(default_factory=list)
    connect: list[SceneEdge] = Field(default_factory=list)
    content: Figure | None = None
    style: dict[str, Any] | None = None

    @field_validator("id")
    @classmethod
    def _id_chars(cls, v: str) -> str:
        return _check_id_chars(v, "Scene id")

    @property
    def ir_id(self) -> str:
        return f"scene_{self.id}"

    @model_validator(mode="after")
    def _validate_scene(self) -> Self:
        if self.content is not None and self.slots:
            raise ValueError(
                f"Scene '{self.id}' is either a slot-graph (slots) or an "
                "embedded Figure (content), not both"
            )
        slot_ids = _collect_slot_ids(self.slots)
        if len(slot_ids) != len(set(slot_ids)):
            raise ValueError(f"Slot ids must be unique within scene '{self.id}'")
        slot_id_set = set(slot_ids)
        for att in self.attach:
            if att.child not in slot_id_set:
                raise ValueError(
                    f"Scene '{self.id}' attach references unknown child slot "
                    f"'{att.child}'"
                )
            if att.parent is not None and att.parent not in slot_id_set:
                raise ValueError(
                    f"Scene '{self.id}' attach references unknown parent slot "
                    f"'{att.parent}'"
                )
        for edge in self.connect:
            for ref in (edge.from_anchor, edge.to_anchor):
                slot_token = ref.split(".", 1)[0]
                if slot_token not in slot_id_set:
                    raise ValueError(
                        f"Scene '{self.id}' connect references unknown slot "
                        f"'{slot_token}' in anchor '{ref}'"
                    )
        return self


class StepDelta(_IRBase):
    """One mutation applied for a step — slot-granular (add/remove/replace a
    slot or edge, or add a label). No in-place sub-atom mutation: opaque
    primitive Groups can't be edited after construction.

    ``target`` is a slot id, 'slot.anchor', or an edge ir_id in the base scene.
    It is required for remove/replace/add_label (which act on an existing
    element) and optional for ADD (which introduces a new element via ``value``,
    optionally naming a parent to attach to). ``value`` is the op payload.
    """
    op: StepOp
    target: str | None = None
    value: dict[str, Any] | None = None

    @property
    def ir_id(self) -> str:
        ref = self.target or (self.value or {}).get("id") or "anon"
        return f"delta_{self.op.value}_{ref}"


class Step(_IRBase):
    """One rendered copy in a StepSequence: badge/label overrides + deltas."""
    id: str
    badge: str | None = None
    label: str | None = None
    deltas: list[StepDelta] = Field(default_factory=list)
    style: dict[str, Any] | None = None


class StepSequence(_IRBase):
    """One base Scene + an ordered per-step delta list. The engine expands this
    to one Scene per step (cumulative by default), giving cross-panel continuity
    (untouched slots stay identical) and the state-diff story for free."""
    id: str
    base: Scene
    steps: list[Step] = Field(default_factory=list)
    cumulative: bool = True

    @property
    def ir_id(self) -> str:
        return f"steps_{self.id}"

    @model_validator(mode="after")
    def _validate_steps(self) -> Self:
        step_ids = [s.id for s in self.steps]
        if len(step_ids) != len(set(step_ids)):
            raise ValueError(
                f"Step ids must be unique within sequence '{self.id}'"
            )
        base_ids = set(_collect_slot_ids(self.base.slots))
        known = set(base_ids)
        for step in self.steps:
            if not self.cumulative:
                known = set(base_ids)
            for d in step.deltas:
                if d.op == StepOp.ADD:
                    # an ADD introduces a new slot id (via value); register it
                    # leniently so a later delta may target it.
                    if isinstance(d.value, dict):
                        new_id = d.value.get("id") or (
                            (d.value.get("slot") or {}).get("id")
                            if isinstance(d.value.get("slot"), dict) else None
                        )
                        if new_id:
                            known.add(new_id)
                    continue
                if d.target is None:
                    raise ValueError(
                        f"Step '{step.id}' {d.op.value} delta requires a target"
                    )
                token = d.target.split(".", 1)[0]
                if token not in known:
                    raise ValueError(
                        f"Step '{step.id}' delta target '{d.target}' does not "
                        f"resolve to a slot in base scene '{self.base.id}'"
                    )
        return self


class Rail(_IRBase):
    """A named reference line declared on a Tier. ``at`` is a fraction (0..1) of
    the tier's cross-axis extent (0.5 = midline) — resolution-independent."""
    name: str
    axis: RailAxis = RailAxis.Y
    at: float = 0.5

    @field_validator("name")
    @classmethod
    def _name_chars(cls, v: str) -> str:
        return _check_id_chars(v, "Rail name")

    @field_validator("at")
    @classmethod
    def _at_in_range(cls, v: float) -> float:
        if not (0.0 <= v <= 1.0):
            raise ValueError("Rail.at must be between 0 and 1")
        return v

    @property
    def ir_id(self) -> str:
        return f"rail_{self.name}"


class TierEdge(_IRBase):
    """A cross-cell edge held at the Tier level (exempt from the intra-Figure
    relation rule). Endpoints are 'scene.slot.anchor', 'scene@edge', or
    'rail:NAME'; ``on_rail`` clamps both endpoints' cross-axis to that rail."""
    from_ref: str
    to_ref: str
    type: SceneEdgeType = SceneEdgeType.TRANSITION
    on_rail: str | None = None
    label: str | None = None
    style: dict[str, Any] | None = None

    @property
    def ir_id(self) -> str:
        return f"tedge_{self.from_ref}_{self.to_ref}"


class Tier(_IRBase):
    """A full-width horizontal band — the chassis's top-level container, stacked
    vertically (Figure.tiers order = top-to-bottom). Holds a row of scenes OR a
    step_sequence (plus optional gutter overlays), exposes named rails, and
    carries cross-cell transition arrows."""
    id: str
    role: TierRole
    label: str | None = None
    subtitle: str | None = None
    layout: TierLayout = TierLayout.EQUAL_COLUMNS
    height_frac: float | None = None
    scenes: list[Scene] = Field(default_factory=list)
    step_sequence: StepSequence | None = None
    sections: list[str] = Field(default_factory=list)
    rails: list[Rail] = Field(default_factory=list)
    transitions: list[TierEdge] = Field(default_factory=list)
    overlays: list[Scene] = Field(default_factory=list)
    content: Figure | None = None
    style: dict[str, Any] | None = None

    @field_validator("id")
    @classmethod
    def _id_chars(cls, v: str) -> str:
        return _check_id_chars(v, "Tier id")

    @field_validator("height_frac")
    @classmethod
    def _frac_in_range(cls, v: float | None) -> float | None:
        if v is not None and not (0.0 < v <= 1.0):
            raise ValueError("Tier.height_frac must be in (0, 1]")
        return v

    @property
    def ir_id(self) -> str:
        return f"tier_{self.id}"

    @model_validator(mode="after")
    def _validate_tier(self) -> Self:
        modes = [bool(self.scenes), self.step_sequence is not None,
                 self.content is not None]
        if sum(modes) > 1:
            raise ValueError(
                f"Tier '{self.id}' must use at most one of scenes / "
                "step_sequence / content"
            )
        rail_names = [r.name for r in self.rails]
        if len(rail_names) != len(set(rail_names)):
            raise ValueError(
                f"Rail names must be unique within tier '{self.id}'"
            )
        rail_set = set(rail_names)
        scene_ids = {s.id for s in self.scenes} | {s.id for s in self.overlays}
        if self.step_sequence is not None:
            scene_ids.add(self.step_sequence.base.id)
            scene_ids |= {st.id for st in self.step_sequence.steps}
        for te in self.transitions:
            if te.on_rail is not None and te.on_rail not in rail_set:
                raise ValueError(
                    f"Tier '{self.id}' transition on_rail '{te.on_rail}' is "
                    "not a declared rail"
                )
            for ref in (te.from_ref, te.to_ref):
                if ref.startswith("rail:"):
                    if ref[len("rail:"):] not in rail_set:
                        raise ValueError(
                            f"Tier '{self.id}' transition references unknown "
                            f"rail '{ref}'"
                        )
                else:
                    scene_token = ref.split(".", 1)[0].split("@", 1)[0]
                    if scene_token not in scene_ids:
                        raise ValueError(
                            f"Tier '{self.id}' transition references unknown "
                            f"scene '{scene_token}' in '{ref}'"
                        )
        return self


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


# Resolve forward refs. Scene.content / Tier.content reference Figure (defined
# after them) and Slot is self-recursive, so every model is rebuilt once all
# classes — Figure included — exist. Order-insensitive; Figure last by habit.
Slot.model_rebuild()
Attach.model_rebuild()
SceneEdge.model_rebuild()
Scene.model_rebuild()
StepDelta.model_rebuild()
Step.model_rebuild()
StepSequence.model_rebuild()
Rail.model_rebuild()
TierEdge.model_rebuild()
Tier.model_rebuild()
Panel.model_rebuild()
Figure.model_rebuild()
