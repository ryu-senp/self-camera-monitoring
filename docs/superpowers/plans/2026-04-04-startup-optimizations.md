# Startup Optimizations + Stale Refresh Text

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reducir el tiempo de inicio de la app (~237ms ganados con lazy PTZ) y mostrar "Refrescando..." en el thumbnail cuando el stream es reiniciado por stale detection.

**Architecture:** Tres cambios independientes: (1) mover el import de `PTZController` (que arrastra zeep/onvif ~237ms) al interior del método que lo usa, (2) cachear el path del ejecutable FFmpeg a nivel módulo en lugar de resolverlo en cada conexión, (3) mostrar texto de feedback en el thumbnail antes de emitir `restart_requested`.

**Tech Stack:** Python 3.10+, PyQt5, imageio_ffmpeg

---

## Archivos a modificar

| Archivo | Cambio |
|---|---|
| `ui/main_window.py` | Lazy import de `PTZController` — mover línea 16 al interior de `_on_ptz_requested` |
| `core/stream_worker.py` | Reemplazar función `_ffmpeg_exe()` con variable módulo cacheada |
| `core/audio_worker.py` | Cachear `imageio_ffmpeg.get_ffmpeg_exe()` en variable módulo |
| `ui/thumbnail_tile.py` | Mostrar "Refrescando..." + limpiar pixmap en `_check_stale()` |

---

## Task 1: Lazy import de PTZController (~237ms ganados)

**Archivo:** `ui/main_window.py`

`PTZController` se importa en el top-level (línea 16) pero solo se usa cuando el usuario activa PTZ. Moverlo al interior de `_on_ptz_requested` elimina el costo de importar zeep+onvif del startup.

El campo `self._ptz: dict[str, PTZController]` usa `PTZController` como type hint — se puede reemplazar por `dict` sin anotación ya que Python no evalúa anotaciones de instancia en runtime.

- [ ] **Eliminar el import top-level de PTZController** — localizar en `ui/main_window.py`:

```python
from core.ptz_controller import PTZController
```

Eliminarlo completamente.

- [ ] **Actualizar la anotación de `self._ptz`** — localizar:

```python
        self._ptz:        dict[str, PTZController] = {}
```

Reemplazar con:

```python
        self._ptz:        dict = {}
```

- [ ] **Agregar el import lazy dentro de `_on_ptz_requested`** — localizar:

```python
    def _on_ptz_requested(self, camera_id: str, pan: float, tilt: float, zoom: float):
        config = self._manager.get_camera(camera_id)
        if not config:
            return
        controller = self._ptz.setdefault(camera_id, PTZController(config))
```

Reemplazar con:

```python
    def _on_ptz_requested(self, camera_id: str, pan: float, tilt: float, zoom: float):
        from core.ptz_controller import PTZController   # lazy: evita importar onvif en startup
        config = self._manager.get_camera(camera_id)
        if not config:
            return
        controller = self._ptz.setdefault(camera_id, PTZController(config))
```

- [ ] **Verificar que la app arranca sin error**:

```
cd C:\Users\pardo\source\nvr_app && python -c "
import sys; sys.path.insert(0, '.')
from PyQt5.QtWidgets import QApplication
app = QApplication(sys.argv)
from ui.main_window import MainWindow
import inspect
src = inspect.getsource(MainWindow._on_ptz_requested)
assert 'from core.ptz_controller import PTZController' in src, 'lazy import missing'
# Verificar que PTZController NO está en los imports top-level del módulo
import ui.main_window as mw
assert not hasattr(mw, 'PTZController'), 'PTZController still top-level'
print('Task 1 OK')
"
```

---

## Task 2: Cachear path de FFmpeg

**Archivos:** `core/stream_worker.py`, `core/audio_worker.py`

`imageio_ffmpeg.get_ffmpeg_exe()` resuelve el path del binario FFmpeg en disco. Actualmente se llama en cada frame loop (`stream_worker`) y en cada reconexión de audio (`audio_worker`). Cachearlo a nivel módulo lo resuelve una sola vez.

### stream_worker.py

- [ ] **Reemplazar la función `_ffmpeg_exe` con una constante módulo** — localizar en `core/stream_worker.py`:

```python
import imageio_ffmpeg

from core.camera import CameraConfig

RECONNECT_DELAY = 5
FRAME_W, FRAME_H = 1280, 720


def _ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()
```

Reemplazar con:

```python
import imageio_ffmpeg

from core.camera import CameraConfig

RECONNECT_DELAY = 5
FRAME_W, FRAME_H = 1280, 720

_FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()
```

