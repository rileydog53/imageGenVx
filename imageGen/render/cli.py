"""Command-line entry point for imageGen.

Two invocation modes, dispatched by the first positional arg:

1. **Raw IR JSON (original, unchanged):**

       python -m imageGen IR_PATH --output OUT [--style ...] [--format ...]
                                  [--dpi N] [--smiles-map FILE.json]
                                  [--no-labels]

2. **Spec mode (v2):** a flat YAML/JSON spec gets piped through
   `imageGen.ir.builder.build` → `render_figure`. Same render flags apply.

       python -m imageGen render-spec SPEC_PATH --output OUT [flags...]

   The spec is a tiny dict with `archetype`, optional `style`/`title`/
   `caption`, and lists of `entities` / `relations` / `compartments` —
   each item either a list (tuple-shape) or a mapping. See
   `imageGen.ir.builder.build` for the accepted shapes.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, get_args

from imageGen.ir.builder import build as build_figure
from imageGen.ir.schema import Figure
from imageGen.render.compositor import Format, render_figure
from imageGen.styles.loader import list_presets


# ---------------------------------------------------------------------------
# Shared render flags — both modes accept the same downstream options.
# ---------------------------------------------------------------------------


def _add_render_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-o", "--output", required=True, help="Output file path.")
    parser.add_argument(
        "--style",
        choices=list_presets(),
        default=None,
        help="Journal style preset (overrides ir.style_preset).",
    )
    parser.add_argument(
        "--format",
        choices=get_args(Format),
        default=None,
        help="Output format (inferred from --output suffix when omitted).",
    )
    parser.add_argument(
        "--dpi", type=int, default=300, help="Output resolution (default 300)."
    )
    parser.add_argument(
        "--display-dpi",
        dest="display_dpi",
        type=int,
        default=None,
        metavar="N",
        help="Also write a low-DPI screen copy at <stem>_display.png (e.g. 96). "
        "The full-res deliverable at --output is never replaced. "
        "Ignored for SVG/PDF output.",
    )
    parser.add_argument(
        "--smiles-map",
        default=None,
        help="Path to JSON file mapping entity ids to SMILES strings "
        "(required for REACTION_SCHEME figures).",
    )
    parser.add_argument(
        "--no-labels",
        dest="labels",
        action="store_false",
        help="Suppress automatic label placement.",
    )
    parser.add_argument(
        "--canvas",
        default=None,
        metavar="WxH",
        help="Pin the SVG canvas to WxH pixels (e.g. 1200x800). "
        "Default: auto-size from content with an 800x600 floor.",
    )
    parser.add_argument(
        "--strict-labels",
        dest="strict_labels",
        action="store_true",
        help="Fail loud (LabelPlacementError) when a label can't be placed "
        "without overlap, instead of the default relax-and-retry fallback.",
    )
    parser.add_argument(
        "--legend",
        action="store_true",
        help="Render an inset key (top-right) explaining the glyph conventions "
        "the figure uses (relation arrow types + the 'P' phosphorylation "
        "badge). Off by default.",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="After rendering, run the three verifiers (semantic, legibility, "
        "convention) on the output SVG and print a one-line report. Lets a "
        "single command render + verify without a second round-trip.",
    )
    parser.add_argument(
        "--autocrop",
        action="store_true",
        help="Trim excess whitespace from the primary deliverable in place "
        "(render_figure(autocrop=True)), so the shipped figure has no dead "
        "margin. Unlike --crop this rewrites the main output rather than "
        "writing a sibling file.",
    )
    parser.add_argument(
        "--crop",
        action="store_true",
        help="Write a sibling *_cropped figure reframed onto its content "
        "(plus a comfortable margin), removing excess whitespace. The "
        "original render is left intact.",
    )
    parser.add_argument(
        "--crop-keep-aspect",
        dest="crop_keep_aspect",
        action="store_true",
        help="With --crop, keep the original canvas aspect ratio (uniform "
        "figure shape) instead of fitting the content's own shape. Note: "
        "usually crops little, since layouts fill a full dimension.",
    )
    parser.add_argument(
        "--crop-margin",
        type=float,
        default=0.15,
        metavar="FRAC",
        help="Margin around content when --crop is set, as a fraction of "
        "content size (default 0.15 = comfortable).",
    )
    parser.add_argument(
        "--layout",
        choices=["circular"],
        default=None,
        help="Override the layout for a compartment-free pathway. 'circular' "
        "forces a ring layout (sets figure.layout_hint). Pure single-cycle "
        "pathways ring automatically without this flag.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m imageGen",
        description="Render an imageGen IR JSON file to SVG, PNG, or PDF.",
    )
    parser.add_argument("ir_path", metavar="IR_PATH", help="Path to IR JSON file.")
    _add_render_flags(parser)
    return parser


def _build_spec_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m imageGen render-spec",
        description=(
            "Render a figure from a flat YAML or JSON spec file. "
            "The spec is piped through imageGen.ir.builder.build, so all "
            "schema validators still fire."
        ),
    )
    parser.add_argument(
        "spec_path",
        metavar="SPEC_PATH",
        help="Path to YAML or JSON spec file.",
    )
    _add_render_flags(parser)
    return parser


# ---------------------------------------------------------------------------
# Spec ingest
# ---------------------------------------------------------------------------


def _load_spec(path: Path) -> dict[str, Any]:
    """Load a YAML or JSON spec file into a dict.

    YAML is preferred for handwritten specs; JSON falls out for free since
    PyYAML's safe-loader accepts JSON. Format is picked by suffix: .json
    → json.loads, anything else → yaml.safe_load.
    """
    text = path.read_text()
    if path.suffix.lower() == ".json":
        return json.loads(text)
    # PyYAML is a hard dep of the wider Desktop venv; import lazily so the
    # raw-IR path doesn't pay the import cost.
    import yaml  # noqa: PLC0415

    return yaml.safe_load(text)


def _run_verification(ir: Figure, svg_path: Path) -> bool:
    """Run all three verifiers on `svg_path` and print a one-line report.

    Returns True when every check passes. Never raises — each verifier's
    failure is caught and folded into the printed report so a single
    `--verify` render command always completes and surfaces every issue at
    once (rather than aborting on the first).
    """
    from imageGen.verify.convention_check import ConventionCheckError, convention_check
    from imageGen.verify.legibility_check import LegibilityCheckError, legibility_check
    from imageGen.verify.semantic_check import SemanticCheckError, semantic_check

    parts: list[str] = []
    ok = True
    try:
        semantic_check(ir, svg_path)
        parts.append("semantic=OK")
    except SemanticCheckError as e:
        parts.append(f"semantic=FAIL({e})")
        ok = False
    try:
        result = legibility_check(svg_path)
        parts.append(f"legibility=OK(needs_crop={result.needs_crop})")
    except LegibilityCheckError as e:
        parts.append(f"legibility=FAIL({e})")
        ok = False
    try:
        convention_check(ir, svg_path)
        parts.append("convention=OK")
    except ConventionCheckError as e:
        parts.append(f"convention=FAIL({e})")
        ok = False

    # FR9: advisory only — never flips `ok`. Reports acronyms in labels that the
    # figure's glossary doesn't define (no-op when the figure has no glossary).
    from imageGen.verify.glossary_check import glossary_check
    undefined = glossary_check(ir)
    if undefined:
        parts.append(f"glossary=WARN(undefined: {', '.join(undefined)})")
    elif ir.glossary:
        parts.append("glossary=OK")

    print("VERIFY:", " ".join(parts))
    return ok


def _spec_to_figure(spec: dict[str, Any]) -> Figure:
    """Map a flat spec dict into a `Figure` via the builder.

    Unknown top-level keys are forwarded as-is to `build` so a typo surfaces
    as a Python TypeError rather than silently being dropped. The builder
    itself runs everything through `Figure.model_validate`.
    """
    archetype = spec.pop("archetype", None)
    if archetype is None:
        raise ValueError("Spec is missing required key 'archetype'.")
    # Accept the IR-native field name `style_preset` as an alias for the
    # builder's `style` kwarg, so a full IR JSON works as a spec unchanged.
    if "style_preset" in spec and "style" not in spec:
        spec["style"] = spec.pop("style_preset")
    # Tuple-shaped list items arrive as plain lists from YAML/JSON; the
    # builder's normalisers accept tuples *or* dicts, so coerce lists → tuples.
    # (Panels are left as-is — their nested content is full IR dicts.)
    for key in ("entities", "relations", "compartments", "glossary"):
        if key in spec and isinstance(spec[key], list):
            spec[key] = [tuple(item) if isinstance(item, list) else item for item in spec[key]]
    return build_figure(archetype, **spec)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    import sys

    raw = list(sys.argv[1:] if argv is None else argv)

    # Subcommand sniff: the legacy CLI takes a positional IR_PATH first, so
    # a literal `render-spec` token in slot 0 unambiguously selects the new
    # mode without breaking the old one.
    if raw and raw[0] == "render-spec":
        args = _build_spec_parser().parse_args(raw[1:])
        spec = _load_spec(Path(args.spec_path))
        ir = _spec_to_figure(spec)
    else:
        args = _build_parser().parse_args(raw)
        ir = Figure.model_validate_json(Path(args.ir_path).read_text())

    # LT1: --layout circular forces ring layout via the IR hint.
    if getattr(args, "layout", None) == "circular":
        ir = ir.model_copy(update={"layout_hint": "circular"})

    smiles_map = None
    if args.smiles_map is not None:
        smiles_map = json.loads(Path(args.smiles_map).read_text())

    canvas = None
    if args.canvas is not None:
        try:
            w_s, h_s = args.canvas.lower().split("x")
            canvas = (float(w_s), float(h_s))
        except (ValueError, AttributeError) as e:
            raise SystemExit(
                f"--canvas must be WxH (e.g. 1200x800), got {args.canvas!r}"
            ) from e

    out = render_figure(
        ir,
        args.output,
        style_name=args.style,
        format=args.format,
        smiles_map=smiles_map,
        labels=args.labels,
        dpi=args.dpi,
        display_dpi=args.display_dpi,
        canvas=canvas,
        strict_labels=args.strict_labels,
        autocrop=args.autocrop,
        legend=args.legend,
    )
    print(out)

    svg_path = out if out.suffix == ".svg" else out.with_suffix(".svg")

    if args.crop:
        from imageGen.render.crop import apply_crop

        fmt = out.suffix.lstrip(".")
        cropped_out, _box = apply_crop(
            svg_path, out, fmt,
            margin_frac=args.crop_margin,
            keep_aspect=args.crop_keep_aspect,
            dpi=args.dpi,
        )
        print(cropped_out)

    if args.verify:
        _run_verification(ir, svg_path)

    return 0
