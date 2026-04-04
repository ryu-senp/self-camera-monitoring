from __future__ import annotations
import os
import re
import unicodedata

_ENV_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", ".env")
)


def _normalize_name(name: str) -> str:
    """Convierte un nombre de cámara a un sufijo válido para variable de entorno."""
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = nfkd.encode("ascii", "ignore").decode("ascii")
    clean = re.sub(r"[^A-Z0-9]+", "_", ascii_str.upper()).strip("_")
    return clean or "CAM"


def make_env_var_name(camera_name: str, existing_vars: set[str]) -> str:
    """Devuelve un nombre único de variable de entorno para la cámara dada."""
    base = f"NVR_CAM_{_normalize_name(camera_name)}_PASSWORD"
    if base not in existing_vars:
        return base
    for i in range(2, 1000):
        candidate = f"{base}_{i}"
        if candidate not in existing_vars:
            return candidate
    return base


def read_env_file() -> dict[str, str]:
    """Retorna todos los pares key=value del archivo .env."""
    if not os.path.exists(_ENV_PATH):
        return {}
    result: dict[str, str] = {}
    with open(_ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def remove_env_var(key: str) -> None:
    """Elimina key del archivo .env si existe."""
    if not os.path.exists(_ENV_PATH):
        return
    with open(_ENV_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
    new_lines = [l for l in lines if not l.strip().startswith(f"{key}=")]
    with open(_ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def write_env_var(key: str, value: str) -> None:
    """Agrega o actualiza key=value en el archivo .env."""
    lines: list[str] = []
    if os.path.exists(_ENV_PATH):
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    new_line = f"{key}={value}\n"

    for i, line in enumerate(lines):
        if line.strip().startswith(f"{key}="):
            lines[i] = new_line
            with open(_ENV_PATH, "w", encoding="utf-8") as f:
                f.writelines(lines)
            return

    # Clave no encontrada → agregar al final
    if lines and not lines[-1].endswith("\n"):
        lines.append("\n")
    lines.append(new_line)
    with open(_ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(lines)
