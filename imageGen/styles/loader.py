"""Journal-style preset loader.

Phase 4. Turns a preset name (e.g. "cell_press", "nature", "acs") into
a flat dict ready to feed into any primitive as `style_dict=…`. Phase 5
renderer will call `load_style(name)` once and thread the result through
every primitive call, flipping a figure's aesthetic with one argument.

Design (locked-in for v1):
  - Presets live as JSON files in this directory; one file per preset,
    name = filename stem.
  - Each preset's `overrides` block is *sparse* — it enumerates only
    the keys it wants to change from primitive `DEFAULT_STYLE`
    defaults. Each primitive already does
    `{**DEFAULT_STYLE, **(style_dict or {})}` so missing keys fall
    back cleanly.
  - `palette` (8 entries) is informational + grep-able. The loader
    does NOT auto-derive primitive fills from palette indices; each
    `*_fill` override is explicit. Palette-to-key auto-derivation is
    flagged in BACKLOG.md as a V2 stretch.
  - `meta` (name + description) is required so a glance at the JSON
    explains what the preset is for.
  - Validation uses the same Pydantic v2 + `extra="forbid"` idiom as
    `ir/schema.py`, keeping the discipline consistent with IR fixtures.

V2 / ST5 — unknown-key validation:
  ``KNOWN_STYLE_KEYS`` is assembled at import time by unioning every
  primitive module's ``DEFAULT_STYLE`` key set. ``load_preset_full``
  emits a ``UserWarning`` for any key in ``overrides`` that isn't in
  this set — a cheap typo guard that never breaks callers (warn, not
  raise).  Add keys here when a new primitive module is introduced.

Layout-params (`pathway_canvas`, `panel_margin`, `pathway_seed`, …)
are NOT in the preset — they're geometric/behavioral and caller-set.
A future preset could carry a `layout_overrides` block; flagged in
BACKLOG as deferred.

Phase 5 renderer coupling:
  The renderer calls `load_style(name)` and passes the returned dict
  into every primitive call. Layout engines forward it via their
  existing `style_dict=` kwarg, untouched.
"""
from __future__ import annotations

import json
import re
import warnings
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

# Palette → primitive-fill recipe (R6 split). Re-exported here so
# ``PALETTE_RECIPE`` and ``apply_palette_recipe`` stay importable from
# ``imageGen.styles.loader`` unchanged; ``load_style`` calls the latter.
from imageGen.styles._palette import PALETTE_RECIPE, apply_palette_recipe


PRESET_DIR = Path(__file__).parent
DEFAULT_PRESET = "cell_press"

_HEX_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")

# ---------------------------------------------------------------------------
# V2 / ST5: master key set — union of every primitive module's DEFAULT_STYLE.
# Assembled once at import time; used by load_preset_full to warn on typos.
# When adding a new primitive module, import it below and add it to the list.
# ---------------------------------------------------------------------------

def _collect_known_style_keys() -> frozenset[str]:
    """Return the union of all primitive DEFAULT_STYLE key sets."""
    from imageGen.primitives import (  # noqa: PLC0415 (local import intentional)
        arrows,
        cells,
        chemistry,
        lab_equipment,
        membranes,
        nucleic_acids,
        proteins,
    )
    keys: set[str] = set()
    for mod in (arrows, cells, chemistry, lab_equipment, membranes, nucleic_acids, proteins):
        keys |= set(mod.DEFAULT_STYLE.keys())
    return frozenset(keys)


KNOWN_STYLE_KEYS: frozenset[str] = _collect_known_style_keys()


# ---------------------------------------------------------------------------
# V2 / ST2: aesthetic layout-param key set.
# These are the *aesthetic* knobs from each layout engine's *_DEFAULT_PARAMS
# dict — colors, strokes, font sizes/families — that make sense to carry in a
# journal preset. Geometric/behavioral knobs (canvas size, seed, padding, …)
# are caller-set and intentionally excluded.
#
# Hardcoded here (not imported from layout engines) to avoid a circular import:
# styles/ sits below layout/ in the dependency graph, so importing
# pathway_layout here would create a cycle.
# Update this set when a new aesthetic param is added to any layout engine.
# ---------------------------------------------------------------------------

KNOWN_LAYOUT_PARAMS: frozenset[str] = frozenset({
    # pathway_layout aesthetic keys
    "pathway_band_fill",
    "pathway_band_stroke",
    "pathway_band_stroke_width",
    "pathway_band_label_color",
    "pathway_band_label_size",
    "pathway_band_label_family",
    # panel_layout aesthetic keys
    "panel_border_stroke",
    "panel_border_stroke_width",
    "panel_border_fill",
    "panel_title_color",
    "panel_title_size",
    "panel_title_family",
    "panel_title_weight",
})


