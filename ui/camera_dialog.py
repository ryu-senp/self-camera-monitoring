from __future__ import annotations
import os
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QSpinBox,
    QDialogButtonBox, QVBoxLayout,
)

from core.camera import CameraConfig


class CameraDialog(QDialog):
    def __init__(self, parent=None, config: CameraConfig = None):
        super().__init__(parent)
        self.setWindowTitle("Agregar cámara" if config is None else "Editar cámara")
        self._existing_id = config.id if config else None
        self._setup_ui()
        if config:
            self._fill(config)

    def _setup_ui(self):
        self._name      = QLineEdit()
        self._rtsp_host = QLineEdit()
        self._rtsp_host.setPlaceholderText("192.168.1.100")
        self._rtsp_port = QSpinBox()
        self._rtsp_port.setRange(1, 65535)
        self._rtsp_port.setValue(554)
        self._rtsp_path = QLineEdit()
        self._rtsp_path.setPlaceholderText("/onvif2  (vacío = raíz)")
        self._host      = QLineEdit()
        self._port      = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(80)
        self._user      = QLineEdit()
        self._password  = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setPlaceholderText("contraseña  o  env:NOMBRE_VARIABLE")

        form = QFormLayout()
        form.addRow("Nombre:",        self._name)
        form.addRow("Host / IP:",     self._rtsp_host)
        form.addRow("Puerto RTSP:",   self._rtsp_port)
        form.addRow("Stream path:",   self._rtsp_path)
        form.addRow("Host ONVIF:",    self._host)
        form.addRow("Puerto ONVIF:",  self._port)
        form.addRow("Usuario:",       self._user)
        form.addRow("Contraseña:",    self._password)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _fill(self, config: CameraConfig):
        self._name.setText(config.name)
        self._rtsp_host.setText(config.rtsp_host)
        self._rtsp_port.setValue(config.rtsp_port)
        self._rtsp_path.setText(config.rtsp_path)
        self._host.setText(config.onvif_host)
        self._port.setValue(config.onvif_port)
        self._user.setText(config.username)
        if config.password_env:
            self._password.setEchoMode(QLineEdit.Normal)
            self._password.setText(f"env:{config.password_env}")
        else:
            self._password.setText(config.password)

    def get_config(self) -> CameraConfig | None:
        if self.result() != QDialog.Accepted:
            return None

        password_text = self._password.text()
        if password_text.startswith("env:"):
            password_env = password_text[4:].strip()
            password = os.environ.get(password_env, "")
        else:
            password_env = ""
            password = password_text

        kwargs = dict(
            name=self._name.text().strip(),
            rtsp_host=self._rtsp_host.text().strip(),
            rtsp_port=self._rtsp_port.value(),
            rtsp_path=self._rtsp_path.text().strip(),
            onvif_host=self._host.text().strip(),
            onvif_port=self._port.value(),
            username=self._user.text().strip(),
            password=password,
            password_env=password_env,
        )
        if self._existing_id:
            kwargs["id"] = self._existing_id
        return CameraConfig(**kwargs)
