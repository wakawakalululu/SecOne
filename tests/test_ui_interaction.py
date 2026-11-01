from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QObject, Signal  # noqa: E402
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
from secone.ui.pages.workbench import WorkbenchPage  # noqa: E402
from secone.ui.theme import apply_theme  # noqa: E402


@pytest.fixture(scope="module")
def qt_app():
    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    yield app


@pytest.fixture
def context(config: AppConfig) -> AppContext:
    store = TaskStore(config.paths.db_file)
    manager = LlamaServerManager(config)
    client = LLMClient(config, manager)
    return AppContext(config, config.paths, store, manager, client)


@pytest.fixture
def page(qt_app, context: AppContext) -> WorkbenchPage:
    widget = WorkbenchPage(context)
    messages: list[tuple[str, str]] = []
    widget.notify.connect(lambda text, tone: messages.append((text, tone)))
    widget.messages = messages  # type: ignore[attr-defined]
    yield widget
    widget.close()


def build_result(tmp_path: Path, *, flags: bool = True) -> AnalysisResult:
    return AnalysisResult(
        task_id="ui-interaction",
        title="交互回归测试",
        mode="auto",
        summary="交互回归结果摘要。",
        flags=(
            [
                FlagCandidate(
                    value="flag{ui_1nt3r4ct}",
                    status=FlagStatus.FOUND,
                    confidence=1.0,
                    source="input/notes.txt",
                    offset=4,
                    method="直接匹配",
                    evidence="flag{ui_1nt3r4ct}",
                )
            ]
            if flags
            else []
        ),
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
                sha256="1" * 64,
                kind="text",
                category="misc",
            )
        ],
        workspace=str(tmp_path),
    )


class StubWorker(QObject):
    progress = Signal(int, str)
    completed = Signal(object)
    cancelled = Signal(str)
    failed = Signal(str)
    finished = Signal()

    instances: list["StubWorker"] = []

    def __init__(self, **kwargs):
        super().__init__(kwargs.get("parent"))
        self.kwargs = kwargs
        self.started = False
        self.cancel_called = False
        StubWorker.instances.append(self)

    def start(self) -> None:
        self.started = True

    def isRunning(self) -> bool:
        return self.started

    def cancel(self) -> None:
        self.cancel_called = True


@pytest.fixture
def stub_worker(monkeypatch) -> list[StubWorker]:
    StubWorker.instances = []
    monkeypatch.setattr(
        "secone.ui.pages.workbench.AnalysisWorker", StubWorker
    )
    return StubWorker.instances


def test_add_paths_accepts_file_and_folder_and_skips_duplicates(
    page: WorkbenchPage, tmp_path: Path
) -> None:
    sample = tmp_path / "notes.txt"
    sample.write_text("flag{...}", encoding="utf-8")
    folder = tmp_path / "materials"
    folder.mkdir()
    missing = tmp_path / "missing.bin"

    page.add_paths([sample, folder, sample, missing, str(sample)])

    assert page.selected_paths == [sample.resolve(), folder.resolve()]
    assert page.file_list.count() == 2
    assert page.file_list.isHidden() is False
    assert page.file_empty.isHidden() is True
    assert page.count_label.text().endswith("2 项")
    assert ("已添加 2 项材料。", "info") in page.messages  # type: ignore[attr-defined]


def test_add_paths_rejects_symlink_only(page: WorkbenchPage, tmp_path: Path) -> None:
    target = tmp_path / "secret.txt"
    target.write_text("flag{symlink_target}", encoding="utf-8")
    link = tmp_path / "linked.txt"
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("当前环境不允许创建符号链接")

    page.add_paths([str(link)])

    assert page.selected_paths == []
    assert page.file_list.count() == 0
    assert page.messages[-1][1] == "warning"  # type: ignore[attr-defined]


def test_drop_zone_signal_feeds_material_list(
    page: WorkbenchPage, tmp_path: Path
) -> None:
    sample = tmp_path / "drop.txt"
    sample.write_text("flag{drop_zone}", encoding="utf-8")

    page.drop_zone.filesDropped.emit([str(sample)])

    assert page.selected_paths == [sample.resolve()]
    assert page.file_list.count() == 1
    item = page.file_list.item(0)
    assert item is not None
    assert item.toolTip() == str(sample.resolve())


def test_remove_selected_and_clear_inputs(
    page: WorkbenchPage, tmp_path: Path
) -> None:
    first = tmp_path / "a.txt"
    second = tmp_path / "b.txt"
    first.write_text("flag{a}", encoding="utf-8")
    second.write_text("flag{b}", encoding="utf-8")
    page.add_paths([first, second])
    page.text_edit.setPlainText("补充文本")

    page.file_list.item(0).setSelected(True)
    page.remove_selected()

    assert page.selected_paths == [second.resolve()]
    assert page.file_list.count() == 1

    page.clear_inputs()

    assert page.selected_paths == []
    assert page.text_edit.toPlainText() == ""
    assert page.file_list.count() == 0
    assert page.file_empty.isHidden() is False