class _PresetMeta(BaseModel):
    model_config = {"extra": "forbid"}
    name: str
    description: str


class StylePreset(BaseModel):
    """Validated journal-style preset.

    The `overrides` dict is the payload primitives consume (style_dict=).
    `layout_overrides` (V2/ST2) carries aesthetic layout-engine knobs
    (colors, strokes, font sizes) that belong to the preset's visual
    identity but live in layout engines rather than primitives. Pass it
    as `layout_params=` to any layout engine call; the engine merges it
    onto its own *_DEFAULT_PARAMS.

    `inherits` (V2/ST3): optional name of a parent preset. The parent's
    `overrides` and `layout_overrides` are merged as a base layer; child
    keys win on conflicts. `palette` and `meta` are always the child's
    (they define the preset's identity). `palette_recipe` is inherited
    from the parent when the child does not set its own.

    `meta` and `palette` are introspectable via `load_preset_full(name)`
    for callers (e.g. tests, future renderer chrome) that need them.
    """
    model_config = {"extra": "forbid"}

    meta: _PresetMeta
    palette: list[str] = Field(min_length=8, max_length=8)
    palette_recipe: list[list[str]] | None = Field(default=None)
    inherits: str | None = Field(default=None)
    overrides: dict[str, Any] = Field(default_factory=dict)
    layout_overrides: dict[str, Any] = Field(default_factory=dict)

    @field_validator("palette")
    @classmethod
    def _validate_palette_hex(cls, v: list[str]) -> list[str]:
        bad = [c for c in v if not _HEX_COLOR_RE.match(c)]
        if bad:
            raise ValueError(
                f"palette entries must be 7-char #RRGGBB hex; bad entries: {bad!r}"
            )
        return v

    @field_validator("palette_recipe")
    @classmethod
    def _validate_recipe_len(cls, v: list[list[str]] | None) -> list[list[str]] | None:
        if v is not None and len(v) != 8:
            raise ValueError(
                f"palette_recipe must have exactly 8 slots (one per palette colour); "
                f"got {len(v)}"
            )
        return v


def _preset_path(name: str) -> Path:
    return PRESET_DIR / f"{name}.json"


def list_presets() -> list[str]:
    """Discover preset names by listing styles/*.json (sorted)."""
    return sorted(p.stem for p in PRESET_DIR.glob("*.json"))


def list_style_keys() -> list[str]:
    """Return the sorted vocabulary of recognised ``style_dict`` keys (P0c.2).

    These are the keys a preset's ``overrides`` block (and any per-figure /
    per-node ``style`` dict) may set — the union of every primitive module's
    ``DEFAULT_STYLE`` (``KNOWN_STYLE_KEYS``). It is the same set ``load_preset_full``
    validates ``overrides`` against, so this is the authoritative inventory rather
    than a hand-kept list. The aesthetic layout params (``KNOWN_LAYOUT_PARAMS``)
    ride a separate channel (``load_layout_params``) and are intentionally not
    folded in here; the ``styles`` CLI prints them under their own heading.
    """
    return sorted(KNOWN_STYLE_KEYS)


def _load_and_warn(name: str) -> StylePreset:
    """Load, validate, and emit unknown-key warnings for a single preset file.

    Does NOT resolve ``inherits`` — call ``_resolve_preset`` for that.
    """
    path = _preset_path(name)
    if not path.exists():
        available = ", ".join(list_presets()) or "(none)"
        raise FileNotFoundError(
            f"No style preset named {name!r} in {PRESET_DIR}; "
            f"available: {available}"
        )
    preset = StylePreset.model_validate(json.loads(path.read_text()))
    unknown_style = sorted(set(preset.overrides) - KNOWN_STYLE_KEYS)
    if unknown_style:
        warnings.warn(
            f"Style preset {name!r} contains unknown override key(s): "
            f"{unknown_style!r}. Check for typos against KNOWN_STYLE_KEYS in "
            f"imageGen.styles.loader.",
            UserWarning,
            stacklevel=3,
        )
    unknown_layout = sorted(set(preset.layout_overrides) - KNOWN_LAYOUT_PARAMS)
    if unknown_layout:
        warnings.warn(
            f"Style preset {name!r} contains unknown layout_override key(s): "
            f"{unknown_layout!r}. Check for typos against KNOWN_LAYOUT_PARAMS in "
            f"imageGen.styles.loader.",
            UserWarning,
            stacklevel=3,
        )
    return preset


