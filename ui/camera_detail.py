from __future__ import annotations
import cv2
import numpy as np
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSlider, QSizePolicy,
)
from PyQt5.QtGui import QImage, QPixmap, QColor, QPainter, QBrush
from PyQt5.QtCore import pyqtSignal, Qt

from core.camera import CameraConfig
from core.stream_worker import StreamWorker
from ui.ptz_panel import PTZPanel

STATUS_CONNECTED    = "#2ea043"
STATUS_DISCONNECTED = "#f85149"
STATUS_CONNECTING   = "#e3b341"


class _StatusDot(QWidget):
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


class CameraDetailWidget(QWidget):
    ptz_requested         = pyqtSignal(str, float, float, float)
    record_toggled        = pyqtSignal(str, bool)
    mute_changed          = pyqtSignal(bool)
    volume_changed        = pyqtSignal(int)
    audio_reconnect_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._config: CameraConfig | None    = None
        self._frame_size: tuple | None       = None
        self._current_worker: StreamWorker | None = None
        self._setup_ui()

    # ── Construcción de UI ───────────────────────────────────────────────────

    def _setup_ui(self):
        # ── Video ──────────────────────────────────────────────────────────
        self._video = QLabel()
        self._video.setAlignment(Qt.AlignCenter)
        self._video.setStyleSheet(
            "background: #010409; color: #30363d; font-size: 14px;"
        )
        self._video.setText("Selecciona una cámara")
        self._video.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # ── Barra de información ────────────────────────────────────────────
        self._dot        = _StatusDot()
        self._name_label = QLabel("—")
        self._name_label.setStyleSheet(
            "color: #c9d1d9; font-weight: bold; font-size: 13px; background: transparent;"
        )

        self._rec_btn = QPushButton("⏺  REC")
        self._rec_btn.setCheckable(True)
        self._rec_btn.setFixedSize(84, 28)
        self._rec_btn.setStyleSheet("""
            QPushButton {
                background: #21262d; color: #8b949e;
                border: 1px solid #30363d; border-radius: 4px; font-size: 11px;
            }
            QPushButton:hover  { background: #3d1f1f; border-color: #f85149; color: #f85149; }
            QPushButton:checked { background: #3d1f1f; border-color: #f85149; color: #f85149; }
        """)
        self._rec_btn.toggled.connect(self._on_rec_toggled)
        self._rec_btn.setEnabled(False)

        info_row = QHBoxLayout()
        info_row.setContentsMargins(12, 6, 12, 6)
        info_row.setSpacing(8)
        info_row.addWidget(self._dot)
        info_row.addWidget(self._name_label)
        info_row.addStretch()
        info_row.addWidget(self._rec_btn)

        info_widget = QWidget()
        info_widget.setLayout(info_row)
        info_widget.setFixedHeight(42)
        info_widget.setStyleSheet(
            "background: #161b22; border-top: 1px solid #30363d;"
        )

        # ── Audio ───────────────────────────────────────────────────────────
        self._mute_btn = QPushButton("🔇")
        self._mute_btn.setCheckable(True)
        self._mute_btn.setChecked(True)   # siempre inicia muteado
        self._mute_btn.setFixedSize(32, 28)
        self._mute_btn.setStyleSheet("""
            QPushButton {
                background: #21262d; color: #8b949e;
                border: 1px solid #30363d; border-radius: 4px;
                font-size: 15px; padding: 0px;
            }
            QPushButton:hover   { background: #30363d; }
            QPushButton:checked { background: #1c2128; color: #8b949e; }
        """)
        self._mute_btn.toggled.connect(self._on_mute_toggled)
        self._mute_btn.setEnabled(False)

        self._vol_slider = QSlider(Qt.Horizontal)
        self._vol_slider.setRange(0, 100)
        self._vol_slider.setValue(50)
        self._vol_slider.setFixedWidth(180)
        self._vol_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px; background: #30363d; border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #2ea043; width: 12px; height: 12px;
                margin: -4px 0; border-radius: 6px;
            }
            QSlider::sub-page:horizontal {
                background: #2ea043; border-radius: 2px;
            }
            QSlider:disabled::handle:horizontal { background: #30363d; }
            QSlider:disabled::sub-page:horizontal { background: #21262d; }
        """)
        self._vol_slider.valueChanged.connect(self._on_volume_changed)
        self._vol_slider.setEnabled(False)

        self._vol_label = QLabel("50")
        self._vol_label.setFixedWidth(28)
        self._vol_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self._vol_label.setStyleSheet(
            "color: #8b949e; font-size: 11px; background: transparent;"
        )

        self._audio_info = QLabel("")
        self._audio_info.setStyleSheet(
            "font-size: 10px; background: transparent;"
        )

        self._audio_reconnect_btn = QPushButton("🔄  Reconectar audio")
        self._audio_reconnect_btn.setFixedHeight(24)
        self._audio_reconnect_btn.setVisible(False)
        self._audio_reconnect_btn.setStyleSheet("""
            QPushButton {
                background: #21262d; color: #e3b341;
                border: 1px solid #e3b341; border-radius: 4px; font-size: 10px;
                padding: 0 8px;
            }
            QPushButton:hover { background: #2d2a1a; }
        """)
        self._audio_reconnect_btn.clicked.connect(self.audio_reconnect_requested)

        audio_row = QHBoxLayout()
        audio_row.setContentsMargins(12, 6, 12, 6)
        audio_row.setSpacing(8)
        audio_row.addWidget(self._mute_btn)
        audio_row.addWidget(self._vol_slider)
        audio_row.addWidget(self._vol_label)
        audio_row.addWidget(self._audio_info)
        audio_row.addWidget(self._audio_reconnect_btn)
        audio_row.addStretch()

        audio_widget = QWidget()
        audio_widget.setLayout(audio_row)
        audio_widget.setFixedHeight(40)
        audio_widget.setStyleSheet(
            "background: #0d1117; border-top: 1px solid #30363d;"
        )

        # ── PTZ ─────────────────────────────────────────────────────────────
        self._ptz = PTZPanel(button_size=38)
        self._ptz.move_requested.connect(self._on_ptz_move)
        self._ptz.stop_requested.connect(self._on_ptz_stop)
        self._ptz.setEnabled(False)

        ptz_row = QHBoxLayout()
        ptz_row.setContentsMargins(12, 10, 12, 10)
        ptz_row.addStretch()
        ptz_row.addWidget(self._ptz)
        ptz_row.addStretch()

        ptz_widget = QWidget()
        ptz_widget.setLayout(ptz_row)
        ptz_widget.setStyleSheet(
            "background: #161b22; border-top: 1px solid #30363d;"
        )
        ptz_widget.setFixedHeight(150)

        # ── Layout principal ────────────────────────────────────────────────
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        ptz_widget.hide()   # PTZ deshabilitado temporalmente
        layout.addWidget(self._video,    stretch=1)
        layout.addWidget(info_widget)
        layout.addWidget(audio_widget)
        layout.addWidget(ptz_widget)

    # ── API pública ──────────────────────────────────────────────────────────

    def load_camera(self, config: CameraConfig, worker: StreamWorker):
        """Carga una cámara en el panel central."""
        self._disconnect_worker()
        self._config     = config
        self._frame_size = None

        self._name_label.setText(config.name or config.rtsp_url)
        self._dot.set_color(STATUS_CONNECTING)
        self._video.setPixmap(QPixmap())
        self._video.setText("Conectando...")

        self._current_worker = worker
        worker.frame_ready.connect(self._on_frame)
        worker.connection_lost.connect(self._on_lost)
        worker.connection_restored.connect(self._on_restored)

        # Habilitar controles
        self._rec_btn.setEnabled(True)
        self._rec_btn.setChecked(False)
        self._rec_btn.setText("⏺  REC")

        self._mute_btn.setEnabled(True)
        self._mute_btn.setChecked(True)   # siempre muteado al cargar
        self._vol_slider.setEnabled(False)  # deshabilitado mientras esté muteado
        self._ptz.setEnabled(True)
        self._vol_label.setText(str(self._vol_slider.value()))
        self._update_audio_ui(muted=True)

    def clear(self):
        """Limpia el panel (ninguna cámara seleccionada)."""
        self._disconnect_worker()
        self._config     = None
        self._frame_size = None

        self._video.setPixmap(QPixmap())
        self._video.setText("Selecciona una cámara")
        self._name_label.setText("—")
        self._dot.set_color(STATUS_CONNECTING)

        self._rec_btn.setEnabled(False)
        self._rec_btn.setChecked(False)
        self._mute_btn.setEnabled(False)
        self._mute_btn.setChecked(True)
        self._vol_slider.setEnabled(False)
        self._ptz.setEnabled(False)

    def frame_size(self) -> tuple | None:
        return self._frame_size

    def is_recording(self) -> bool:
        return self._rec_btn.isChecked()

    def set_audio_status(self, status: str):
        show_reconnect = False
        if status == "playing":
            self._audio_info.setStyleSheet(
                "color: #2ea043; font-size: 10px; background: transparent;"
            )
            self._audio_info.setText("● Audio conectado")
        elif status == "no_audio":
            self._audio_info.setStyleSheet(
                "color: #8b949e; font-size: 10px; background: transparent;"
            )
            self._audio_info.setText("Sin pista de audio")
            show_reconnect = True
        elif status == "no_pyaudio":
            self._audio_info.setStyleSheet(
                "color: #f85149; font-size: 10px; background: transparent;"
            )
            self._audio_info.setText("pip install pyaudio")
        else:   # connecting / vacío
            self._audio_info.setStyleSheet(
                "color: #8b949e; font-size: 10px; background: transparent;"
            )
            self._audio_info.setText("")
        self._audio_reconnect_btn.setVisible(show_reconnect)

    @property
    def camera_id(self) -> str | None:
        return self._config.id if self._config else None

    @property
    def volume(self) -> int:
        return self._vol_slider.value()

    # ── Slots privados ───────────────────────────────────────────────────────

    def _on_frame(self, camera_id: str, frame: np.ndarray):
        if not self._config or camera_id != self._config.id:
            return
        if self._frame_size is None:
            h, w = frame.shape[:2]
            self._frame_size = (w, h)
            self._dot.set_color(STATUS_CONNECTED)
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        img    = QImage(rgb.data, w, h, ch * w, QImage.Format_RGB888)
        pixmap = QPixmap.fromImage(img).scaled(
            self._video.width(), self._video.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation,
        )
        self._video.setPixmap(pixmap)

    def _on_lost(self, camera_id: str):
        if not self._config or camera_id != self._config.id:
            return
        self._frame_size = None   # resetear para que el dot vuelva a verde al reconectar
        self._dot.set_color(STATUS_DISCONNECTED)
        self._video.setPixmap(QPixmap())
        self._video.setText("Sin señal")

    def _on_restored(self, camera_id: str):
        if not self._config or camera_id != self._config.id:
            return
        self._dot.set_color(STATUS_CONNECTING)
        self._video.setPixmap(QPixmap())
        self._video.setText("Reconectando...")

    def _on_rec_toggled(self, active: bool):
        self._rec_btn.setText("⏹  STOP" if active else "⏺  REC")
        if self._config:
            self.record_toggled.emit(self._config.id, active)

    def _on_mute_toggled(self, muted: bool):
        self._update_audio_ui(muted)
        self.mute_changed.emit(muted)

    def _on_volume_changed(self, value: int):
        self._vol_label.setText(str(value))
        self.volume_changed.emit(value)

    def _on_ptz_move(self, pan: float, tilt: float, zoom: float):
        if self._config:
            self.ptz_requested.emit(self._config.id, pan, tilt, zoom)

    def _on_ptz_stop(self):
        if self._config:
            self.ptz_requested.emit(self._config.id, 0.0, 0.0, 0.0)

    def _update_audio_ui(self, muted: bool):
        self._mute_btn.setText("🔇" if muted else "🔊")
        self._vol_slider.setEnabled(not muted)
        color = "#30363d" if muted else "#8b949e"
        self._vol_label.setStyleSheet(
            f"color: {color}; font-size: 11px; background: transparent;"
        )

    def _disconnect_worker(self):
        if self._current_worker:
            try:
                self._current_worker.frame_ready.disconnect(self._on_frame)
                self._current_worker.connection_lost.disconnect(self._on_lost)
                self._current_worker.connection_restored.disconnect(self._on_restored)
            except Exception:
                pass
        self._current_worker = None
