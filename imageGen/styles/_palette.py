"""Palette → primitive-fill recipe.

Internals of :mod:`imageGen.styles.loader` (R6 split). Holds the palette-to-key
recipe (`PALETTE_RECIPE`) and the pure derivation function (`apply_palette_recipe`)
that turns an 8-colour palette into a flat style dict. `loader.load_style` calls
this and merges the result *under* the preset's explicit overrides so overrides
always win. Both names are re-exported from `loader` so the public surface is
unchanged.
"""
from __future__ import annotations


# ---------------------------------------------------------------------------
# V2 / ST1: palette-to-primitive fill recipe.
# Each slot i maps palette[i] to a list of style keys that should receive
# that colour. apply_palette_recipe() derives a flat style dict from any
# 8-colour palette; load_style() merges it under explicit overrides so
# overrides always win. Presets can supply a custom palette_recipe to
# redefine the mapping; None means "use PALETTE_RECIPE".
# ---------------------------------------------------------------------------

PALETTE_RECIPE: list[list[str]] = [
    ["protein_fill"],               # palette[0] — generic entity / protein fill
    ["kinase_fill"],                # palette[1] — kinase / enzyme fill
    ["receptor_fill"],              # palette[2] — receptor fill
    ["gpcr_helix_fill"],            # palette[3] — GPCR helix fill
    ["tf_fill"],                    # palette[4] — transcription factor fill
    ["dna_strand1_stroke"],         # palette[5] — DNA strand colour
    ["rna_stroke"],                 # palette[6] — RNA stroke colour
    ["chromatin_nucleosome_fill"],  # palette[7] — chromatin / histone fill
]


def apply_palette_recipe(
    palette: list[str],
    recipe: list[list[str]] | None = None,
) -> dict[str, str]:
    """Derive a flat style dict from a palette using a slot→key recipe.

    Args:
        palette: Exactly 8 ``#RRGGBB`` hex strings.
        recipe: List of 8 slots; slot ``i`` is a list of style keys to set
                to ``palette[i]``. Defaults to ``PALETTE_RECIPE`` when ``None``.

    Returns:
        Flat ``{style_key: hex_colour}`` dict. When multiple slots map to the
        same key (unusual), the last slot wins (deterministic, palette-order).
        Always call this before merging explicit overrides so overrides win.
    """
    active = recipe if recipe is not None else PALETTE_RECIPE
    result: dict[str, str] = {}
    for colour, keys in zip(palette, active):
        for key in keys:
            result[key] = colour
    return result
