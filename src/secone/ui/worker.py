from __future__ import annotations

import logging
import threading
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from ..core.pipeline import AnalysisPipeline, PipelineCancelled
from ..llm import LLMError
from .context import AppContext

logger = logging.getLogger(__name__)


class AnalysisWorker(QThread):
    progress = Signal(int, str)
    completed = Signal(object)
    cancelled = Signal(str)
    failed = Signal(str)

    def __init__(
        self,
        context: AppContext,
        sources: list[Path],
        text: str,
        mode: str,
        title_hint: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.context = context
        self.sources = sources
        self.text = text
        self.mode = mode
        self.title_hint = title_hint
        self._cancel_event = threading.Event()

    def cancel(self) -> None:
        self._cancel_event.set()

    def run(self) -> None:
        try:
            pipeline = AnalysisPipeline(
                config=self.context.config,
                store=self.context.store,
                llm=self.context.client,
                manager=self.context.manager,
                progress=lambda percent, message: self.progress.emit(percent, message),
                cancel_event=self._cancel_event,
            )
            result = pipeline.run(
                sources=self.sources,
                text=self.text,
                mode=self.mode,
                title_hint=self.title_hint,
            )
            self.completed.emit(result)
        except PipelineCancelled:
            logger.info("Analysis worker cancelled")
            self.cancelled.emit("分析已取消，材料输入已保留。")
        except Exception as exc:
            logger.exception("Analysis worker failed")
            self.failed.emit(str(exc) or exc.__class__.__name__)


class ModelWorker(QThread):
    progress = Signal(str)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, context: AppContext, action: str, parent=None):
        super().__init__(parent)
        self.context = context
        self.action = action

    def run(self) -> None:
        try:
            manager = self.context.manager
            if self.action == "start":
                self.progress.emit("正在加载 GGUF 模型并启动 llama.cpp …")
                info = manager.start()
                self.completed.emit(
                    f"本地推理服务已启动：{info.display_name} · {info.quantization}"
                )
            elif self.action == "restart":
                self.progress.emit("正在重启本地推理服务 …")
                info = manager.restart()
                self.completed.emit(f"本地推理服务已重启：{info.display_name}")
            elif self.action == "stop":
                manager.stop()
                self.completed.emit("本地推理服务已停止。")
            elif self.action == "test":
                if not manager.health():
                    self.progress.emit("服务未运行，正在加载模型 …")
                    manager.start()
                self.progress.emit("正在发送模型连通性测试 …")
                response = self.context.client.test()
                self.completed.emit(f"模型响应正常：{response.content[:160]}")
            else:
                raise LLMError(f"未知模型操作：{self.action}")
        except Exception as exc:
            logger.exception("Model worker failed")
            self.failed.emit(str(exc) or exc.__class__.__name__)
