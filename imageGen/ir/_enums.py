"""IR enums (R2 split).

Internals of :mod:`imageGen.ir.schema`. Holds every ``str``/``Enum`` kind enum —
the v2 leaf enums (`EntityType`, `CompartmentType`, `RelationType`,
`RelationLabelSide`, `Archetype`, `AnnotationType`, `NamedSlot`) and the V3
scene-chassis enums (`TierRole`, `TierLayout`, `SlotKind`, `AttachEdge`,
`StepOp`, `SceneEdgeType`, `RailAxis`). This is the dependency leaf: it imports
nothing from the other schema sub-modules, and both `_v2_models` and `_v3_models`
import their enums from here. `schema` re-exports all of them unchanged.
"""
from __future__ import annotations

from enum import Enum


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
