from __future__ import annotations
from PyQt5.QtCore import QObject, pyqtSignal

from core.camera import CameraConfig
from services.config_service import ConfigService


class CameraManager(QObject):
    camera_added   = pyqtSignal(object)   # CameraConfig
    camera_removed = pyqtSignal(str)     # camera_id
    camera_updated = pyqtSignal(object)  # CameraConfig

    def __init__(self, config_service: ConfigService):
        super().__init__()
        self._service = config_service
        self._cameras: dict[str, CameraConfig] = {}

    def load_cameras(self) -> list[CameraConfig]:
        cameras = self._service.load()
        self._cameras = {c.id: c for c in cameras}
        return cameras

    def add_camera(self, config: CameraConfig):
        self._cameras[config.id] = config
        self._persist()
        self.camera_added.emit(config)

    def remove_camera(self, camera_id: str):
        self._cameras.pop(camera_id, None)
        self._persist()
        self.camera_removed.emit(camera_id)

    def get_camera(self, camera_id: str) -> CameraConfig | None:
        return self._cameras.get(camera_id)

    def update_camera(self, config: CameraConfig):
        self._cameras[config.id] = config
        self._persist()
        self.camera_updated.emit(config)

    def get_all(self) -> list[CameraConfig]:
        return list(self._cameras.values())

    def _persist(self):
        self._service.save(list(self._cameras.values()))
