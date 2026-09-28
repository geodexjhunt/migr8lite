from PyQt6.QtWidgets import QApplication
import os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CHECKMARK_PATH = os.path.join(BASE_DIR, "img", "checkmark_white.svg").replace("\\", "/")

DARK_STYLESHEET = """
/* Base application */
QWidget {
    background-color: #202124;
    color: #e8eaed;
    font-size: 10pt;
}

/* Labels */
QLabel {
    background: transparent;
    color: #e8eaed;
}

/* Buttons */
QPushButton {
    background-color: #3c4043;
    border: 1px solid #5f6368;
    border-radius: 4px;
    color: #e8eaed;
    min-height: 26px;
    padding: 4px 10px;
}

QPushButton:hover {
    background-color: #4b5054;
    border-color: #8ab4f8;
}

QPushButton:pressed {
    background-color: #2f3133;
}

QPushButton:disabled {
    background-color: #303134;
    border-color: #3c4043;
    color: #9aa0a6;
}

/* Inputs and combo boxes */
QLineEdit,
QTextEdit,
QPlainTextEdit,
QSpinBox,
QDoubleSpinBox,
QDateEdit,
QTimeEdit,
QDateTimeEdit,
QComboBox {
    background-color: #292a2d;
    border: 1px solid #5f6368;
    border-radius: 4px;
    color: #e8eaed;
    min-height: 24px;
    padding: 3px 6px;
    selection-background-color: #3b82c4;
    selection-color: #ffffff;
}

QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus,
QComboBox:focus {
    border: 1px solid #8ab4f8;
}

/* Combo-box dropdown */
QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    width: 8px;
    height: 8px;
}

QComboBox QAbstractItemView {
    background-color: #292a2d;
    border: 1px solid #5f6368;
    color: #e8eaed;
    selection-background-color: #3b82c4;
    selection-color: #ffffff;
    outline: none;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #4f5256;
    background-color: #202124;
    top: -1px;
}

QTabBar::tab {
    background-color: #303134;
    border: 1px solid #4f5256;
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    color: #bdc1c6;
    margin-right: 2px;
    min-height: 25px;
    padding: 6px 12px;
}

QTabBar::tab:hover {
    background-color: #3c4043;
    color: #ffffff;
}

QTabBar::tab:selected {
    background-color: #202124;
    border-bottom: 1px solid #202124;
    color: #8ab4f8;
    font-weight: bold;
}

/* Data grids, trees, and lists */
QTableWidget,
QTableView,
QTreeWidget,
QTreeView,
QListWidget,
QListView {
    alternate-background-color: #292a2d;
    background-color: #202124;
    border: 1px solid #4f5256;
    color: #e8eaed;
    gridline-color: #45474a;
    outline: none;
    selection-background-color: #3b82c4;
    selection-color: #ffffff;
}

QTableWidget::item,
QTableView::item,
QTreeWidget::item,
QTreeView::item,
QListWidget::item,
QListView::item {
    min-height: 23px;
    padding: 2px;
}

QTableWidget::item:selected,
QTableView::item:selected,
QTreeWidget::item:selected,
QTreeView::item:selected,
QListWidget::item:selected,
QListView::item:selected {
    background-color: #3b82c4;
    color: #ffffff;
}

/* Grid/tree headers */
QHeaderView::section {
    background-color: #303134;
    border: none;
    border-right: 1px solid #4f5256;
    border-bottom: 1px solid #4f5256;
    color: #e8eaed;
    font-weight: bold;
    min-height: 25px;
    padding: 4px 6px;
}

/* Menus */
QMenuBar {
    background-color: #202124;
    color: #e8eaed;
}

QMenuBar::item {
    background: transparent;
    padding: 5px 9px;
}

QMenuBar::item:selected {
    background-color: #3c4043;
}

QMenu {
    background-color: #292a2d;
    border: 1px solid #5f6368;
    color: #e8eaed;
}

QMenu::item {
    padding: 6px 25px 6px 12px;
}

QMenu::item:selected {
    background-color: #3b82c4;
    color: #ffffff;
}

/* Dialogs and button boxes */
QDialog {
    background-color: #202124;
    color: #e8eaed;
}

QMessageBox {
    background-color: #202124;
    color: #e8eaed;
}

/* Group boxes */
QGroupBox {
    border: 1px solid #4f5256;
    border-radius: 5px;
    color: #e8eaed;
    font-weight: bold;
    margin-top: 10px;
    padding-top: 8px;
}

QGroupBox::title {
    left: 9px;
    padding: 0 4px;
}

/* Splitter */
QSplitter::handle {
    background-color: #4f5256;
}

QSplitter::handle:hover {
    background-color: #8ab4f8;
}

/* Scroll bars */
QScrollBar:vertical {
    background-color: #202124;
    border: none;
    margin: 0;
    width: 12px;
}

QScrollBar::handle:vertical {
    background-color: #5f6368;
    border-radius: 5px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background-color: #8ab4f8;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: #202124;
    border: none;
    height: 12px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: #5f6368;
    border-radius: 5px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #8ab4f8;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}

/* Status bars */
QStatusBar {
    background-color: #292a2d;
    border-top: 1px solid #4f5256;
    color: #bdc1c6;
}
"""


