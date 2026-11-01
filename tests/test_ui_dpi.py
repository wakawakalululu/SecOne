from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROBE = Path(__file__).with_name("_dpi_probe.py")
SCALES = ("1.0", "1.25", "1.5", "2.0")


@pytest.mark.parametrize("scale", SCALES)
def test_ui_renders_across_scales_and_sizes(scale: str, tmp_path: Path) -> None:
    """Window must build, lay out and paint at 100/125/150/200% scaling.

    Each scale runs in its own process because QT_SCALE_FACTOR is read when
    QApplication starts. This verifies real Qt scaling and rasterisation, not a
    physical monitor; real-mouse drag on a scaled display still needs manual QA.
    """
    out = tmp_path / "probe.json"
    env = dict(os.environ)
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_SCALE_FACTOR"] = scale
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")

    result = subprocess.run(
        [sys.executable, str(PROBE), scale, str(out)],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr[-3000:]
    payload = json.loads(out.read_text("utf-8"))
    assert payload["scale"] == float(scale)
    assert abs(payload["ratio"] - float(scale)) <= 0.01
    assert len(payload["cases"]) == 3

    for case in payload["cases"]:
        assert case["zero_size"] == [], case
        assert case["clipped_buttons"] == [], case
        assert case["pixmap_ok"] is True, case
        assert all(case["page_pixmaps_ok"]), case
