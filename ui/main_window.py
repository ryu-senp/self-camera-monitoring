from __future__ import annotations
import os
from dataclasses import replace as dc_replace
import numpy as np
from PyQt5.QtWidgets import (
    QMainWindow, QWidget,
    QToolBar, QAction, QLabel, QMessageBox, QSizePolicy,
    QSplitter, QListWidget, QListWidgetItem, QVBoxLayout,
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QSize

from core.camera import CameraConfig
from core.stream_worker import StreamWorker
from core.recorder import Recorder
from core.audio_worker import AudioWorker
from services.camera_manager import CameraManager
from ui.thumbnail_tile import ThumbnailTile
from ui.camera_detail import CameraDetailWidget
from ui.camera_dialog import CameraDialog
from ui.camera_properties_dialog import CameraPropertiesDialog
from ui.camera_edit_name_dialog import CameraEditNameDialog
from ui.network_scan_dialog import NetworkScanDialog

RECORDINGS_DIR = os.path.join(os.path.dirname(__file__), "..", "recordings")
DEFAULT_FPS    = 15.0
DEFAULT_SIZE   = (1280, 720)


class MainWindow(QMainWindow):
    def __init__(self, camera_manager: CameraManager):
        super().__init__()
        self._manager     = camera_manager
        self._workers:    dict[str, StreamWorker]  = {}
        self._thumbnails: dict[str, ThumbnailTile] = {}
        self._recorders:  dict[str, Recorder]      = {}
        self._ptz:        dict = {}
        self._audio:         AudioWorker | None       = None
        self._dying_audio:   list                    = []   # workers detenidos esperando que el thread termine
        self._selected_id:   str | None              = None
        self._setup_ui()
        self._connect_manager()
        self._load_existing()

    # ── Construcción de UI ───────────────────────────────────────────────────

    def _setup_ui(self):
        self.setWindowTitle("NVR  —  Sistema de Vigilancia")
        self.resize(1440, 860)

        # ── Toolbar ─────────────────────────────────────────────────────────
        toolbar = QToolBar()
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(16, 16))

        title = QLabel("  NVR")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        title.setStyleSheet(
            "color: #2ea043; background: transparent; padding-right: 16px;"
        )
        toolbar.addWidget(title)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        add_action = QAction("➕  Agregar cámara", self)
        add_action.triggered.connect(self._open_add_dialog)
        toolbar.addAction(add_action)

        scan_action = QAction("🔍  Escanear red", self)
        scan_action.triggered.connect(self._open_scan_dialog)
        toolbar.addAction(scan_action)

        refresh_action = QAction("🔄  Reiniciar todo", self)
        refresh_action.triggered.connect(self._restart_all)
        toolbar.addAction(refresh_action)

        self.addToolBar(toolbar)

        # ── Panel izquierdo: lista de cámaras ────────────────────────────────
        list_header = QLabel("  CÁMARAS")
        list_header.setFixedHeight(32)
        list_header.setStyleSheet(
            "background: #161b22; color: #8b949e; font-size: 10px; font-weight: bold;"
            " border-bottom: 1px solid #30363d; padding: 8px 10px;"
        )

        self._cam_list = QListWidget()
        self._cam_list.setStyleSheet("""
            QListWidget {
                background: #161b22;
                border: none;
                padding: 4px;
            }
            QListWidget::item {
                padding: 8px 10px;
                border-radius: 4px;
                color: #c9d1d9;
                border-left: 3px solid transparent;
            }
            QListWidget::item:selected {
                background: #21262d;
                border-left: 3px solid #2ea043;
                color: #ffffff;
            }
            QListWidget::item:hover:!selected {
                background: #1c2128;
            }
        """)
        self._cam_list.setCursor(Qt.PointingHandCursor)
        self._cam_list.currentRowChanged.connect(self._on_list_row_changed)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)
        left_layout.addWidget(list_header)
        left_layout.addWidget(self._cam_list)
        left_panel.setMinimumWidth(160)
        left_panel.setMaximumWidth(240)
        left_panel.setStyleSheet(
            "background: #161b22; border-right: 1px solid #30363d;"
        )

        # ── Panel central: vista detalle ─────────────────────────────────────
        self._detail = CameraDetailWidget()
        self._detail.ptz_requested.connect(self._on_ptz_requested)
        self._detail.record_toggled.connect(self._on_record_toggled)
        self._detail.mute_changed.connect(self._on_mute_changed)
        self._detail.volume_changed.connect(self._on_volume_changed)
        self._detail.audio_reconnect_requested.connect(self._on_audio_reconnect)

        # ── Panel derecho: miniaturas ────────────────────────────────────────
        thumb_header = QLabel("  MINIATURAS")
        thumb_header.setFixedHeight(32)
        thumb_header.setStyleSheet(
            "background: #161b22; color: #8b949e; font-size: 10px; font-weight: bold;"
            " border-bottom: 1px solid #30363d;"
            " border-left: 1px solid #30363d; padding: 8px 10px;"
        )

        self._thumb_col_widget = QWidget()
        self._thumb_col_widget.setStyleSheet("background: #0d1117;")
        self._thumb_col = QVBoxLayout(self._thumb_col_widget)
        self._thumb_col.setSpacing(2)
        self._thumb_col.setContentsMargins(4, 4, 4, 4)

        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)
        right_layout.addWidget(thumb_header)
        right_layout.addWidget(self._thumb_col_widget)
        right_panel.setMinimumWidth(200)
        right_panel.setMaximumWidth(560)

        # ── Splitter ──────────────────────────────────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left_panel)
        splitter.addWidget(self._detail)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 3)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([200, 940, 300])
        splitter.setStyleSheet(
            "QSplitter::handle { background: #30363d; width: 1px; }"
        )
        self.setCentralWidget(splitter)

        # ── Status bar ────────────────────────────────────────────────────────
        self.statusBar().setStyleSheet(
            "background: #161b22; color: #8b949e; border-top: 1px solid #30363d;"
        )
        self.statusBar().showMessage("Listo")

    # ── Señales del manager ──────────────────────────────────────────────────

    def _connect_manager(self):
        self._manager.camera_added.connect(self._on_camera_added)
        self._manager.camera_removed.connect(self._on_camera_removed)
        self._manager.camera_updated.connect(self._on_camera_updated)

    def _load_existing(self):
        for config in self._manager.load_cameras():
            self._add_camera(config)

    # ── Diálogo ──────────────────────────────────────────────────────────────

    def _on_properties_requested(self, camera_id: str):
        config = self._manager.get_camera(camera_id)
        if config:
            CameraPropertiesDialog(config, self).exec_()

    def _on_edit_requested(self, camera_id: str):
        config = self._manager.get_camera(camera_id)
        if not config:
            return
        dialog = CameraEditNameDialog(config, self)
        if dialog.exec_():
            updated = CameraConfig(**{
                **config.to_dict(),
                "name":        dialog.get_name() or config.name,
                "onvif_host":  dialog.get_onvif_host(),
                "onvif_port":  dialog.get_onvif_port(),
            })
            self._manager.update_camera(updated)
            # Reiniciar PTZ para que tome los nuevos datos ONVIF
            self._ptz.pop(camera_id, None)

    def _on_camera_updated(self, config: CameraConfig):
        # Actualizar miniatura
        if config.id in self._thumbnails:
            self._thumbnails[config.id].update_name(config.name)
        # Actualizar lista izquierda
        for i in range(self._cam_list.count()):
            if self._cam_list.item(i).data(Qt.UserRole) == config.id:
                self._cam_list.item(i).setText(f"  {config.name or 'Sin nombre'}")
                break
        # Actualizar panel central si es la cámara activa
        if config.id == self._selected_id:
            self._detail._name_label.setText(config.name or config.rtsp_url)
        self.statusBar().showMessage(f"Cámara renombrada a '{config.name}'")

    def _open_scan_dialog(self):
        existing_ips = {
            c.rtsp_host
            for c in self._manager.get_all()
            if c.rtsp_host
        }
        dialog = NetworkScanDialog(existing_ips, self)
        dialog.camera_selected.connect(self._on_camera_from_scan)
        dialog.exec_()

    def _on_remove_requested(self, camera_id: str):
        config = self._manager.get_camera(camera_id)
        name = config.name if config else camera_id
        reply = QMessageBox.question(
            self,
            "Eliminar cámara",
            f"¿Está seguro que desea eliminar la cámara «{name}»?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        if config and config.password_env:
            from services.env_service import remove_env_var
            remove_env_var(config.password_env)
            os.environ.pop(config.password_env, None)
        self._manager.remove_camera(camera_id)

    def _on_camera_from_scan(self, config: CameraConfig):
        config = self._ensure_password_env(config)
        self._manager.add_camera(config)

    def _open_add_dialog(self):
        dialog = CameraDialog(self)
        if dialog.exec_() == CameraDialog.Accepted:
            config = dialog.get_config()
            if config:
                config = self._ensure_password_env(config)
                self._manager.add_camera(config)

    def _ensure_password_env(self, config: CameraConfig) -> CameraConfig:
        """Si la cámara tiene contraseña en texto plano, la persiste en .env
        y actualiza la config para referenciar la variable de entorno."""
        if config.password_env or not config.password:
            return config
        from services.env_service import make_env_var_name, read_env_file, write_env_var
        existing = set(read_env_file().keys())
        var_name = make_env_var_name(config.name, existing)
        write_env_var(var_name, config.password)
        os.environ[var_name] = config.password  # disponible en el proceso actual
        return dc_replace(config, password_env=var_name)

    # ── Alta / Baja de cámaras ───────────────────────────────────────────────

    def _on_camera_added(self, config: CameraConfig):
        self._add_camera(config)
        n = len(self._thumbnails)
        self.statusBar().showMessage(
            f"Cámara '{config.name}' agregada  —  {n} cámara(s) activa(s)"
        )

    def _on_camera_removed(self, camera_id: str):
        self._remove_camera(camera_id)
        n = len(self._thumbnails)
        self.statusBar().showMessage(f"{n} cámara(s) activa(s)")

    def _add_camera(self, config: CameraConfig):
        worker = StreamWorker(config)
        thumb  = ThumbnailTile(config, worker)
        thumb.selected.connect(self._on_thumb_selected)
        thumb.remove_requested.connect(self._on_remove_requested)
        thumb.properties_requested.connect(self._on_properties_requested)
        thumb.edit_requested.connect(self._on_edit_requested)
        thumb.restart_requested.connect(self._restart_camera)
        worker.frame_ready.connect(self._on_frame_for_recording)

        self._workers[config.id]    = worker
        self._thumbnails[config.id] = thumb

        # Lista izquierda
        item = QListWidgetItem(f"  {config.name or 'Sin nombre'}")
        item.setData(Qt.UserRole, config.id)
        self._cam_list.addItem(item)

        self._relayout_thumbs()
        worker.start()

        # Seleccionar automáticamente la primera cámara
        if len(self._thumbnails) == 1:
            self._select_camera(config.id)

    def _remove_camera(self, camera_id: str):
        # Detener grabación activa
        if camera_id in self._recorders:
            self._recorders.pop(camera_id).stop()

        # Detener stream
        if camera_id in self._workers:
            self._workers.pop(camera_id).stop()

        # Eliminar miniatura
        if camera_id in self._thumbnails:
            thumb = self._thumbnails.pop(camera_id)
            self._thumb_col.removeWidget(thumb)
            thumb.deleteLater()

        self._ptz.pop(camera_id, None)

        # Eliminar de la lista
        for i in range(self._cam_list.count()):
            if self._cam_list.item(i).data(Qt.UserRole) == camera_id:
                self._cam_list.takeItem(i)
                break

        # Si era la cámara activa, limpiar el centro y seleccionar otra
        if self._selected_id == camera_id:
            self._selected_id = None
            self._detail.clear()
            self._stop_audio()
            if self._thumbnails:
                first_id = next(iter(self._thumbnails))
                self._select_camera(first_id)

        self._relayout_thumbs()

    def _relayout_thumbs(self):
        # Limpiar layout sin destruir los widgets
        while self._thumb_col.count():
            self._thumb_col.takeAt(0)
        for thumb in self._thumbnails.values():
            self._thumb_col.addWidget(thumb, stretch=1)

    # ── Selección de cámara ──────────────────────────────────────────────────

    def _on_thumb_selected(self, camera_id: str):
        self._select_camera(camera_id)

    def _on_list_row_changed(self, row: int):
        item = self._cam_list.item(row)
        if item:
            self._select_camera(item.data(Qt.UserRole))

    def _select_camera(self, camera_id: str):
        if camera_id == self._selected_id:
            return

        # Detener grabación si estaba activa
        if self._selected_id and self._detail.is_recording():
            self._on_record_toggled(self._selected_id, False)

        # Actualizar highlight de miniaturas
        if self._selected_id and self._selected_id in self._thumbnails:
            self._thumbnails[self._selected_id].set_active(False)
        if camera_id in self._thumbnails:
            self._thumbnails[camera_id].set_active(True)

        # Sincronizar lista (sin disparar señal)
        self._cam_list.blockSignals(True)
        for i in range(self._cam_list.count()):
            if self._cam_list.item(i).data(Qt.UserRole) == camera_id:
                self._cam_list.setCurrentRow(i)
                break
        self._cam_list.blockSignals(False)

        self._selected_id = camera_id

        # Cargar panel central
        config = self._manager.get_camera(camera_id)
        worker = self._workers.get(camera_id)
        if config and worker:
            self._detail.load_camera(config, worker)

        # Reiniciar AudioWorker (siempre muteado)
        self._stop_audio()
        if config:
            self._audio = AudioWorker(config.rtsp_url)
            self._audio.set_muted(True)
            self._audio.set_volume(self._detail.volume)
            self._audio.status_changed.connect(self._detail.set_audio_status)
            self._audio.start()

        name = config.name if config else "—"
        self.statusBar().showMessage(f"Cámara activa: {name}")

    # ── Reinicio de stream ───────────────────────────────────────────────────

    def _restart_camera(self, camera_id: str):
        worker = self._workers.get(camera_id)
        if worker:
            worker.restart()
        config = self._manager.get_camera(camera_id)
        name = config.name if config else camera_id
        self.statusBar().showMessage(f"Reiniciando '{name}'...")

    def _restart_all(self):
        for camera_id, worker in self._workers.items():
            worker.restart()
        n = len(self._workers)
        self.statusBar().showMessage(f"Reiniciando {n} cámara(s)...")

    # ── PTZ ──────────────────────────────────────────────────────────────────

    def _on_ptz_requested(self, camera_id: str, pan: float, tilt: float, zoom: float):
        from core.ptz_controller import PTZController   # lazy: evita importar onvif en startup
        config = self._manager.get_camera(camera_id)
        if not config:
            return
        controller = self._ptz.setdefault(camera_id, PTZController(config))
        try:
            if pan == 0 and tilt == 0 and zoom == 0:
                controller.stop_move()
            else:
                controller.move(pan, tilt, zoom)
        except Exception as e:
            QMessageBox.warning(self, "PTZ Error", str(e))

    # ── Grabación ────────────────────────────────────────────────────────────

    def _on_record_toggled(self, camera_id: str, active: bool):
        if active:
            size = self._detail.frame_size() or DEFAULT_SIZE
            rec  = Recorder(camera_id, RECORDINGS_DIR, DEFAULT_FPS, size)
            rec.start()
            self._recorders[camera_id] = rec
            config = self._manager.get_camera(camera_id)
            name   = config.name if config else camera_id
            self.statusBar().showMessage(f"Grabando '{name}'...")
        else:
            rec = self._recorders.pop(camera_id, None)
            if rec:
                rec.stop()
            self.statusBar().showMessage("Grabación detenida")

    def _on_frame_for_recording(self, camera_id: str, frame: np.ndarray):
        rec = self._recorders.get(camera_id)
        if rec:
            rec.write_frame(frame)

    # ── Audio ────────────────────────────────────────────────────────────────

    def _on_mute_changed(self, muted: bool):
        if self._audio:
            self._audio.set_muted(muted)

    def _on_volume_changed(self, value: int):
        if self._audio:
            self._audio.set_volume(value)

    def _on_audio_reconnect(self):
        """Reinicia el AudioWorker de la cámara activa."""
        if not self._selected_id:
            return
        config = self._manager.get_camera(self._selected_id)
        if not config:
            return
        self._stop_audio()
        self._audio = AudioWorker(config.rtsp_url)
        self._audio.set_muted(self._detail._mute_btn.isChecked())
        self._audio.set_volume(self._detail.volume)
        self._audio.status_changed.connect(self._detail.set_audio_status)
        self._audio.start()
        self.statusBar().showMessage("Reconectando audio...")

    def _stop_audio(self):
        """Detiene el AudioWorker sin bloquear la UI.
        Mantiene la referencia Python en _dying_audio hasta que finished() se emita,
        evitando el error 'QThread: Destroyed while thread is still running'."""
        if not self._audio:
            return
        worker = self._audio
        self._audio = None
        worker.status_changed.disconnect()
        self._dying_audio.append(worker)            # mantener referencia Python viva
        worker.finished.connect(lambda: self._reap_audio(worker))
        worker.stop_async()                         # señaliza stop + mata proc, no bloquea

    def _reap_audio(self, worker):
        """Llamado desde el hilo principal cuando el AudioWorker termina."""
        try:
            self._dying_audio.remove(worker)        # liberar referencia → GC puede destruir
        except ValueError:
            pass

    # ── Cierre ───────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        # Detener el worker activo de forma bloqueante
        if self._audio:
            self._audio.stop()
            self._audio = None
        # Esperar a los workers que están terminando en background
        for worker in list(self._dying_audio):
            worker.wait(2000)
        for rec in self._recorders.values():
            rec.stop()
        for worker in self._workers.values():
            worker.stop()
        event.accept()
