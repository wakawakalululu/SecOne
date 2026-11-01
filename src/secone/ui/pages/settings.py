from __future__ import annotations

import logging
from pathlib import Path

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from ...core.fileio import format_size
from ..context import AppContext
from ..widgets import StatusChip
from ..worker import ModelWorker

logger = logging.getLogger(__name__)


class SettingsPage(QWidget):
    notify = Signal(str, str)
    modelChanged = Signal()

    def __init__(self, context: AppContext, parent: QWidget | None = None):
        super().__init__(parent)
        self.context = context
        self.worker = None
        self._busy = False
        self._build_ui()
        self._load_values()
        self.refresh_status()

    @property
    def is_busy(self) -> bool:
        return self._busy

    @property
    def worker_running(self) -> bool:
        return bool(self.worker and self.worker.isRunning())

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 10, 20)
        layout.setSpacing(16)

        header = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(4)
        kicker = QLabel("ENGINE / POLICY / DIAGNOSTICS")
        kicker.setObjectName("Kicker")
        titles.addWidget(kicker)
        title = QLabel("模型与设置")
        title.setObjectName("PageTitle")
        titles.addWidget(title)
        subtitle = QLabel("替换模型无需重新编译程序。所有路径与参数保存在本机配置文件。")
        subtitle.setObjectName("PageSub")
        titles.addWidget(subtitle)
        header.addLayout(titles, 1)
        self.save_btn = QPushButton("保存设置")
        self.save_btn.setObjectName("PrimaryButton")
        self.save_btn.clicked.connect(self.save_settings)
        header.addWidget(self.save_btn, 0, Qt.AlignBottom)
        layout.addLayout(header)

        layout.addWidget(self._build_engine_panel())
        panels = QHBoxLayout()
        panels.setSpacing(14)
        panels.addWidget(self._build_model_panel(), 3)
        panels.addWidget(self._build_analysis_panel(), 2)
        layout.addLayout(panels)
        layout.addWidget(self._build_diagnostics_panel())
        layout.addStretch(1)
        scroll.setWidget(content)
        root.addWidget(scroll)

    def _build_engine_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        top = QHBoxLayout()
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        title = QLabel("本地推理引擎")
        title.setObjectName("PanelTitle")
        info_layout.addWidget(title)
        self.engine_detail = QLabel("正在读取模型状态 …")
        self.engine_detail.setObjectName("PanelSub")
        self.engine_detail.setWordWrap(True)
        info_layout.addWidget(self.engine_detail)
        top.addLayout(info_layout, 1)
        self.model_chip = StatusChip("模型检查中", "neutral")
        self.runtime_chip = StatusChip("引擎检查中", "neutral")
        self.health_chip = StatusChip("服务检查中", "neutral")
        top.addWidget(self.model_chip)
        top.addWidget(self.runtime_chip)
        top.addWidget(self.health_chip)
        layout.addLayout(top)

        actions = QHBoxLayout()
        actions.setSpacing(7)
        self.start_btn = QPushButton("启动本地引擎")
        self.start_btn.setObjectName("ModeButton")
        self.start_btn.clicked.connect(lambda: self.run_model_action("start"))
        self.stop_btn = QPushButton("停止服务")
        self.stop_btn.setObjectName("GhostButton")
        self.stop_btn.clicked.connect(lambda: self.run_model_action("stop"))
        self.test_btn = QPushButton("测试模型连接")
        self.test_btn.setObjectName("GhostButton")
        self.test_btn.clicked.connect(lambda: self.run_model_action("test"))
        self.open_models_btn = QPushButton("打开模型目录")
        self.open_models_btn.setObjectName("LinkButton")
        self.open_models_btn.clicked.connect(
            lambda: self._open_directory(self.context.paths.models)
        )
        self.open_runtime_btn = QPushButton("打开运行目录")
        self.open_runtime_btn.setObjectName("LinkButton")
        self.open_runtime_btn.clicked.connect(
            lambda: self._open_directory(self.context.paths.runtime)
        )
        actions.addWidget(self.start_btn)
        actions.addWidget(self.stop_btn)
        actions.addWidget(self.test_btn)
        actions.addStretch(1)
        actions.addWidget(self.open_models_btn)
        actions.addWidget(self.open_runtime_btn)
        layout.addLayout(actions)

        self.engine_progress = QLabel(
            "模型服务通过 127.0.0.1 的 OpenAI 兼容接口通信，不访问公网。"
        )
        self.engine_progress.setObjectName("Dim")
        self.engine_progress.setWordWrap(True)
        layout.addWidget(self.engine_progress)
        return panel

    def _build_model_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = QLabel("模型资源")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)
        subtitle = QLabel("替换 GGUF 或推理引擎后无需修改业务代码。")
        subtitle.setObjectName("PanelSub")
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setSpacing(9)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        self.display_name = QLineEdit()
        form.addRow("显示名称", self.display_name)
        self.model_path = QLineEdit()
        self.model_path.setObjectName("Mono")
        form.addRow(
            "GGUF 模型",
            self._path_field(self.model_path, "选择 GGUF 模型", "GGUF 模型 (*.gguf);;所有文件 (*.*)", False),
        )
        self.runtime_path = QLineEdit()
        self.runtime_path.setObjectName("Mono")
        form.addRow(
            "llama-server",
            self._path_field(self.runtime_path, "选择推理引擎", "可执行文件 (*.exe);;所有文件 (*.*)", False),
        )

        self.discover_row = QHBoxLayout()
        self.discover_combo = QComboBox()
        self.discover_combo.setObjectName("Mono")
        self.discover_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.discover_combo.setVisible(False)
        self.discover_btn = QPushButton("扫描 models/ 中的 GGUF")
        self.discover_btn.setObjectName("GhostButton")
        self.discover_btn.clicked.connect(self._on_discover_models)
        self.discover_combo.currentIndexChanged.connect(self._apply_discovered_model)
        self.discover_row.addWidget(self.discover_combo, 1)
        self.discover_row.addWidget(self.discover_btn)
        self.discover_row.addStretch(1)
        form.addRow("可用模型", self._wrap_row(self.discover_row))

        spin_row = QHBoxLayout()
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.context_spin = QSpinBox()
        self.context_spin.setRange(2048, 131072)
        self.context_spin.setSingleStep(1024)
        self.gpu_spin = QSpinBox()
        self.gpu_spin.setRange(0, 200)
        self.thread_spin = QSpinBox()
        self.thread_spin.setRange(0, 256)
        for label, widget in (
            ("端口", self.port_spin),
            ("上下文", self.context_spin),
            ("GPU 层", self.gpu_spin),
            ("线程", self.thread_spin),
        ):
            field = QVBoxLayout()
            field.setSpacing(3)
            field_label = QLabel(label)
            field_label.setObjectName("PanelSub")
            field.addWidget(field_label)
            field.addWidget(widget)
            spin_row.addLayout(field)
        layout.addLayout(form)
        layout.addLayout(spin_row)

        self.managed_check = QCheckBox("由 SecOne 管理 llama-server 进程")
        self.auto_start_check = QCheckBox("启动 SecOne 时自动加载模型")
        layout.addWidget(self.managed_check)
        layout.addWidget(self.auto_start_check)
        note = QLabel("模型加载失败不会导致主程序退出，诊断区会显示具体原因。")
        note.setObjectName("Dim")
        note.setWordWrap(True)
        layout.addWidget(note)
        return panel

    def _build_analysis_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(10)
        title = QLabel("分析与安全策略")
        title.setObjectName("PanelTitle")
        layout.addWidget(title)
        subtitle = QLabel("限制文件规模、模型上下文与解码深度。")
        subtitle.setObjectName("PanelSub")
        layout.addWidget(subtitle)

        form = QFormLayout()
        form.setSpacing(9)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        self.ai_enabled = QCheckBox("启用本地 AI 深度分析")
        form.addRow("", self.ai_enabled)
        self.max_file_spin = QSpinBox()
        self.max_file_spin.setRange(1, 2048)
        self.max_file_spin.setSuffix(" MB")
        form.addRow("单文件上限", self.max_file_spin)
        self.ai_context_spin = QSpinBox()
        self.ai_context_spin.setRange(1000, 100000)
        self.ai_context_spin.setSingleStep(1000)
        form.addRow("AI 材料字符", self.ai_context_spin)
        self.decode_depth_spin = QSpinBox()
        self.decode_depth_spin.setRange(0, 6)
        form.addRow("解码递归深度", self.decode_depth_spin)
        self.prefix_edit = QLineEdit()
        self.prefix_edit.setPlaceholderText("例如：flag,ctf,myctf")
        form.addRow("自定义 Flag 前缀", self.prefix_edit)
        layout.addLayout(form)

        note = QLabel(
            "程序不会扫描公网、不会执行未知二进制，也不会把模型输出当作可信命令。"
        )
        note.setObjectName("Muted")
        note.setWordWrap(True)
        layout.addWidget(note)
        layout.addStretch(1)
        return panel

    def _build_diagnostics_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Panel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(9)
        header = QHBoxLayout()
        title = QLabel("运行诊断")
        title.setObjectName("PanelTitle")
        header.addWidget(title)
        header.addStretch(1)
        refresh_log_btn = QPushButton("刷新日志")
        refresh_log_btn.setObjectName("LinkButton")
        refresh_log_btn.clicked.connect(self.refresh_log)
        header.addWidget(refresh_log_btn)
        layout.addLayout(header)

        self.diag_grid = QLabel()
        self.diag_grid.setObjectName("Muted")
        self.diag_grid.setWordWrap(True)
        self.diag_grid.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(self.diag_grid)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMinimumHeight(150)
        self.log_view.setMaximumHeight(240)
        self.log_view.setPlaceholderText("运行日志会显示在这里。")
        layout.addWidget(self.log_view)
        return panel

    @staticmethod
    def _path_field(
        line_edit: QLineEdit,
        title: str,
        filter_text: str,
        directory: bool,
    ) -> QWidget:
        container = QWidget()
        layout = QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(line_edit, 1)
        button = QPushButton("浏览")
        button.setObjectName("GhostButton")

        def browse() -> None:
            if directory:
                path = QFileDialog.getExistingDirectory(container, title, line_edit.text())
            else:
                path, _ = QFileDialog.getOpenFileName(
                    container, title, line_edit.text(), filter_text
                )
            if path:
                line_edit.setText(path)

        button.clicked.connect(browse)
        layout.addWidget(button)
        return container

    @staticmethod
    def _wrap_row(inner: QHBoxLayout) -> QWidget:
        container = QWidget()
        container.setLayout(inner)
        inner.setContentsMargins(0, 0, 0, 0)
        return container

    def _on_discover_models(self) -> None:
        """Populate the model picker from GGUF files present in models/."""
        found = self.context.manager.discover_models()
        if not found:
            self.discover_combo.setVisible(False)
            self.notify.emit(
                "models/ 中没有可用的 GGUF。请先把模型文件放入 models/ 目录。", "error"
            )
            return
        current = self.model_path.text().strip()
        self.discover_combo.blockSignals(True)
        self.discover_combo.clear()
        for path in found:
            try:
                size = format_size(path.stat().st_size)
            except OSError:
                size = "?"
            self.discover_combo.addItem(f"{path.name} · {size}", str(path))
            if Path(current) == path:
                self.discover_combo.setCurrentIndex(self.discover_combo.count() - 1)
        self.discover_combo.blockSignals(False)
        self.discover_combo.setVisible(True)
        self.notify.emit(f"发现 {len(found)} 个 GGUF 模型。选择后点击“保存并生效”。", "success")

    def _apply_discovered_model(self) -> None:
        data = self.discover_combo.currentData()
        if data:
            self.model_path.setText(str(data))

    def _load_values(self) -> None:
        config = self.context.config
        self.display_name.setText(str(config.get("engine.display_name", "")))
        self.model_path.setText(str(config.model_path))
        self.runtime_path.setText(str(config.runtime_path))
        self.port_spin.setValue(int(config.get("engine.port", 18080)))
        self.context_spin.setValue(int(config.get("engine.context_size", 8192)))
        self.gpu_spin.setValue(int(config.get("engine.gpu_layers", 0)))
        self.thread_spin.setValue(int(config.get("engine.threads", 0)))
        self.managed_check.setChecked(bool(config.get("engine.managed", True)))
        self.auto_start_check.setChecked(bool(config.get("engine.auto_start", True)))
        self.ai_enabled.setChecked(bool(config.get("analysis.ai_enabled", True)))
        self.max_file_spin.setValue(int(config.get("analysis.max_file_mb", 64)))
        self.ai_context_spin.setValue(int(config.get("analysis.ai_context_chars", 16000)))
        self.decode_depth_spin.setValue(int(config.get("analysis.decode_depth", 3)))
        prefixes = config.get("flags.custom_prefixes", []) or []
        self.prefix_edit.setText(",".join(str(item) for item in prefixes))

    def save_settings(self) -> None:
        if self._busy:
            self.notify.emit("模型任务正在运行，请等待完成后再保存。", "warning")
            return
        config = self.context.config
        old_endpoint = (str(config.model_path), config.api_base_url)
        display_name = self.display_name.text().strip() or "SecOne 本地引擎"
        model_path = self.model_path.text().strip()
        runtime_path = self.runtime_path.text().strip()
        if not model_path or not runtime_path:
            self.notify.emit("模型路径与推理引擎路径不能为空。", "warning")
            return
        prefixes = [
            token.strip()
            for token in self.prefix_edit.text().replace(";", ",").split(",")
            if token.strip()
        ]
        config.set("engine.display_name", display_name)
        config.set("engine.gguf", self._stored_path(Path(model_path)))
        config.set("engine.runtime", self._stored_path(Path(runtime_path)))
        config.set("engine.port", self.port_spin.value())
        config.set("engine.context_size", self.context_spin.value())
        config.set("engine.gpu_layers", self.gpu_spin.value())
        config.set("engine.threads", self.thread_spin.value())
        config.set("engine.managed", self.managed_check.isChecked())
        config.set("engine.auto_start", self.auto_start_check.isChecked())
        config.set("analysis.ai_enabled", self.ai_enabled.isChecked())
        config.set("analysis.max_file_mb", self.max_file_spin.value())
        config.set("analysis.ai_context_chars", self.ai_context_spin.value())
        config.set("analysis.decode_depth", self.decode_depth_spin.value())
        config.set("flags.custom_prefixes", prefixes)
        try:
            config.save()
        except Exception as exc:
            logger.exception("Saving settings failed")
            self.notify.emit(f"保存配置失败：{exc}", "error")
            return
        new_endpoint = (str(config.model_path), config.api_base_url)
        if old_endpoint != new_endpoint and self.context.manager.health():
            self.context.manager.stop()
            self.notify.emit("设置已保存。模型端点已变化，本地服务已停止，请重新启动。", "warning")
        else:
            self.notify.emit("设置已保存。新任务将使用当前配置。", "success")
        self.refresh_status()
        self.modelChanged.emit()

    def run_model_action(self, action: str) -> None:
        if self._busy:
            self.notify.emit("已有模型操作正在执行。", "warning")
            return
        self._busy = True
        self._set_actions_enabled(False)
        labels = {
            "start": "正在启动本地推理服务 …",
            "stop": "正在停止本地推理服务 …",
            "test": "正在测试模型连接 …",
            "restart": "正在重启本地推理服务 …",
        }
        self.engine_progress.setText(labels.get(action, "正在执行模型操作 …"))
        self.worker = ModelWorker(self.context, action, parent=self)
        self.worker.progress.connect(self._on_model_progress)
        self.worker.completed.connect(self._on_model_completed)
        self.worker.failed.connect(self._on_model_failed)
        self.worker.finished.connect(self._on_model_finished)
        self.worker.start()

    def _on_model_progress(self, message: str) -> None:
        self.engine_progress.setText(message)
        self.refresh_log()

    def _on_model_completed(self, message: str) -> None:
        self._busy = False
        self.engine_progress.setText(message)
        self.notify.emit(message, "success")
        self.refresh_status()
        self.refresh_log()
        self.modelChanged.emit()

    def _on_model_failed(self, message: str) -> None:
        self._busy = False
        self.engine_progress.setText("模型操作失败。请检查路径、端口和诊断日志。")
        self.notify.emit(message[:900], "error")
        self.refresh_status()
        self.refresh_log()
        self.modelChanged.emit()

    def _on_model_finished(self) -> None:
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def refresh_status(self) -> None:
        try:
            info = self.context.manager.model_info()
        except Exception as exc:
            self.model_chip.set_tone("状态异常", "danger")
            self.engine_detail.setText(f"读取模型状态失败：{exc}")
            return
        if not info.model_exists:
            self.model_chip.set_tone("模型未安装", "danger")
        elif not info.gguf_valid:
            self.model_chip.set_tone("模型无效", "danger")
        elif info.metadata_ok and not info.chat_template_present:
            self.model_chip.set_tone("缺少对话模板", "danger")
        elif info.health_ok:
            self.model_chip.set_tone("模型已就绪", "success")
        else:
            self.model_chip.set_tone("模型已就绪（未验证）", "neutral")
        self.runtime_chip.set_tone(
            "引擎已安装" if info.runtime_exists else "引擎缺失",
            "success" if info.runtime_exists else "danger",
        )
        self.health_chip.set_tone(
            "推理服务在线" if info.health_ok else "推理服务未启动",
            "success" if info.health_ok else "neutral",
        )
        size = format_size(info.size_bytes) if info.size_bytes else "—"
        architecture = info.architecture or "未知架构"
        context_size = info.context_length or self.context.config.get(
            "engine.context_size", 8192
        )
        self.engine_detail.setText(
            f"{info.display_name} · {info.quantization} · {size} · "
            f"{architecture} · 上下文 {context_size}"
        )
        model_state = (
            f"GGUF v{info.gguf_version} 有效" if info.gguf_valid else "未通过 GGUF 校验"
        )
        template_state = (
            "已配置"
            if info.chat_template_present
            else ("缺失（请检查模型包）" if info.metadata_ok else "未解析")
        )
        metadata_state = (
            "元数据已解析" if info.metadata_ok else (info.metadata_error or "未解析")
        )
        self.diag_grid.setText(
            f"模型文件：{info.model_path}\n"
            f"运行组件：{info.runtime_path}\n"
            f"模型状态：{model_state} · {size} · {architecture} · "
            f"{info.block_count or '—'} 层\n"
            f"对话模板：{template_state}\n"
            f"元数据：{metadata_state}\n"
            f"服务地址：{self.context.manager.base_url}\n"
            f"服务健康：{'在线' if info.health_ok else '不可达'}\n"
            f"推理验证：{'已完成实机连通' if info.runtime_verified else '尚未完成实机推理验证'}"
        )
        self._set_actions_enabled(not self._busy)
        self.start_btn.setEnabled(
            not self._busy
            and info.model_exists
            and info.gguf_valid
            and info.runtime_exists
            and not info.health_ok
        )
        self.stop_btn.setEnabled(not self._busy and info.health_ok)
        self.test_btn.setEnabled(
            not self._busy and info.model_exists and info.gguf_valid
        )

    def _set_actions_enabled(self, enabled: bool) -> None:
        self.save_btn.setEnabled(enabled)
        for button in (self.start_btn, self.stop_btn, self.test_btn):
            button.setEnabled(enabled)

    def refresh_log(self) -> None:
        sections: list[str] = []
        server_log = self.context.manager.log_tail(90)
        if server_log:
            sections.append("===== llama-server.log =====\n" + server_log)
        app_log = self._read_app_log(70)
        if app_log:
            sections.append("===== secone.log =====\n" + app_log)
        self.log_view.setPlainText("\n\n".join(sections) or "暂无日志。")
        self.log_view.verticalScrollBar().setValue(
            self.log_view.verticalScrollBar().maximum()
        )

    def _read_app_log(self, lines: int) -> str:
        path = self.context.paths.logs / "secone.log"
        if not path.exists():
            return ""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""
        return "\n".join(content.splitlines()[-lines:])

    def _stored_path(self, path: Path) -> str:
        path = path.expanduser()
        try:
            resolved = path.resolve()
            return resolved.relative_to(self.context.paths.root).as_posix()
        except (OSError, ValueError):
            return str(path)

    @staticmethod
    def _open_directory(path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self.refresh_status()
        self.refresh_log()
