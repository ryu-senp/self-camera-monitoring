from __future__ import annotations
import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QMenu, QSizePolicy,
)
from PyQt5.QtGui import QImage, QPixmap, QColor, QPainter, QBrush, QCursor
import time
from PyQt5.QtCore import pyqtSignal, Qt, QTimer

from core.camera import CameraConfig
from core.stream_worker import StreamWorker

THUMB_W, THUMB_H = 240, 135

STATUS_CONNECTED    = "#2ea043"
STATUS_DISCONNECTED = "#f85149"
STATUS_CONNECTING   = "#e3b341"


class _StatusDot(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(8, 8)
        self._color = STATUS_CONNECTING

    def set_color(self, color: str):
        self._color = color
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setBrush(QBrush(QColor(self._color)))
        p.setPen(Qt.NoPen)
        p.drawEllipse(0, 0, 8, 8)


class ThumbnailTile(QWidget):
    selected             = pyqtSignal(str)   # camera_id  (doble clic)
    remove_requested     = pyqtSignal(str)   # camera_id
    properties_requested = pyqtSignal(str)   # camera_id
    edit_requested       = pyqtSignal(str)   # camera_id
    restart_requested    = pyqtSignal(str)   # camera_id

    def __init__(self, config: CameraConfig, worker: StreamWorker, parent=None):
        super().__init__(parent)
        self._config        = config
        self._active        = False
        self._frozen        = False
        self._last_frame_ts = time.monotonic()
        self._setup_ui()
        self._connect_worker(worker)
        self._start_stale_timer()

    # ── UI ───────────────────────────────────────────────────────────────────

    def _setup_ui(self):
        self._video = QLabel()
        self._video.setAlignment(Qt.AlignCenter)
        self._video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._video.setMinimumHeight(56)
        self._video.setStyleSheet(
            "background: #010409; color: #30363d; font-size: 11px;"
        )
        self._video.setText("Conectando...")

        self._dot  = _StatusDot()
        self._name = QLabel(self._config.name or "Sin nombre")
        self._name.setStyleSheet(
            "color: #c9d1d9; font-size: 11px; background: transparent;"
        )

        bar = QHBoxLayout()
        bar.setContentsMargins(6, 3, 6, 3)
        bar.setSpacing(5)
        bar.addWidget(self._dot)
        bar.addWidget(self._name)
        bar.addStretch()

        self._bar = QWidget()
        self._bar.setLayout(bar)
        self._bar.setFixedHeight(24)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._video, stretch=1)
        layout.addWidget(self._bar)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setCursor(Qt.PointingHandCursor)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        # Overlay de ojo para la cámara activa
        self._eye = QLabel("👁", self)
        self._eye.setAlignment(Qt.AlignCenter)
        self._eye.setStyleSheet(
            "color: white; font-size: 26px; background: transparent;"
        )
        self._eye.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._eye.hide()

        self._refresh_style()
        self._refresh_tooltip()

    def _connect_worker(self, worker: StreamWorker):
        worker.frame_ready.connect(self._on_frame)
        worker.connection_lost.connect(self._on_lost)
        worker.connection_restored.connect(self._on_restored)

    # ── Estado activo ────────────────────────────────────────────────────────

    def set_active(self, active: bool):
        self._active = active
        self._frozen = active
        self._eye.setVisible(active)
        if active:
            self._position_eye()
        self._refresh_style()

    def _refresh_style(self):
        if self._active:
            self.setStyleSheet("""
                ThumbnailTile {
                    border: 2px solid #2ea043;
                    border-radius: 4px;
                    background: #0d1117;
                }
            """)
            self._bar.setStyleSheet(
                "background: #0f2d1a; border-top: 2px solid #2ea043;"
            )
            self._name.setStyleSheet(
                "color: #ffffff; font-size: 11px; font-weight: bold; background: transparent;"
            )
        else:
            self.setStyleSheet("""
                ThumbnailTile {
                    border: 1px solid #30363d;
                    border-radius: 4px;
                    background: #0d1117;
                }
                ThumbnailTile:hover {
                    border-color: #8b949e;
                }
            """)
            self._bar.setStyleSheet(
                "background: #161b22; border-top: 1px solid #30363d;"
            )
            self._name.setStyleSheet(
                "color: #c9d1d9; font-size: 11px; background: transparent;"
            )

    def _position_eye(self):
        """Centra el overlay de ojo sobre el área de video."""
        vr = self._video.geometry()
        size = 48
        x = vr.x() + (vr.width() - size) // 2
        y = vr.y() + (vr.height() - size) // 2
        self._eye.setGeometry(x, y, size, size)
        self._eye.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._active:
            self._position_eye()

    # ── Eventos ──────────────────────────────────────────────────────────────

    def mouseDoubleClickEvent(self, event):
        self.selected.emit(self._config.id)
        super().mouseDoubleClickEvent(event)

    def update_name(self, name: str):
        self._name.setText(name or "Sin nombre")
        self._refresh_tooltip()

    def _refresh_tooltip(self):
        c = self._config
        onvif = c.onvif_host or "—"
        lines = [
            c.name or "Sin nombre",
            f"Host: {c.rtsp_host}:{c.rtsp_port}",
            f"Stream path: {c.rtsp_path or '/'}",
            f"ONVIF host: {onvif}",
        ]
        self.setToolTip("\n".join(lines))

    def _show_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction("🔄  Reiniciar stream").triggered.connect(
            lambda: self.restart_requested.emit(self._config.id)
        )
        menu.addSeparator()
        menu.addAction("📋  Ver propiedades").triggered.connect(
            lambda: self.properties_requested.emit(self._config.id)
        )
        menu.addAction("✏️  Editar nombre").triggered.connect(
            lambda: self.edit_requested.emit(self._config.id)
        )
        menu.addSeparator()
        menu.addAction(f"🗑  Eliminar '{self._config.name}'").triggered.connect(
            lambda: self.remove_requested.emit(self._config.id)
        )
        menu.exec_(self.mapToGlobal(pos))

    # ── Slots de stream ──────────────────────────────────────────────────────

    def _on_frame(self, camera_id: str, frame: np.ndarray):
        if camera_id != self._config.id:
            return
        self._last_frame_ts = time.monotonic()
        if self._frozen:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img).scaled(
            self._video.width(), self._video.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._video.setPixmap(pixmap)
        self._dot.set_color(STATUS_CONNECTED)

    def _on_lost(self, camera_id: str):
        if camera_id != self._config.id:
            return
        self._dot.set_color(STATUS_DISCONNECTED)
        self._video.setPixmap(QPixmap())
        self._video.setText("Sin señal")

    def _on_restored(self, camera_id: str):
        if camera_id != self._config.id:
            return
        self._last_frame_ts = time.monotonic()   # resetear al reconectar
        self._dot.set_color(STATUS_CONNECTING)
        self._video.setText("Reconectando...")

    def _start_stale_timer(self):
        self._stale_timer = QTimer(self)
        self._stale_timer.setInterval(10_000)   # verificar cada 10 s
        self._stale_timer.timeout.connect(self._check_stale)
        self._stale_timer.start()

    def _check_stale(self):
        """Reinicia el stream si la cámara inactiva lleva >15 s sin frames."""
        if self._active:
            return
        elapsed = time.monotonic() - self._last_frame_ts
        if elapsed > 15.0:
            print(
                f"[ThumbnailTile] '{self._config.name}' sin frames hace "
                f"{elapsed:.0f}s — reiniciando stream"
            )
            self._last_frame_ts = time.monotonic()   # evitar reintentos en cascada
            self._video.setPixmap(QPixmap())
            self._video.setText("Refrescando...")
            self.restart_requested.emit(self._config.id)

    # ── Acceso ───────────────────────────────────────────────────────────────

    @property
    def camera_id(self) -> str:
        return self._config.id
