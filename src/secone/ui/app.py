from __future__ import annotations

import logging
import sys
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from .. import __version__
from ..config import load_config
from ..db import TaskStore
from ..llm import LLMClient, LlamaServerManager
from ..paths import setup_logging
from .context import AppContext
from .main_window import MainWindow
from .theme import apply_theme

logger = logging.getLogger(__name__)


def _install_exception_hook() -> None:
    def handle(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical(
            "Unhandled exception:\n%s",
            "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)),
        )
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle


def _set_windows_app_id() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "SecOne.LocalSecurityWorkstation.0.1"
        )
    except Exception:
        pass


def main() -> int:
    _set_windows_app_id()
    app = QApplication(sys.argv)
    app.setApplicationName("SecOne")
    app.setApplicationDisplayName("SecOne · 本地 AI 安全分析工作台")
    app.setOrganizationName("SecOne")
    app.setOrganizationDomain("secone.local")
    apply_theme(app)

    try:
        config = load_config()
        setup_logging(config.paths)
        icon_path = config.paths.root / "assets" / "secone.svg"
        if icon_path.exists():
            app.setWindowIcon(QIcon(str(icon_path)))
        store = TaskStore(config.paths.db_file)
        manager = LlamaServerManager(config)
        client = LLMClient(config, manager)
        context = AppContext(
            config=config,
            paths=config.paths,
            store=store,
            manager=manager,
            client=client,
        )
    except Exception as exc:
        logger.exception("Application initialization failed")
        QMessageBox.critical(None, "SecOne 启动失败", f"无法初始化应用：\n{exc}")
        return 1

    _install_exception_hook()
    manager = context.manager
    app.aboutToQuit.connect(manager.stop)
    window = MainWindow(context)
    window.show()
    QTimer.singleShot(500, window.bootstrap)
    logger.info(
        "SecOne %s started; root=%s",
        config.get("app.version", __version__),
        config.paths.root,
    )
    return app.exec()
