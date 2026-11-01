from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from ...core.fileio import format_size, kind_label
from ...core.report import MODE_LABELS, ReportWriter
from ...domain import AnalysisResult, FlagStatus, Severity
from ..context import AppContext
from ..widgets import (
    DropZone,
    EmptyState,
    FindingCard,
    FlagCard,
    MetricCard,
    StatusChip,
)
from ..worker import AnalysisWorker

logger = logging.getLogger(__name__)


class WorkbenchPage(QWidget):
    notify = Signal(str, str)
    historyChanged = Signal()
    statusChanged = Signal()
    analysisFinished = Signal()

    def __init__(self, context: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.context = context
        self.selected_paths: list[Path] = []
        self.current_result: AnalysisResult | None = None
        self.worker = None
        self._busy = False

        self._build_ui()
        self._connect_shortcuts()
        self._refresh_file_list()

    @property
    def is_busy(self) -> bool:
        return self._busy

    @property
    def worker_running(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(16)

        root.addLayout(self._build_hero())

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.setHandleWidth(16)
        splitter.addWidget(self._build_input_panel())
        splitter.addWidget(self._build_result_panel())
        splitter.setStretchFactor(0, 5)
        splitter.setStretchFactor(1, 6)
        splitter.setSizes([540, 650])
        root.addWidget(splitter, 1)
        root.addWidget(self._build_action_panel())

    def _build_hero(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(18)
        text_layout = QVBoxLayout()
        text_layout.setSpacing(6)
        kicker = QLabel("LOCAL / ZERO TELEMETRY / EVIDENCE FIRST")
        kicker.setObjectName("Kicker")
        text_layout.addWidget(kicker)
        title = QLabel("本地 AI 安全分析工作台")
        title.setObjectName("HeroTitle")
        text_layout.addWidget(title)
        subtitle = QLabel("拖入题目材料，选择分析路径。模型推理、文件解析与证据索引都留在本机。")
        subtitle.setObjectName("HeroSub")
        subtitle.setWordWrap(True)
        text_layout.addWidget(subtitle)
        layout.addLayout(text_layout, 1)

        index = QLabel("01")
        index.setStyleSheet(
            "color: #182B37; font-family: Consolas; font-size: 58px; font-weight: 700;"
        )
        index.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(index)
        index_meta = QVBoxLayout()
        index_meta.setSpacing(2)
        index_meta.addStretch(1)
        label = QLabel("MATERIAL\nINTAKE")
        label.setStyleSheet(
            "color: #536A7C; font-family: Consolas; font-size: 9px;"
        )
        label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        index_meta.addWidget(label)
        index_meta.addStretch(1)
        layout.addLayout(index_meta)
        return layout

    def _build_input_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setMinimumWidth(420)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("输入材料")
        title.setObjectName("PanelTitle")
        titles.addWidget(title)
        subtitle = QLabel("文件、压缩包、文件夹与文本可混合提交")
        subtitle.setObjectName("PanelSub")
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.count_label = StatusChip("0 项", "neutral")
        header.addWidget(self.count_label)
        layout.addLayout(header)

        self.drop_zone = DropZone()
        self.drop_zone.filesDropped.connect(self.add_paths)
        self.drop_zone.browseRequested.connect(self.browse_files)
        layout.addWidget(self.drop_zone)

        button_row = QHBoxLayout()
        button_row.setSpacing(6)
        self.add_file_btn = QPushButton("添加文件")
        self.add_file_btn.setObjectName("GhostButton")
        self.add_file_btn.clicked.connect(self.browse_files)
        self.add_dir_btn = QPushButton("添加文件夹")
        self.add_dir_btn.setObjectName("GhostButton")
        self.add_dir_btn.clicked.connect(self.browse_folder)
        self.remove_btn = QPushButton("移除选中")
        self.remove_btn.setObjectName("LinkButton")
        self.remove_btn.clicked.connect(self.remove_selected)
        self.clear_btn = QPushButton("清空")
        self.clear_btn.setObjectName("LinkButton")
        self.clear_btn.clicked.connect(self.clear_inputs)
        button_row.addWidget(self.add_file_btn)
        button_row.addWidget(self.add_dir_btn)
        button_row.addStretch(1)
        button_row.addWidget(self.remove_btn)
        button_row.addWidget(self.clear_btn)
        layout.addLayout(button_row)

        self.file_empty = QLabel("尚未选择材料。拖入文件或文件夹后，会显示在这里。")
        self.file_empty.setObjectName("EmptySub")
        self.file_empty.setWordWrap(True)
        self.file_empty.setMinimumHeight(44)
        layout.addWidget(self.file_empty)

        self.file_list = QListWidget()
        self.file_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.file_list.setMinimumHeight(72)
        self.file_list.setMaximumHeight(128)
        self.file_list.itemSelectionChanged.connect(self._update_button_state)
        layout.addWidget(self.file_list)
        self.file_list.hide()

        text_label = QLabel("补充文本 / 源码")
        text_label.setObjectName("PanelSub")
        layout.addWidget(text_label)
        self.text_edit = QPlainTextEdit()
        self.text_edit.setPlaceholderText(
            "可粘贴题目描述、编码字符串、日志片段或源码。该内容会与文件一起进入分析任务。"
        )
        self.text_edit.setMinimumHeight(82)
        self.text_edit.setMaximumHeight(120)
        self.text_edit.textChanged.connect(self._update_button_state)
        layout.addWidget(self.text_edit)
        return panel

    def _build_result_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        panel.setMinimumWidth(470)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(1)
        title = QLabel("分析结果")
        title.setObjectName("PanelTitle")
        titles.addWidget(title)
        self.result_sub = QLabel("Flag 候选、静态发现、模型研判与材料证据")
        self.result_sub.setObjectName("PanelSub")
        titles.addWidget(self.result_sub)
        header.addLayout(titles, 1)
        self.open_report_btn = QPushButton("打开报告目录")
        self.open_report_btn.setObjectName("LinkButton")
        self.open_report_btn.clicked.connect(self.open_report_folder)
        self.open_report_btn.setEnabled(False)
        header.addWidget(self.open_report_btn)
        self.result_chip = StatusChip("待分析", "neutral")
        header.addWidget(self.result_chip)
        layout.addLayout(header)

        self.summary_label = QLabel("尚未运行分析。拖入材料后选择分析模式。")
        self.summary_label.setObjectName("Muted")
        self.summary_label.setWordWrap(True)
        self.summary_label.setMinimumHeight(36)
        layout.addWidget(self.summary_label)

        metrics = QHBoxLayout()
        metrics.setSpacing(7)
        self.files_metric = MetricCard("文件", "0")
        self.findings_metric = MetricCard("静态发现", "0")
        self.high_metric = MetricCard("高危", "0")
        self.duration_metric = MetricCard("耗时", "—")
        for card in (
            self.files_metric,
            self.findings_metric,
            self.high_metric,
            self.duration_metric,
        ):
            metrics.addWidget(card, 1)
        layout.addLayout(metrics)

        self.result_stack = QStackedWidget()
        empty = EmptyState(
            "等待分析",
            "结果会按 Flag 候选、静态发现、AI 研判和材料清单分栏展示。",
            "◇",
        )
        self.result_stack.addWidget(empty)
        self.result_stack.addWidget(self._build_result_tabs())
        layout.addWidget(self.result_stack, 1)
        return panel

    def _build_result_tabs(self) -> QTabWidget:
        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)

        self.flags_scroll = QScrollArea()
        self.flags_scroll.setWidgetResizable(True)
        self.flags_widget = QWidget()
        self.flags_layout = QVBoxLayout(self.flags_widget)
        self.flags_layout.setContentsMargins(2, 8, 8, 8)
        self.flags_layout.setSpacing(8)
        self.flags_layout.addStretch(1)
        self.flags_scroll.setWidget(self.flags_widget)
        self.tabs.addTab(self.flags_scroll, "结论")

        self.findings_scroll = QScrollArea()
        self.findings_scroll.setWidgetResizable(True)
        self.findings_widget = QWidget()
        self.findings_layout = QVBoxLayout(self.findings_widget)
        self.findings_layout.setContentsMargins(2, 8, 8, 8)
        self.findings_layout.setSpacing(7)
        self.findings_layout.addStretch(1)
        self.findings_scroll.setWidget(self.findings_widget)
        self.tabs.addTab(self.findings_scroll, "发现")

        self.ai_view = QTextBrowser()
        self.ai_view.setOpenLinks(False)
        self.ai_view.setOpenExternalLinks(False)
        self.ai_view.setPlaceholderText("本地模型尚未参与分析。")
        self.tabs.addTab(self.ai_view, "AI 分析")

        self.materials_list = QListWidget()
        self.materials_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.tabs.addTab(self.materials_list, "材料")

        self.tabs.setCurrentIndex(0)
        return self.tabs

    def _build_action_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 12, 18, 13)
        layout.setSpacing(8)

        progress_row = QHBoxLayout()
        progress_row.setSpacing(8)
        self.progress_label = QLabel("就绪。静态分析不依赖模型，联网状态始终为离线。")
        self.progress_label.setObjectName("PanelSub")
        progress_row.addWidget(self.progress_label, 1)
        self.progress_pct = QLabel("—")
        self.progress_pct.setObjectName("Dim")
        progress_row.addWidget(self.progress_pct)
        layout.addLayout(progress_row)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(6)
        layout.addWidget(self.progress)

        buttons = QHBoxLayout()
        buttons.setSpacing(7)
        self.auto_btn = QPushButton("一键梭哈")
        self.auto_btn.setObjectName("PrimaryButton")
        self.auto_btn.setToolTip("自动识别题型并执行完整分析流水线（Ctrl+Enter）")
        self.auto_btn.clicked.connect(lambda: self.start_analysis("auto"))
        self.crypto_btn = QPushButton("Crypto 分析")
        self.crypto_btn.setObjectName("ModeButton")
        self.crypto_btn.clicked.connect(lambda: self.start_analysis("crypto"))
        self.forensics_btn = QPushButton("文件取证")
        self.forensics_btn.setObjectName("ModeButton")
        self.forensics_btn.clicked.connect(lambda: self.start_analysis("forensics"))
        self.web_btn = QPushButton("代码审计")
        self.web_btn.setObjectName("ModeButton")
        self.web_btn.clicked.connect(lambda: self.start_analysis("web"))
        self.export_btn = QPushButton("导出报告")
        self.export_btn.setObjectName("GhostButton")
        self.export_btn.clicked.connect(self.export_report)
        self.export_btn.setEnabled(False)
        self.cancel_btn = QPushButton("取消任务")
        self.cancel_btn.setObjectName("GhostButton")
        self.cancel_btn.setToolTip("停止当前分析任务；已生成的部分结果不会保存。")
        self.cancel_btn.clicked.connect(self.cancel_analysis)
        self.cancel_btn.hide()
        buttons.addWidget(self.auto_btn)
        buttons.addWidget(self.crypto_btn)
        buttons.addWidget(self.forensics_btn)
        buttons.addWidget(self.web_btn)
        buttons.addStretch(1)
        buttons.addWidget(self.cancel_btn)
        buttons.addWidget(self.export_btn)
        layout.addLayout(buttons)
        self.mode_buttons = [
            self.auto_btn,
            self.crypto_btn,
            self.forensics_btn,
            self.web_btn,
        ]
        return panel

    def _connect_shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+O"), self).activated.connect(self.browse_files)
        QShortcut(QKeySequence("Ctrl+Return"), self).activated.connect(
            lambda: self.start_analysis("auto")
        )

    def browse_files(self) -> None:
        files, _ = QFileDialog.getOpenFileNames(self, "选择分析材料", "", "所有文件 (*.*)")
        if files:
            self.add_paths(files)

    def browse_folder(self) -> None:
        directory = QFileDialog.getExistingDirectory(self, "选择材料文件夹")
        if directory:
            self.add_paths([directory])

    def add_paths(self, paths) -> None:
        if self._busy:
            return
        existing = {path.resolve() for path in self.selected_paths}
        added = 0
        for raw in paths:
            path = Path(str(raw)).expanduser()
            if path.is_symlink():
                continue
            try:
                path = path.resolve()
            except OSError:
                continue
            if not path.exists() or path in existing:
                continue
            self.selected_paths.append(path)
            existing.add(path)
            added += 1
        if added:
            self._refresh_file_list()
            self.notify.emit(f"已添加 {added} 项材料。", "info")
        elif paths:
            self.notify.emit("未添加新路径：路径不存在、重复或为符号链接。", "warning")

    def remove_selected(self) -> None:
        selected = {
            item.data(Qt.UserRole)
            for item in self.file_list.selectedItems()
            if item.data(Qt.UserRole)
        }
        if not selected:
            return
        self.selected_paths = [
            path for path in self.selected_paths if str(path) not in selected
        ]
        self._refresh_file_list()

    def clear_inputs(self) -> None:
        if self._busy:
            return
        self.selected_paths.clear()
        self.text_edit.clear()
        self._refresh_file_list()

    def _refresh_file_list(self) -> None:
        self.file_list.clear()
        for path in self.selected_paths:
            try:
                if path.is_dir():
                    detail = "文件夹"
                else:
                    detail = f"{format_size(path.stat().st_size)} · 文件"
            except OSError:
                detail = "无法读取"
            item = QListWidgetItem(f"{path.name}\n{detail}  ·  {path.parent}")
            item.setData(Qt.UserRole, str(path))
            item.setToolTip(str(path))
            item.setSizeHint(QSize(0, 42))
            self.file_list.addItem(item)
        count = len(self.selected_paths)
        self.count_label.set_tone(f"{count} 项", "success" if count else "neutral")
        self.file_list.setVisible(bool(count))
        self.file_empty.setVisible(not count)
        self._update_button_state()

    def _update_button_state(self) -> None:
        self.remove_btn.setEnabled(bool(self.file_list.selectedItems()) and not self._busy)
        self.clear_btn.setEnabled(
            bool(self.selected_paths or self.text_edit.toPlainText().strip())
            and not self._busy
        )
        self.export_btn.setEnabled(self.current_result is not None and not self._busy)

    def start_analysis(self, mode: str) -> None:
        if self._busy:
            self.notify.emit("已有分析任务正在运行，请等待完成。", "warning")
            return
        text = self.text_edit.toPlainText()
        if not self.selected_paths and not text.strip():
            self.notify.emit("请先拖入材料、添加文件夹，或粘贴题目文本。", "warning")
            return
        self._busy = True
        self._set_controls_enabled(False)
        self.result_chip.set_tone("分析中", "info")
        self.progress.setValue(0)
        self.progress_pct.setText("0%")
        self.progress_label.setText(f"启动{MODE_LABELS.get(mode, mode)}流水线 …")
        self.summary_label.setText("正在处理材料。静态分析完成后会调用本地模型进行深度研判。")
        self.open_report_btn.setEnabled(False)

        title_hint = ""
        self.worker = AnalysisWorker(
            context=self.context,
            sources=list(self.selected_paths),
            text=text,
            mode=mode,
            title_hint=title_hint,
            parent=self,
        )
        self.worker.progress.connect(self._on_progress)
        self.worker.completed.connect(self._on_completed)
        self.worker.cancelled.connect(self._on_cancelled)
        self.worker.failed.connect(self._on_failed)
        self.worker.finished.connect(self._on_worker_finished)
        self.worker.start()

    def _set_controls_enabled(self, enabled: bool) -> None:
        for widget in (
            self.drop_zone,
            self.text_edit,
            self.add_file_btn,
            self.add_dir_btn,
            self.file_list,
        ):
            widget.setEnabled(enabled)
        for button in self.mode_buttons:
            button.setEnabled(enabled)
        self.remove_btn.setEnabled(enabled and bool(self.file_list.selectedItems()))
        self.clear_btn.setEnabled(
            enabled
            and bool(self.selected_paths or self.text_edit.toPlainText().strip())
        )
        self.export_btn.setEnabled(enabled and self.current_result is not None)
        self.cancel_btn.setVisible(not enabled)
        self.cancel_btn.setEnabled(not enabled)

    def cancel_analysis(self) -> None:
        if not self._busy or not self.worker:
            return
        if not self.worker_running:
            return
        self.worker.cancel()
        self.cancel_btn.setEnabled(False)
        self.result_chip.set_tone("取消中", "warning")
        self.progress_label.setText("正在取消任务 …")
        self.notify.emit("正在取消分析任务，请稍候。", "info")

    def _on_cancelled(self, message: str) -> None:
        self._busy = False
        self._set_controls_enabled(True)
        self.result_chip.set_tone("已取消", "neutral")
        self.progress.setValue(0)
        self.progress_pct.setText("—")
        self.progress_label.setText("任务已取消。材料输入已保留，可重新运行。")
        self.notify.emit(message or "分析已取消。", "warning")
        self.historyChanged.emit()
        self.statusChanged.emit()
        self.analysisFinished.emit()

    def _on_progress(self, percent: int, message: str) -> None:
        self.progress.setValue(percent)
        self.progress_pct.setText(f"{percent}%")
        self.progress_label.setText(message)

    def _on_completed(self, result: AnalysisResult) -> None:
        self._busy = False
        self._set_controls_enabled(True)
        self.current_result = result
        self.progress.setValue(100)
        self.progress_pct.setText("100%")
        self.progress_label.setText(
            f"分析完成 · {len(result.files)} 个文件 · {len(result.flags)} 个 Flag 结果 · "
            f"{len(result.findings)} 条发现"
        )
        self.export_btn.setEnabled(True)
        self.show_result(result)
        self.historyChanged.emit()
        self.statusChanged.emit()
        self.analysisFinished.emit()
        if result.flags:
            self.notify.emit(
                f"分析完成：{len(result.flags)} 个 Flag 结果，{len(result.findings)} 条证据。",
                "success",
            )
        else:
            self.notify.emit(
                "分析完成，但未发现可靠 Flag。可补充题目文本或查看静态发现。",
                "warning",
            )

    def _on_failed(self, message: str) -> None:
        self._busy = False
        self._set_controls_enabled(True)
        self.result_chip.set_tone("分析失败", "danger")
        self.progress.setValue(0)
        self.progress_pct.setText("—")
        self.progress_label.setText("分析中断。请查看日志或调整材料后重试。")
        self.notify.emit(message[:800], "error")
        self.historyChanged.emit()
        self.statusChanged.emit()
        self.analysisFinished.emit()

    def _on_worker_finished(self) -> None:
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def show_result(self, result: AnalysisResult, historical: bool = False) -> None:
        self.current_result = result
        self.summary_label.setText(result.summary or "分析完成。")
        confirmed = len(result.confirmed_flags)
        candidates = len(result.candidates)
        if confirmed:
            self.result_chip.set_tone(
                "已验证 Flag" if any(
                    flag.status == FlagStatus.VERIFIED for flag in result.flags
                ) else "已发现 Flag",
                "success",
            )
        elif candidates:
            self.result_chip.set_tone("待验证候选", "warning")
        else:
            self.result_chip.set_tone("未发现 Flag", "neutral")
        if historical:
            self.result_chip.set_tone("历史结果", "info")

        self.files_metric.set_value(len(result.files))
        self.findings_metric.set_value(len(result.findings))
        high = sum(
            1
            for finding in result.findings
            if finding.severity in (Severity.CRITICAL, Severity.HIGH)
        )
        self.high_metric.set_value(high)
        self.duration_metric.set_value(f"{result.duration_seconds:.1f}s")
        self._render_flags(result)
        self._render_findings(result)
        self._render_ai(result)
        self._render_materials(result)
        self.tabs.setTabText(0, f"结论 · {len(result.flags)}")
        self.tabs.setTabText(1, f"发现 · {len(result.findings)}")
        self.tabs.setTabText(2, "AI 分析" if not result.ai_used else "AI 分析 · 已完成")
        self.tabs.setTabText(3, f"材料 · {len(result.files)}")
        self.result_stack.setCurrentIndex(1)
        self.export_btn.setEnabled(not self._busy)
        self.open_report_btn.setEnabled(bool(result.report_paths))
        self.flags_scroll.verticalScrollBar().setValue(0)
        self.findings_scroll.verticalScrollBar().setValue(0)
        self.tabs.setCurrentIndex(0)

    def _render_flags(self, result: AnalysisResult) -> None:
        self._clear_layout(self.flags_layout)
        if not result.flags:
            self.flags_layout.addWidget(
                EmptyState(
                    "尚未发现 Flag",
                    "规则、解码与模型均未产生可靠候选。可查看静态发现，或补充题目文本后重试。",
                    "Ø",
                ),
                1,
            )
            return
        intro = QLabel(
            f"{len(result.confirmed_flags)} 个已发现 · "
            f"{len(result.candidates)} 个候选。候选必须人工验证后才能视为答案。"
        )
        intro.setObjectName("PanelSub")
        intro.setWordWrap(True)
        self.flags_layout.addWidget(intro)
        for candidate in result.flags:
            self.flags_layout.addWidget(FlagCard(candidate))
        self.flags_layout.addStretch(1)

    def _render_findings(self, result: AnalysisResult) -> None:
        self._clear_layout(self.findings_layout)
        if not result.findings:
            self.findings_layout.addWidget(
                EmptyState(
                    "没有静态发现",
                    "当前材料未命中审计规则。该结果不代表材料绝对安全。",
                    "—",
                ),
                1,
            )
            return
        display_limit = 100
        intro = QLabel(
            f"共 {len(result.findings)} 条，按严重程度排序"
            + (
                f"，当前展示前 {display_limit} 条。"
                if len(result.findings) > display_limit
                else "。"
            )
        )
        intro.setObjectName("PanelSub")
        self.findings_layout.addWidget(intro)
        for finding in result.findings[:display_limit]:
            self.findings_layout.addWidget(FindingCard(finding))
        self.findings_layout.addStretch(1)

    def _render_ai(self, result: AnalysisResult) -> None:
        if result.ai_used and result.ai_text:
            self.ai_view.setMarkdown(result.ai_text)
        elif result.ai_error:
            self.ai_view.setMarkdown(
                f"**AI 分析未完成**\n\n{result.ai_error}\n\n"
                "静态分析结果与 Flag 候选仍然有效。"
            )
        else:
            self.ai_view.setMarkdown(
                "**AI 分析未启用**\n\n"
                "本次任务只使用了本地静态工具与规则引擎。"
            )

    def _render_materials(self, result: AnalysisResult) -> None:
        self.materials_list.clear()
        for artifact in result.files:
            category = artifact.category.upper()
            text = (
                f"{artifact.path}\n"
                f"{kind_label(artifact.kind)}  ·  {category}  ·  {format_size(artifact.size)}  ·  "
                f"sha256 {artifact.sha256[:16]}…"
            )
            item = QListWidgetItem(text)
            item.setToolTip(f"完整 SHA256：{artifact.sha256}")
            self.materials_list.addItem(item)

    def export_report(self) -> None:
        if not self.current_result:
            self.notify.emit("当前没有可导出的分析结果。", "warning")
            return
        try:
            paths = ReportWriter(self.context.config, self.context.paths).write(
                self.current_result
            )
        except Exception as exc:
            logger.exception("Report export failed")
            self.notify.emit(f"导出报告失败：{exc}", "error")
            return
        self.open_report_btn.setEnabled(True)
        self.notify.emit(f"报告已导出：{paths['markdown']}", "success")
        if self.context.config.get("ui.open_report_folder", False):
            self.open_report_folder()

    def open_report_folder(self) -> None:
        if not self.current_result:
            return
        candidates = [
            self.current_result.report_paths.get("markdown"),
        ]
        directory = None
        for value in candidates:
            if value and Path(value).exists():
                directory = Path(value).parent
                break
        if not directory:
            workspace = Path(self.current_result.workspace)
            directory = workspace / "report"
        if directory.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))
        else:
            self.notify.emit("报告目录尚未生成，请先点击“导出报告”。", "warning")

    @staticmethod
    def _clear_layout(layout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