def merge_style(*layers: dict | None) -> dict:
    """Shallow, later-wins merge of style layers — the one chassis/preset idiom.

    Each later layer's keys win over earlier ones (``{**a, **b, **c}``), and
    ``None``/empty layers are skipped. This is the *same* shallow semantics the
    preset ``inherits`` chain uses (`_resolve_preset`) and the V3 chassis style
    cascade (`base preset → tier → scene → slot/step`) uses — kept in one place
    so there is never a second merge implementation to drift.

    NOTE: the merge is intentionally SHALLOW. A nested dict value (e.g. a
    molecule slot's ``anchor_names``) is replaced wholesale by a later layer,
    not deep-merged. Chassis style keys must therefore stay flat scalars; the
    moment a real nested style sub-dict is introduced this clobbers it. (No
    preset or chassis layer sets such a key today — see V3 "Do not" list.)
    """
    out: dict = {}
    for layer in layers:
        if layer:
            out.update(layer)
    return out


def _resolve_preset(name: str, chain: tuple[str, ...]) -> StylePreset:
    """Recursively load a preset, merging ancestor ``overrides`` under child keys.

    ``chain`` is the ancestor path used for cycle detection; callers pass ``()``
    at the root. Raises ``ValueError`` on circular ``inherits`` references.
    """
    if name in chain:
        cycle = " → ".join(chain + (name,))
        raise ValueError(f"Circular preset inheritance detected: {cycle}")
    preset = _load_and_warn(name)
    if preset.inherits is None:
        return preset
    parent = _resolve_preset(preset.inherits, chain + (name,))
    # Merge: parent as base layer, child wins on every key conflict.
    # palette and meta are identity fields — always the child's.
    return StylePreset.model_construct(
        meta=preset.meta,
        palette=preset.palette,
        palette_recipe=(
            preset.palette_recipe if preset.palette_recipe is not None
            else parent.palette_recipe
        ),
        inherits=None,  # inheritance already resolved
        overrides=merge_style(parent.overrides, preset.overrides),
        layout_overrides=merge_style(parent.layout_overrides, preset.layout_overrides),
    )


def load_preset_full(name: str = DEFAULT_PRESET) -> StylePreset:
    """Load + validate a preset; return the typed StylePreset model.

    Resolves ``inherits`` chains (V2/ST3): the returned preset has fully
    merged ``overrides`` and ``layout_overrides`` with child keys winning.

    Useful for tests + future renderer chrome that needs ``meta`` /
    ``palette``. Most callers want ``load_style`` instead.

    V2 / ST5: emits a ``UserWarning`` for any key in ``overrides`` that
    is not present in ``KNOWN_STYLE_KEYS`` (the union of all primitive
    ``DEFAULT_STYLE`` dicts). This is a typo guard — it never raises so
    callers are never broken by it.

    Raises:
        FileNotFoundError: name has no matching JSON in styles/.
        pydantic.ValidationError: schema check failed (missing meta,
            palette wrong length, malformed hex, unknown extra fields).
        ValueError: circular ``inherits`` chain detected.
    """
    return _resolve_preset(name, ())


def load_style(name: str = DEFAULT_PRESET) -> dict:
    """Load a journal preset → flat style dict for primitives.

    Merges in two layers (later wins):
    1. Palette-recipe fill derivation — ``apply_palette_recipe(palette, preset.palette_recipe)``
    2. Explicit ``overrides`` from the preset JSON

    This means a preset can omit ``*_fill`` entries and rely on the palette
    recipe to supply them; explicit overrides are still respected. Existing
    presets that spell out all fills are unaffected — their overrides win.

    Args:
        name: Preset stem (e.g. "cell_press"). Defaults to cell_press.

    Returns:
        Flat style dict. Pass as ``style_dict=…`` to any primitive.

    Raises:
        FileNotFoundError: unknown preset name.
        pydantic.ValidationError: malformed preset JSON.
    """
    preset = load_preset_full(name)
    recipe_style = apply_palette_recipe(preset.palette, preset.palette_recipe)
    return merge_style(recipe_style, preset.overrides)


def load_layout_params(name: str = DEFAULT_PRESET) -> dict:
    """Load a journal preset → aesthetic layout-params dict for layout engines.

    V2 / ST2. Returns the preset's ``layout_overrides`` block — the
    aesthetic layout-engine knobs (band colors, panel border, font sizes, …)
    that belong to the preset's visual identity. Pass directly as
    ``layout_params=…`` to any layout engine; the engine merges it onto
    its own ``*_DEFAULT_PARAMS``, so geometric/behavioral knobs not in
    the preset are unaffected.

    Args:
        name: Preset stem (e.g. "cell_press"). Defaults to cell_press.

    Returns:
        The preset's ``layout_overrides`` block as a flat dict. Empty dict
        when the preset carries no layout overrides (any engine's own
        defaults apply in full).

    Raises:
        FileNotFoundError: unknown preset name.
        pydantic.ValidationError: malformed preset JSON.
    """
    return load_preset_full(name).layout_overrides
