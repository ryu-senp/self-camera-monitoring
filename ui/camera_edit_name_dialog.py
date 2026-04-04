from __future__ import annotations
from urllib.parse import urlparse
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLabel, QLineEdit, QSpinBox,
    QDialogButtonBox, QVBoxLayout, QFrame,
)
from PyQt5.QtCore import Qt

from core.camera import CameraConfig


class CameraEditNameDialog(QDialog):
    def __init__(self, config: CameraConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Editar cámara")
        self.setMinimumWidth(320)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._setup_ui(config)

    def _setup_ui(self, config: CameraConfig):
        # Auto-fill host ONVIF desde RTSP URL si está vacío
        onvif_host = config.onvif_host
        if not onvif_host:
            try:
                onvif_host = urlparse(config.rtsp_url).hostname or ""
            except Exception:
                onvif_host = ""

        def lbl(text):
            l = QLabel(text)
            l.setStyleSheet("color: #8b949e; font-size: 11px; background: transparent;")
            return l

        self._name = QLineEdit(config.name)
        self._name.setPlaceholderText("Nombre de la cámara")

        self._onvif_host = QLineEdit(onvif_host)
        self._onvif_host.setPlaceholderText("192.168.x.x")

        self._onvif_port = QSpinBox()
        self._onvif_port.setRange(1, 65535)
        self._onvif_port.setValue(config.onvif_port or 80)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #30363d; margin: 4px 0;")

        form = QFormLayout()
        form.setContentsMargins(16, 12, 16, 4)
        form.setSpacing(8)
        form.addRow(lbl("Nombre:"),       self._name)
        form.addRow(sep)
        form.addRow(lbl("Host ONVIF:"),   self._onvif_host)
        form.addRow(lbl("Puerto ONVIF:"), self._onvif_port)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def get_name(self) -> str:
        return self._name.text().strip()

    def get_onvif_host(self) -> str:
        return self._onvif_host.text().strip()

    def get_onvif_port(self) -> int:
        return self._onvif_port.value()
