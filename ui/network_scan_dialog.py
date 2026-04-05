from __future__ import annotations
import socket
import subprocess
import concurrent.futures
import uuid
import xml.etree.ElementTree as ET
from urllib.parse import urlparse
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QWidget, QDialogButtonBox,
    QLineEdit, QFormLayout, QSizePolicy, QComboBox,
)
from PyQt5.QtCore import pyqtSignal, Qt, QThread
from PyQt5.QtGui import QColor

from core.camera import CameraConfig


# ── WS-Discovery constants ────────────────────────────────────────────────────

_WSD_MULTICAST_IP = "239.255.255.250"
_WSD_PORT         = 3702
_WSD_TIMEOUT_S    = 3
_WSD_NS_D         = "http://schemas.xmlsoap.org/ws/2005/04/discovery"


def _get_local_ips() -> list[str]:
    """Retorna todas las IPs IPv4 del host (sin loopback ni link-local)."""
    ips: list[str] = []
    try:
        _, _, addr_list = socket.gethostbyname_ex(socket.gethostname())
        for ip in addr_list:
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                ips.append(ip)
    except Exception:
        pass
    if not ips:                          # fallback: interfaz primaria
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            pass
    return ips


# ── Workers ───────────────────────────────────────────────────────────────────

class ScanWorker(QThread):
    camera_found  = pyqtSignal(str)   # IP con puerto 554 abierto
    scan_finished = pyqtSignal(int)   # total encontradas

    def __init__(self, source_ip: str, parent=None):
        super().__init__(parent)
        self._source_ip = source_ip

    def run(self):
        prefix = ".".join(self._source_ip.split(".")[:3])
        hosts  = [f"{prefix}.{i}" for i in range(1, 255)]
        found  = 0

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


class DiscoveryWorker(QThread):
    device_found  = pyqtSignal(str, str)   # (ip, xaddr)
    scan_finished = pyqtSignal()

    def __init__(self, source_ip: str, parent=None):
        super().__init__(parent)
        self._source_ip = source_ip

    def run(self):
        msg_id = str(uuid.uuid4())
        probe  = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<s:Envelope'
            ' xmlns:s="http://www.w3.org/2003/05/soap-envelope"'
            ' xmlns:a="http://schemas.xmlsoap.org/ws/2004/08/addressing"'
            ' xmlns:d="http://schemas.xmlsoap.org/ws/2005/04/discovery"'
            ' xmlns:dn="http://www.onvif.org/ver10/network/wsdl">'
            '<s:Header>'
            '<a:Action>http://schemas.xmlsoap.org/ws/2005/04/discovery/Probe</a:Action>'
            f'<a:MessageID>uuid:{msg_id}</a:MessageID>'
            '<a:To>urn:schemas-xmlsoap-org:ws:2005:04:discovery</a:To>'
            '</s:Header>'
            '<s:Body><d:Probe>'
            '<d:Types>dn:NetworkVideoTransmitter</d:Types>'
            '</d:Probe></s:Body>'
            '</s:Envelope>'
        ).encode("utf-8")

        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM,
                                 socket.IPPROTO_UDP)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            # Forzar salida por la interfaz seleccionada (crítico en Windows)
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF,
                            socket.inet_aton(self._source_ip))
            sock.settimeout(_WSD_TIMEOUT_S)
            sock.sendto(probe, (_WSD_MULTICAST_IP, _WSD_PORT))
            while True:
                try:
                    data, _ = sock.recvfrom(65535)
                except socket.timeout:
                    break
                self._parse_response(data)
        except Exception:
            pass
        finally:
            if sock:
                sock.close()
        self.scan_finished.emit()

    def _parse_response(self, data: bytes):
        try:
            root = ET.fromstring(data.decode("utf-8", errors="ignore"))
        except ET.ParseError:
            return
        for xaddrs_elem in root.iter(f"{{{_WSD_NS_D}}}XAddrs"):
            text = (xaddrs_elem.text or "").strip()
            for xaddr in text.split():
                try:
                    ip = urlparse(xaddr).hostname
                    if ip:
                        self.device_found.emit(ip, xaddr)
                        return
                except Exception:
                    continue


