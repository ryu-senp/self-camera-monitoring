from __future__ import annotations
import re
import subprocess
import time
import threading
import numpy as np
from collections import deque
from PyQt5.QtCore import QThread, pyqtSignal

import imageio_ffmpeg

_FFMPEG_EXE     = imageio_ffmpeg.get_ffmpeg_exe()
_CREDENTIAL_RE  = re.compile(r'(rtsp://[^:@/\s]+:)[^@\s]+(@)', re.IGNORECASE)


def _mask(text: str) -> str:
    """Reemplaza contraseñas en URLs RTSP antes de imprimir en logs."""
    return _CREDENTIAL_RE.sub(r'\1****\2', text)

SAMPLE_RATE = 16000
CHANNELS    = 1
CHUNK       = 1024   # samples por chunk
_BYTES_PER_CHUNK = CHUNK * CHANNELS * 2   # int16 = 2 bytes


def _drain_stderr(proc: subprocess.Popen, buf: deque) -> None:
    """Lee stderr del proceso en background para evitar que el pipe se llene."""
    try:
        for line in proc.stderr:
            buf.append(line.decode(errors="ignore").rstrip())
    except Exception:
        pass


class AudioWorker(QThread):
    """Decodifica audio RTSP y lo reproduce via PyAudio. Siempre inicia muteado."""
    status_changed = pyqtSignal(str)
    # "connecting" | "playing" | "no_audio" | "no_pyaudio"

    def __init__(self, rtsp_url: str):
        super().__init__()
        self._rtsp_url        = rtsp_url
        self._running         = False
        self._muted           = True
        self._volume          = 50
        self._lock            = threading.Lock()
        self._proc            = None
        self._last_transport  = "udp"   # Fix Bug 4: empieza con UDP, recuerda el que funcionó

    # ── API pública (thread-safe) ─────────────────────────────────────────────

    def set_muted(self, muted: bool):
        with self._lock:
            self._muted = muted

    def set_volume(self, value: int):
        with self._lock:
            self._volume = max(0, min(100, value))

    def _kill_proc(self):
        with self._lock:
            proc = self._proc
        if proc and proc.poll() is None:
            try:
                proc.kill()
            except Exception:
                pass

    def stop(self):
        """Bloqueante — solo para closeEvent."""
        self._running = False
        self._kill_proc()
        self.wait()

    def stop_async(self):
        """No bloqueante — para cambio de cámara."""
        self._running = False
        self._kill_proc()

    # ── Loop principal ────────────────────────────────────────────────────────

    def run(self):
        try:
            import pyaudio
        except ImportError:
            self.status_changed.emit("no_pyaudio")
            return

        self._running     = True
        pa                = pyaudio.PyAudio()
        consecutive_fails = 0

        while self._running:
            self.status_changed.emit("connecting")
            proc, transport = self._connect()

            if proc is None:
                consecutive_fails += 1
                if consecutive_fails >= 3:
                    self.status_changed.emit("no_audio")
                self._sleep(5)
                continue

            # Fix Bug 4: recordar el transporte que funcionó
            self._last_transport = transport

            try:
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=CHANNELS,
                    rate=SAMPLE_RATE,
                    output=True,
                    frames_per_buffer=CHUNK,
                )
            except Exception:
                proc.kill()
                consecutive_fails += 1
                if consecutive_fails >= 3:
                    self.status_changed.emit("no_audio")
                self._sleep(5)
                continue

            got_data = False  # Fix Bug 3: "playing" solo se emite cuando llegan datos reales

            while self._running:
                try:
                    raw = proc.stdout.read(_BYTES_PER_CHUNK)
                except Exception:
                    break
                if len(raw) < _BYTES_PER_CHUNK:
                    break

                if not got_data:
                    got_data = True
                    consecutive_fails = 0  # Fix Bug 1: resetear solo cuando hay datos reales
                    self.status_changed.emit("playing")

                with self._lock:
                    muted  = self._muted
                    volume = self._volume

                if muted:
                    stream.write(b'\x00' * _BYTES_PER_CHUNK)
                else:
                    samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
                    samples *= volume / 100.0
                    np.clip(samples, -32768, 32767, out=samples)
                    stream.write(samples.astype(np.int16).tobytes())

            stream.stop_stream()
            stream.close()

            with self._lock:
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
                consecutive_fails += 1
                if consecutive_fails >= 3:
                    self.status_changed.emit("no_audio")
                self._sleep(5)

        pa.terminate()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _sleep(self, seconds: float):
        """Sleep interrumpible si _running se pone en False."""
        deadline = time.monotonic() + seconds
        while self._running and time.monotonic() < deadline:
            time.sleep(0.05)

    def _connect(self) -> tuple[subprocess.Popen | None, str]:
        """Intenta conectar al stream de audio.
        Prueba primero el último transporte que funcionó (Fix Bug 4).
        Captura stderr para diagnóstico (Fix Bug 2).
        Retorna (proc, transport) si tiene éxito, o (None, '') si falla."""
        other      = "tcp" if self._last_transport == "udp" else "udp"
        transports = [self._last_transport, other]

        for transport in transports:
            if not self._running:
                return None, ""

            stderr_buf: deque = deque(maxlen=20)
            cmd = [
                _FFMPEG_EXE,
                "-rtsp_transport", transport,
                "-i",  self._rtsp_url,
                "-vn",
                "-f",  "s16le",
                "-ac", str(CHANNELS),
                "-ar", str(SAMPLE_RATE),
                "-",
            ]
            try:
                proc = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,   # Fix Bug 2: capturar en lugar de descartar
                    bufsize=10 * _BYTES_PER_CHUNK,
                )
                # Drenar stderr en background para que el pipe no se bloquee
                threading.Thread(
                    target=_drain_stderr, args=(proc, stderr_buf), daemon=True
                ).start()

                with self._lock:
                    self._proc = proc

                deadline = time.monotonic() + 3.0
                while time.monotonic() < deadline:
                    if not self._running:
                        proc.kill()
                        return None, ""
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)

                if proc.poll() is None:
                    return proc, transport   # proceso vivo → éxito

                # Proceso murió — imprimir stderr para diagnóstico (sin credenciales)
                if stderr_buf:
                    print(f"[AudioWorker] FFmpeg/{transport} falló en {_mask(self._rtsp_url)}:")
                    for line in stderr_buf:
                        print(f"  {_mask(line)}")

            except Exception:
                pass

        with self._lock:
            self._proc = None
        return None, ""
