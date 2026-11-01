from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ...core.report import MODE_LABELS, ReportWriter
from ...domain import AnalysisResult, TaskRecord, TaskStatus
from ..context import AppContext
from ..widgets import EmptyState, MetricCard

logger = logging.getLogger(__name__)

STATUS_LABELS = {
    TaskStatus.COMPLETED: "已完成",
    TaskStatus.FAILED: "失败",
    TaskStatus.RUNNING: "运行中",
    TaskStatus.QUEUED: "排队中",
    TaskStatus.CANCELLED: "已取消",
}
STATUS_COLORS = {
    TaskStatus.COMPLETED: "#3CE0B2",
    TaskStatus.FAILED: "#FF6F7D",
    TaskStatus.RUNNING: "#7DBAF7",
    TaskStatus.QUEUED: "#F4BC5C",
    TaskStatus.CANCELLED: "#8597A8",
}


class HistoryPage(QWidget):
    notify = Signal(str, str)
    openResult = Signal(object)

    def __init__(self, context: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.context = context
        self.records: list[TaskRecord] = []
        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(16)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        kicker = QLabel("CASE ARCHIVE / LOCAL ONLY")
        kicker.setObjectName("Kicker")
        titles.addWidget(kicker)
        title = QLabel("任务历史")
        title.setObjectName("PageTitle")
        titles.addWidget(title)
        subtitle = QLabel("所有任务记录、证据目录与报告都保存在本机工作区。")
        subtitle.setObjectName("PageSub")
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.refresh_btn = QPushButton("刷新记录")
        self.refresh_btn.setObjectName("GhostButton")
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn, 0, Qt.AlignBottom)
        layout.addLayout(header)

        stats = QHBoxLayout()
        stats.setSpacing(8)
        self.total_metric = MetricCard("任务总数", "0")
        self.completed_metric = MetricCard("已完成", "0")
        self.flags_metric = MetricCard("Flag 结果", "0")
        stats.addWidget(self.total_metric)
        stats.addWidget(self.completed_metric)
        stats.addWidget(self.flags_metric)
        stats.addStretch(1)
        layout.addLayout(stats)

        panel = QFrame()
        panel.setObjectName("Panel")
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(14, 14, 14, 12)
        panel_layout.setSpacing(10)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(7)
        toolbar.addStretch(1)
        self.open_btn = QPushButton("查看结果")
        self.open_btn.setObjectName("ModeButton")
        self.open_btn.clicked.connect(self.open_selected)
        self.folder_btn = QPushButton("打开任务目录")
        self.folder_btn.setObjectName("GhostButton")
        self.folder_btn.clicked.connect(self.open_folder)
        self.export_btn = QPushButton("导出报告")
        self.export_btn.setObjectName("GhostButton")
        self.export_btn.clicked.connect(self.export_selected)
        toolbar.addWidget(self.export_btn)
        toolbar.addWidget(self.folder_btn)
        toolbar.addWidget(self.open_btn)
        panel_layout.addLayout(toolbar)

        self.stack = QStackedWidget()
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["任务名称", "模式", "时间", "文件", "Flag", "状态"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setFocusPolicy(Qt.StrongFocus)
        self.table.doubleClicked.connect(self.open_selected)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(45)
        self.stack.addWidget(self.table)
        self.stack.addWidget(
            EmptyState(
                "还没有分析任务",
                "在“分析工作台”中拖入材料并运行一次分析，记录会出现在这里。",
                "◇",
            )
        )
        panel_layout.addWidget(self.stack, 1)
        layout.addWidget(panel, 1)
        self._update_buttons()

    def refresh(self) -> None:
        try:
            self.records = self.context.store.list(200)
            counts = self.context.store.counts()
        except Exception as exc:
            logger.exception("History refresh failed")
            self.notify.emit(f"读取任务历史失败：{exc}", "error")
            return
        self.total_metric.set_value(counts["total"])
        self.completed_metric.set_value(counts["completed"])
        self.flags_metric.set_value(counts["flags"])
        self.table.setRowCount(len(self.records))
        for row, record in enumerate(self.records):
            title_item = QTableWidgetItem(record.title)
            title_item.setData(Qt.UserRole, record.id)
            title_item.setToolTip(record.summary or record.title)
            self.table.setItem(row, 0, title_item)
            self.table.setItem(
                row, 1, QTableWidgetItem(MODE_LABELS.get(record.mode, record.mode))
            )
            self.table.setItem(row, 2, QTableWidgetItem(self._format_time(record.created_at)))
            files_item = QTableWidgetItem(str(record.input_count))
            files_item.setTextAlignment(Qt.AlignCenter)
            self.table.setItem(row, 3, files_item)
            flag_item = QTableWidgetItem(str(record.flag_count))
            flag_item.setTextAlignment(Qt.AlignCenter)
            if record.flag_count:
                flag_item.setForeground(QColor("#3CE0B2"))
            self.table.setItem(row, 4, flag_item)
            status_item = QTableWidgetItem(STATUS_LABELS.get(record.status, record.status))
            status_item.setForeground(
                QColor(STATUS_COLORS.get(record.status, "#8597A8"))
            )
            if record.error:
                status_item.setToolTip(record.error)
            self.table.setItem(row, 5, status_item)
        self.stack.setCurrentIndex(0 if self.records else 1)
        self._update_buttons()

    def open_selected(self) -> None:
        record = self._selected_record()
        if not record:
            self.notify.emit("请先选择一个任务。", "warning")
            return
        result = self.context.store.get_result(record.id)
        if not result:
            self.notify.emit("该任务没有可查看的结果，可能已失败或结果文件缺失。", "warning")
            return
        self.openResult.emit(result)

    def open_folder(self) -> None:
        record = self._selected_record()
        if not record:
            self.notify.emit("请先选择一个任务。", "warning")
            return
        path = Path(record.workspace)
        if path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        else:
            self.notify.emit(f"任务目录不存在：{path}", "warning")

    def export_selected(self) -> None:
        record = self._selected_record()
        if not record:
            self.notify.emit("请先选择一个任务。", "warning")
            return
        result = self.context.store.get_result(record.id)
        if not result:
            self.notify.emit("该任务没有可导出的完整结果。", "warning")
            return
        try:
            paths = ReportWriter(self.context.config, self.context.paths).write(result)
        except Exception as exc:
            logger.exception("History report export failed")
            self.notify.emit(f"导出报告失败：{exc}", "error")
            return
        self.notify.emit(f"报告已导出：{paths['markdown']}", "success")
        self.refresh()

    def _selected_record(self) -> TaskRecord | None:
        rows = self.table.selectionModel().selectedRows() if self.table.selectionModel() else []
        if not rows:
            return None
        row = rows[0].row()
        return self.records[row] if 0 <= row < len(self.records) else None

    def _update_buttons(self) -> None:
        enabled = self._selected_record() is not None
        self.open_btn.setEnabled(enabled)
        self.folder_btn.setEnabled(enabled)
        self.export_btn.setEnabled(enabled)

    @staticmethod
    def _format_time(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
            return parsed.strftime("%Y-%m-%d %H:%M")
        except (TypeError, ValueError):
            return (value or "")[:16].replace("T", " ")
