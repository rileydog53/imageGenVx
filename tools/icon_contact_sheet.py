#!/usr/bin/env python3
"""Render a labeled grid PNG of icon candidates for review (DECISIONS D9).

Dev-time tool. Two modes:

  # already-ingested assets from the store:
  python tools/icon_contact_sheet.py --assets western_blot agarose-gel -o sheet.png

  # candidate Bioicons paths (fetched + cleaned in-memory, nothing written):
  python tools/icon_contact_sheet.py --bioicons \
      static/icons/cc-0/Microbiology/A/microscope.svg \
      static/icons/cc-0/Microbiology/B/inverted_microscope.svg -o sheet.png

Each cell shows the icon scaled to fit, its label, and (for --bioicons) the
license folder + a path-complexity hint, so the simplest/cleanest option is easy
to pick before committing to an ingest. The sheet is composed as one SVG (nested
<svg> per cell) and rasterized with cairosvg — no PIL dependency.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import cairosvg

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_icon import _fetch_bioicons, clean_svg  # noqa: E402

_ASSETS = Path(__file__).resolve().parent.parent / "imageGen" / "assets" / "icons"
_CELL = 170.0
_PAD = 12.0
_LABEL_H = 30.0
_COLS = 4


def _cell_svg(cleaned: str, label: str, sublabel: str, x: float, y: float) -> str:
    """A grid cell: border, the icon (auto-fit via nested viewBox), and labels."""
    vb = re.search(r'viewBox="([^"]+)"', cleaned)
    vb_attr = f'viewBox="{vb.group(1)}"' if vb else ""
    inner = re.sub(r"^<svg[^>]*>", "", cleaned).rsplit("</svg>", 1)[0]
    iw = _CELL
    ih = _CELL - _LABEL_H
    return (
        f'<g transform="translate({x},{y})">'
        f'<rect x="0" y="0" width="{_CELL}" height="{_CELL}" fill="#FFFFFF" '
        f'stroke="#C8D4DD" stroke-width="1"/>'
        f'<svg x="6" y="6" width="{iw - 12}" height="{ih - 6}" {vb_attr} '
        f'preserveAspectRatio="xMidYMid meet">{inner}</svg>'
        f'<text x="{_CELL/2}" y="{ih + 12}" text-anchor="middle" '
        f'font-family="Arial" font-size="12" font-weight="bold" fill="#1A1A1A">{label}</text>'
        f'<text x="{_CELL/2}" y="{ih + 25}" text-anchor="middle" '
        f'font-family="Arial" font-size="9" fill="#5A6B6E">{sublabel}</text>'
        f"</g>"
    )


def _complexity(cleaned: str) -> str:
    n_path = cleaned.count("<path")
    n_shape = sum(cleaned.count(f"<{t}") for t in ("rect", "circle", "ellipse", "polygon"))
    return f"{n_path} paths · {n_shape} shapes · {len(cleaned)//1000}kB"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Contact sheet of icon candidates.")
    ap.add_argument("--assets", nargs="*", default=[], help="asset names from the store")
    ap.add_argument("--bioicons", nargs="*", default=[], help="Bioicons repo paths")
    ap.add_argument("-o", "--out", default="/tmp/icon_contact_sheet.png")
    args = ap.parse_args(argv)

    cells: list[tuple[str, str, str]] = []  # (cleaned_svg, label, sublabel)
    for name in args.assets:
        cleaned = (_ASSETS / f"{name}.svg").read_text()
        cells.append((cleaned, name, _complexity(cleaned)))
    for path in args.bioicons:
        cleaned = clean_svg(_fetch_bioicons(path), "cand")
        lic = path.split("/")[2] if path.startswith("static/") else "?"
        fname = path.split("/")[-1].replace(".svg", "")
        cells.append((cleaned, fname, f"{lic} · {_complexity(cleaned)}"))

    if not cells:
        ap.error("supply --assets and/or --bioicons")

    cols = min(_COLS, len(cells))
    rows = (len(cells) + cols - 1) // cols
    W = _PAD + cols * (_CELL + _PAD)
    H = _PAD + rows * (_CELL + _PAD)
    body = []
    for i, (cleaned, label, sub) in enumerate(cells):
        cx = _PAD + (i % cols) * (_CELL + _PAD)
        cy = _PAD + (i // cols) * (_CELL + _PAD)
        body.append(_cell_svg(cleaned, label, sub, cx, cy))
    sheet = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}"><rect width="{W}" height="{H}" fill="#F7F9FB"/>'
        + "".join(body) + "</svg>"
    )
    cairosvg.svg2png(bytestring=sheet.encode("utf-8"), write_to=args.out,
                     output_width=int(W * 2), output_height=int(H * 2))
    print(f"wrote {args.out}  ({len(cells)} icons, {cols}×{rows})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
