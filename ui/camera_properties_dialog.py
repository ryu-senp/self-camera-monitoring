from __future__ import annotations
from urllib.parse import urlparse
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLabel, QDialogButtonBox, QVBoxLayout, QFrame,
)
from PyQt5.QtCore import Qt

from core.camera import CameraConfig


def _parse_rtsp(url: str) -> dict:
    try:
        p = urlparse(url)
        return {
            "host":     p.hostname or "—",
            "port":     str(p.port) if p.port else "554",
            "username": p.username or "—",
            "password": p.password or "",
            "path":     p.path or "/",
        }
    except Exception:
        return {"host": "—", "port": "554", "username": "—", "password": "", "path": "/"}


def _value_label(text: str) -> QLabel:
    lbl = QLabel(text or "—")
    lbl.setStyleSheet("color: #c9d1d9; font-size: 12px; background: transparent;")
    lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
    return lbl


def _section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        "color: #8b949e; font-size: 10px; font-weight: bold;"
        " background: transparent; padding-top: 6px;"
    )
    return lbl


class CameraPropertiesDialog(QDialog):
    def __init__(self, config: CameraConfig, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Propiedades — {config.name or 'Cámara'}")
        self.setMinimumWidth(360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._build_ui(config)

    def _build_ui(self, config: CameraConfig):
        rtsp = _parse_rtsp(config.rtsp_url)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setSpacing(6)
        form.setContentsMargins(16, 8, 16, 8)
        form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)

        def row(label: str, value: str):
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #8b949e; font-size: 11px; background: transparent;")
            form.addRow(lbl, _value_label(value))

        # ── General ─────────────────────────────────────────────────────────
        form.addRow(_section_label("GENERAL"), QLabel(""))
        row("Nombre:",     config.name or "Sin nombre")
        row("ID:",         config.id)

        # ── Separador ───────────────────────────────────────────────────────
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.HLine)
        sep1.setStyleSheet("color: #30363d;")
        form.addRow(sep1)

        # ── RTSP ────────────────────────────────────────────────────────────
        form.addRow(_section_label("STREAM RTSP"), QLabel(""))
        row("IP / Host:",      rtsp["host"])
        row("Puerto:",         rtsp["port"])
        row("Canal (path):",   rtsp["path"])
        row("Usuario:",        rtsp["username"])
        row("Contraseña:",     "●" * 8 if rtsp["password"] else "—")

        # ── Separador ───────────────────────────────────────────────────────
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #30363d;")
        form.addRow(sep2)

        # ── ONVIF ───────────────────────────────────────────────────────────
        form.addRow(_section_label("ONVIF (PTZ)"), QLabel(""))
        row("Host ONVIF:",     config.onvif_host or "—")
        row("Puerto ONVIF:",   str(config.onvif_port))
        row("Usuario:",        config.username or "—")
        row("Contraseña:",     "●" * 8 if config.password else "—")

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.setCenterButtons(True)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)
