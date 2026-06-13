"""Icon attribution collection for embedded Bioicons (DECISIONS D9).

Embedded icons carry a per-icon license recorded in
``imageGen/assets/icons/credits.json`` (written by the ingest tool). A figure's
*used* icons are derived deterministically from the IR — each entity's resolved
primitive is looked up in ``primitive_specs.ICON_ASSETS`` — so attribution never
depends on scanning rendered output.

Two outputs (the user-approved policy):
- :func:`credit_lines` — short on-figure lines for **CC-BY** icons (CC0/MIT need
  no figure credit), shown as the Credits section of the unified info box.
- :func:`write_credits_sidecar` — a ``<output>.credits.txt`` listing **every**
  used icon (CC0/MIT included) with full author/license/source/modifications.

Both are no-ops until a batch registers embedded-icon adapters (``ICON_ASSETS``
is empty), so this wiring is inert — not dead — in the meantime.
"""
from __future__ import annotations

import json
from pathlib import Path

from imageGen.ir.schema import Figure
from imageGen.layout._geom import resolve_entity_primitive
from imageGen.primitives.primitive_specs import ICON_ASSETS

_CREDITS_JSON = Path(__file__).resolve().parent.parent / "assets" / "icons" / "credits.json"


def _load_credits() -> dict:
    """Parse ``assets/icons/credits.json`` → {asset: record}; {} when absent."""
    try:
        return json.loads(_CREDITS_JSON.read_text())
    except (FileNotFoundError, ValueError):
        return {}


def _walk(fig: Figure):
    """Yield ``fig`` and every nested panel content figure."""
    yield fig
    for panel in fig.panels:
        yield from _walk(panel.content)


def icon_assets_in_figure(ir: Figure) -> list[str]:
    """Ordered, de-duplicated asset names for the embedded icons ``ir`` uses."""
    seen: set[str] = set()
    out: list[str] = []
    for fig in _walk(ir):
        for e in fig.entities:
            asset = ICON_ASSETS.get(resolve_entity_primitive(e))
            if asset and asset not in seen:
                seen.add(asset)
                out.append(asset)
    return out


def _requires_attribution(license_str: str) -> bool:
    """True for any CC-BY family license (CC-BY, CC-BY-SA) — CC0/MIT need none."""
    return license_str.upper().replace(" ", "").startswith("CC-BY")


def _short_line(rec: dict) -> str:
    title = rec.get("title") or rec.get("name") or "icon"
    author = rec.get("author") or "unknown"
    lic = rec.get("license") or ""
    suffix = ", modified" if rec.get("modifications") else ""
    return f"{title} — {author} ({lic}{suffix})"


def credit_lines(ir: Figure, mode: bool | str = "auto") -> list[str]:
    """On-figure Credits lines for CC-BY icons used by ``ir``.

    ``mode`` False suppresses the section entirely; "auto"/True includes a line
    per distinct CC-BY icon (CC0/MIT contribute nothing on-figure).
    """
    if mode is False:
        return []
    creds = _load_credits()
    lines: list[str] = []
    for asset in icon_assets_in_figure(ir):
        rec = creds.get(asset)
        if rec and _requires_attribution(rec.get("license", "")):
            lines.append(_short_line(rec))
    return lines


def write_credits_sidecar(ir: Figure, output_path: Path, mode: bool | str = "auto") -> Path | None:
    """Write ``<output>.credits.txt`` for every embedded icon used; return its
    path, or ``None`` when the figure uses no embedded icons.

    Independent of ``mode`` (the sidecar is the durable record); ``mode`` only
    governs the on-figure Credits section.
    """
    assets = icon_assets_in_figure(ir)
    if not assets:
        return None
    creds = _load_credits()
    out = Path(output_path)
    sidecar = out.with_name(out.name + ".credits.txt")
    blocks = ["Icon attributions for this figure (source: Bioicons).", ""]
    for asset in assets:
        rec = creds.get(asset, {})
        blocks.append(f"- {rec.get('title', asset)} [{asset}]")
        blocks.append(f"    author:  {rec.get('author', 'unknown')}")
        blocks.append(f"    license: {rec.get('license', 'unknown')}  {rec.get('license_url', '')}".rstrip())
        if rec.get("source_url"):
            blocks.append(f"    source:  {rec['source_url']}")
        if rec.get("modifications"):
            blocks.append(f"    changes: {rec['modifications']}")
        blocks.append("")
    sidecar.write_text("\n".join(blocks))
    return sidecar