- [ ] **Actualizar el uso de `_ffmpeg_exe()` en `_start_process`** — localizar dentro de `StreamWorker._start_process`:

```python
        cmd = [
            _ffmpeg_exe(),
```

Reemplazar con:

```python
        cmd = [
            _FFMPEG_EXE,
```

### audio_worker.py

- [ ] **Agregar constante módulo y eliminar llamada repetida** — localizar en `core/audio_worker.py`:

```python
import imageio_ffmpeg

_CREDENTIAL_RE = re.compile(r'(rtsp://[^:@/\s]+:)[^@\s]+(@)', re.IGNORECASE)
```

Reemplazar con:

```python
import imageio_ffmpeg

_FFMPEG_EXE     = imageio_ffmpeg.get_ffmpeg_exe()
_CREDENTIAL_RE  = re.compile(r'(rtsp://[^:@/\s]+:)[^@\s]+(@)', re.IGNORECASE)
```

- [ ] **Actualizar el uso en `_connect`** — localizar dentro de `AudioWorker._connect`:

```python
        ffmpeg = imageio_ffmpeg.get_ffmpeg_exe()

        other      = "tcp" if self._last_transport == "udp" else "udp"
```

Reemplazar con:

```python
        other      = "tcp" if self._last_transport == "udp" else "udp"
```

Y más abajo en el mismo método, localizar:

```python
                proc = subprocess.Popen(
                    cmd,
```

La variable `ffmpeg` ya no existe — buscar dónde se usa en el `cmd`:

```python
            cmd = [
                ffmpeg,
```

Reemplazar con:

```python
            cmd = [
                _FFMPEG_EXE,
```

- [ ] **Verificar imports correctos**:

```
cd C:\Users\pardo\source\nvr_app && python -c "
import sys; sys.path.insert(0, '.')
from core import stream_worker, audio_worker
assert hasattr(stream_worker, '_FFMPEG_EXE'), '_FFMPEG_EXE missing in stream_worker'
assert hasattr(audio_worker, '_FFMPEG_EXE'), '_FFMPEG_EXE missing in audio_worker'
assert callable(getattr(stream_worker, '_ffmpeg_exe', None)) == False, '_ffmpeg_exe function should be gone'
print('Task 2 OK — ffmpeg path:', stream_worker._FFMPEG_EXE)
"
```

---

## Task 3: Texto "Refrescando..." en thumbnail al detectar stale

**Archivo:** `ui/thumbnail_tile.py`

Cuando `_check_stale()` detecta un stream pegado, debe limpiar el pixmap del video y mostrar "Refrescando..." antes de emitir `restart_requested`. Cuando llegue el próximo frame, `_on_frame()` actualiza el pixmap normalmente y el texto desaparece solo.

- [ ] **Actualizar `_check_stale`** — localizar:

```python
    def _check_stale(self):
        """Reinicia el stream si la cámara inactiva lleva >15 s sin frames."""
        if self._active:
            return
        elapsed = time.monotonic() - self._last_frame_ts
        if elapsed > 15.0:
            print(
                f"[ThumbnailTile] '{self._config.name}' sin frames hace "
                f"{elapsed:.0f}s — reiniciando stream"
            )
            self._last_frame_ts = time.monotonic()   # evitar reintentos en cascada
            self.restart_requested.emit(self._config.id)
```

Reemplazar con:

```python
    def _check_stale(self):
        """Reinicia el stream si la cámara inactiva lleva >15 s sin frames."""
        if self._active:
            return
        elapsed = time.monotonic() - self._last_frame_ts
        if elapsed > 15.0:
            print(
                f"[ThumbnailTile] '{self._config.name}' sin frames hace "
                f"{elapsed:.0f}s — reiniciando stream"
            )
            self._last_frame_ts = time.monotonic()   # evitar reintentos en cascada
            self._video.setPixmap(QPixmap())
            self._video.setText("Refrescando...")
            self.restart_requested.emit(self._config.id)
```

- [ ] **Verificar que `QPixmap` está importado** — buscar en los imports de `thumbnail_tile.py`:

```python
from PyQt5.QtGui import QImage, QPixmap, QColor, QPainter, QBrush, QCursor
```

`QPixmap` ya está importado. No se requiere cambio.

- [ ] **Verificar manualmente**: ejecutar `python main.py`, esperar a que una cámara se desconecte o simular desconexión. Después de ~15s sin frames, el thumbnail debe mostrar "Refrescando..." hasta que el stream se restaure.
