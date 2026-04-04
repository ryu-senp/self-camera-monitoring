from PyQt5.QtWidgets import QWidget, QGridLayout, QPushButton
from PyQt5.QtCore import pyqtSignal

DIRECTIONS = {
    "▲": (0.0,  0.5,  0.0),
    "▼": (0.0, -0.5,  0.0),
    "◄": (-0.5, 0.0,  0.0),
    "►": (0.5,  0.0,  0.0),
    "+": (0.0,  0.0,  0.5),
    "−": (0.0,  0.0, -0.5),
}

LAYOUT = [
    (None, "▲", None,  "+"),
    ("◄",  None, "►", None),
    (None, "▼", None,  "−"),
]

BTN_STYLE = """
    QPushButton {
        background-color: #21262d;
        color: #8b949e;
        border: 1px solid #30363d;
        border-radius: 4px;
        font-size: 13px;
        padding: 0px;
    }
    QPushButton:hover {
        background-color: #1f6feb;
        border-color: #1f6feb;
        color: #ffffff;
    }
    QPushButton:pressed {
        background-color: #1158c7;
    }
"""


class PTZPanel(QWidget):
    move_requested = pyqtSignal(float, float, float)
    stop_requested = pyqtSignal()

    def __init__(self, parent=None, button_size: int = 28):
        super().__init__(parent)
        self._button_size = button_size
        self._setup_ui()

    def _setup_ui(self):
        grid = QGridLayout(self)
        grid.setSpacing(3)
        grid.setContentsMargins(0, 0, 0, 0)
        for row, cols in enumerate(LAYOUT):
            for col, label in enumerate(cols):
                if label is None:
                    continue
                btn = QPushButton(label)
                btn.setFixedSize(self._button_size, self._button_size)
                btn.setStyleSheet(BTN_STYLE)
                pan, tilt, zoom = DIRECTIONS[label]
                btn.pressed.connect(lambda p=pan, t=tilt, z=zoom: self.move_requested.emit(p, t, z))
                btn.released.connect(self.stop_requested.emit)
                grid.addWidget(btn, row, col)
