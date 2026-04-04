APP_STYLE = """
/* ── Base ── */
QWidget {
    background-color: #0d1117;
    color: #c9d1d9;
    font-family: 'Segoe UI', Arial, sans-serif;
    font-size: 12px;
}

/* ── Tooltip ── */
QToolTip {
    background-color: #f6f8fa;
    color: #ffffff;
    border: 1px solid #d0d7de;
    padding: 6px 8px;
    border-radius: 4px;
    font-size: 11px;
}

/* ── Toolbar ── */
QToolBar {
    background-color: #161b22;
    border-bottom: 1px solid #30363d;
    padding: 4px 8px;
    spacing: 6px;
}
QToolBar QToolButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 6px 14px;
    font-size: 12px;
}
QToolBar QToolButton:hover {
    background-color: #2ea043;
    border-color: #2ea043;
    color: #ffffff;
}
QToolBar QToolButton:pressed {
    background-color: #238636;
}

/* ── Buttons ── */
QPushButton {
    background-color: #21262d;
    color: #c9d1d9;
    border: 1px solid #30363d;
    border-radius: 5px;
    padding: 4px 10px;
}
QPushButton:hover {
    background-color: #30363d;
    border-color: #8b949e;
}
QPushButton:pressed {
    background-color: #161b22;
}
QPushButton:checked {
    background-color: #3d1f1f;
    border-color: #f85149;
    color: #f85149;
}

/* ── Inputs ── */
QLineEdit, QSpinBox {
    background-color: #0d1117;
    border: 1px solid #30363d;
    border-radius: 5px;
    padding: 5px 8px;
    color: #c9d1d9;
    selection-background-color: #1f6feb;
}
QLineEdit:focus, QSpinBox:focus {
    border-color: #1f6feb;
}
QSpinBox::up-button, QSpinBox::down-button {
    background-color: #21262d;
    border: none;
    width: 16px;
}

/* ── Dialog ── */
QDialog {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 8px;
}
QDialogButtonBox QPushButton {
    min-width: 80px;
    padding: 6px 16px;
}
QDialogButtonBox QPushButton[text="OK"],
QDialogButtonBox QPushButton[text="Aceptar"] {
    background-color: #238636;
    border-color: #2ea043;
    color: #ffffff;
}
QDialogButtonBox QPushButton[text="OK"]:hover,
QDialogButtonBox QPushButton[text="Aceptar"]:hover {
    background-color: #2ea043;
}

/* ── Labels ── */
QLabel {
    background: transparent;
    color: #c9d1d9;
}

/* ── Context menu ── */
QMenu {
    background-color: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 4px;
}
QMenu::item {
    padding: 6px 20px;
    border-radius: 4px;
}
QMenu::item:selected {
    background-color: #21262d;
    color: #f85149;
}

/* ── Scrollbar ── */
QScrollBar:vertical {
    background: #0d1117;
    width: 8px;
    border-radius: 4px;
}
QScrollBar::handle:vertical {
    background: #30363d;
    border-radius: 4px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover { background: #8b949e; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }

/* ── Form labels ── */
QFormLayout QLabel {
    color: #8b949e;
    font-size: 11px;
}
"""
