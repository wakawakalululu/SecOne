from __future__ import annotations

from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

COLORS = {
    "bg": "#080D12",
    "sidebar": "#0B1219",
    "panel": "#0E1720",
    "panel_alt": "#111D28",
    "card": "#121F2B",
    "border": "#1D2C3A",
    "border_strong": "#2A3F52",
    "text": "#E6EDF3",
    "muted": "#8597A8",
    "dim": "#5A6B7B",
    "accent": "#3CE0B2",
    "accent_dim": "#1D8E73",
    "action": "#FF7A59",
    "action_hover": "#FF8E70",
    "danger": "#FF5D6C",
    "warning": "#F4BC5C",
    "info": "#60A5FA",
    "purple": "#A78BFA",
}

QSS = """
* {
    outline: none;
}
QWidget {
    color: #E6EDF3;
    font-size: 13px;
    selection-background-color: #1D8E73;
    selection-color: #F5FFFC;
}
QMainWindow, QWidget#Root {
    background-color: #080D12;
}
QWidget#ContentArea {
    background-color: #080D12;
}
QFrame#Sidebar {
    background-color: #0B1219;
    border-right: 1px solid #1D2C3A;
}
QFrame#TopBar {
    background-color: #080D12;
    border-bottom: 1px solid #16232E;
}
QLabel#Brand {
    color: #F2F8F6;
    font-family: "Consolas";
    font-size: 19px;
    font-weight: 700;
    letter-spacing: 2px;
}
QLabel#BrandSub {
    color: #5F7485;
    font-family: "Consolas";
    font-size: 9px;
    letter-spacing: 1px;
}
QLabel#Kicker {
    color: #5F7485;
    font-family: "Consolas";
    font-size: 10px;
    letter-spacing: 1px;
}
QLabel#TopPath {
    color: #728596;
    font-family: "Consolas";
    font-size: 11px;
}
QLabel#PageTitle {
    color: #F3F8F7;
    font-size: 28px;
    font-weight: 700;
}
QLabel#PageSub {
    color: #8092A3;
    font-size: 13px;
}
QLabel#HeroTitle {
    color: #F5FAF8;
    font-size: 32px;
    font-weight: 700;
}
QLabel#HeroSub {
    color: #8295A6;
    font-size: 13px;
}
QLabel#PanelTitle {
    color: #E9F1EF;
    font-size: 15px;
    font-weight: 600;
}
QLabel#PanelSub {
    color: #6D8091;
    font-size: 11px;
}
QLabel#Muted {
    color: #8295A6;
}
QLabel#Dim {
    color: #5A6B7B;
    font-size: 11px;
}
QLabel#MetricValue {
    color: #EFF7F4;
    font-family: "Consolas";
    font-size: 23px;
    font-weight: 700;
}
QLabel#MetricLabel {
    color: #6D8091;
    font-size: 10px;
}
QLabel#FlagValue {
    color: #3CE0B2;
    font-family: "Consolas";
    font-size: 15px;
    font-weight: 600;
}
QLabel#FlagMeta {
    color: #7E91A2;
    font-size: 11px;
}
QLabel#InlineError {
    color: #FF8A95;
    background-color: #2A1118;
    border: 1px solid #54212B;
    border-radius: 6px;
    padding: 8px 10px;
}
QLabel#Toast {
    background-color: #13212C;
    border: 1px solid #2A4052;
    border-radius: 9px;
    padding: 11px 16px;
    color: #E9F2F0;
    font-size: 12px;
}
QLabel#Toast[tone="success"] {
    background-color: #0E2A24;
    border-color: #1D6655;
    color: #8DF3D8;
}
QLabel#Toast[tone="error"] {
    background-color: #2A1016;
    border-color: #6B2835;
    color: #FF9CA6;
}
QLabel#Toast[tone="warning"] {
    background-color: #2B2210;
    border-color: #665124;
    color: #F7D28A;
}
QFrame#Panel {
    background-color: #0E1720;
    border: 1px solid #1D2C3A;
    border-radius: 12px;
}
QFrame#SubCard {
    background-color: #111D28;
    border: 1px solid #213242;
    border-radius: 9px;
}
QFrame#MetricCard {
    background-color: #0F1A24;
    border: 1px solid #1C2D3B;
    border-radius: 9px;
}
QFrame#DropZone {
    background-color: #0C151D;
    border: 1px dashed #2A4354;
    border-radius: 10px;
}
QFrame#DropZone[active="true"] {
    background-color: #0E2823;
    border: 1px dashed #3CE0B2;
}
QFrame#Divider {
    background-color: #1B2A37;
    max-height: 1px;
    min-height: 1px;
    border: none;
}
QPushButton {
    background-color: #13212C;
    border: 1px solid #263A4A;
    border-radius: 7px;
    color: #D7E3E8;
    font-size: 12px;
    padding: 9px 14px;
    min-height: 18px;
}
QPushButton:hover {
    background-color: #182A37;
    border-color: #345066;
    color: #F2FAF7;
}
QPushButton:pressed {
    background-color: #0E1A23;
}
QPushButton:disabled {
    background-color: #0D151C;
    border-color: #17232E;
    color: #485865;
}
QPushButton#PrimaryButton {
    background-color: #FF7A59;
    border: 1px solid #FF8E70;
    color: #1B0D09;
    font-size: 13px;
    font-weight: 700;
    padding: 11px 18px;
    border-radius: 8px;
}
QPushButton#PrimaryButton:hover {
    background-color: #FF8E70;
}
QPushButton#PrimaryButton:pressed {
    background-color: #E66A4A;
}
QPushButton#PrimaryButton:disabled {
    background-color: #2A201D;
    border-color: #3C2B25;
    color: #7B625A;
}
QPushButton#GhostButton {
    background-color: transparent;
    border: 1px solid #263A4A;
    color: #9FB2C0;
}
QPushButton#GhostButton:hover {
    border-color: #3B5A70;
    color: #E8F0ED;
}
QPushButton#LinkButton {
    background-color: transparent;
    border: none;
    color: #3CE0B2;
    padding: 3px 4px;
    text-align: left;
}
QPushButton#LinkButton:hover {
    color: #74F4CE;
}
QPushButton#NavButton {
    background-color: transparent;
    border: 1px solid transparent;
    border-left: 2px solid transparent;
    border-radius: 6px;
    color: #7F93A3;
    font-size: 12px;
    text-align: left;
    padding: 10px 12px;
    min-height: 20px;
}
QPushButton#NavButton:hover {
    background-color: #101C25;
    color: #D9E5E2;
}
QPushButton#NavButton:checked {
    background-color: #10251F;
    border-left: 2px solid #3CE0B2;
    color: #BDF7E7;
    font-weight: 600;
}
QPushButton#ModeButton {
    background-color: #101C25;
    border: 1px solid #223746;
    color: #BFD0DA;
    padding: 9px 13px;
}
QPushButton#ModeButton:hover {
    border-color: #3CE0B2;
    color: #E9FFF9;
}
QLabel#StatusChip {
    border-radius: 10px;
    padding: 4px 9px;
    font-size: 10px;
    font-family: "Consolas";
    background-color: #111D27;
    border: 1px solid #263B4B;
    color: #8FA4B3;
}
QLabel#StatusChip[tone="success"] {
    background-color: #0E2A24;
    border-color: #1C5E4E;
    color: #62EAC7;
}
QLabel#StatusChip[tone="warning"] {
    background-color: #2B2210;
    border-color: #5E4B22;
    color: #F3C86A;
}
QLabel#StatusChip[tone="danger"] {
    background-color: #2A1117;
    border-color: #5E2530;
    color: #FF8794;
}
QLabel#StatusChip[tone="info"] {
    background-color: #101F31;
    border-color: #24415C;
    color: #7DBAF7;
}
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox {
    background-color: #0A131A;
    border: 1px solid #223747;
    border-radius: 7px;
    color: #E4ECEF;
    padding: 8px 10px;
    selection-background-color: #1D8E73;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QSpinBox:focus {
    border: 1px solid #3A7D69;
    background-color: #0C161E;
}
QLineEdit:disabled, QPlainTextEdit:disabled {
    color: #576774;
}
QLineEdit#Mono {
    font-family: "Consolas";
    font-size: 12px;
}
QPlainTextEdit {
    font-family: "Microsoft YaHei UI";
    font-size: 12px;
}
QComboBox {
    background-color: #0A131A;
    border: 1px solid #223747;
    border-radius: 7px;
    padding: 7px 10px;
}
QComboBox QAbstractItemView {
    background-color: #101C25;
    border: 1px solid #2A4052;
    selection-background-color: #173B32;
}
QCheckBox {
    color: #AABBC6;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 4px;
    border: 1px solid #345064;
    background-color: #0A131A;
}
QCheckBox::indicator:checked {
    background-color: #3CE0B2;
    border-color: #3CE0B2;
}
QListWidget, QTableWidget {
    background-color: transparent;
    border: none;
    color: #D4E0E5;
    alternate-background-color: #0C161E;
    font-size: 12px;
}
QListWidget::item {
    border-bottom: 1px solid #16242F;
    padding: 8px 6px;
}
QListWidget::item:selected {
    background-color: #122A23;
    color: #DDFAF1;
    border-radius: 5px;
}
QTableWidget {
    gridline-color: #172632;
    selection-background-color: #122A23;
    selection-color: #E9FFF9;
}
QTableWidget::item {
    padding: 7px 8px;
    border-bottom: 1px solid #16242F;
}
QHeaderView::section {
    background-color: #0B141C;
    color: #6F8394;
    border: none;
    border-bottom: 1px solid #21323F;
    padding: 9px 8px;
    font-size: 10px;
    font-family: "Consolas";
}
QTabWidget::pane {
    border: none;
    background: transparent;
}
QTabBar::tab {
    background: transparent;
    color: #6F8394;
    border: none;
    border-bottom: 2px solid transparent;
    padding: 9px 13px;
    font-size: 11px;
}
QTabBar::tab:hover {
    color: #C9D8DE;
}
QTabBar::tab:selected {
    color: #DDFAF1;
    border-bottom: 2px solid #3CE0B2;
}
QTextBrowser {
    background-color: transparent;
    border: none;
    color: #C9D7DE;
    font-size: 12px;
    selection-background-color: #1D8E73;
}
QProgressBar {
    background-color: #0B141B;
    border: 1px solid #1D2E3B;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}
QProgressBar::chunk {
    background-color: #3CE0B2;
    border-radius: 3px;
}
QScrollArea {
    background: transparent;
    border: none;
}
QScrollArea > QWidget > QWidget {
    background: transparent;
}
QScrollBar:vertical {
    background: transparent;
    width: 8px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: #263B4B;
    min-height: 24px;
    border-radius: 4px;
}
QScrollBar::handle:vertical:hover {
    background: #385569;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {
    height: 0px;
    background: transparent;
}
QScrollBar:horizontal {
    background: transparent;
    height: 8px;
}
QScrollBar::handle:horizontal {
    background: #263B4B;
    min-width: 24px;
    border-radius: 4px;
}
QSplitter::handle {
    background-color: transparent;
    width: 16px;
}
QToolTip {
    background-color: #16242F;
    color: #DDE9E6;
    border: 1px solid #2F4759;
    padding: 6px;
}
QMessageBox {
    background-color: #0E1720;
}
QDialog {
    background-color: #0E1720;
}
QLabel#DropIcon {
    color: #3CE0B2;
    font-family: "Consolas";
    font-size: 27px;
    font-weight: 400;
}
QLabel#DropTitle {
    color: #DDEBE7;
    font-size: 14px;
    font-weight: 600;
}
QLabel#DropSub {
    color: #657A8B;
    font-size: 11px;
}
QLabel#EmptySymbol {
    color: #294456;
    font-family: "Consolas";
    font-size: 30px;
    font-weight: 300;
}
QLabel#EmptyTitle {
    color: #AFC0CA;
    font-size: 13px;
    font-weight: 600;
}
QLabel#EmptySub {
    color: #5D7283;
    font-size: 11px;
}
QLabel#FindingTitle {
    color: #E6EFEC;
    font-size: 12px;
    font-weight: 600;
}
QLabel#FindingEvidence {
    color: #708595;
    background-color: #0B141B;
    border: 1px solid #192A36;
    border-radius: 5px;
    padding: 6px 8px;
    font-family: "Consolas";
    font-size: 10px;
}
QLabel#FlagEvidence {
    color: #7D918F;
    background-color: #0B141B;
    border: 1px solid #192A36;
    border-radius: 5px;
    padding: 6px 8px;
    font-family: "Consolas";
    font-size: 10px;
}
QFrame#SectionCard {
    background-color: #0B151D;
    border: 1px solid #1A2A36;
    border-radius: 9px;
}
"""


def apply_theme(app: QApplication) -> None:
    app.setStyle("Fusion")
    families = set(QFontDatabase.families())
    ui_family = (
        "Microsoft YaHei UI"
        if "Microsoft YaHei UI" in families
        else "Microsoft YaHei"
        if "Microsoft YaHei" in families
        else "Segoe UI"
    )
    app.setFont(QFont(ui_family, 10))
    app.setStyleSheet(QSS)
