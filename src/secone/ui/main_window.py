from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from ..domain import AnalysisResult
from .context import AppContext
from .pages.history import HistoryPage
from .pages.settings import SettingsPage
from .pages.workbench import WorkbenchPage
from .widgets import ElidedLabel, LogoMark, NavButton, StatusChip, Toast
from .worker import ModelWorker

logger = logging.getLogger(__name__)

PAGE_PATHS = {
    "workbench": "WORKBENCH",
    "history": "CASE ARCHIVE",
    "settings": "ENGINE / SETTINGS",
}
PAGE_INDEX = {"workbench": "01", "history": "02", "settings": "03"}


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext):
        super().__init__()
        self.context = context
        self._closing = False
        self.auto_worker: ModelWorker | None = None
        self.nav_buttons: dict[str, NavButton] = {}
        self.setWindowTitle("SecOne · 本地 AI 安全分析工作台")
        self.setMinimumSize(1120, 740)
        self.resize(1380, 880)
        icon_path = context.paths.root / "assets" / "secone.svg"
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        self._build_ui()
        self._connect_signals()
        self.navigate("workbench", initial=True)
        self._fit_to_screen()

    def _build_ui(self) -> None:
        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())

        content = QWidget()
        content.setObjectName("ContentArea")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._build_topbar())

        page_container = QWidget()
        page_layout = QVBoxLayout(page_container)
        page_layout.setContentsMargins(26, 18, 26, 20)
        page_layout.setSpacing(0)
        self.pages = QStackedWidget()
        self.workbench = WorkbenchPage(self.context)
        self.history = HistoryPage(self.context)
        self.settings = SettingsPage(self.context)
        self.pages.addWidget(self.workbench)
        self.pages.addWidget(self.history)
        self.pages.addWidget(self.settings)
        page_layout.addWidget(self.pages)
        content_layout.addWidget(page_container, 1)
        layout.addWidget(content, 1)

        self.toast = Toast(self)
        self.toast.hide()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(232)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(18, 22, 16, 18)
        layout.setSpacing(0)

        brand = QHBoxLayout()
        brand.setSpacing(10)
        brand.addWidget(LogoMark())
        brand_text = QVBoxLayout()
        brand_text.setSpacing(1)
        title = QLabel("SECONE")
        title.setObjectName("Brand")
        brand_text.addWidget(title)
        subtitle = QLabel("LOCAL SECURITY LAB")
        subtitle.setObjectName("BrandSub")
        brand_text.addWidget(subtitle)
        brand.addLayout(brand_text)
        brand.addStretch(1)
        layout.addLayout(brand)
        layout.addSpacing(34)

        section = QLabel("WORKSPACE")
        section.setObjectName("Kicker")
        layout.addWidget(section)
        layout.addSpacing(8)

        group = QButtonGroup(sidebar)
        group.setExclusive(True)
        for name, index, text in (
            ("workbench", "01", "分析工作台"),
            ("history", "02", "任务历史"),
            ("settings", "03", "模型与设置"),
        ):
            button = NavButton(index, text)
            button.clicked.connect(lambda checked=False, page=name: self.navigate(page))
            group.addButton(button)
            self.nav_buttons[name] = button
            layout.addWidget(button)
            layout.addSpacing(4)
        layout.addStretch(1)

        line = QFrame()
        line.setObjectName("Divider")
        layout.addWidget(line)
        layout.addSpacing(14)

        status_title = QLabel("SYSTEM STATUS")
        status_title.setObjectName("Kicker")
        layout.addWidget(status_title)
        layout.addSpacing(7)
        self.sidebar_offline = StatusChip("数据不出本机", "success")
        layout.addWidget(self.sidebar_offline, 0, Qt.AlignLeft)
        layout.addSpacing(6)
        self.sidebar_model = StatusChip("模型检查中", "neutral")
        layout.addWidget(self.sidebar_model, 0, Qt.AlignLeft)
        layout.addSpacing(14)

        workspace_label = QLabel("工作区")
        workspace_label.setObjectName("Kicker")
        layout.addWidget(workspace_label)
        self.workspace_path = ElidedLabel(str(self.context.paths.workspace))
        self.workspace_path.setObjectName("Dim")
        layout.addWidget(self.workspace_path)
        open_workspace = QPushButton("打开工作区")
        open_workspace.setObjectName("LinkButton")
        open_workspace.clicked.connect(self._open_workspace)
        layout.addWidget(open_workspace, 0, Qt.AlignLeft)
        layout.addSpacing(14)
        version = QLabel(f"v{self.context.config.get('app.version', '1.0.0-rc1')} · PYSIDE6 · LLAMA.CPP")
        version.setObjectName("BrandSub")
        layout.addWidget(version)
        return sidebar

    def _build_topbar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(58)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(26, 0, 26, 0)
        layout.setSpacing(8)
        self.path_label = QLabel("SECONE / 01 / WORKBENCH")
        self.path_label.setObjectName("TopPath")
        layout.addWidget(self.path_label)
        layout.addStretch(1)
        self.offline_chip = StatusChip("OFFLINE", "success")
        self.offline_chip.setToolTip("静态分析与模型推理均在本机完成")
        self.model_chip = StatusChip("模型检查中", "neutral")
        self.server_chip = StatusChip("引擎检查中", "neutral")
        layout.addWidget(self.offline_chip)
        layout.addWidget(self.model_chip)
        layout.addWidget(self.server_chip)
        return bar

    def _connect_signals(self) -> None:
        self.workbench.notify.connect(self.notify)
        self.workbench.historyChanged.connect(self.history.refresh)
        self.workbench.statusChanged.connect(self.refresh_status)
        self.workbench.analysisFinished.connect(self._on_analysis_finished)
        self.history.notify.connect(self.notify)
        self.history.openResult.connect(self.open_result)
        self.settings.notify.connect(self.notify)
        self.settings.modelChanged.connect(self._on_model_changed)

    def navigate(self, page: str, initial: bool = False) -> None:
        mapping = {"workbench": 0, "history": 1, "settings": 2}
        index = mapping.get(page, 0)
        self.pages.setCurrentIndex(index)
        for name, button in self.nav_buttons.items():
            button.setChecked(name == page)
        current = [name for name, idx in mapping.items() if idx == index][0]
        self.path_label.setText(f"SECONE / {PAGE_INDEX[current]} / {PAGE_PATHS[current]}")
        if page == "history":
            self.history.refresh()
        elif page == "settings":
            self.settings.refresh_status()
            self.settings.refresh_log()
        if initial:
            self.toast.reposition()

    def open_result(self, result: AnalysisResult) -> None:
        self.workbench.show_result(result, historical=True)
        self.navigate("workbench")
        self.notify(f"已载入历史任务：{result.title}", "info")

    def notify(self, message: str, tone: str = "info") -> None:
        if not message:
            return
        milliseconds = 7000 if tone in ("error", "warning") else 4500
        self.toast.display(message, tone, milliseconds)
        self.toast.reposition()

    def bootstrap(self) -> None:
        self.refresh_status()
        try:
            info = self.context.manager.model_info()
        except Exception as exc:
            logger.exception("Model status check failed")
            self.notify(f"模型状态检查失败：{exc}", "error")
            return
        if info.health_ok:
            return
        if not info.model_exists:
            self.notify(
                "未检测到可用的本地模型（GGUF）。静态分析仍可离线使用；请在“模型与设置”中安装模型资源，更换模型无需改动程序。",
                "warning",
            )
            return
        if not info.runtime_exists:
            self.notify(
                "检测到模型文件，但缺少 llama-server 运行组件。请安装 runtime/ 中的推理引擎。",
                "warning",
            )
            return
        if self.context.config.get("engine.auto_start", True):
            self._auto_start_model()

    def _auto_start_model(self) -> None:
        if self.auto_worker and self.auto_worker.isRunning():
            return
        self.model_chip.set_tone("模型加载中", "info")
        self.server_chip.set_tone("引擎启动中", "info")
        self.auto_worker = ModelWorker(self.context, "start", parent=self)
        self.auto_worker.progress.connect(
            lambda message: self.server_chip.set_tone("引擎加载中", "info")
        )
        self.auto_worker.completed.connect(self._on_auto_model_completed)
        self.auto_worker.failed.connect(self._on_auto_model_failed)
        self.auto_worker.finished.connect(self._on_auto_worker_finished)
        self.auto_worker.start()

    def _on_auto_model_completed(self, message: str) -> None:
        self.notify(message, "success")
        self.refresh_status()

    def _on_auto_model_failed(self, message: str) -> None:
        self.notify(f"本地模型启动失败：{message[:700]}", "error")
        self.refresh_status()

    def _on_auto_worker_finished(self) -> None:
        if self.auto_worker:
            self.auto_worker.deleteLater()
            self.auto_worker = None
        if self._closing:
            QTimer.singleShot(200, self._try_close)

    def _on_model_changed(self) -> None:
        self.refresh_status()
        if self._closing:
            QTimer.singleShot(200, self._try_close)

    def _on_analysis_finished(self) -> None:
        self.refresh_status()
        if self._closing:
            QTimer.singleShot(200, self._try_close)

    def refresh_status(self) -> None:
        try:
            info = self.context.manager.model_info()
        except Exception as exc:
            logger.exception("Refresh model status failed")
            self.model_chip.set_tone("模型状态异常", "danger")
            self.server_chip.set_tone("引擎状态异常", "danger")
            self.sidebar_model.set_tone("模型状态异常", "danger")
            return
        if not info.model_exists:
            self.model_chip.set_tone("模型未安装", "danger")
            self.sidebar_model.set_tone("模型未安装", "danger")
        elif not info.gguf_valid:
            self.model_chip.set_tone("模型文件无效", "danger")
            self.sidebar_model.set_tone("模型文件无效", "danger")
        elif info.health_ok:
            self.model_chip.set_tone("模型在线", "success")
            self.sidebar_model.set_tone("本地模型在线", "success")
        elif not info.runtime_exists:
            self.model_chip.set_tone("模型已安装", "info")
            self.sidebar_model.set_tone("缺少推理引擎", "danger")
        else:
            self.model_chip.set_tone("模型就绪", "info")
            self.sidebar_model.set_tone("模型待启动", "neutral")

        if info.health_ok:
            self.server_chip.set_tone("LLAMA.CPP 在线", "success")
        elif not info.runtime_exists:
            self.server_chip.set_tone("引擎缺失", "danger")
        elif info.model_exists and info.gguf_valid:
            self.server_chip.set_tone("引擎待启动", "neutral")
        else:
            self.server_chip.set_tone("引擎不可用", "danger")
        self.model_chip.setToolTip(
            str(info.model_path) if info.model_exists else "未找到 GGUF 模型文件"
        )
        self.server_chip.setToolTip(self.context.manager.base_url)

    def _try_close(self) -> None:
        if self._any_worker_running():
            QTimer.singleShot(350, self._try_close)
            return
        self.close()

    def _any_worker_running(self) -> bool:
        return bool(
            self.workbench.worker_running
            or self.settings.worker_running
            or (self.auto_worker and self.auto_worker.isRunning())
        )

    def closeEvent(self, event) -> None:  # noqa: N802
        if self.workbench.is_busy:
            self.notify("分析任务正在运行，请等待完成后再关闭窗口。", "warning")
            event.ignore()
            return
        if self._any_worker_running():
            self._closing = True
            self.notify("正在停止后台模型任务，请稍候 …", "info")
            self.context.manager.stop()
            event.ignore()
            QTimer.singleShot(250, self._try_close)
            return
        self.context.manager.stop()
        self.toast.hide()
        event.accept()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        if hasattr(self, "toast"):
            self.toast.reposition()

    def _fit_to_screen(self) -> None:
        screen = self.screen()
        if not screen:
            return
        available = screen.availableGeometry()
        width = min(self.width(), max(available.width() - 80, 1120))
        height = min(self.height(), max(available.height() - 100, 740))
        self.resize(width, height)
        self.move(
            available.x() + (available.width() - width) // 2,
            available.y() + (available.height() - height) // 2,
        )

    def _open_workspace(self) -> None:
        path = self.context.paths.workspace
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
