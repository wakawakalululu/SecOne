from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from secone.ui.widgets import LogoMark  # noqa: E402


def main() -> None:
    app = QApplication([])
    if not QFontDatabase.families():
        for name in ("msyh.ttc", "msyhbd.ttc", "consola.ttf", "consolab.ttf"):
            path = Path("C:/Windows/Fonts") / name
            if path.exists():
                QFontDatabase.addApplicationFont(str(path))
    mark = LogoMark(size=256)
    pixmap = mark.grab()
    png_path = ROOT / "assets" / "secone.png"
    pixmap.save(str(png_path))
    image = Image.open(png_path).convert("RGBA")
    image.save(
        ROOT / "assets" / "secone.ico",
        sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
    )
    print(png_path)
    print(ROOT / "assets" / "secone.ico")


if __name__ == "__main__":
    main()
