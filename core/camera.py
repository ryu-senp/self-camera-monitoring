from __future__ import annotations
import os
from dataclasses import dataclass, field
from uuid import uuid4
from urllib.parse import urlparse


@dataclass
class CameraConfig:
    name: str
    rtsp_host: str
    onvif_host: str
    onvif_port: int
    username: str
    password: str
    rtsp_port: int = 554
    rtsp_path: str = ""
    id: str = field(default_factory=lambda: str(uuid4()))
    enabled: bool = True
    # Nombre de la variable de entorno que contiene la contraseña de esta cámara.
    # Cuando está seteado, 'password' se resuelve en tiempo de carga desde os.environ.
    password_env: str = ""

    @property
    def rtsp_url(self) -> str:
        """URL RTSP completa con credenciales, lista para pasar a FFmpeg/ONVIF."""
        creds = f"{self.username}:{self.password}@" if self.username else ""
        return f"rtsp://{creds}{self.rtsp_host}:{self.rtsp_port}{self.rtsp_path}"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "rtsp_host": self.rtsp_host,
            "rtsp_port": self.rtsp_port,
            "rtsp_path": self.rtsp_path,
            "onvif_host": self.onvif_host,
            "onvif_port": self.onvif_port,
            "username": self.username,
            "password": "" if self.password_env else self.password,
            "password_env": self.password_env,
            "enabled": self.enabled,
        }

    @staticmethod
    def from_dict(d: dict) -> CameraConfig:
        # Resolver contraseña
        password_env = d.get("password_env", "")
        if password_env:
            password = os.environ.get(password_env, "")
            if not password:
                raise EnvironmentError(
                    f"La variable de entorno '{password_env}' no está definida.\n"
                    f"Configúrala antes de iniciar la aplicación."
                )
        else:
            password = d.get("password", "")

        # Compatibilidad hacia atrás: si el JSON tiene rtsp_url en lugar de campos atómicos
        if "rtsp_host" in d:
            rtsp_host = d["rtsp_host"]
            rtsp_port = int(d.get("rtsp_port", 554))
            rtsp_path = d.get("rtsp_path", "")
        else:
            parsed    = urlparse(d.get("rtsp_url", ""))
            rtsp_host = parsed.hostname or ""
            rtsp_port = parsed.port or 554
            rtsp_path = parsed.path or ""

        return CameraConfig(
            id=d["id"],
            name=d["name"],
            rtsp_host=rtsp_host,
            rtsp_port=rtsp_port,
            rtsp_path=rtsp_path,
            onvif_host=d.get("onvif_host", ""),
            onvif_port=d.get("onvif_port", 80),
            username=d.get("username", ""),
            password=password,
            enabled=d.get("enabled", True),
            password_env=password_env,
        )
