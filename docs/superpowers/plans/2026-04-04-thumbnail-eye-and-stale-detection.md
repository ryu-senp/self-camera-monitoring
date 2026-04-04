# Thumbnail Eye Overlay + Stale Frame Detection

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Agregar dos comportamientos al panel de miniaturas: (1) congelar la miniatura activa y mostrar un ícono de ojo encima, y (2) detectar automáticamente miniaturas de cámaras inactivas que llevan más de 15 segundos sin recibir frames y reiniciarlas.

**Architecture:** Ambas funcionalidades viven exclusivamente en `ui/thumbnail_tile.py`. El overlay es un `QLabel` hijo posicionado absolutamente sobre el área de video y reposicionado en `resizeEvent`. La detección de stale usa `time.monotonic()` + un `QTimer` periódico; la señal `restart_requested` ya existe y ya está conectada a `MainWindow._restart_camera`.

**Tech Stack:** Python 3.10+, PyQt5 (QLabel, QTimer, resizeEvent)

---

## Archivos a modificar

| Archivo | Cambio |
|---|---|
| `ui/thumbnail_tile.py` | Único archivo modificado: overlay de ojo, congelado de frame, detección de stale |

**No requieren cambios:**
- `ui/main_window.py` — `restart_requested` ya está conectado a `_restart_camera`
- `core/stream_worker.py` — `restart()` ya existe

---

## Task 1: Eye overlay + congelar miniatura activa

**Archivo:** `ui/thumbnail_tile.py`

El overlay es un `QLabel` hijo de `ThumbnailTile` (no de `self._video`) posicionado absolutamente sobre el área de video. Se muestra/oculta desde `set_active()`. El congelado se implementa con un flag `_frozen` que hace que `_on_frame()` descarte los frames cuando está activa.

- [ ] **Actualizar imports** — agregar `QTimer` y `time` (necesarios también para Task 2). Localizar la línea:

```python
from PyQt5.QtCore import pyqtSignal, Qt
```

Reemplazar con:

```python
import time
from PyQt5.QtCore import pyqtSignal, Qt, QTimer
```

- [ ] **Agregar `_frozen` y el overlay en `__init__`** — localizar:

```python
    def __init__(self, config: CameraConfig, worker: StreamWorker, parent=None):
        super().__init__(parent)
        self._config  = config
        self._active  = False
        self._setup_ui()
        self._connect_worker(worker)
```

Reemplazar con:

```python
    def __init__(self, config: CameraConfig, worker: StreamWorker, parent=None):
        super().__init__(parent)
        self._config        = config
        self._active        = False
        self._frozen        = False
        self._last_frame_ts = time.monotonic()
        self._setup_ui()
        self._connect_worker(worker)
        self._start_stale_timer()
```

- [ ] **Crear el overlay en `_setup_ui`** — insertar justo antes de `self._refresh_style()`:

```python
        # Overlay de ojo para la cámara activa
        self._eye = QLabel("👁", self)
        self._eye.setAlignment(Qt.AlignCenter)
        self._eye.setStyleSheet(
            "color: white; font-size: 26px; background: transparent;"
        )
        self._eye.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._eye.hide()
```

- [ ] **Mostrar/ocultar overlay y activar congelado en `set_active`** — localizar:

```python
    def set_active(self, active: bool):
        self._active = active
        self._refresh_style()
```

Reemplazar con:

```python
    def set_active(self, active: bool):
        self._active = active
        self._frozen = active
        self._eye.setVisible(active)
        if active:
            self._position_eye()
        self._refresh_style()
```

- [ ] **Agregar `_position_eye` y `resizeEvent`** — insertar después de `_refresh_style`:

```python
    def _position_eye(self):
        """Centra el overlay de ojo sobre el área de video."""
        vr = self._video.geometry()
        size = 48
        x = vr.x() + (vr.width() - size) // 2
        y = vr.y() + (vr.height() - size) // 2
        self._eye.setGeometry(x, y, size, size)
        self._eye.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._active:
            self._position_eye()
```

- [ ] **Congelar frames en `_on_frame`** — localizar:

```python
    def _on_frame(self, camera_id: str, frame: np.ndarray):
        if camera_id != self._config.id:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
```

Reemplazar con:

```python
    def _on_frame(self, camera_id: str, frame: np.ndarray):
        if camera_id != self._config.id:
            return
        self._last_frame_ts = time.monotonic()
        if self._frozen:
            return
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
```

- [ ] **Verificar manualmente:** ejecutar `python main.py`, seleccionar una cámara y confirmar que:
  - La miniatura muestra el `👁` centrado sobre el video
  - El frame del thumbnail deja de actualizarse mientras está seleccionada
  - Al seleccionar otra cámara, la primera retoma las actualizaciones y el ojo desaparece

---

## Task 2: Detección de frame congelado (stale) en cámaras inactivas

**Archivo:** `ui/thumbnail_tile.py`

Un `QTimer` dispara cada 10 segundos. Si la cámara no está activa y han pasado más de 15 segundos desde el último frame recibido, se emite `restart_requested`.

- [ ] **Agregar `_start_stale_timer`** — insertar después de `resizeEvent`:

```python
    def _start_stale_timer(self):
        self._stale_timer = QTimer(self)
        self._stale_timer.setInterval(10_000)   # verificar cada 10 s
        self._stale_timer.timeout.connect(self._check_stale)
        self._stale_timer.start()

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

- [ ] **Resetear timestamp en `_on_lost` y `_on_restored`** para evitar falsos positivos durante reconexiones. Localizar:

```python
    def _on_lost(self, camera_id: str):
        if camera_id != self._config.id:
            return
        self._dot.set_color(STATUS_DISCONNECTED)
        self._video.setPixmap(QPixmap())
        self._video.setText("Sin señal")

    def _on_restored(self, camera_id: str):
        if camera_id != self._config.id:
            return
        self._dot.set_color(STATUS_CONNECTING)
        self._video.setText("Reconectando...")
```

Reemplazar con:

```python
    def _on_lost(self, camera_id: str):
        if camera_id != self._config.id:
            return
        self._last_frame_ts = time.monotonic()   # resetear para no disparar stale
        self._dot.set_color(STATUS_DISCONNECTED)
        self._video.setPixmap(QPixmap())
        self._video.setText("Sin señal")

    def _on_restored(self, camera_id: str):
        if camera_id != self._config.id:
            return
        self._last_frame_ts = time.monotonic()   # resetear al reconectar
        self._dot.set_color(STATUS_CONNECTING)
        self._video.setText("Reconectando...")
```

- [ ] **Verificar manualmente:** ejecutar `python main.py` y simular una cámara congelada:
  - Desconectar una cámara de la red (o detener su servicio RTSP)
  - Esperar ~15 segundos
  - Confirmar en consola que aparece: `[ThumbnailTile] 'nombre' sin frames hace 15s — reiniciando stream`
  - Confirmar que el `StreamWorker` intenta reconectarse (el dot pasa a amarillo)
