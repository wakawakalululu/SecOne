from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
)
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..domain import FlagCandidate, FlagStatus, Finding, Severity
from .theme import COLORS

FLAG_LABELS = {
    FlagStatus.VERIFIED: "已验证",
    FlagStatus.FOUND: "已发现",
    FlagStatus.CANDIDATE: "候选",
    FlagStatus.NONE: "未发现",
}
SEVERITY_LABELS = {
    Severity.CRITICAL: "严重",
    Severity.HIGH: "高危",
    Severity.MEDIUM: "中危",
    Severity.LOW: "低危",
    Severity.INFO: "信息",
}
SEVERITY_TONES = {
    Severity.CRITICAL: "danger",
    Severity.HIGH: "danger",
    Severity.MEDIUM: "warning",
    Severity.LOW: "info",
    Severity.INFO: "neutral",
}


class LogoMark(QWidget):
    def __init__(self, parent: QWidget | None = None, size: int = 40):
        super().__init__(parent)
        self.setFixedSize(size, size)

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        width, height = self.width(), self.height()
        path = QPainterPath()
        path.moveTo(width / 2, 2)
        path.lineTo(width - 4, 8)
        path.lineTo(width - 5, height - 12)
        path.lineTo(width / 2, height - 2)
        path.lineTo(5, height - 12)
        path.lineTo(4, 8)
        path.closeSubpath()
        gradient = QLinearGradient(0, 0, width, height)
        gradient.setColorAt(0.0, QColor("#2FD5A7"))
        gradient.setColorAt(1.0, QColor("#0F6B59"))
        painter.fillPath(path, gradient)
        painter.setPen(QPen(QColor("#08130F"), 1.2))
        painter.drawPath(path)
        font = QFont("Consolas", max(8, int(self.width() * 0.28)))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor("#07110E"))
        painter.drawText(self.rect(), Qt.AlignCenter, "S1")


class StatusChip(QLabel):
    def __init__(self, text: str = "", tone: str = "neutral", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("StatusChip")
        self.setAlignment(Qt.AlignCenter)
        self.set_tone(text, tone)

    def set_tone(self, text: str, tone: str = "neutral") -> None:
        self.setText(f"●  {text}")
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)


