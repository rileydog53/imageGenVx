"""Phase 0 smoke tests: imports and environment checks only."""
import subprocess
import sys


def test_python_version():
    assert sys.version_info >= (3, 12), f"Expected Python 3.12+, got {sys.version}"


def test_venv():
    assert "Desktop/.venv" in sys.executable, (
        f"Not running in Desktop venv. sys.executable={sys.executable}"
    )


# --- third-party package imports ---

def test_import_rdkit():
    import rdkit  # noqa: F401
    from rdkit import Chem
    mol = Chem.MolFromSmiles("CCO")
    assert mol is not None, "RDKit parsed ethanol to None — build may be broken"


def test_import_cairo():
    import cairo  # noqa: F401


def test_import_svgwrite():
    import svgwrite  # noqa: F401


def test_import_svgutils():
    import svgutils  # noqa: F401


def test_import_networkx():
    import networkx  # noqa: F401


def test_import_numpy():
    import numpy  # noqa: F401


def test_import_scipy():
    import scipy  # noqa: F401


def test_import_pillow():
    import PIL  # noqa: F401


def test_import_pydantic():
    import pydantic  # noqa: F401


def test_import_cairosvg():
    import cairosvg  # noqa: F401


def test_import_matplotlib():
    import matplotlib  # noqa: F401


def test_cairosvg_roundtrip():
    """cairosvg can convert a minimal SVG to PNG bytes without crashing."""
    import cairosvg
    minimal_svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>'
    png = cairosvg.svg2png(bytestring=minimal_svg)
    assert len(png) > 0, "cairosvg produced empty output"


# --- project module imports ---

def test_import_ir():
    import imageGen.ir.schema  # noqa: F401


def test_import_primitives():
    import imageGen.primitives.arrows  # noqa: F401
    import imageGen.primitives.proteins  # noqa: F401
    import imageGen.primitives.membranes  # noqa: F401
    import imageGen.primitives.nucleic_acids  # noqa: F401
    import imageGen.primitives.cells  # noqa: F401
    import imageGen.primitives.chemistry  # noqa: F401
    import imageGen.primitives.lab_equipment  # noqa: F401


def test_import_layout():
    import imageGen.layout.pathway_layout  # noqa: F401
    import imageGen.layout.reaction_layout  # noqa: F401
    import imageGen.layout.panel_layout  # noqa: F401
    import imageGen.layout.label_placement  # noqa: F401


def test_import_styles():
    import imageGen.styles.loader  # noqa: F401


def test_import_render():
    import imageGen.render.compositor  # noqa: F401
    import imageGen.render.export  # noqa: F401
    import imageGen.render.cli  # noqa: F401


def test_import_verify():
    import imageGen.verify.semantic_check  # noqa: F401
    import imageGen.verify.legibility_check  # noqa: F401
    import imageGen.verify.convention_check  # noqa: F401


# --- directory structure ---

def test_directory_structure():
    from pathlib import Path
    root = Path(__file__).parent.parent
    required = [
        "imageGen/ir/schema.py",
        "imageGen/primitives/arrows.py", "imageGen/primitives/proteins.py",
        "imageGen/primitives/membranes.py", "imageGen/primitives/nucleic_acids.py",
        "imageGen/primitives/cells.py", "imageGen/primitives/chemistry.py",
        "imageGen/primitives/lab_equipment.py",
        "imageGen/layout/pathway_layout.py", "imageGen/layout/reaction_layout.py",
        "imageGen/layout/panel_layout.py", "imageGen/layout/label_placement.py",
        "imageGen/styles/loader.py",
        "imageGen/render/compositor.py", "imageGen/render/export.py", "imageGen/render/cli.py",
        "imageGen/verify/semantic_check.py", "imageGen/verify/legibility_check.py",
        "imageGen/verify/convention_check.py",
        "references/journal_conventions.md",
        "tests/fixtures", "tests/figures",
        "README.md",
    ]
    missing = [p for p in required if not (root / p).exists()]
    assert not missing, f"Missing from project tree: {missing}"
