"""IR schema — aggregator (R2 decomposition).

The IR is load-bearing (see CONTRIBUTING.md). This module is now a thin
aggregator that re-exports the full schema surface from three `_`-prefixed
sibling modules and runs the single `model_rebuild()` block that resolves the
cross-model forward references. Every name historically importable from
``imageGen.ir.schema`` stays importable here unchanged.

  - ``_enums``      — every kind enum (v2 + V3 scene-chassis).
  - ``_v2_models``  — `_IRBase` + the v2 models (`Entity` … `Panel`, `Figure`).
  - ``_v3_models``  — the V3 scene-chassis models (`Slot` … `Tier`) +
                      `_check_id_chars` / `_collect_slot_ids`.

`Figure` (in `_v2_models`) references `Tier` (in `_v3_models`) and the V3 models
reference `Figure` — a true type-graph cycle. It is resolved without an import
cycle: the sub-modules define their classes but do NOT rebuild; the
`model_rebuild()` block below runs after all models are imported into this
module's namespace, so every forward ref resolves here (exactly as the original
single-file module resolved them at module end). The block is load-bearing under
`from __future__ import annotations` — do not remove it.
"""
from __future__ import annotations

# Re-export the stdlib/pydantic names that HEAD's single-file schema imported at
# module level, so they stay importable from ``imageGen.ir.schema`` exactly as
# before (e.g. ``from imageGen.ir.schema import Field``). The aggregator does not
# use them directly — they are preserved purely for import-surface parity.
from enum import Enum  # noqa: F401
from typing import Any, Self  # noqa: F401

from pydantic import (  # noqa: F401
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from imageGen.ir._enums import (
    AnnotationType,
    Archetype,
    AttachEdge,
    CompartmentType,
    EntityType,
    NamedSlot,
    RailAxis,
    RelationLabelSide,
    RelationType,
    SceneEdgeType,
    SlotKind,
    StepOp,
    TierLayout,
    TierRole,
)
from imageGen.ir._v2_models import (
    Annotation,
    Compartment,
    Entity,
    Figure,
    GlossaryEntry,
    Panel,
    ReactionConditions,
    Relation,
    _IRBase,
)
from imageGen.ir._v3_models import (
    Attach,
    Rail,
    Scene,
    SceneEdge,
    Slot,
    Step,
    StepDelta,
    StepSequence,
    Tier,
    TierEdge,
    _check_id_chars,
    _collect_slot_ids,
)


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
