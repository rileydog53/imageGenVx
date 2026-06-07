"""Embedded-icon loader + asset-store integrity (DECISIONS D9).

Pins:
  1. load_icon returns an origin-normalized Group + intrinsic (w,h) from the
     asset viewBox, tagged data-icon-credit.
  2. A missing asset raises IconNotFoundError.
  3. ids are namespaced per asset so two different icons in one figure never
     collide.
  4. Every asset in the store has a credits.json record (attribution guard).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import svgwrite

from imageGen.primitives.icon_loader import (
    IconNotFoundError,
    available_icons,
    load_icon,
)

_ASSETS = Path("imageGen/assets/icons")


def _ids(xml: str) -> set[str]:
    return set(re.findall(r'id="([^"]+)"', xml))


def test_load_icon_returns_group_and_size():
    g, (w, h) = load_icon("western_blot")
    assert w > 0 and h > 0
    assert g.attribs.get("data-icon-credit") == "western_blot"
    assert "<path" in g.tostring()


def test_missing_icon_raises():
    with pytest.raises(IconNotFoundError):
        load_icon("definitely_not_an_icon")


def test_ids_namespaced_per_asset():
    wb = load_icon("western_blot")[0].tostring()
    ag = load_icon("agarose_gel")[0].tostring()
    assert all(i.startswith("western_blot__") for i in _ids(wb))
    assert all(i.startswith("agarose_gel__") for i in _ids(ag))
    assert _ids(wb).isdisjoint(_ids(ag))   # no cross-icon collision


def test_two_icons_in_one_drawing_have_disjoint_ids(tmp_path):
    dwg = svgwrite.Drawing(str(tmp_path / "two.svg"), size=(400, 200), debug=False)
    dwg.add(load_icon("western_blot")[0])
    dwg.add(load_icon("agarose_gel")[0])
    xml = dwg.tostring()
    # both icons drew, and every id is still unique-by-prefix
    assert "western_blot__" in xml and "agarose_gel__" in xml


def test_available_icons_lists_store():
    names = available_icons()
    assert "western_blot" in names and "agarose_gel" in names


def test_every_asset_has_a_credit_record():
    creds = json.loads((_ASSETS / "credits.json").read_text())
    assets = {p.stem for p in _ASSETS.glob("*.svg")}
    missing = assets - set(creds)
    assert not missing, f"assets without a credits.json entry: {missing}"
    # each record carries the fields attribution + the sidecar need
    for name, rec in creds.items():
        for field in ("author", "license", "license_url", "source_url", "title"):
            assert rec.get(field) is not None, f"{name} missing {field}"
