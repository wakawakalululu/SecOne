"""Subprocess probe used by tests/test_ui_dpi.py.

QT_SCALE_FACTOR is applied when QApplication starts, so each scale factor needs
its own process. Writes a JSON summary; never imported by pytest directly.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton, QWidget  # noqa: E402

from secone.config import AppConfig  # noqa: E402
from secone.db import TaskStore  # noqa: E402
from secone.llm import LLMClient, LlamaServerManager  # noqa: E402
from secone.paths import AppPaths  # noqa: E402
from secone.ui.context import AppContext  # noqa: E402
from secone.ui.main_window import MainWindow  # noqa: E402
from secone.ui.theme import apply_theme  # noqa: E402

CORE_BUTTONS = ("一键梭哈", "Crypto 分析", "文件取证", "代码审计", "导出报告")
SIZES = ((1280, 800), (1600, 900), (1920, 1080))
PAGES = ("workbench", "history", "settings")


def distinct_colors(pixmap) -> int:
    image = pixmap.toImage()
    width, height = image.width(), image.height()
    step_x = max(1, width // 16)
    step_y = max(1, height // 16)
    colors = set()
    for x in range(0, width, step_x):
        for y in range(0, height, step_y):
            colors.add(image.pixel(x, y))
    return len(colors)


def main() -> int:
    scale = float(sys.argv[1])
    out_path = Path(sys.argv[2])

    app = QApplication([])
    apply_theme(app)

    workdir = Path(tempfile.mkdtemp(prefix="secone-dpi-"))
    paths = AppPaths(workdir / "app")
    paths.ensure()
    config = AppConfig(paths)
    config.set("analysis.ai_enabled", False)
    config.set("engine.port", 1)
    store = TaskStore(paths.db_file)
    manager = LlamaServerManager(config)
    client = LLMClient(config, manager)
    window = MainWindow(AppContext(config, paths, store, manager, client))

    cases = []
    try:
        for width, height in SIZES:
            window.navigate("workbench")
            window.resize(width, height)
            window.show()
            app.processEvents()

            zero_size = []
            for child in window.findChildren(QWidget):
                if not child.isVisible():
                    continue
                if child.width() <= 0 or child.height() <= 0:
                    zero_size.append(f"{type(child).__name__}:{child.objectName() or '-'}")

            clipped = []
            buttons = {b.text(): b for b in window.findChildren(QPushButton)}
            for label in CORE_BUTTONS:
                button = buttons.get(label)
                if button is None or not button.isVisible():
                    clipped.append(f"missing:{label}")
                    continue
                needed = button.fontMetrics().horizontalAdvance(label)
                if button.width() < needed:
                    clipped.append(f"{label}:{button.width()}<{needed}")

            shot = window.grab()
            ratio = window.devicePixelRatioF()
            expected_w = round(window.width() * ratio)
            expected_h = round(window.height() * ratio)
            pixmap_ok = (
                not shot.isNull()
                and abs(shot.width() - expected_w) <= 1
                and abs(shot.height() - expected_h) <= 1
                and distinct_colors(shot) >= 2
            )

            page_ok = []
            for page in PAGES:
                window.navigate(page)
                app.processEvents()
                pix = window.grab()
                page_ok.append(not pix.isNull() and distinct_colors(pix) >= 2)

            cases.append(
                {
                    "requested": [width, height],
                    "actual": [window.width(), window.height()],
                    "ratio": ratio,
                    "zero_size": zero_size,
                    "clipped_buttons": clipped,
                    "pixmap_ok": pixmap_ok,
                    "page_pixmaps_ok": page_ok,
                }
            )
    finally:
        window.close()

    payload = {"scale": scale, "ratio": window.devicePixelRatioF(), "cases": cases}
    out_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
