from __future__ import annotations
import socket
import subprocess
import concurrent.futures
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QWidget, QDialogButtonBox,
    QLineEdit, QFormLayout, QSizePolicy, QComboBox,
)
from PyQt5.QtCore import pyqtSignal, Qt, QThread
from PyQt5.QtGui import QColor

from core.camera import CameraConfig


# ── Worker ───────────────────────────────────────────────────────────────────

class ScanWorker(QThread):
    camera_found  = pyqtSignal(str)   # IP con puerto 554 abierto
    scan_finished = pyqtSignal(int)   # total encontradas

    def run(self):
        try:
            # Conectar UDP a una IP externa para detectar qué interfaz usa el sistema
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
        except Exception:
            self.scan_finished.emit(0)
            return

        # Derivar subred /24
        prefix = ".".join(local_ip.split(".")[:3])
        hosts  = [f"{prefix}.{i}" for i in range(1, 255)]

        found = 0

        def check(ip: str):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(0.5)
                if s.connect_ex((ip, 554)) == 0:
                    s.close()
                    return ip
                s.close()
            except Exception:
                pass
            return None

        with concurrent.futures.ThreadPoolExecutor(max_workers=100) as ex:
            for ip in ex.map(check, hosts):
                if ip:
                    found += 1
                    self.camera_found.emit(ip)

        self.scan_finished.emit(found)


# ── Fila de resultado ─────────────────────────────────────────────────────────

class _CameraRow(QWidget):
    add_requested = pyqtSignal(str)   # IP

    def __init__(self, ip: str, already_added: bool, parent=None):
        super().__init__(parent)
        self._ip = ip

        dot = QLabel("●")
        dot.setStyleSheet("color: #2ea043; background: transparent; font-size: 10px;")
        dot.setFixedWidth(14)

        ip_lbl = QLabel(ip)
        ip_lbl.setStyleSheet("color: #c9d1d9; background: transparent; font-size: 12px;")
        ip_lbl.setFixedWidth(160)

        port_lbl = QLabel("RTSP : 554")
        port_lbl.setStyleSheet("color: #8b949e; background: transparent; font-size: 11px;")

        self._btn = QPushButton("✓  Agregada" if already_added else "+  Agregar")
        self._btn.setFixedSize(100, 26)
        self._btn.setEnabled(not already_added)
        self._btn.setStyleSheet("""
            QPushButton {
                background: #238636; color: #ffffff;
                border: 1px solid #2ea043; border-radius: 4px; font-size: 11px;
            }
            QPushButton:hover  { background: #2ea043; }
            QPushButton:disabled {
                background: #21262d; color: #8b949e; border-color: #30363d;
            }
        """)
        self._btn.clicked.connect(lambda: self.add_requested.emit(self._ip))

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)
        row.addWidget(dot)
        row.addWidget(ip_lbl)
        row.addWidget(port_lbl)
        row.addStretch()
        row.addWidget(self._btn)

    def mark_added(self):
        self._btn.setText("✓  Agregada")
        self._btn.setEnabled(False)


# ── Worker de prueba de conexión ─────────────────────────────────────────────

