from __future__ import annotations
import os
from onvif import ONVIFCamera

from core.camera import CameraConfig

# WSDL files bundled en nvr_app/wsdl/
_WSDL_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "wsdl")


class PTZController:
    def __init__(self, config: CameraConfig):
        self._config = config
        self._ptz    = None
        self._token  = None

    def _resolve_credentials(self) -> tuple:
        """Devuelve (host, port, user, password).
        Si onvif_host está vacío, usa rtsp_host como fallback.
        """
        host = self._config.onvif_host or self._config.rtsp_host
        return host, self._config.onvif_port, self._config.username, self._config.password

    def _init_service(self):
        host, port, user, pwd = self._resolve_credentials()
        cam          = ONVIFCamera(host, port, user, pwd, _WSDL_DIR)
        media        = cam.create_media_service()
        self._ptz    = cam.create_ptz_service()
        profiles     = media.GetProfiles()
        self._token  = profiles[0].token

    def move(self, pan: float, tilt: float, zoom: float):
        if self._ptz is None:
            self._init_service()
        req = self._ptz.create_type("ContinuousMove")
        req.ProfileToken = self._token
        req.Velocity = {
            "PanTilt": {"x": pan, "y": tilt},
            "Zoom":    {"x": zoom},
        }
        self._ptz.ContinuousMove(req)

    def stop_move(self):
        if self._ptz is None:
            return
        self._ptz.Stop({"ProfileToken": self._token})
