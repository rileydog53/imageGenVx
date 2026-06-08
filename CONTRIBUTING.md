# Contributing to imageGen

This project is built by a three-role team — a product owner, a senior
architect, and a builder (often an AI agent). This file is the entry point
for anyone extending the project. For *using* imageGen, see
[README.md](README.md); for the LLM-facing interface, see [SKILL.md](SKILL.md).

## Start here

Before writing code, read in order:

1. **[DECISIONS.md](DECISIONS.md)** — cross-phase architectural decisions
   (D1/D3/D4: IR-id tagging, label auto-invoke, `smiles_map`; D2 watermarking
   was retired).
2. **[BACKLOG.md](BACKLOG.md)** — open, in-scope defects.
3. **[V3_FEATURES.md](V3_FEATURES.md)** — larger features parked for a
   possible v3.
4. **The pattern file for the area you're touching** — e.g. `primitives/proteins.py`
   for a primitive, `layout/reaction_layout.py` for a layout engine. Copy its style.

## Hard rules

1. **No SVG strings.** Always `svgwrite` element objects.
2. **Every IR field is validated.** No raw dicts through the pipeline.
3. **Every primitive gets a golden-image test.** Visual regressions are silent.
4. **Conventions over creativity.** Copy how Nature/Cell draws it.
5. **Don't change `ir/schema.py` without explicit approval.** It is
   load-bearing.
6. **All project files live in `~/Desktop/imageGen-v2.6/`.** Throwaway
   scripts go in `~/Desktop/scratch/`.

## Code conventions

- **Future-proof every module.** Composable private helpers (`_helper_name`)
  over copy-paste. Flat namespaced style keys (`module_*`). Optional params
  default to "off". New variants extend existing helpers.
- **Decouple via protocols, not imports.** When two modules must talk, define
  the contract on a small dataclass (see `MembraneCurve.anchor_at()`).
- **Determinism matters.** Seed any randomness (NetworkX layout, etc.) with a
  fixed value.
- **Comment for the future reader.** Module docstring: visual conventions +
  future-phase coupling. Function docstring: Args, Returns, one-line
  scientific rationale. Inline comments only for non-obvious geometry. Prefer
  self-documenting names.

## Environment

- **Python:** the shared venv at `~/Desktop/.venv` (3.12). Don't create a
  project-local venv.
- **Package:** importable as `imageGen` (`pip install -e .` done); CLI is
  `python -m imageGen`.
- **Repo:** `~/Desktop/imageGen-v2.6/` (local dir renamed with each version), remote
  `https://github.com/rileydog53/imageGenVx` (renamed from `imageGenV0` so the
  version number isn't tied to the repo name).
