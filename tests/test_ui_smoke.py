from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from secone.config import AppConfig  # noqa: E402
from secone.db import TaskStore  # noqa: E402
from secone.domain import (  # noqa: E402
    AnalysisResult,
    FileArtifact,
    Finding,
    FlagCandidate,
    FlagStatus,
    Severity,
)
from secone.llm import LLMClient, LlamaServerManager  # noqa: E402
from secone.ui.context import AppContext  # noqa: E402
from secone.ui.main_window import MainWindow  # noqa: E402
from secone.ui.theme import apply_theme  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    yield app


def build_result(tmp_path: Path) -> AnalysisResult:
    return AnalysisResult(
        task_id="test-task",
        title="UI 冒烟测试",
        mode="auto",
        summary="UI 冒烟测试结果摘要。",
        flags=[
            FlagCandidate(
                value="flag{ui_sm0ke}",
                status=FlagStatus.FOUND,
                confidence=1.0,
                source="input/notes.txt",
                offset=10,
                method="直接匹配",
                evidence="flag{ui_sm0ke}",
            )
        ],
        findings=[
            Finding(
                title="危险命令执行函数",
                category="web",
                severity=Severity.HIGH,
                description="命令执行入口",
                evidence="os.system(cmd)",
                path="input/app.py",
                line=3,
                rule_id="web.command_exec",
            )
        ],
        files=[
            FileArtifact(
                path="input/notes.txt",
                size=32,
                sha256="0" * 64,
                kind="text",
                category="misc",
            )
        ],
        workspace=str(tmp_path),
    )


def test_discover_models_lists_gguf(
    qt_app, config: AppConfig, tmp_path: Path
) -> None:
    """The settings page must surface installed GGUF files instead of dead-ending."""
    models_dir = config.paths.models
    good = models_dir / "candidate-q6_k.gguf"
    good.write_bytes(b"GGUF" + b"\x00" * (128 * 1024))
    (models_dir / "tiny-fragment.gguf").write_bytes(b"GGUF")  # too small to be usable
    (models_dir / "notes.txt").write_text("not a model", encoding="utf-8")

    store = TaskStore(config.paths.db_file)
    manager = LlamaServerManager(config)
    client = LLMClient(config, manager)
    context = AppContext(config, config.paths, store, manager, client)
    window = MainWindow(context)
    try:
        settings = window.settings
        assert settings.discover_combo.isHidden() is True

        settings._on_discover_models()
        assert settings.discover_combo.isHidden() is False
        assert settings.discover_combo.count() == 1
        assert settings.discover_combo.itemText(0).startswith("candidate-q6_k.gguf")

        settings._apply_discovered_model()
        assert settings.model_path.text() == str(good)
    finally:
        window.close()


def test_discover_models_reports_empty_directory(
    qt_app, config: AppConfig, tmp_path: Path
) -> None:
    store = TaskStore(config.paths.db_file)
    manager = LlamaServerManager(config)
    client = LLMClient(config, manager)
    context = AppContext(config, config.paths, store, manager, client)
    window = MainWindow(context)
    messages: list[tuple[str, str]] = []
    try:
        window.settings.notify.connect(lambda text, tone: messages.append((text, tone)))
        window.settings._on_discover_models()
        assert messages and messages[-1][1] == "error"
        assert window.settings.discover_combo.isHidden() is True
    finally:
        window.close()


def test_main_window_renders_result(qt_app, config: AppConfig, tmp_path: Path) -> None:
    config.set("engine.port", 1)
    store = TaskStore(config.paths.db_file)
    manager = LlamaServerManager(config)
    client = LLMClient(config, manager)
    context = AppContext(config, config.paths, store, manager, client)
    window = MainWindow(context)
    try:
        assert window.pages.count() == 3
        assert window.workbench.count_label.text().endswith("0 项")
        window.workbench.show_result(build_result(tmp_path))
        assert window.workbench.result_stack.currentIndex() == 1
        assert window.workbench.tabs.count() == 4
        assert "结论" in window.workbench.tabs.tabText(0)
        assert window.workbench.export_btn.isEnabled()
        assert window.workbench.materials_list.count() == 1
        window.navigate("settings")
        assert window.pages.currentIndex() == 2
        window.navigate("history")
        assert window.pages.currentIndex() == 1
    finally:
        window.close()