# ── Fila de resultado ─────────────────────────────────────────────────────────

class _CameraRow(QWidget):
    add_requested = pyqtSignal(str, str)   # (ip, xaddr)

    def __init__(self, ip: str, already_added: bool,
                 is_onvif: bool = False, xaddr: str = "", parent=None):
        super().__init__(parent)
        self._ip    = ip
        self._xaddr = xaddr

        dot = QLabel("●")
        dot.setStyleSheet("color: #2ea043; background: transparent; font-size: 10px;")
        dot.setFixedWidth(14)

        ip_lbl = QLabel(ip)
        ip_lbl.setStyleSheet("color: #c9d1d9; background: transparent; font-size: 12px;")
        ip_lbl.setFixedWidth(140)

        port_lbl = QLabel("RTSP : 554")
        port_lbl.setStyleSheet("color: #8b949e; background: transparent; font-size: 11px;")

        self._badge = QLabel("ONVIF")
        self._badge.setStyleSheet(
            "color: #ffffff; background: #1f6feb;"
            " border-radius: 3px; font-size: 9px; padding: 1px 5px;"
        )
        self._badge.setVisible(is_onvif)

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
        self._btn.clicked.connect(lambda: self.add_requested.emit(self._ip, self._xaddr))

        row = QHBoxLayout(self)
        row.setContentsMargins(8, 4, 8, 4)
        row.setSpacing(8)
        row.addWidget(dot)
        row.addWidget(ip_lbl)
        row.addWidget(port_lbl)
        row.addWidget(self._badge)
        row.addStretch()
        row.addWidget(self._btn)

    def upgrade_to_onvif(self, xaddr: str):
        self._xaddr = xaddr
        self._badge.setVisible(True)

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
    def __init__(self, ip: str, xaddr: str = "", parent=None):
        super().__init__(parent)
        self._ip    = ip
        self._xaddr = xaddr
        self.setWindowTitle(f"Agregar cámara  —  {ip}")
        self.setMinimumWidth(360)
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

        # ONVIF host — pre-llenado si viene de WS-Discovery
        onvif_default = ""
        if self._xaddr:
            try:
                onvif_default = urlparse(self._xaddr).hostname or self._ip
            except Exception:
                onvif_default = self._ip
        self._onvif_host = QLineEdit()
        self._onvif_host.setPlaceholderText("IP del servicio ONVIF (opcional, para PTZ)")
        if onvif_default:
            self._onvif_host.setText(onvif_default)

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

        form.addRow(lbl("Nombre:"),       self._name)
        form.addRow(lbl("Usuario:"),      self._user)
        form.addRow(lbl("Contraseña:"),   self._pass)
        form.addRow(lbl("ONVIF host:"),   self._onvif_host)
        form.addRow(lbl("Canal / Path:"), self._path_combo)
        self._path_custom_row_lbl = lbl("")
        form.addRow(self._path_custom_row_lbl, self._path_custom)
        form.addRow(lbl("URL:"),          self._url_preview)

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

    def get_onvif_host(self) -> str:
        return self._onvif_host.text().strip()

    def get_rtsp_url(self) -> str:
        return self._build_url()


# ── Diálogo principal ─────────────────────────────────────────────────────────

