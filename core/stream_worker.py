from __future__ import annotations
import subprocess
import threading
import time
import numpy as np
from PyQt5.QtCore import QThread, pyqtSignal

import imageio_ffmpeg

from core.camera import CameraConfig

RECONNECT_DELAY = 5
FRAME_W, FRAME_H = 1280, 720


_FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()


class StreamWorker(QThread):
    frame_ready        = pyqtSignal(str, np.ndarray)
    connection_lost    = pyqtSignal(str)
    connection_restored = pyqtSignal(str)

    def __init__(self, config: CameraConfig):
        super().__init__()
        self._config        = config
        self._running       = False
        self._proc          = None   # subprocess activo
        self._wake          = threading.Event()  # despierta el sleep de reconexión

    def run(self):
        self._running = True
        while self._running:
            proc = self._start_process()
            if proc is None:
                self.connection_lost.emit(self._config.id)
                self._wake.wait(RECONNECT_DELAY)   # interruptible
                self._wake.clear()
                continue

            self._proc = proc
            self.connection_restored.emit(self._config.id)
            frame_bytes = FRAME_W * FRAME_H * 3

            while self._running:
                raw = proc.stdout.read(frame_bytes)
                if len(raw) < frame_bytes:
                    break
                frame = np.frombuffer(raw, dtype=np.uint8).reshape((FRAME_H, FRAME_W, 3))
                self.frame_ready.emit(self._config.id, frame)

            self._proc = None
            try:
                proc.stdout.close()
            except Exception:
                pass
            try:
                proc.wait(timeout=2)
            except Exception:
                pass
            if self._running:
                self.connection_lost.emit(self._config.id)
                self._wake.wait(RECONNECT_DELAY)   # interruptible
                self._wake.clear()

    def restart(self):
        """Fuerza reconexión inmediata: mata el proc actual y cancela cualquier delay."""
        self._wake.set()   # cancela el sleep de reconexión si estaba esperando
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass

    def stop(self):
        self._running = False
        self._wake.set()   # desbloquea el sleep de reconexión
        if self._proc and self._proc.poll() is None:
            try:
                self._proc.kill()
            except Exception:
                pass
        self.wait()

    def _start_process(self):
        cmd = [
            _FFMPEG_EXE,
            "-rtsp_transport", "udp",
            "-i", self._config.rtsp_url,
            "-vf", f"scale={FRAME_W}:{FRAME_H}",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-an",
            "-",
        ]
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                bufsize=10 * FRAME_W * FRAME_H * 3,
            )
            # Guardar proc antes del sleep para que stop() pueda matarlo
            self._proc = proc
            # Esperar en intervalos cortos para poder salir si se llama stop()
            deadline = time.monotonic() + 1.5
            while time.monotonic() < deadline:
                if not self._running:
                    proc.kill()
                    return None
                if proc.poll() is not None:
                    return None
                time.sleep(0.05)
            if proc.poll() is not None:
                return None
            return proc
        except Exception:
            return None
