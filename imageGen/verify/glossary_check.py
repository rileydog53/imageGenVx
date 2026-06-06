"""Glossary coverage check (FR9) — advisory, not fail-loud.

Unlike the other verifiers (which ``raise`` on the first violation),
``glossary_check`` returns a list of acronyms that appear in the figure's labels
but have no matching ``Figure.glossary`` term. Acronym detection is inherently
noisy — ATP / DNA / GPCR are common knowledge and shouldn't be hard errors — so
this is **advisory**: the CLI folds the result into the ``--verify`` report as a
warning, and the check is a **no-op when the figure declares no glossary** (don't
nag figures that opted out of glossaries entirely).

An "acronym" here is a run of >=2 uppercase letters, optionally trailed by digits
(``GPCR``, ``RNA``, ``PI3K``, ``G6P``). Greek/lowercase tokens are ignored.
"""
from __future__ import annotations

import re

from imageGen.ir.schema import Figure

# A token that looks like an abbreviation worth defining.
_ACRONYM = re.compile(r"\b[A-Z]{2,}[0-9]*\b")


def _labels(figure: Figure) -> list[str]:
    """Every author-facing text string in the figure (recurses into panels)."""
    out: list[str] = []
    for e in figure.entities:
        if e.label:
            out.append(e.label)
    for c in figure.compartments:
        if c.label:
            out.append(c.label)
    for r in figure.relations:
        if r.label:
            out.append(r.label)
    for p in figure.panels:
        out.extend(_labels(p.content))
    return out


def glossary_check(figure: Figure) -> list[str]:
    """Return acronyms used in labels but absent from the glossary (advisory).

    Empty when the figure has no glossary (opted out) or every acronym is
    covered. Order is stable (sorted) for deterministic reporting.
    """
    if not figure.glossary:
        return []
    defined = {entry.term for entry in figure.glossary}
    used: set[str] = set()
    for text in _labels(figure):
        used.update(_ACRONYM.findall(text))
    return sorted(used - defined)
