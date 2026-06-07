"""Runtime loader for embedded, cleaned SVG icon assets (Bioicons; DECISIONS D9).

Assets live in ``imageGen/assets/icons/<name>.svg`` — namespace-free, CSS-inlined,
id-namespaced SVGs produced by ``tools/ingest_icon.py``. :func:`load_icon`
returns an origin-normalized ``svgwrite`` Group (spanning ``[0,w]×[0,h]`` from the
asset's ``viewBox``) plus that intrinsic ``(w, h)``, so the entity adapters can
scale-to-fit it into a slot via the usual ``_fit_icon`` path.

Faithful color: the asset's own ``fill``/``stroke`` are preserved verbatim (the
icons intentionally do not retheme — see DECISIONS D9). The returned Group is
tagged ``data-icon-credit="<name>"`` so ``render/credits`` can collect the icons
a figure uses for attribution.

Embedding mechanism: the cleaned asset is parsed with stdlib ElementTree and the
shape subtree is handed to ``svgwrite`` *verbatim* via :class:`_EmbeddedSVG`
(a thin BaseElement whose ``get_xml`` returns the prepared element). This avoids
lossily round-tripping every attribute through svgwrite's shape classes. Assets
are namespace-free so they inherit the Drawing's default SVG namespace cleanly.
"""
from __future__ import annotations

import copy
import xml.etree.ElementTree as ET
from functools import lru_cache
from pathlib import Path

import svgwrite.base
import svgwrite.container

_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets" / "icons"


class IconNotFoundError(FileNotFoundError):
    """Raised when an embedded icon asset does not exist."""


class _EmbeddedSVG(svgwrite.base.BaseElement):
    """svgwrite element that emits a pre-built stdlib ElementTree subtree as-is."""

    elementname = "g"

    def __init__(self, xml_element: ET.Element) -> None:
        super().__init__()
        self._xml_element = xml_element

    def get_xml(self) -> ET.Element:  # noqa: D401 — svgwrite hook
        return self._xml_element


def _parse_viewbox(root: ET.Element) -> tuple[float, float, float, float]:
    """Return (min_x, min_y, w, h) from the asset's viewBox (or width/height)."""
    vb = root.get("viewBox")
    if vb:
        parts = [float(p) for p in vb.replace(",", " ").split()]
        if len(parts) == 4:
            return (parts[0], parts[1], parts[2], parts[3])
    w = float(root.get("width", "0") or 0)
    h = float(root.get("height", "0") or 0)
    return (0.0, 0.0, w, h)


@lru_cache(maxsize=None)
def _cached_asset(name: str) -> tuple[ET.Element, tuple[float, float]]:
    """Parse + normalize an asset once: a `<g translate>` wrapper + intrinsic size."""
    asset = _ASSETS_DIR / f"{name}.svg"
    if not asset.exists():
        raise IconNotFoundError(f"no embedded icon asset {name!r} at {asset}")
    root = ET.fromstring(asset.read_text())
    min_x, min_y, w, h = _parse_viewbox(root)
    wrapper = ET.Element("g")
    if min_x or min_y:
        wrapper.set("transform", f"translate({-min_x},{-min_y})")
    for child in list(root):
        wrapper.append(child)
    return wrapper, (w, h)


def load_icon(name: str) -> tuple[svgwrite.container.Group, tuple[float, float]]:
    """Load embedded icon ``name`` → (origin-normalized Group, intrinsic (w, h)).

    The Group spans ``[0,w]×[0,h]`` and is tagged ``data-icon-credit`` for the
    attribution pipeline. Raises :class:`IconNotFoundError` if the asset is absent.
    """
    wrapper, size = _cached_asset(name)
    g = svgwrite.container.Group()
    g._parameter.debug = False  # allow the data-* attribute
    g.attribs["data-icon-credit"] = name
    g.add(_EmbeddedSVG(copy.deepcopy(wrapper)))  # deepcopy: one ET node per render
    return g, size


def available_icons() -> list[str]:
    """Sorted asset names present in the icon store (no extension)."""
    if not _ASSETS_DIR.exists():
        return []
    return sorted(p.stem for p in _ASSETS_DIR.glob("*.svg"))
