#!/usr/bin/env python3
"""Ingest a Bioicons SVG into the embedded-icon asset store (DECISIONS D9).

Dev-time tool — NOT imported by the render path. Fetches a Bioicons SVG, cleans
it (strips editor cruft, inlines `<style>` CSS, namespaces ids, drops XML
namespaces), normalizes its viewBox, writes `imageGen/assets/icons/<name>.svg`,
and upserts the attribution record in `imageGen/assets/icons/credits.json`.

Usage:
  # from the Bioicons GitHub repo (license + author derived from the path):
  python tools/ingest_icon.py --bioicons static/icons/cc-0/Microbiology/Foo/bar.svg --name microscope

  # from a local file (supply credit explicitly):
  python tools/ingest_icon.py --file ./bar.svg --name microscope \
      --author "Foo" --license "CC0 1.0" --license-url "https://creativecommons.org/publicdomain/zero/1.0/" \
      --source-url "https://example.com/bar.svg" --title "Microscope"

The clean transforms are recorded as the icon's `modifications` so CC-BY
attribution can state that the icon was modified.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

from lxml import etree

_REPO = "duerrsimon/bioicons"
_ASSETS = Path(__file__).resolve().parent.parent / "imageGen" / "assets" / "icons"
_CREDITS = _ASSETS / "credits.json"

_LICENSE_MAP = {
    "cc-0": ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/"),
    "cc-by-3.0": ("CC-BY 3.0", "https://creativecommons.org/licenses/by/3.0/"),
    "cc-by-4.0": ("CC-BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
    "cc-by-sa-3.0": ("CC-BY-SA 3.0", "https://creativecommons.org/licenses/by-sa/3.0/"),
    "cc-by-sa-4.0": ("CC-BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
    "mit": ("MIT", "https://opensource.org/licenses/MIT"),
    "bsd": ("BSD-3-Clause", "https://opensource.org/licenses/BSD-3-Clause"),
}

_MODIFICATIONS = "cleaned (stripped editor metadata), inlined CSS, namespaced ids, normalized viewBox"

# Namespaces whose elements are pure editor metadata and can be dropped wholesale.
_DROP_NS = {
    "http://www.inkscape.org/namespaces/inkscape",
    "http://sodipodi.sourceforge.net/DTD/sodipodi-0.0.dtd",
    "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    "http://purl.org/dc/elements/1.1/",
    "http://creativecommons.org/ns#",
}
_DROP_LOCAL = {"metadata", "namedview", "RDF", "Work", "format", "type", "title"}


def _fetch_bioicons(path: str) -> str:
    out = subprocess.run(
        ["gh", "api", f"repos/{_REPO}/contents/{path}"],
        capture_output=True, text=True, check=True,
    )
    return base64.b64decode(json.loads(out.stdout)["content"]).decode("utf-8", "replace")


def _credit_from_path(path: str) -> dict:
    # static/icons/<license>/<category>/<author>/<file>.svg
    parts = path.split("/")
    lic_folder = parts[2] if len(parts) > 2 else ""
    author = parts[4].replace("-", " ").replace("_", " ") if len(parts) > 4 else "unknown"
    lic, lic_url = _LICENSE_MAP.get(lic_folder, (lic_folder or "unknown", ""))
    return {
        "author": author,
        "license": lic,
        "license_url": lic_url,
        "source_url": f"https://github.com/{_REPO}/blob/main/{path}",
    }


# --- cleaning ---------------------------------------------------------------

def _inline_css(root: etree._Element) -> None:
    """Resolve `<style>` class rules onto element presentation attributes."""
    style_els = root.xpath("//*[local-name()='style']")
    rules: dict[str, dict[str, str]] = {}
    for st in style_els:
        css = st.text or ""
        for sel, body in re.findall(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", css):
            props = {}
            for decl in body.split(";"):
                if ":" in decl:
                    k, v = decl.split(":", 1)
                    props[k.strip()] = v.strip()
            rules.setdefault(sel, {}).update(props)
        st.getparent().remove(st)
    if not rules:
        return
    for el in root.iter():
        cls = el.get("class")
        if not cls:
            continue
        for token in cls.split():
            for k, v in rules.get(token, {}).items():
                if el.get(k) is None:
                    el.set(k, v)
        del el.attrib["class"]


def _namespace_ids(root: etree._Element, prefix: str) -> None:
    """Prefix every id and url(#id)/href ref so multiple icons never collide."""
    id_map: dict[str, str] = {}
    for el in root.iter():
        old = el.get("id")
        if old:
            new = f"{prefix}__{old}"
            id_map[old] = new
            el.set("id", new)
    if not id_map:
        return
    ref_attrs = ("clip-path", "fill", "stroke", "mask", "filter",
                 "{http://www.w3.org/1999/xlink}href", "href")
    for el in root.iter():
        for attr in ref_attrs:
            val = el.get(attr)
            if not val:
                continue
            for old, new in id_map.items():
                val = val.replace(f"#{old})", f"#{new})").replace(f'"#{old}"', f'"#{new}"')
                if val in (f"#{old}",):
                    val = f"#{new}"
            el.set(attr, val)


def _strip_namespaces(root: etree._Element) -> None:
    """Drop editor-namespace elements/attrs and flatten remaining tags to local."""
    for el in list(root.iter()):
        qn = etree.QName(el)
        if qn.namespace in _DROP_NS or qn.localname in _DROP_LOCAL:
            parent = el.getparent()
            if parent is not None:
                parent.remove(el)
            continue
    for el in root.iter():
        el.tag = etree.QName(el).localname
        for attr in list(el.attrib):
            ns = etree.QName(attr).namespace if "}" in attr else None
            if ns in _DROP_NS or (ns and ns != "http://www.w3.org/2000/svg"):
                del el.attrib[attr]
    etree.cleanup_namespaces(root)


def _viewbox(root: etree._Element) -> str:
    vb = root.get("viewBox")
    if vb:
        return vb
    w = root.get("width", "0")
    h = root.get("height", "0")
    w = re.sub(r"[a-z%]+$", "", w) or "0"
    h = re.sub(r"[a-z%]+$", "", h) or "0"
    return f"0 0 {w} {h}"


def clean_svg(svg_text: str, name: str) -> str:
    """Return a namespace-free `<svg viewBox=...>…</svg>` cleaned asset string."""
    parser = etree.XMLParser(remove_comments=True, recover=True)
    root = etree.fromstring(svg_text.encode("utf-8"), parser=parser)
    _inline_css(root)
    _namespace_ids(root, name)
    vb = _viewbox(root)
    _strip_namespaces(root)
    out = etree.Element("svg")
    out.set("viewBox", vb)
    for child in list(root):
        out.append(child)
    return etree.tostring(out, pretty_print=False).decode("utf-8")


_NOTICE = Path(__file__).resolve().parent.parent / "THIRD_PARTY_ICONS.md"


def _upsert_credit(name: str, record: dict) -> None:
    creds = {}
    if _CREDITS.exists():
        creds = json.loads(_CREDITS.read_text())
    creds[name] = record
    _CREDITS.write_text(json.dumps(creds, indent=2, sort_keys=True) + "\n")
    _write_notice(creds)


def _write_notice(creds: dict) -> None:
    """Regenerate the human-readable NOTICE from credits.json (always current)."""
    lines = [
        "# Third-party icons",
        "",
        "Embedded lab/biology glyphs are sourced from "
        "[Bioicons](https://bioicons.com) and cleaned for the imageGen house "
        "pipeline (editor metadata stripped, CSS inlined, ids namespaced). Each "
        "icon keeps its original license below. CC-BY icons are also credited "
        "on any figure that uses them and in a per-figure `*.credits.txt` "
        "sidecar; CC0/MIT need no figure credit.",
        "",
        "| Asset | Title | Author | License | Source |",
        "|---|---|---|---|---|",
    ]
    for name in sorted(creds):
        r = creds[name]
        lic = f"[{r.get('license','?')}]({r['license_url']})" if r.get("license_url") else r.get("license", "?")
        src = f"[link]({r['source_url']})" if r.get("source_url") else ""
        lines.append(f"| `{name}` | {r.get('title','')} | {r.get('author','')} | {lic} | {src} |")
    _NOTICE.write_text("\n".join(lines) + "\n")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Ingest a Bioicons SVG into the asset store.")
    ap.add_argument("--bioicons", help="repo path, e.g. static/icons/cc-0/Cat/Author/file.svg")
    ap.add_argument("--file", help="local SVG file (alternative to --bioicons)")
    ap.add_argument("--name", required=True, help="target glyph asset name")
    ap.add_argument("--title")
    ap.add_argument("--author")
    ap.add_argument("--license")
    ap.add_argument("--license-url", default="")
    ap.add_argument("--source-url", default="")
    args = ap.parse_args(argv)

    if args.bioicons:
        svg_text = _fetch_bioicons(args.bioicons)
        credit = _credit_from_path(args.bioicons)
    elif args.file:
        svg_text = Path(args.file).read_text()
        credit = {"author": args.author or "unknown", "license": args.license or "unknown",
                  "license_url": args.license_url, "source_url": args.source_url}
    else:
        ap.error("one of --bioicons or --file is required")

    title = args.title or args.name.replace("_", " ").replace("-", " ").title()
    credit.update({"title": title, "modifications": _MODIFICATIONS})

    cleaned = clean_svg(svg_text, args.name)
    _ASSETS.mkdir(parents=True, exist_ok=True)
    (_ASSETS / f"{args.name}.svg").write_text(cleaned + "\n")
    _upsert_credit(args.name, credit)

    print(f"wrote {_ASSETS / (args.name + '.svg')}  ({len(cleaned)} bytes)")
    print(f"credit: {credit['author']} · {credit['license']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