class ElidedLabel(QLabel):
    def __init__(self, text: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._full_text = text
        self.setToolTip(text)
        self.setText(text)

    def set_full_text(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        self._apply_elision()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._apply_elision()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._apply_elision()

    def _apply_elision(self) -> None:
        metrics = self.fontMetrics()
        self.setText(
            metrics.elidedText(self._full_text, Qt.ElideMiddle, max(self.width(), 40))
        )


class NavButton(QPushButton):
    def __init__(self, index: str, text: str, parent: QWidget | None = None):
        super().__init__(f"{index}   {text}", parent)
        self.setObjectName("NavButton")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)


class DropZone(QFrame):
    filesDropped = Signal(list)
    browseRequested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(150)
        self.setProperty("active", False)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(5)
        layout.addStretch(1)

        icon = QLabel("+")
        icon.setObjectName("DropIcon")
        icon.setAlignment(Qt.AlignCenter)
        icon.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(icon)

        title = QLabel("拖入文件、文件夹或压缩包")
        title.setObjectName("DropTitle")
        title.setAlignment(Qt.AlignCenter)
        title.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(title)

        sub = QLabel("支持 ZIP / 7z / PDF / 图片 / 源码 / 日志 / 二进制 · 点击选择文件")
        sub.setObjectName("DropSub")
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(sub)
        layout.addStretch(1)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            paths = self._local_paths(event)
            if paths:
                event.acceptProposedAction()
                self._set_active(True)
                return
        event.ignore()

    def dragLeaveEvent(self, event) -> None:  # noqa: N802
        self._set_active(False)
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        paths = self._local_paths(event)
        self._set_active(False)
        if paths:
            event.acceptProposedAction()
            self.filesDropped.emit(paths)
        else:
            event.ignore()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self.rect().contains(event.position().toPoint()):
            self.browseRequested.emit()
        super().mouseReleaseEvent(event)

    def _set_active(self, active: bool) -> None:
        self.setProperty("active", active)
        self.style().unpolish(self)
        self.style().polish(self)

    @staticmethod
    def _local_paths(event) -> list[str]:
        result: list[str] = []
        for url in event.mimeData().urls():
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.exists():
                result.append(str(path))
        return result


class MetricCard(QFrame):
    def __init__(self, label: str, value: str = "0", parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("MetricCard")
        self.setMinimumHeight(64)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 9, 12, 9)
        layout.setSpacing(2)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        layout.addWidget(self.value_label)
        label_widget = QLabel(label)
        label_widget.setObjectName("MetricLabel")
        layout.addWidget(label_widget)

    def set_value(self, value: str | int) -> None:
        self.value_label.setText(str(value))


class FlagCard(QFrame):
    def __init__(self, candidate: FlagCandidate, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SubCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(7)

        header = QHBoxLayout()
        header.setSpacing(8)
        status = candidate.status
        tone = "success" if status == FlagStatus.FOUND else "info" if status == FlagStatus.VERIFIED else "warning"
        chip = StatusChip(FLAG_LABELS.get(status, status), tone)
        header.addWidget(chip)
        confidence = QLabel(f"置信度 {candidate.confidence:.0%}")
        confidence.setObjectName("FlagMeta")
        header.addWidget(confidence)
        source = QLabel(candidate.source or "未知来源")
        source.setObjectName("Dim")
        source.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        source.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        source.setToolTip(candidate.source)
        header.addWidget(source)
        layout.addLayout(header)

        value = QLabel(candidate.value)
        value.setObjectName("FlagValue")
        value.setWordWrap(True)
        value.setTextInteractionFlags(Qt.TextSelectableByMouse)
        layout.addWidget(value)

        method = QLabel(candidate.method or "规则匹配")
        method.setObjectName("FlagMeta")
        method.setWordWrap(True)
        layout.addWidget(method)

        if candidate.offset is not None:
            offset = QLabel(f"偏移 {candidate.offset}")
            offset.setObjectName("Dim")
            layout.addWidget(offset)
        if candidate.evidence:
            evidence = QLabel(candidate.evidence[:420])
            evidence.setObjectName("FlagEvidence")
            evidence.setWordWrap(True)
            evidence.setToolTip(candidate.evidence)
            layout.addWidget(evidence)
        if candidate.ai_generated:
            note = QLabel("AI 线索 · 已回查原文 · 尚未人工验证")
            note.setObjectName("Dim")
            layout.addWidget(note)


class FindingCard(QFrame):
    def __init__(self, finding: Finding, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("SubCard")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 11, 14, 11)
        layout.setSpacing(5)

        header = QHBoxLayout()
        header.setSpacing(8)
        tone = SEVERITY_TONES.get(finding.severity, "neutral")
        chip = StatusChip(SEVERITY_LABELS.get(finding.severity, finding.severity), tone)
        header.addWidget(chip)
        title = QLabel(finding.title)
        title.setObjectName("FindingTitle")
        title.setWordWrap(True)
        header.addWidget(title, 1)
        layout.addLayout(header)

        location_text = finding.path or "全局"
        if finding.line:
            location_text += f":{finding.line}"
        if finding.rule_id:
            location_text += f"  ·  {finding.rule_id}"
        location = QLabel(location_text)
        location.setObjectName("Dim")
        location.setWordWrap(True)
        layout.addWidget(location)

        if finding.description:
            description = QLabel(finding.description)
            description.setObjectName("Muted")
            description.setWordWrap(True)
            layout.addWidget(description)
        if finding.evidence:
            evidence = QLabel(finding.evidence[:340])
            evidence.setObjectName("FindingEvidence")
            evidence.setWordWrap(True)
            evidence.setToolTip(finding.evidence)
            layout.addWidget(evidence)


class EmptyState(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str = "",
        symbol: str = "∅",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 28, 18, 28)
        layout.setSpacing(5)
        layout.addStretch(1)
        icon = QLabel(symbol)
        icon.setObjectName("EmptySymbol")
        icon.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon)
        heading = QLabel(title)
        heading.setObjectName("EmptyTitle")
        heading.setAlignment(Qt.AlignCenter)
        heading.setWordWrap(True)
        layout.addWidget(heading)
        if subtitle:
            note = QLabel(subtitle)
            note.setObjectName("EmptySub")
            note.setAlignment(Qt.AlignCenter)
            note.setWordWrap(True)
            layout.addWidget(note)
        layout.addStretch(1)


class Toast(QLabel):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setMaximumWidth(560)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.hide()
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def display(self, message: str, tone: str = "info", milliseconds: int = 4500) -> None:
        self.setText(message)
        self.setProperty("tone", tone)
        self.style().unpolish(self)
        self.style().polish(self)
        self.adjustSize()
        self.resize(min(max(self.width(), 300), 560), self.height())
        self.show()
        self.raise_()
        self._timer.start(milliseconds)

    def reposition(self) -> None:
        if not self.parentWidget():
            return
        parent = self.parentWidget()
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - 30
        self.move(QPoint(x, y))
