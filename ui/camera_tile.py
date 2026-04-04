from __future__ import annotations
import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QMenu,
)
from PyQt5.QtGui import QImage, QPixmap, QColor, QPainter, QBrush
from PyQt5.QtCore import pyqtSignal, Qt, QSize

from core.camera import CameraConfig
from core.stream_worker import StreamWorker
from ui.ptz_panel import PTZPanel

TILE_W, TILE_H = 480, 270

STATUS_CONNECTED    = "#2ea043"
STATUS_DISCONNECTED = "#f85149"
STATUS_CONNECTING   = "#e3b341"


class StatusDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._color = STATUS_CONNECTING

    def set_color(self, color: str):
        self._color = color
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor(self._color)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, 10, 10)


class CameraTile(QWidget):
    ptz_requested    = pyqtSignal(str, float, float, float)
    record_toggled   = pyqtSignal(str, bool)
    remove_requested = pyqtSignal(str)

    def __init__(self, config: CameraConfig, worker: StreamWorker, parent=None):
        super().__init__(parent)
        self._config = config
        self._frame_size: tuple | None = None
        self._setup_ui()
        self._connect_worker(worker)

    def _setup_ui(self):
        # Video area
        self._video_label = QLabel()
        self._video_label.setAlignment(Qt.AlignCenter)
        self._video_label.setMinimumSize(TILE_W, TILE_H)
        self._video_label.setStyleSheet("background: #010409;")
        self._video_label.setText("Conectando...")
        self._video_label.setStyleSheet("background: #010409; color: #30363d; font-size: 14px;")

        # Bottom bar
        self._dot = StatusDot()

        self._name_label = QLabel(self._config.name)
        self._name_label.setStyleSheet(
            "color: #c9d1d9; font-weight: bold; font-size: 12px; background: transparent;"
        )

        self._rec_btn = QPushButton("⏺  REC")
        self._rec_btn.setCheckable(True)
        self._rec_btn.setFixedSize(72, 26)
        self._rec_btn.setStyleSheet("""
            QPushButton {
                background: #21262d; color: #8b949e;
                border: 1px solid #30363d; border-radius: 4px; font-size: 11px;
            }
            QPushButton:hover { background: #3d1f1f; border-color: #f85149; color: #f85149; }
            QPushButton:checked {
                background: #3d1f1f; border-color: #f85149; color: #f85149;
            }
        """)
        self._rec_btn.toggled.connect(self._on_rec_toggled)

        ptz = PTZPanel(self)
        ptz.move_requested.connect(
            lambda p, t, z: self.ptz_requested.emit(self._config.id, p, t, z)
        )
        ptz.stop_requested.connect(
            lambda: self.ptz_requested.emit(self._config.id, 0, 0, 0)
        )

        bar = QHBoxLayout()
        bar.setContentsMargins(8, 4, 8, 4)
        bar.setSpacing(6)
        bar.addWidget(self._dot)
        bar.addWidget(self._name_label)
        bar.addStretch()
        bar.addWidget(ptz)
        bar.addWidget(self._rec_btn)

        bar_widget = QWidget()
        bar_widget.setLayout(bar)
        bar_widget.setFixedHeight(40)
        bar_widget.setStyleSheet("background: #161b22; border-top: 1px solid #30363d;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._video_label, stretch=1)
        layout.addWidget(bar_widget)

        self.setStyleSheet("""
            CameraTile {
                border: 1px solid #30363d;
                border-radius: 6px;
            }
            CameraTile:hover {
                border-color: #8b949e;
            }
        """)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)

    def _connect_worker(self, worker: StreamWorker):
        worker.frame_ready.connect(self._on_frame)
        worker.connection_lost.connect(self._on_lost)
        worker.connection_restored.connect(self._on_restored)

    def _on_frame(self, camera_id: str, frame: np.ndarray):
        if camera_id != self._config.id:
            return
        if self._frame_size is None:
            h, w = frame.shape[:2]
            self._frame_size = (w, h)
            self._dot.set_color(STATUS_CONNECTED)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img).scaled(
            self._video_label.width(), self._video_label.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._video_label.setPixmap(pixmap)

    def _on_lost(self, camera_id: str):
        if camera_id != self._config.id:
            return
        self._dot.set_color(STATUS_DISCONNECTED)
        self._video_label.setPixmap(QPixmap())
        self._video_label.setText("Sin señal")

    def _on_restored(self, camera_id: str):
        if camera_id != self._config.id:
            return
        self._dot.set_color(STATUS_CONNECTING)
        self._video_label.setText("Reconectando...")

    def _on_rec_toggled(self, active: bool):
        self._rec_btn.setText("⏹  STOP" if active else "⏺  REC")
        self.record_toggled.emit(self._config.id, active)

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction(f"🗑  Eliminar '{self._config.name}'").triggered.connect(
            lambda: self.remove_requested.emit(self._config.id)
        )
        menu.exec_(self.mapToGlobal(pos))

    def frame_size(self) -> tuple | None:
        return self._frame_size