class NetworkScanDialog(QDialog):
    camera_selected = pyqtSignal(object)   # CameraConfig

    def __init__(self, existing_ips: set, parent=None):
        super().__init__(parent)
        self._existing_ips  = set(existing_ips)
        self._rows:          dict[str, _CameraRow]  = {}
        self._worker:        ScanWorker       | None = None
        self._disc_worker:   DiscoveryWorker  | None = None
        self._scan_finished  = False
        self._disc_finished  = False
        self._total_found    = 0

        self.setWindowTitle("Escanear red")
        self.setMinimumSize(480, 360)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self._setup_ui()

    def _setup_ui(self):
        # ── Selector de interfaz ────────────────────────────────────────────
        iface_lbl = QLabel("Interfaz:")
        iface_lbl.setStyleSheet(
            "color: #8b949e; font-size: 11px; background: transparent;"
        )

        self._iface_combo = QComboBox()
        self._iface_combo.setFixedHeight(28)
        self._iface_combo.setMinimumWidth(140)
        for ip in (_get_local_ips() or ["(sin red)"]):
            self._iface_combo.addItem(ip)

        # ── Botón escanear ──────────────────────────────────────────────────
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
        top_row.addWidget(iface_lbl)
        top_row.addWidget(self._iface_combo)
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
        self._scan_finished = self._disc_finished = False
        self._total_found   = 0
        self._scan_btn.setEnabled(False)

        source_ip = self._iface_combo.currentText()
        prefix    = ".".join(source_ip.split(".")[:3])
        self._status.setText(f"Escaneando {prefix}.0/24 + WS-Discovery...")

        self._worker = ScanWorker(source_ip)
        self._worker.camera_found.connect(self._on_camera_found_tcp)
        self._worker.scan_finished.connect(self._on_scan_finished_tcp)
        self._worker.start()

        self._disc_worker = DiscoveryWorker(source_ip)
        self._disc_worker.device_found.connect(self._on_device_found_onvif)
        self._disc_worker.scan_finished.connect(self._on_scan_finished_disc)
        self._disc_worker.start()

    def _on_camera_found_tcp(self, ip: str):
        if ip in self._rows:
            return
        row = _CameraRow(ip, ip in self._existing_ips)
        row.add_requested.connect(self._on_add_requested)
        self._rows[ip] = row
        self._total_found += 1
        self._add_row_to_list(row)

    def _on_device_found_onvif(self, ip: str, xaddr: str):
        if ip in self._rows:
            self._rows[ip].upgrade_to_onvif(xaddr)
        else:
            row = _CameraRow(ip, ip in self._existing_ips, is_onvif=True, xaddr=xaddr)
            row.add_requested.connect(self._on_add_requested)
            self._rows[ip] = row
            self._total_found += 1
            self._add_row_to_list(row)

    def _add_row_to_list(self, row: _CameraRow):
        item = QListWidgetItem()
        item.setSizeHint(row.sizeHint())
        self._list.addItem(item)
        self._list.setItemWidget(item, row)

    def _on_scan_finished_tcp(self, _total: int):
        self._scan_finished = True
        self._check_all_done()

    def _on_scan_finished_disc(self):
        self._disc_finished = True
        self._check_all_done()

    def _check_all_done(self):
        if not (self._scan_finished and self._disc_finished):
            return
        self._scan_btn.setEnabled(True)
        self._status.setText(
            f"{self._total_found} cámara(s) encontrada(s)."
            if self._total_found else "No se encontraron cámaras."
        )

    # ── Agregar cámara ───────────────────────────────────────────────────────

    def _on_add_requested(self, ip: str, xaddr: str):
        dialog = _AddCameraDialog(ip, xaddr, self)
        if dialog.exec_() != QDialog.Accepted:
            return

        config = CameraConfig(
            name       = dialog.get_name(),
            rtsp_host  = ip,
            rtsp_port  = 554,
            rtsp_path  = dialog.get_path(),
            onvif_host = dialog.get_onvif_host(),
            onvif_port = 80,
            username   = dialog.get_username(),
            password   = dialog.get_password(),
        )
        self._existing_ips.add(ip)
        self.camera_selected.emit(config)

        if ip in self._rows:
            self._rows[ip].mark_added()

    def closeEvent(self, event):
        for w in (self._worker, self._disc_worker):
            if w and w.isRunning():
                w.terminate()
                w.wait()
        super().closeEvent(event)
