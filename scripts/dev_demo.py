from __future__ import annotations

import base64
import codecs
import io
import os
import sys
import zipfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PIL import Image  # noqa: E402
from PySide6.QtGui import QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from secone.config import load_config  # noqa: E402
from secone.core.pipeline import AnalysisPipeline  # noqa: E402
from secone.core.report import ReportWriter  # noqa: E402
from secone.db import TaskStore  # noqa: E402
from secone.llm import LLMClient, LlamaServerManager  # noqa: E402
from secone.ui.context import AppContext  # noqa: E402
from secone.ui.main_window import MainWindow  # noqa: E402
from secone.ui.theme import apply_theme  # noqa: E402

SAMPLES = ROOT / "artifacts" / "demo_materials"


def xor(data: bytes, key: int) -> bytes:
    return bytes(byte ^ key for byte in data)


def build_samples() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)
    b64_flag = "flag{cr0ypt0_fl4g_v1a_b4s3_64}"
    hex_flag = "flag{h3x_enc0d3d_t0k3n}"
    rot_flag = "flag{rot13_1s_n0t_s3cur3}"
    plain_flag = "flag{pl41n_t3xt_1n_n0t3s}"
    xor_flag = "flag{x0r_s1ngl3_byt3_r3c0v3r3d}"

    notes = "\n".join(
        [
            "CTF 取证练习材料 / 仅本地分析",
            "",
            "题目描述：取证人员从一台主机导出了编码后的线索文件，请还原 flag。",
            "",
            f"线索 A（Base64）：{base64.b64encode(b64_flag.encode()).decode()}",
            f"线索 B（Hex）：{hex_flag.encode().hex()}",
            f"线索 C（ROT13）：{codecs.encode(rot_flag, 'rot_13')}",
            f"线索 D（明文）：{plain_flag}",
            "",
            "提交格式：flag{...}",
        ]
    )
    (SAMPLES / "notes.txt").write_text(notes, encoding="utf-8")
    (SAMPLES / "xor_blob.bin").write_bytes(xor(xor_flag.encode(), 0x5A))

    source = """import os
import sqlite3
import pickle
import hashlib

DEBUG = True
SECRET_KEY = "dev-only-secret-key"

def handle(request):
    os.system(request.args.get("cmd", ""))
    result = eval(request.args.get("expr", "1+1"))
    name = request.args.get("name", "")
    query = "SELECT * FROM users WHERE name='" + name + "'"
    row = sqlite3.connect("app.db").execute(query).fetchall()
    payload = pickle.loads(request.body)
    digest = hashlib.md5(payload).hexdigest()
    return row, result, digest
"""
    (SAMPLES / "vuln_app.py").write_text(source, encoding="utf-8")

    archive_flag = "flag{arch1v3_tr4v3rs4l_gu4rd3d}"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("inner/readme.md", f"归档线索：{base64.b64encode(archive_flag.encode()).decode()}")
        archive.writestr("inner/nested.txt", "第二层材料，用于验证递归解包。")
    (SAMPLES / "challenge.zip").write_bytes(buffer.getvalue())

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("../escape.txt", "这不应被解包到工作区之外。")
        archive.writestr("safe/ok.txt", "safe entry")
    (SAMPLES / "traversal.zip").write_bytes(buffer.getvalue())

    image_flag = "flag{ex1f_m3t4d4t4_l34k}"
    exif = Image.Exif()
    exif[0x010E] = f"调查备注：{image_flag}"
    exif[0x013B] = "SecOne Demo"
    Image.new("RGB", (320, 200), (18, 32, 44)).save(
        SAMPLES / "evidence.jpg", exif=exif, quality=90
    )


def load_system_fonts() -> None:
    if QFontDatabase.families():
        return
    fonts = Path("C:/Windows/Fonts")
    for name in ("msyh.ttc", "msyhbd.ttc", "consola.ttf", "consolab.ttf", "segoeui.ttf"):
        path = fonts / name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))


def main() -> None:
    build_samples()
    config = load_config(ROOT)
    config.set("analysis.ai_enabled", False)
    store = TaskStore(config.paths.db_file)
    manager = LlamaServerManager(config)
    client = LLMClient(config, manager)
    pipeline = AnalysisPipeline(config, store, llm=client, manager=manager)
    result = pipeline.run([SAMPLES], mode="auto", title_hint="Demo 取证材料")
    writer = ReportWriter(config, config.paths)
    paths = writer.write(result)
    print(
        f"task={result.task_id} files={len(result.files)} flags={len(result.flags)} "
        f"findings={len(result.findings)}"
    )
    for flag in result.flags:
        print(f"  [{flag.status}] {flag.value} conf={flag.confidence:.0%} src={flag.source}")
    print("report:", paths["markdown"])

    app = QApplication([])
    load_system_fonts()
    apply_theme(app)
    context = AppContext(config, config.paths, store, manager, client)
    window = MainWindow(context)
    window.resize(1440, 900)
    window.show()
    window.refresh_status()
    window.workbench.show_result(result)
    window.toast.hide()
    app.processEvents()
    output = ROOT / "artifacts" / "screenshots"
    output.mkdir(parents=True, exist_ok=True)
    window.grab().save(str(output / "workbench_result.png"))
    window.workbench.tabs.setCurrentIndex(1)
    window.toast.hide()
    app.processEvents()
    window.grab().save(str(output / "workbench_findings.png"))
    print(output / "workbench_result.png")


if __name__ == "__main__":
    main()
