# RTSP Atomic Fields Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Descomponer `rtsp_url` en campos atómicos (`rtsp_host`, `rtsp_port`, `rtsp_path`) para que la URL se construya siempre de forma determinista y no pueda perder partes al guardar/cargar.

**Architecture:** `rtsp_url` pasa a ser una `@property` calculada desde los campos atómicos más las credenciales resueltas. El JSON persiste los campos atómicos. Todos los consumidores actuales (`StreamWorker`, `AudioWorker`, `PTZController`) siguen usando `config.rtsp_url` sin cambios, ya que la property devuelve el mismo string que antes.

**Tech Stack:** Python 3.10+, PyQt5, dataclasses, urllib.parse

---

## Archivos a modificar

| Archivo | Cambio |
|---|---|
| `core/camera.py` | Reemplazar campo `rtsp_url: str` por `rtsp_host`, `rtsp_port`, `rtsp_path`; agregar property `rtsp_url`; eliminar `_inject_credentials` y `_strip_credentials` |
| `config/cameras.json` | Migrar entradas al nuevo formato |
| `ui/camera_dialog.py` | Reemplazar campo "URL RTSP" por tres campos: Host, Puerto RTSP, Stream path |
| `ui/network_scan_dialog.py` | Actualizar construcción de `CameraConfig` en `_on_add_requested`; agregar `get_path()` |
| `core/ptz_controller.py` | Simplificar `_resolve_credentials` para usar `config.rtsp_host` directamente |

**No requieren cambios** (usan `config.rtsp_url` que seguirá funcionando vía property):
- `core/stream_worker.py`
- `core/audio_worker.py`
- `ui/main_window.py`
- `ui/camera_detail.py`
- `ui/camera_properties_dialog.py`
- `ui/camera_edit_name_dialog.py`

---

## Task 1: Refactorizar CameraConfig

**Archivo:** `core/camera.py`

- [ ] **Reemplazar el contenido completo de `core/camera.py`** con lo siguiente:

```python
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
```

- [ ] **Verificar que la property funciona manualmente** — abrir una terminal Python y ejecutar:

```python
import sys; sys.path.insert(0, ".")
from core.camera import CameraConfig
c = CameraConfig(name="test", rtsp_host="192.168.1.1", rtsp_port=554,
                 rtsp_path="/onvif2", onvif_host="", onvif_port=80,
                 username="admin", password="secret")
assert c.rtsp_url == "rtsp://admin:secret@192.168.1.1:554/onvif2", c.rtsp_url

c2 = CameraConfig(name="anon", rtsp_host="10.0.0.1", rtsp_port=554,
                  rtsp_path="", onvif_host="", onvif_port=80,
                  username="", password="")
assert c2.rtsp_url == "rtsp://10.0.0.1:554", c2.rtsp_url
print("OK")
```

- [ ] **Verificar backward compat (from_dict con rtsp_url antiguo):**

```python
import os; os.environ["NVR_CAM_TEST_PASSWORD"] = "secret"
from core.camera import CameraConfig
d = {"id": "abc", "name": "cam", "rtsp_url": "rtsp://192.168.1.1:554/onvif2",
     "onvif_host": "", "onvif_port": 80, "username": "admin",
     "password_env": "NVR_CAM_TEST_PASSWORD", "enabled": True}
c = CameraConfig.from_dict(d)
assert c.rtsp_host == "192.168.1.1"
assert c.rtsp_port == 554
assert c.rtsp_path == "/onvif2"
assert c.rtsp_url  == "rtsp://admin:secret@192.168.1.1:554/onvif2"
print("OK")
```

---

## Task 2: Migrar cameras.json

**Archivo:** `config/cameras.json`

- [ ] **Reemplazar el contenido** con el formato nuevo (ajusta los valores reales de host/path de tus cámaras):

```json
[
  {
    "id": "ba999361-9d78-48ac-9123-ff6d9ae4ff6b",
    "name": "entrada",
    "rtsp_host": "192.168.100.14",
    "rtsp_port": 554,
    "rtsp_path": "/onvif2",
    "onvif_host": "",
    "onvif_port": 80,
    "username": "admin",
    "password": "",
    "password_env": "NVR_CAM_ENTRADA_PASSWORD",
    "enabled": true
  },
  {
    "id": "6685963e-4578-43fa-bd04-25f69a5a7702",
    "name": "pasillo",
    "rtsp_host": "192.168.100.77",
    "rtsp_port": 554,
    "rtsp_path": "/onvif1",
    "onvif_host": "",
    "onvif_port": 80,
    "username": "admin",
    "password": "",
    "password_env": "NVR_CAM_PASILLO_PASSWORD",
    "enabled": true
  },
  {
    "id": "c2477861-7072-4ae7-95f9-c545624620a6",
    "name": "popita",
    "rtsp_host": "192.168.100.143",
    "rtsp_port": 554,
    "rtsp_path": "/onvif2",
    "onvif_host": "",
    "onvif_port": 80,
    "username": "admin",
    "password": "",
    "password_env": "NVR_CAM_POPITA_PASSWORD",
    "enabled": true
  },
  {
    "id": "27ec5cd6-e4ed-4493-96ac-4219b4fd35d6",
    "name": "patio",
    "rtsp_host": "192.168.100.157",
    "rtsp_port": 554,
    "rtsp_path": "/onvif2",
    "onvif_host": "192.168.100.157",
    "onvif_port": 80,
    "username": "admin",
    "password": "",
    "password_env": "NVR_CAM_PATIO_PASSWORD",
    "enabled": true
  }
]
```

