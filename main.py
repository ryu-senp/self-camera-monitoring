import sys
import os

# Allow imports from project root
sys.path.insert(0, os.path.dirname(__file__))

from PyQt5.QtWidgets import QApplication


def _load_dotenv():
    """Load variables from a .env file in the project root into os.environ.
    Existing environment variables are never overwritten, so system-level
    variables always take precedence.  Works on Windows, macOS, and Linux."""
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value

from services.config_service import ConfigService
from services.camera_manager import CameraManager
from ui.main_window import MainWindow
from ui.style import APP_STYLE


def main():
    _load_dotenv()

    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(APP_STYLE)

    config_service = ConfigService()
    camera_manager = CameraManager(config_service)
    window = MainWindow(camera_manager)
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