LIGHT_STYLESHEET = """
/* Base application */
QWidget {
    background-color: #f2f1f5;
    color: #322c3d;
    font-size: 10pt;
}

/* Labels */
QLabel {
    background: transparent;
    color: #322c3d;
}

/* Buttons */
QPushButton {
    background-color: #e6e3ec;
    border: 1px solid #c3bdd1;
    border-radius: 4px;
    color: #322c3d;
    min-height: 26px;
    padding: 4px 10px;
}

QPushButton:hover {
    background-color: #ded8ea;
    border-color: #9b7fc2;
}

QPushButton:pressed {
    background-color: #cfc6df;
}

QPushButton:disabled {
    background-color: #ececec;
    border-color: #d6d6d6;
    color: #a3a0aa;
}

/* Inputs and combo boxes */
QLineEdit,
QTextEdit,
QPlainTextEdit,
QSpinBox,
QDoubleSpinBox,
QDateEdit,
QTimeEdit,
QDateTimeEdit,
QComboBox {
    background-color: #ffffff;
    border: 1px solid #c3bdd1;
    border-radius: 4px;
    color: #322c3d;
    min-height: 24px;
    padding: 3px 6px;
    selection-background-color: #9b7fc2;
    selection-color: #ffffff;
}

QLineEdit:focus,
QTextEdit:focus,
QPlainTextEdit:focus,
QComboBox:focus {
    border: 1px solid #7e57c2;
}

/* Combo-box dropdown */
QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    width: 8px;
    height: 8px;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    border: 1px solid #c3bdd1;
    color: #322c3d;
    selection-background-color: #9b7fc2;
    selection-color: #ffffff;
    outline: none;
}

/* Tabs */
QTabWidget::pane {
    border: 1px solid #cfc9d9;
    background-color: #f2f1f5;
    top: -1px;
}

QTabBar::tab {
    background-color: #e6e3ec;
    border: 1px solid #cfc9d9;
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
    color: #5c5568;
    margin-right: 2px;
    min-height: 25px;
    padding: 6px 12px;
}

QTabBar::tab:hover {
    background-color: #ded8ea;
    color: #322c3d;
}

QTabBar::tab:selected {
    background-color: #f2f1f5;
    border-bottom: 1px solid #f2f1f5;
    color: #7e57c2;
    font-weight: bold;
}

/* Data grids, trees, and lists */
QTreeWidget::item {
    color: #322c3d;
    background-color: #ffffff;
    padding: 2px;
    min-height: 23px;
}

QTreeWidget::item:hover {
    background-color: #f0ede8;
}

QTreeWidget::item:selected {
    background-color: #9b7fc2;
    color: #ffffff;
}

QTreeWidget::item:first-column {
    color: #0000ff;
    background-color: #d3d3d3;
}

QTableWidget,
QTableView,
QTreeWidget,
QTreeView,
QListWidget,
QListView {
    alternate-background-color: #ebe9f0;
    background-color: #ffffff;
    border: 1px solid #cfc9d9;
    color: #322c3d;
    gridline-color: #dcd8e4;
    outline: none;
    selection-background-color: #9b7fc2;
    selection-color: #ffffff;
}

QTableWidget::item,
QTableView::item,
QTreeWidget::item,
QTreeView::item,
QListWidget::item,
QListView::item {
    min-height: 23px;
    padding: 2px;
}

QTableWidget::item:selected,
QTableView::item:selected,
QTreeWidget::item:selected,
QTreeView::item:selected,
QListWidget::item:selected,
QListView::item:selected {
    background-color: #9b7fc2;
    color: #ffffff;
}

/* Grid/tree headers */
QHeaderView::section {
    background-color: #e6e3ec;
    border: none;
    border-right: 1px solid #cfc9d9;
    border-bottom: 1px solid #cfc9d9;
    color: #4a4356;
    font-weight: bold;
    min-height: 25px;
    padding: 4px 6px;
}

/* Menus */
QMenuBar {
    background-color: #f2f1f5;
    color: #322c3d;
}

QMenuBar::item {
    background: transparent;
    padding: 5px 9px;
}

QMenuBar::item:selected {
    background-color: #ded8ea;
}

QMenu {
    background-color: #ffffff;
    border: 1px solid #c3bdd1;
    color: #322c3d;
}

QMenu::item {
    padding: 6px 25px 6px 12px;
}

QMenu::item:selected {
    background-color: #9b7fc2;
    color: #ffffff;
}

/* Dialogs and button boxes */
QDialog {
    background-color: #f2f1f5;
    color: #322c3d;
}

QMessageBox {
    background-color: #f2f1f5;
    color: #322c3d;
}

/* Check boxes * /
QCheckBox {
    color: #000000;
    spacing: 5px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border: 2px solid #333333;
    border-radius: 2px;
    background-color: #FFFFFF;
}

QCheckBox::indicator:hover {
    border: 2px solid #0078D4;
    background-color: #F0F7FF;
}

QCheckBox::indicator:checked {
    background-color: #0078D4;
    border: 2px solid #0078D4;
    image: url(:/icons/checkmark.png);
}

QCheckBox::indicator:unchecked:focus {
    border: 2px solid #0078D4;
    outline: 1px solid #0078D4;
}


/* Group boxes */
QGroupBox {
    border: 1px solid #cfc9d9;
    border-radius: 5px;
    color: #4a4356;
    font-weight: bold;
    margin-top: 10px;
    padding-top: 8px;
}

QGroupBox::title {
    left: 9px;
    padding: 0 4px;
}

/* Splitter */
QSplitter::handle {
    background-color: #cfc9d9;
}

QSplitter::handle:hover {
    background-color: #9b7fc2;
}

/* Scroll bars */
QScrollBar:vertical {
    background-color: #f2f1f5;
    border: none;
    margin: 0;
    width: 12px;
}

QScrollBar::handle:vertical {
    background-color: #c3bdd1;
    border-radius: 5px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background-color: #9b7fc2;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
}

QScrollBar:horizontal {
    background-color: #f2f1f5;
    border: none;
    height: 12px;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background-color: #c3bdd1;
    border-radius: 5px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background-color: #9b7fc2;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
}

/* Status bars */
QStatusBar {
    background-color: #e6e3ec;
    border-top: 1px solid #cfc9d9;
    color: #4a4356;
}
"""


def set_dark_mode(enabled: bool) -> None:
    """Apply the selected application-wide stylesheet."""
    app = QApplication.instance()

    if app is None:
        return

    app.setStyleSheet(DARK_STYLESHEET if enabled else LIGHT_STYLESHEET)