> **Nota:** Si la cámara que se agregó vía UI tiene `"id": "1bad9336-..."` con path incorrecto, reemplázala o elimínala; se volverá a agregar correctamente.

---

## Task 3: Actualizar CameraDialog

**Archivo:** `ui/camera_dialog.py`

El diálogo actual tiene un campo de texto libre "URL RTSP". Se reemplaza por tres campos atómicos: Host/IP, Puerto RTSP, y Stream path.

- [ ] **Reemplazar el contenido completo de `ui/camera_dialog.py`:**

```python
from __future__ import annotations
import os
from PyQt5.QtWidgets import (
    QDialog, QFormLayout, QLineEdit, QSpinBox,
    QDialogButtonBox, QVBoxLayout,
)

from core.camera import CameraConfig


class CameraDialog(QDialog):
    def __init__(self, parent=None, config: CameraConfig = None):
        super().__init__(parent)
        self.setWindowTitle("Agregar cámara" if config is None else "Editar cámara")
        self._existing_id = config.id if config else None
        self._setup_ui()
        if config:
            self._fill(config)

    def _setup_ui(self):
        self._name      = QLineEdit()
        self._rtsp_host = QLineEdit()
        self._rtsp_host.setPlaceholderText("192.168.1.100")
        self._rtsp_port = QSpinBox()
        self._rtsp_port.setRange(1, 65535)
        self._rtsp_port.setValue(554)
        self._rtsp_path = QLineEdit()
        self._rtsp_path.setPlaceholderText("/onvif2  (vacío = raíz)")
        self._host      = QLineEdit()
        self._port      = QSpinBox()
        self._port.setRange(1, 65535)
        self._port.setValue(80)
        self._user      = QLineEdit()
        self._password  = QLineEdit()
        self._password.setEchoMode(QLineEdit.Password)
        self._password.setPlaceholderText("contraseña  o  env:NOMBRE_VARIABLE")

        form = QFormLayout()
        form.addRow("Nombre:",        self._name)
        form.addRow("Host / IP:",     self._rtsp_host)
        form.addRow("Puerto RTSP:",   self._rtsp_port)
        form.addRow("Stream path:",   self._rtsp_path)
        form.addRow("Host ONVIF:",    self._host)
        form.addRow("Puerto ONVIF:",  self._port)
        form.addRow("Usuario:",       self._user)
        form.addRow("Contraseña:",    self._password)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _fill(self, config: CameraConfig):
        self._name.setText(config.name)
        self._rtsp_host.setText(config.rtsp_host)
        self._rtsp_port.setValue(config.rtsp_port)
        self._rtsp_path.setText(config.rtsp_path)
        self._host.setText(config.onvif_host)
        self._port.setValue(config.onvif_port)
        self._user.setText(config.username)
        if config.password_env:
            self._password.setEchoMode(QLineEdit.Normal)
            self._password.setText(f"env:{config.password_env}")
        else:
            self._password.setText(config.password)

    def get_config(self) -> CameraConfig | None:
        if self.result() != QDialog.Accepted:
            return None

        password_text = self._password.text()
        if password_text.startswith("env:"):
            password_env = password_text[4:].strip()
            password = os.environ.get(password_env, "")
        else:
            password_env = ""
            password = password_text

        kwargs = dict(
            name=self._name.text().strip(),
            rtsp_host=self._rtsp_host.text().strip(),
            rtsp_port=self._rtsp_port.value(),
            rtsp_path=self._rtsp_path.text().strip(),
            onvif_host=self._host.text().strip(),
            onvif_port=self._port.value(),
            username=self._user.text().strip(),
            password=password,
            password_env=password_env,
        )
        if self._existing_id:
            kwargs["id"] = self._existing_id
        return CameraConfig(**kwargs)
```

---

## Task 4: Actualizar NetworkScanDialog

**Archivo:** `ui/network_scan_dialog.py`

`_AddCameraDialog` ya captura el path en `_path_combo`. Solo hay que:
1. Agregar `get_path()` que devuelva el path seleccionado.
2. Actualizar la construcción de `CameraConfig` en `_on_add_requested` para usar campos atómicos.

- [ ] **Agregar `get_path()` en `_AddCameraDialog`** — insertar justo después de `get_rtsp_url`:

Localizar en `network_scan_dialog.py` el bloque:
```python
    def get_rtsp_url(self) -> str:
        return self._build_url()
```

Reemplazarlo con:
```python
    def get_path(self) -> str:
        return self._get_path()

    def get_rtsp_url(self) -> str:
        return self._build_url()
```