def test_start_analysis_requires_material(page: WorkbenchPage) -> None:
    page.start_analysis("auto")

    assert page.is_busy is False
    assert page.messages[-1][1] == "warning"  # type: ignore[attr-defined]
    assert "拖入材料" in page.messages[-1][0]  # type: ignore[attr-defined]


def test_text_only_start_locks_controls_and_rejects_second_run(
    page: WorkbenchPage, stub_worker
) -> None:
    page.text_edit.setPlainText("题目描述：flag{...}")

    page.start_analysis("crypto")

    assert len(stub_worker) == 1
    worker = stub_worker[0]
    assert worker.started is True
    assert worker.kwargs["sources"] == []
    assert worker.kwargs["text"] == "题目描述：flag{...}"
    assert worker.kwargs["mode"] == "crypto"
    assert page.is_busy is True
    assert page.worker_running is True
    assert page.auto_btn.isEnabled() is False
    assert page.text_edit.isEnabled() is False
    assert page.drop_zone.isEnabled() is False

    page.start_analysis("web")

    assert len(stub_worker) == 1
    assert page.messages[-1][1] == "warning"  # type: ignore[attr-defined]
    assert "已有分析任务" in page.messages[-1][0]  # type: ignore[attr-defined]


def test_cancel_analysis_marks_cancelled_and_unlocks(
    page: WorkbenchPage, stub_worker
) -> None:
    page.text_edit.setPlainText("题目描述：flag{...}")
    page.start_analysis("auto")
    worker = stub_worker[0]

    assert page.cancel_btn.isHidden() is False
    assert page.cancel_btn.isEnabled() is True

    page.cancel_analysis()

    assert worker.cancel_called is True
    assert page.cancel_btn.isEnabled() is False
    assert page.is_busy is True
    assert "正在取消" in page.progress_label.text()
    assert page.messages[-1] == ("正在取消分析任务，请稍候。", "info")  # type: ignore[attr-defined]

    page._on_cancelled("分析已取消，材料输入已保留。")

    assert page.is_busy is False
    assert "已取消" in page.result_chip.text()
    assert page.cancel_btn.isHidden() is True
    assert page.auto_btn.isEnabled() is True
    assert page.text_edit.isEnabled() is True
    assert page.text_edit.toPlainText() == "题目描述：flag{...}"
    assert page.progress_pct.text() == "—"
    assert "已取消" in page.progress_label.text()
    assert page.messages[-1] == (  # type: ignore[attr-defined]
        "分析已取消，材料输入已保留。",
        "warning",
    )


def test_progress_updates_are_visible(page: WorkbenchPage) -> None:
    page._on_progress(42, "正在解码第 3 层")

    assert page.progress.value() == 42
    assert page.progress_pct.text() == "42%"
    assert page.progress_label.text() == "正在解码第 3 层"


def test_completed_result_renders_and_unlocks_controls(
    page: WorkbenchPage, tmp_path: Path
) -> None:
    result = build_result(tmp_path)
    page._busy = True
    page._set_controls_enabled(False)

    page._on_completed(result)

    assert page.is_busy is False
    assert page.current_result is result
    assert page.progress.value() == 100
    assert page.progress_pct.text() == "100%"
    assert "分析完成" in page.progress_label.text()
    assert page.auto_btn.isEnabled() is True
    assert page.text_edit.isEnabled() is True
    assert page.export_btn.isEnabled() is True
    assert page.result_stack.currentIndex() == 1
    assert page.tabs.count() == 4
    assert page.tabs.tabText(0) == "结论 · 1"
    assert page.tabs.tabText(1) == "发现 · 1"
    assert page.tabs.tabText(3) == "材料 · 1"
    assert page.files_metric.value_label.text() == "1"
    assert page.findings_metric.value_label.text() == "1"
    assert page.high_metric.value_label.text() == "1"
    assert page.materials_list.count() == 1
    assert "已验证" in page.result_chip.text() or "已发现" in page.result_chip.text()
    assert page.messages[-1][1] == "success"  # type: ignore[attr-defined]


def test_export_report_writes_files(
    page: WorkbenchPage, tmp_path: Path, config: AppConfig
) -> None:
    page.show_result(build_result(tmp_path))

    page.export_report()

    assert page.messages[-1][1] == "success"  # type: ignore[attr-defined]
    assert page.open_report_btn.isEnabled() is True
    report_paths = page.current_result.report_paths
    for key in ("json", "markdown", "text", "summary"):
        assert Path(report_paths[key]).is_file()
    candidates = tmp_path / "flags" / "candidates.json"
    evidence = tmp_path / "evidence" / "index.json"
    assert candidates.is_file()
    assert evidence.is_file()


def test_failure_recovers_controls(page: WorkbenchPage) -> None:
    page._busy = True
    page._set_controls_enabled(False)

    page._on_failed("模拟推理服务不可用")

    assert page.is_busy is False
    assert page.auto_btn.isEnabled() is True
    assert page.text_edit.isEnabled() is True
    assert "分析失败" in page.result_chip.text()
    assert "分析中断" in page.progress_label.text()
    assert page.progress_pct.text() == "—"
    assert page.messages[-1] == ("模拟推理服务不可用", "error")  # type: ignore[attr-defined]
