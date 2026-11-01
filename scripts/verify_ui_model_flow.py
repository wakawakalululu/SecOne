#!/usr/bin/env python
"""Headless acceptance: configure a discovered model through the settings page,
save it, start the engine, and chat — proving the UI wiring works, not just the
backend classes.

Runs against an isolated ``SECONE_HOME`` sandbox so the operator's real
config/app.yaml is never touched.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

MODEL = ROOT / "models" / "verify-qwen2.5-0.5b-instruct-q4_k_m.gguf"
RUNTIME = ROOT / "runtime" / "llama-server.exe"

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" :: {detail}" if detail else ""))
    if not ok:
        failures.append(name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="验证界面配置模型、保存、启动与推理流程。")
    parser.add_argument("--gguf", type=Path, default=MODEL)
    parser.add_argument("--runtime", type=Path, default=RUNTIME)
    args = parser.parse_args(argv)
    model = args.gguf.resolve()
    runtime = args.runtime.resolve()
    if not model.is_file():
        print(f"缺少验证模型：{model}")
        return 1
    sandbox = Path(tempfile.mkdtemp(prefix="secone-ui-"))
    try:
        # Mirror the app layout inside the sandbox so paths resolve identically.
        for sub in ("models", "runtime", "config", "data", "workspace", "output", "logs"):
            (sandbox / sub).mkdir(parents=True, exist_ok=True)
        # Rename the copy so the configured default path stays absent until the
        # settings page discovers and saves it; otherwise "模型未安装" cannot be observed.
        shutil.copy2(model, sandbox / "models" / f"discovered-{model.name}")
        shutil.copy2(ROOT / "config" / "app.yaml", sandbox / "config" / "app.yaml")
        os.environ["SECONE_HOME"] = str(sandbox)

        from PySide6.QtWidgets import QApplication

        from secone.config import load_config
        from secone.db import TaskStore
        from secone.llm import LLMClient, LlamaServerManager
        from secone.ui.context import AppContext
        from secone.ui.main_window import MainWindow
        from secone.ui.theme import apply_theme

        app = QApplication.instance() or QApplication([])
        apply_theme(app)

        config = load_config(sandbox)
        config.set("engine.runtime", str(runtime))
        config.set("engine.port", 18105)
        config.set("engine.context_size", 2048)
        config.set("engine.startup_timeout", 180)
        config.set("engine.request_timeout", 180)
        store = TaskStore(config.paths.db_file)
        manager = LlamaServerManager(config)
        client = LLMClient(config, manager)
        context = AppContext(config, config.paths, store, manager, client)
        window = MainWindow(context)
        window.show()
        window.refresh_status()

        check("初始状态：模型未安装", "未安装" in window.model_chip.text(), window.model_chip.text())

        settings = window.settings
        settings._on_discover_models()
        check("扫描发现模型", settings.discover_combo.count() == 1, settings.discover_combo.currentText())
        settings._apply_discovered_model()
        discovered = Path(settings.model_path.text())
        check("选择后写入 GGUF 路径", discovered.is_file(), str(discovered))

        settings._save() if hasattr(settings, "_save") else None
        settings.save_btn.click()
        saved = str(load_config(sandbox).model_path)
        check("保存后配置持久化", saved == str(discovered), saved)

        window.refresh_status()
        check(
            "顶栏识别模型已安装",
            "已安装" in window.model_chip.text() or "就绪" in window.model_chip.text(),
            window.model_chip.text(),
        )
        check("启动按钮可用", settings.start_btn.isEnabled(), "")

        info = manager.start()
        check("经管理器启动真实服务", info.health_ok, manager.base_url)
        reply = client.test()
        check("界面配置的模型可推理", bool(reply.content.strip()), reply.content.strip()[:60])
        manager.stop()
        check("停止后端口释放", not manager.health(timeout=1.0), manager.base_url)
        window.close()
    except Exception as exc:  # noqa: BLE001 - acceptance harness
        import traceback

        traceback.print_exc()
        failures.append(f"{type(exc).__name__}: {exc}")
    finally:
        shutil.rmtree(sandbox, ignore_errors=True)
    print(f"\n结论：{'全部通过' if not failures else '失败项 ' + str(failures)}")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
