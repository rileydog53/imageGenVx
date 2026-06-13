"""Tests for render/cli.py — Phase 5 Step 6.

Covers the argparse CLI wrapper around `render_figure`, exercised both
through direct `main()` calls and via one end-to-end `python -m imageGen`
subprocess invocation.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest
from PIL import Image

from imageGen.render.cli import main
from tests._helpers import FIXTURES_DIR

MAPK = str(FIXTURES_DIR / "mapk_cascade.json")
OXIDATION = str(FIXTURES_DIR / "oxidation_reaction.json")

OXIDATION_SMILES = {"alcohol": "CCO", "aldehyde": "CC=O"}


def test_main_writes_svg(tmp_path):
    out = tmp_path / "fig.svg"
    rc = main([MAPK, "-o", str(out)])
    assert rc == 0
    assert out.exists()
    assert out.stat().st_size > 0


def test_main_writes_png_readable_by_pillow(tmp_path):
    out = tmp_path / "fig.png"
    rc = main([MAPK, "-o", str(out)])
    assert rc == 0
    with Image.open(out) as img:
        assert img.format == "PNG"
        assert img.width > 0 and img.height > 0


def test_main_writes_pdf(tmp_path):
    out = tmp_path / "fig.pdf"
    rc = main([MAPK, "-o", str(out)])
    assert rc == 0
    assert out.read_bytes().startswith(b"%PDF-")


def test_main_accepts_style_nature(tmp_path):
    out = tmp_path / "fig.svg"
    rc = main([MAPK, "-o", str(out), "--style", "nature"])
    assert rc == 0
    assert out.exists()


def test_main_loads_smiles_map_for_reaction_scheme(tmp_path):
    smiles_path = tmp_path / "smiles.json"
    smiles_path.write_text(json.dumps(OXIDATION_SMILES))
    out = tmp_path / "fig.svg"
    rc = main([OXIDATION, "-o", str(out), "--smiles-map", str(smiles_path)])
    assert rc == 0
    assert out.exists()


def test_python_m_invocation_writes_file(tmp_path):
    out = tmp_path / "fig.svg"
    result = subprocess.run(
        [sys.executable, "-m", "imageGen", MAPK, "-o", str(out)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert out.exists()
    assert str(out) in result.stdout


def test_main_rejects_unknown_format(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        main([MAPK, "-o", str(tmp_path / "fig.png"), "--format", "foo"])
    assert excinfo.value.code == 2


# ---------------------------------------------------------------------------
# v2 — render-spec, --verify, --canvas, --strict-labels
# ---------------------------------------------------------------------------

_SPEC_YAML = """\
archetype: pathway
style: nature
entities:
  - [ras, protein, Ras]
  - [raf, kinase, Raf]
  - [mek, kinase, MEK]
relations:
  - [ras, activates, raf]
  - [raf, phosphorylates, mek]
