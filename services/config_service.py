import json
import os
from core.camera import CameraConfig

DEFAULT_PATH = os.path.join(os.path.dirname(__file__), "..", "config", "cameras.json")


class ConfigService:
    def __init__(self, path: str = DEFAULT_PATH):
        self._path = os.path.abspath(path)

    def load(self) -> list[CameraConfig]:
        if not os.path.exists(self._path):
            return []
        with open(self._path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return [CameraConfig.from_dict(d) for d in data]

    def save(self, cameras: list[CameraConfig]):
        os.makedirs(os.path.dirname(self._path), exist_ok=True)
        with open(self._path, "w", encoding="utf-8") as f:
            json.dump([c.to_dict() for c in cameras], f, indent=2)