class _ProbeWorker(QThread):
    result = pyqtSignal(bool, str)   # (ok, mensaje)

    def __init__(self, url: str):
        super().__init__()
        self._url = url

    def run(self):
        try:
            import imageio_ffmpeg
            ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()
        except Exception:
            ffmpeg = "ffmpeg"

        try:
            proc = subprocess.Popen(
                [
                    ffmpeg,
                    "-rtsp_transport", "udp",
                    "-i", self._url,
                    "-t", "3",
                    "-f", "null", "-",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
            try:
                _, stderr = proc.communicate(timeout=12)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                self.result.emit(False, "✗ Tiempo de espera agotado")
                return

            output = stderr.decode(errors="ignore")
            # "Input #" aparece siempre que FFmpeg abre la fuente con éxito
            if "Input #" in output:
                self.result.emit(True, "✓ Conexión satisfactoria")
            elif "401" in output or "Unauthorized" in output:
                self.result.emit(False, "✗ Credenciales incorrectas")
            elif "Connection refused" in output or "timed out" in output.lower():
                self.result.emit(False, "✗ Sin respuesta de la cámara")
            else:
                self.result.emit(False, f"✗ Sin stream detectado")
        except Exception as e:
            self.result.emit(False, f"✗ Error: {e}")


# ── Diálogo para agregar cámara ───────────────────────────────────────────────

class _AddCameraDialog(QDialog):
    def __init__(self, ip: str, parent=None):
        super().__init__(parent)
        self._ip = ip
        self.setWindowTitle(f"Agregar cámara  —  {ip}")
        self.setMinimumWidth(340)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._setup_ui()

    def _setup_ui(self):
        def field(placeholder="", echo=QLineEdit.Normal):
            e = QLineEdit()
            e.setPlaceholderText(placeholder)
            e.setEchoMode(echo)
            return e

        self._name = field("Nombre de la cámara")
        self._user = field("usuario")
        self._pass = field("contraseña", QLineEdit.Password)

        # Path / canal RTSP
        _PATHS = [
            ("Raíz  /",                          ""),
            ("ONVIF stream 1  /onvif1",           "/onvif1"),
            ("ONVIF stream 2  /onvif2",           "/onvif2"),
            ("Genérico  /stream1",                "/stream1"),
            ("Genérico  /stream2",                "/stream2"),
            ("Hikvision main  /Streaming/Channels/101", "/Streaming/Channels/101"),
            ("Hikvision sub   /Streaming/Channels/102", "/Streaming/Channels/102"),
            ("Dahua main  /cam/realmonitor?channel=1&subtype=0",
             "/cam/realmonitor?channel=1&subtype=0"),
            ("Reolink  /h264Preview_01_main",     "/h264Preview_01_main"),
            ("Personalizado…",                    "__custom__"),
        ]
        self._path_combo = QComboBox()
        self._path_combo.setEditable(False)
        for label, _ in _PATHS:
            self._path_combo.addItem(label)
        self._path_combo.currentIndexChanged.connect(
            lambda i: self._on_path_changed(_PATHS[i][1])
        )
        self._path_values = [v for _, v in _PATHS]

        self._path_custom = QLineEdit()
        self._path_custom.setPlaceholderText("/mi/ruta/personalizada")
        self._path_custom.setVisible(False)

        # Label que muestra la URL construida en tiempo real
        self._url_preview = QLabel(f"rtsp://{self._ip}:554")
        self._url_preview.setStyleSheet(
            "color: #58a6ff; font-size: 10px; font-family: monospace;"
            " background: #161b22; border: 1px solid #30363d;"
            " border-radius: 4px; padding: 4px 8px;"
        )
        self._url_preview.setWordWrap(True)

        self._test_lbl = QLabel("")
        self._test_lbl.setStyleSheet(
            "font-size: 11px; background: transparent; padding: 2px 0;"
        )

        form = QFormLayout()
        form.setContentsMargins(16, 14, 16, 6)
        form.setSpacing(8)

        def lbl(text):
            l = QLabel(text)
            l.setStyleSheet("color: #8b949e; font-size: 11px; background: transparent;")
            return l

        form.addRow(lbl("Nombre:"),     self._name)
        form.addRow(lbl("Usuario:"),    self._user)
        form.addRow(lbl("Contraseña:"), self._pass)
        form.addRow(lbl("Canal / Path:"), self._path_combo)
        self._path_custom_row_lbl = lbl("")
        form.addRow(self._path_custom_row_lbl, self._path_custom)
        form.addRow(lbl("URL:"), self._url_preview)

        # Conectar cambios para actualizar el preview
        self._user.textChanged.connect(self._refresh_url_preview)
        self._pass.textChanged.connect(self._refresh_url_preview)
        self._path_combo.currentIndexChanged.connect(self._refresh_url_preview)
        self._path_custom.textChanged.connect(self._refresh_url_preview)

        self._test_btn = QPushButton("Probar conexión")
        self._test_btn.setFixedHeight(28)
        self._test_btn.setStyleSheet("""
            QPushButton {
                background: #21262d; color: #c9d1d9;
                border: 1px solid #30363d; border-radius: 4px; font-size: 11px;
            }
            QPushButton:hover { background: #30363d; }
        """)
        self._test_btn.clicked.connect(self._test_connection)

        test_row = QHBoxLayout()
        test_row.setContentsMargins(16, 0, 16, 0)
        test_row.addWidget(self._test_btn)
        test_row.addWidget(self._test_lbl)
        test_row.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.button(QDialogButtonBox.Ok).setText("Agregar")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.addLayout(form)
        layout.addLayout(test_row)
        layout.addWidget(buttons)

    def _refresh_url_preview(self):
        self._url_preview.setText(self._build_url())

    def _on_path_changed(self, value: str):
        is_custom = value == "__custom__"
        self._path_custom.setVisible(is_custom)
        self._path_custom_row_lbl.setVisible(is_custom)
        self._refresh_url_preview()

    def _test_connection(self):
        self._test_btn.setEnabled(False)
        self._test_lbl.setStyleSheet(
            "color: #e3b341; font-size: 11px; background: transparent;"
        )
        self._test_lbl.setText("Probando...")

        self._probe = _ProbeWorker(self._build_url())
        self._probe.result.connect(self._on_probe_result)
        self._probe.start()

    def _on_probe_result(self, ok: bool, msg: str):
        color = "#2ea043" if ok else "#f85149"
        self._test_lbl.setStyleSheet(
            f"color: {color}; font-size: 11px; background: transparent;"
        )
        self._test_lbl.setText(msg)
        self._test_btn.setEnabled(True)

    def _get_path(self) -> str:
        idx = self._path_combo.currentIndex()
        val = self._path_values[idx]
        if val == "__custom__":
            return self._path_custom.text().strip()
        return val

    def _build_url(self) -> str:
        user = self._user.text().strip()
        pwd  = self._pass.text()
        path = self._get_path()
        if user:
            return f"rtsp://{user}:{pwd}@{self._ip}:554{path}"
        return f"rtsp://{self._ip}:554{path}"

    def _on_accept(self):
        if not self._name.text().strip():
            self._name.setFocus()
            return
        self.accept()

    def get_name(self) -> str:
        return self._name.text().strip()

    def get_username(self) -> str:
        return self._user.text().strip()

    def get_password(self) -> str:
        return self._pass.text()

    def get_path(self) -> str:
        return self._get_path()

    def get_rtsp_url(self) -> str:
        return self._build_url()


# ── Diálogo principal ─────────────────────────────────────────────────────────

class NetworkScanDialog(QDialog):
    camera_selected = pyqtSignal(object)   # CameraConfig

    def __init__(self, existing_ips: set, parent=None):
        super().__init__(parent)
        self._existing_ips = set(existing_ips)
        self._rows: dict[str, _CameraRow] = {}
        self._worker: ScanWorker | None   = None

        self.setWindowTitle("Escanear red")
        self.setMinimumSize(480, 360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._setup_ui()

    def _setup_ui(self):
        # ── Controles superiores ────────────────────────────────────────────
        self._scan_btn = QPushButton("🔍  Escanear")
        self._scan_btn.setFixedHeight(32)
        self._scan_btn.clicked.connect(self._start_scan)

        self._status = QLabel("Presiona Escanear para buscar cámaras en la red local.")
        self._status.setStyleSheet(
            "color: #8b949e; font-size: 11px; background: transparent;"
        )
        self._status.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(self._scan_btn)
        top_row.addWidget(self._status)

        # ── Lista de resultados ─────────────────────────────────────────────
        self._list = QListWidget()
        self._list.setStyleSheet("""
            QListWidget {
                background: #0d1117;
                border: 1px solid #30363d;
                border-radius: 6px;
            }
            QListWidget::item { padding: 0px; border: none; }
            QListWidget::item:selected { background: transparent; }
        """)
        self._list.setSelectionMode(QListWidget.NoSelection)

        # ── Botón cerrar ────────────────────────────────────────────────────
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(16, 16, 16, 12)
        layout.addLayout(top_row)
        layout.addWidget(self._list)
        layout.addWidget(buttons)

    # ── Escaneo ──────────────────────────────────────────────────────────────

    def _start_scan(self):
        self._list.clear()
        self._rows.clear()
        self._scan_btn.setEnabled(False)

        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            prefix = ".".join(local_ip.split(".")[:3])
            self._status.setText(f"Escaneando {prefix}.1 – {prefix}.254 ...")
        except Exception:
            self._status.setText("Escaneando red local...")

        self._worker = ScanWorker()
        self._worker.camera_found.connect(self._on_camera_found)
        self._worker.scan_finished.connect(self._on_scan_finished)
        self._worker.start()

    def _on_camera_found(self, ip: str):
        already = ip in self._existing_ips
        row     = _CameraRow(ip, already)
        row.add_requested.connect(self._on_add_requested)
        self._rows[ip] = row

        item = QListWidgetItem()
        item.setSizeHint(row.sizeHint())
        self._list.addItem(item)
        self._list.setItemWidget(item, row)

    def _on_scan_finished(self, total: int):
        self._scan_btn.setEnabled(True)
        if total == 0:
            self._status.setText("No se encontraron cámaras.")
        else:
            self._status.setText(
                f"{total} cámara(s) encontrada(s). "
                "Doble clic en + para agregar."
            )

    # ── Agregar cámara ───────────────────────────────────────────────────────

    def _on_add_requested(self, ip: str):
        dialog = _AddCameraDialog(ip, self)
        if dialog.exec_() != QDialog.Accepted:
            return

        config = CameraConfig(
            name       = dialog.get_name(),
            rtsp_host  = ip,
            rtsp_port  = 554,
            rtsp_path  = dialog.get_path(),
            onvif_host = "",
            onvif_port = 80,
            username   = dialog.get_username(),
            password   = dialog.get_password(),
        )
        self._existing_ips.add(ip)
        self.camera_selected.emit(config)

        if ip in self._rows:
            self._rows[ip].mark_added()

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait()
        super().closeEvent(event)
