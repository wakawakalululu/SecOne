from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PySide6.QtWidgets import QApplication  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402

from secone.config import load_config  # noqa: E402
from secone.db import TaskStore  # noqa: E402
from secone.llm import LLMClient, LlamaServerManager  # noqa: E402
from secone.ui.context import AppContext  # noqa: E402
from secone.ui.main_window import MainWindow  # noqa: E402
from secone.ui.theme import apply_theme  # noqa: E402


def load_system_fonts() -> None:
    if QFontDatabase.families():
        return
    fonts = Path("C:/Windows/Fonts")
    for name in ("msyh.ttc", "msyhbd.ttc", "consola.ttf", "consolab.ttf", "segoeui.ttf"):
        path = fonts / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))


def main() -> None:
    app = QApplication([])
    load_system_fonts()
    apply_theme(app)
    config = load_config(ROOT)
    store = TaskStore(config.paths.db_file)
    manager = LlamaServerManager(config)
    client = LLMClient(config, manager)
    context = AppContext(config, config.paths, store, manager, client)
    window = MainWindow(context)
    window.resize(1440, 900)
    window.show()
    window.refresh_status()
    window.toast.hide()
    app.processEvents()
    output = ROOT / "artifacts" / "screenshots"
    output.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(output / "workbench.png"))
    window.navigate("settings")
    window.toast.hide()
    app.processEvents()
    window.grab().save(str(output / "settings.png"))
    window.navigate("history")
    window.toast.hide()
    app.processEvents()
    window.grab().save(str(output / "history.png"))
    print(output)


if __name__ == "__main__":
    main()