"""


def test_render_spec_yaml(tmp_path):
    spec = tmp_path / "fig.yaml"
    spec.write_text(_SPEC_YAML)
    out = tmp_path / "fig.png"
    rc = main(["render-spec", str(spec), "-o", str(out)])
    assert rc == 0
    assert out.exists() and out.stat().st_size > 0


def test_render_spec_json(tmp_path):
    spec = tmp_path / "fig.json"
    spec.write_text(json.dumps({
        "archetype": "pathway",
        "entities": [["a", "protein", "A"], ["b", "protein", "B"]],
        "relations": [["a", "activates", "b"]],
    }))
    out = tmp_path / "fig.svg"
    rc = main(["render-spec", str(spec), "-o", str(out)])
    assert rc == 0
    assert out.exists()


def test_render_spec_missing_archetype_raises(tmp_path):
    spec = tmp_path / "bad.yaml"
    spec.write_text("entities:\n  - [a, protein, A]\n")
    with pytest.raises(ValueError, match="archetype"):
        main(["render-spec", str(spec), "-o", str(tmp_path / "x.png")])


def test_verify_flag_prints_report(tmp_path, capsys):
    out = tmp_path / "fig.png"
    rc = main([MAPK, "-o", str(out), "--verify"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "VERIFY:" in captured.out
    assert "semantic=OK" in captured.out


# ---------------------------------------------------------------------------
# P0c.2 — `styles` discovery subcommand
# ---------------------------------------------------------------------------

def test_styles_keys_prints_full_vocabulary(capsys):
    from imageGen.styles.loader import list_style_keys

    rc = main(["styles", "--keys"])
    assert rc == 0
    out_lines = capsys.readouterr().out.strip().splitlines()
    assert out_lines == list_style_keys()


def test_styles_no_flag_defaults_to_keys(capsys):
    from imageGen.styles.loader import list_style_keys

    rc = main(["styles"])
    assert rc == 0
    assert capsys.readouterr().out.strip().splitlines() == list_style_keys()


def test_styles_presets_lists_presets(capsys):
    from imageGen.styles.loader import list_presets

    rc = main(["styles", "--presets"])
    assert rc == 0
    out_lines = capsys.readouterr().out.strip().splitlines()
    assert out_lines == list_presets()


def test_styles_keys_with_layout_params_section(capsys):
    from imageGen.styles.loader import KNOWN_LAYOUT_PARAMS

    rc = main(["styles", "--keys", "--layout-params"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "# layout-params" in out
    for key in KNOWN_LAYOUT_PARAMS:
        assert key in out


def test_autocrop_flag_trims_dead_margin(tmp_path):
    """LT5: --autocrop rewrites the primary SVG so it ships without dead margin.

    The MAPK fixture renders into an 800x600 canvas it doesn't fill, so the
    default render reports needs_crop=True. With --autocrop the viewport is
    trimmed in place and the figure verifies needs_crop=False.
    """
    from imageGen.verify.legibility_check import legibility_check

    plain = tmp_path / "plain.svg"
    main([MAPK, "-o", str(plain)])
    assert legibility_check(plain).needs_crop is True

    cropped = tmp_path / "cropped.svg"
    rc = main([MAPK, "-o", str(cropped), "--autocrop"])
    assert rc == 0
    assert "viewBox" in cropped.read_text()
    assert legibility_check(cropped).needs_crop is False


def test_canvas_flag_pins_size(tmp_path):
    out = tmp_path / "fig.svg"
    rc = main([MAPK, "-o", str(out), "--canvas", "1500x900"])
    assert rc == 0
    svg = out.read_text()
    assert 'width="1500.0"' in svg and 'height="900.0"' in svg


def test_canvas_flag_rejects_bad_value(tmp_path):
    with pytest.raises(SystemExit):
        main([MAPK, "-o", str(tmp_path / "fig.svg"), "--canvas", "wide"])


def test_strict_labels_flag_renders_mrna_vaccine_cleanly(tmp_path):
    # L24 added _LARGE_NUDGES to the fallback ladder, resolving the label
    # collision that previously caused the mRNA-vaccine abstract to fail with
    # --strict-labels. This test confirms that improvement: the fixture now
    # renders without raising LabelPlacementError under strict mode.
    dense = str(FIXTURES_DIR / "graphical_abstract_mrna_vaccine.json")
    rc = main([dense, "-o", str(tmp_path / "fig.png"), "--strict-labels"])
    assert rc == 0
    assert (tmp_path / "fig.png").exists()


def test_render_spec_accepts_style_preset_alias(tmp_path):
    """A full-IR-style spec using `style_preset` (not `style`) renders."""
    spec = tmp_path / "fig.json"
    spec.write_text(json.dumps({
        "archetype": "pathway",
        "style_preset": "nature",
        "entities": [["a", "protein", "A"], ["b", "protein", "B"]],
        "relations": [["a", "activates", "b"]],
    }))
    out = tmp_path / "fig.svg"
    assert main(["render-spec", str(spec), "-o", str(out)]) == 0
    assert out.exists()


def test_render_spec_multipanel_json(tmp_path):
    """A multi-panel spec (panels with nested IR dicts) renders via render-spec."""
    spec = tmp_path / "abstract.json"
    spec.write_text(json.dumps({
        "archetype": "workflow",
        "style_preset": "cell_press",
        "panels": [
            {"id": "p1", "title": "A", "grid": [0, 0, 1, 1], "content": {
                "archetype": "pathway",
                "entities": [{"id": "x", "type": "protein", "label": "X"},
                             {"id": "y", "type": "kinase", "label": "Y"}],
                "relations": [{"source": "x", "target": "y", "type": "activates"}],
            }},
            {"id": "p2", "title": "B", "grid": [0, 1, 1, 1], "content": {
                "archetype": "pathway",
                "entities": [{"id": "m", "type": "protein", "label": "M"},
                             {"id": "n", "type": "protein", "label": "N"}],
                "relations": [{"source": "m", "target": "n", "type": "binds"}],
            }},
        ],
    }))
    out = tmp_path / "abstract.png"
    assert main(["render-spec", str(spec), "-o", str(out)]) == 0
    assert out.exists() and out.stat().st_size > 0
