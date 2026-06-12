"""IR V3 scene-chassis models (R2 split).

Internals of :mod:`imageGen.ir.schema`. Holds the V3 scene-chassis models and
their id helpers:
  Layer A = relative-anchor scene graph (`Slot`/`Attach`/`SceneEdge`/`Scene`);
  Layer B = tier compositor + rails (`Rail`/`TierEdge`/`Tier`);
  Layer C = step/state deltas (`StepDelta`/`Step`/`StepSequence`);
  plus `_check_id_chars` and `_collect_slot_ids`.

Depends one-directionally on `_v2_models` for `_IRBase` (the shared base) and
`Figure` (referenced by `Scene.content` / `Tier.content`). The forward refs are
evaluated by the single `model_rebuild()` block kept in `schema.py`.
"""
from __future__ import annotations

from typing import Any, Self

from pydantic import Field, field_validator, model_validator

from imageGen.ir._enums import (
    AttachEdge,
    RailAxis,
    SceneEdgeType,
    SlotKind,
    StepOp,
    TierLayout,
    TierRole,
)
from imageGen.ir._v2_models import Figure, _IRBase


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
        # P0a.6: statically-known slot ids per scene (scenes + overlays only).
        # step_sequence scenes are excluded — their slot set is built by step
        # deltas at expansion time, so a transition's slot token into one stays a
        # layout-time concern. The dynamic atom segment of every ref is likewise
        # left for layout (P0a.5 aggregates those); only the slot token is known
        # at build, mirroring Scene._validate_scene's connect-ref check.
        scene_slots = {s.id: set(_collect_slot_ids(s.slots))
                       for s in (*self.scenes, *self.overlays)}
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
                    # A 'scene.slot.anchor' ref also names a slot; validate that
                    # token now ('scene@edge' frame refs have no slot token).
                    if "@" not in ref and "." in ref and scene_token in scene_slots:
                        slot_token = ref.split(".")[1]
                        if slot_token not in scene_slots[scene_token]:
                            raise ValueError(
                                f"Tier '{self.id}' transition references unknown "
                                f"slot '{slot_token}' in '{ref}'"
                            )
        return self
