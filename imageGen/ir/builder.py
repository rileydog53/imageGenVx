"""IR builder — a thin, tuple-friendly convenience layer over the Pydantic schema.

The IR schema in `imageGen.ir.schema` is the single source of truth: every
output from this module is run through `Figure.model_validate(...)`, so all
existing validators (id uniqueness, relation-source/target checks,
entity.location → compartment binding, panel grid overlap, leaf-XOR-panel)
still fire and the same `pydantic.ValidationError` surfaces on bad input.

This module exists to save tokens for LLM callers (and keystrokes for human
callers) by accepting:

  * positional tuples instead of named dicts, and
  * a small number of friendly kwargs (`style=` instead of `style_preset=`).

Nothing here adds new IR semantics; it is purely an ergonomic wrapper.

Example::

    from imageGen.ir.builder import build

    fig = build(
        "pathway",
        entities=[
            ("ras", "protein", "Ras"),
            ("raf", "kinase", "Raf"),
        ],
        relations=[
            ("ras", "activates", "raf"),
        ],
        style="nature",
    )

The returned object is a fully validated `Figure` — pass it straight to
`imageGen.render.compositor.render_figure`.
"""
from __future__ import annotations

from typing import Any

from imageGen.ir.schema import Figure


# ---------------------------------------------------------------------------
# Public helpers — explicit constructors for callers who prefer named kwargs
# over positional tuples. Each returns a plain dict so callers can mix-and-
# match (`build(..., entities=[entity("a", "protein", "A"), ("b", "kinase", "B")])`).
# ---------------------------------------------------------------------------


def entity(
    id: str,
    type: str,
    label: str,
    location: str | None = None,
    style: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an entity dict. `type` accepts any `EntityType` value string."""
    d: dict[str, Any] = {"id": id, "type": type, "label": label}
    if location is not None:
        d["location"] = location
    if style is not None:
        d["style"] = style
    return d


def relation(
    source: str,
    type: str,
    target: str,
    label: str | None = None,
    conditions: dict[str, Any] | None = None,
    label_side: str | None = None,
) -> dict[str, Any]:
    """Build a relation dict. Argument order reads naturally as `source verb target`.

    ``label_side`` (FR8): optional ``"above"``/``"below"``/``"left"``/``"right"``
    hint for which side of the arrow the label prefers — use it to split the two
    labels on a parallel forward/back edge pair.
    """
    d: dict[str, Any] = {"source": source, "target": target, "type": type}
    if label is not None:
        d["label"] = label
    if conditions is not None:
        d["conditions"] = conditions
    if label_side is not None:
        d["label_side"] = label_side
    return d


def compartment(id: str, type: str, label: str) -> dict[str, Any]:
    """Build a compartment dict. `type` accepts any `CompartmentType` value string."""
    return {"id": id, "type": type, "label": label}


# ---------------------------------------------------------------------------
# Tuple normalisers — accept either a tuple (most common LLM/CLI shape), a
# dict (when the caller already has one), or a Pydantic model (passthrough).
# Tuples are positional and short on purpose; longer specs should use a dict.
# ---------------------------------------------------------------------------


def _normalize_entity(item: Any) -> dict[str, Any] | Any:
    """Coerce `item` into an entity dict.

    Tuple shapes: ``(id, type, label[, location[, primitive]])``.

    FR7: the optional 5th element is a primitive-override name (e.g. ``"antibody"``,
    ``"gpcr"``), wired through as ``style={"primitive": <name>}`` — the same hook
    dict-form entities already expose via ``style.primitive``. This unblocks
    domain glyphs (the IgG antibody, etc.) from the tuple shorthand. Pass
    ``location=None`` when you need a primitive but no compartment, e.g.
    ``("igg", "protein", "IgG", None, "antibody")``.
    """
    if isinstance(item, dict):
        return item
    if isinstance(item, tuple):
        if len(item) == 3:
            return entity(*item)
        if len(item) == 4:
            return entity(item[0], item[1], item[2], location=item[3])
        if len(item) == 5:
            return entity(
                item[0], item[1], item[2],
                location=item[3], style={"primitive": item[4]},
            )
        raise ValueError(
            f"entity tuple must have 3 to 5 elements "
            f"(id, type, label[, location[, primitive]]); "
            f"got {len(item)}: {item!r}"
        )
    return item  # Pydantic Entity or unknown — let Figure.model_validate complain.


def _normalize_relation(item: Any) -> dict[str, Any] | Any:
    """Coerce `item` into a relation dict. Tuples: (source, type, target[, label])."""
    if isinstance(item, dict):
        return item
    if isinstance(item, tuple):
        if len(item) == 3:
            return relation(*item)
        if len(item) == 4:
            return relation(item[0], item[1], item[2], label=item[3])
        raise ValueError(
            f"relation tuple must have 3 or 4 elements (source, type, target[, label]); "
            f"got {len(item)}: {item!r}"
        )
    return item


def _normalize_compartment(item: Any) -> dict[str, Any] | Any:
    """Coerce `item` into a compartment dict. Tuples: (id, type, label)."""
    if isinstance(item, dict):
        return item
    if isinstance(item, tuple):
        if len(item) == 3:
            return compartment(*item)
        raise ValueError(
            f"compartment tuple must have 3 elements (id, type, label); "
            f"got {len(item)}: {item!r}"
        )
    return item


# ---------------------------------------------------------------------------
# Top-level builder
# ---------------------------------------------------------------------------


def build(
    archetype: str,
    *,
    entities: list[Any] | None = None,
    relations: list[Any] | None = None,
    compartments: list[Any] | None = None,
    panels: list[Any] | None = None,
    annotations: list[Any] | None = None,
    style: str | None = None,
    title: str | None = None,
    caption: str | None = None,
    layout_hint: str | None = None,
) -> Figure:
    """Build and validate a `Figure` from a flat, tuple-friendly spec.

    Args:
        archetype: Archetype value string ("pathway", "reaction_scheme",
            "workflow", "cellular_schematic", "mechanism_cartoon").
        entities: List of entity tuples/dicts. Tuples may be
            `(id, type, label)` or `(id, type, label, location)`.
        relations: List of relation tuples/dicts. Tuples may be
            `(source, type, target)` or `(source, type, target, label)`.
        compartments: List of compartment tuples/dicts. Tuples are
            `(id, type, label)`.
        panels: List of panel dicts (panels nest a `Figure`, so use dicts here).
        annotations: List of annotation dicts.
        style: Convenience alias for `style_preset` ("cell_press", "nature",
            "acs"). Falls through to the schema default when omitted.
        title: Figure title.
        caption: Figure caption.

    Returns:
        A fully validated `Figure` — every schema validator has already fired.

    Raises:
        pydantic.ValidationError: when the resulting figure fails schema
            validation (unknown enum value, dangling relation reference,
            duplicate id, leaf-XOR-panel violation, etc).
        ValueError: when a tuple has the wrong arity for its slot.
    """
    data: dict[str, Any] = {"archetype": archetype}
    if title is not None:
        data["title"] = title
    if caption is not None:
        data["caption"] = caption
    if style is not None:
        data["style_preset"] = style
    if layout_hint is not None:
        data["layout_hint"] = layout_hint
    if entities:
        data["entities"] = [_normalize_entity(e) for e in entities]
    if compartments:
        data["compartments"] = [_normalize_compartment(c) for c in compartments]
    if relations:
        data["relations"] = [_normalize_relation(r) for r in relations]
    if panels:
        data["panels"] = list(panels)
    if annotations:
        data["annotations"] = list(annotations)
    return Figure.model_validate(data)