- [ ] **Actualizar la construcción de `CameraConfig` en `_on_add_requested`** — localizar:

```python
        config = CameraConfig(
            name       = dialog.get_name(),
            rtsp_url   = dialog.get_rtsp_url(),
            onvif_host = "",
            onvif_port = 80,
            username   = dialog.get_username(),
            password   = dialog.get_password(),
        )
```

Reemplazarlo con:
```python
        config = CameraConfig(
            name       = dialog.get_name(),
            rtsp_host  = ip,
            rtsp_port  = 554,
            rtsp_path  = dialog.get_path(),
            onvif_host = "",
            onvif_port = 80,
            username   = dialog.get_username(),
            password   = dialog.get_password(),
        )
```

---

## Task 5: Simplificar PTZController

**Archivo:** `core/ptz_controller.py`

Con los campos atómicos, ya no hace falta parsear `rtsp_url` para obtener el host.

- [ ] **Localizar `_resolve_credentials`:**

```python
    def _resolve_credentials(self) -> tuple:
        """Devuelve (host, port, user, password).
        Si onvif_host está vacío, usa los datos de la RTSP URL como fallback.
        """
        host = self._config.onvif_host
        user = self._config.username
        pwd  = self._config.password

        if not host:
            p    = urlparse(self._config.rtsp_url)
            host = p.hostname or ""
            user = user or p.username or ""
            pwd  = pwd  or p.password or ""

        return host, self._config.onvif_port, user, pwd
```

Reemplazarlo con:
```python
    def _resolve_credentials(self) -> tuple:
        """Devuelve (host, port, user, password).
        Si onvif_host está vacío, usa rtsp_host como fallback.
        """
        host = self._config.onvif_host or self._config.rtsp_host
        return host, self._config.onvif_port, self._config.username, self._config.password
```

- [ ] **Eliminar el import de `urlparse`** en `ptz_controller.py` si ya no se usa en ningún otro lugar del archivo:

```python
from urllib.parse import urlparse   # ← eliminar esta línea
```

---

## Task 6: Actualizar main_window — parseo de hostname

**Archivo:** `ui/main_window.py`

`main_window.py` usa `urlparse(c.rtsp_url).hostname` para extraer IPs existentes al abrir el diálogo de escaneo. Con campos atómicos, puede usar `c.rtsp_host` directamente.

- [ ] **Localizar en `_open_scan_dialog`:**

```python
        existing_ips = {
            urlparse(c.rtsp_url).hostname
            for c in self._manager.get_all()
            if c.rtsp_url
        }
```

Reemplazarlo con:
```python
        existing_ips = {
            c.rtsp_host
            for c in self._manager.get_all()
            if c.rtsp_host
        }
```

- [ ] **Verificar si `urlparse` sigue siendo usado en otro lugar del archivo** — si la única referencia era esa, eliminar el import:

```python
from urllib.parse import urlparse   # ← eliminar si ya no se usa
```

---

## Task 7: Actualizar env_service — generación de nombre de variable

**Archivo:** `services/env_service.py`  
**Archivo:** `ui/main_window.py` — método `_ensure_password_env`

Con el nuevo dataclass, `config.name` sigue existiendo, así que `make_env_var_name(config.name, ...)` no cambia. Sin embargo, `_ensure_password_env` usa `dc_replace` que ahora no puede recibir `rtsp_url` como campo (ya no existe). Hay que verificar que no haya referencias al campo antiguo.

- [ ] **Revisar `_ensure_password_env` en `main_window.py`** — la implementación actual es:

```python
    def _ensure_password_env(self, config: CameraConfig) -> CameraConfig:
        if config.password_env or not config.password:
            return config
        from services.env_service import make_env_var_name, read_env_file, write_env_var
        existing = set(read_env_file().keys())
        var_name = make_env_var_name(config.name, existing)
        write_env_var(var_name, config.password)
        os.environ[var_name] = config.password
        return dc_replace(config, password_env=var_name)
```

`dc_replace(config, password_env=var_name)` usa `dataclasses.replace` que copia todos los campos del dataclass — no hace referencia a `rtsp_url` porque ya no es un campo. **No requiere cambio**, solo confirmar que funciona.

- [ ] **Ejecutar la app** con `python main.py` y agregar una cámara nueva desde el diálogo "Agregar cámara":
  - Ingresar host, puerto, path, usuario, contraseña
  - Verificar que se crea la entrada en `.env`
  - Verificar que `cameras.json` guarda los tres campos atómicos
  - Verificar que el stream conecta correctamente

---

## Verificación final

- [ ] Iniciar la app: `python main.py`
- [ ] Comprobar que las cámaras existentes cargan y conectan (las cuatro del JSON migrado)
- [ ] Agregar una cámara nueva desde "Agregar cámara" — verificar que path se guarda correctamente
- [ ] Agregar una cámara desde "Escanear red" — verificar que el path del combo se respeta
- [ ] Editar una cámara existente — verificar que host/port/path se muestran correctamente en el diálogo
