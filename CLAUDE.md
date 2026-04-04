# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A Python desktop NVR (Network Video Recorder) application for managing multiple IP cameras. Features RTSP video streaming, MP4 recording, PTZ control via ONVIF, and audio playback. UI is in Spanish. Built with PyQt5.

## Setup and Running

```bash
pip install -r requirements.txt
python main.py
```

No test suite or linter is configured.

## Architecture

**Pattern:** MVC with Qt signals/slots. `MainWindow` is the central orchestrator.

### Key Data Flow

```
config/cameras.json
    → ConfigService (JSON persistence)
    → CameraManager (in-memory dict, emits signals on add/remove)
    → MainWindow (orchestrates workers and UI)
        ├── StreamWorker (QThread) — FFmpeg subprocess, emits frame_ready
        │       └── Recorder — writes frames to recordings/*.mp4 via OpenCV
        ├── AudioWorker (QThread) — FFmpeg subprocess → PyAudio playback
        └── PTZController — ONVIF via onvif-zeep, lazy-initialized on first use
```

### Threading Model

- `StreamWorker` and `AudioWorker` are `QThread` subclasses. All cross-thread communication uses Qt signals/slots — never access UI widgets directly from worker threads.
- `MainWindow._dying_audio` is a list that holds references to AudioWorkers being shut down to prevent "Destroyed while thread still running" Qt errors. Workers self-remove from it via a signal when they finish.
- StreamWorker auto-reconnects after a 5-second delay on stream loss.
- AudioWorker attempts UDP then falls back to TCP on connection failure; marks a camera as `no_audio` after 3 consecutive failures.

### PTZ Controller

`PTZController` connects via ONVIF (SOAP/WSDL) to send `ContinuousMove` commands. It is lazy-initialized on the first move request. If no separate ONVIF host is configured, it parses credentials from the RTSP URL. WSDL definitions are bundled in `wsdl/`.

### Configuration

`config/cameras.json` stores all camera configs. `ConfigService` handles reading/writing. `CameraConfig` is a dataclass in `core/camera.py`.

### Recording

Recordings go to `./recordings/` as `{camera_id}_{YYYYMMDD_HHMMSS}.mp4`, written at 1280×720 / 15 fps via `cv2.VideoWriter`.

## UI Structure

- `MainWindow` — top-level window, owns all workers and UI layout
- `ThumbnailTile` — left panel showing all camera thumbnails (`CameraTile` widgets)
- `CameraDetailWidget` — main view for the selected camera's live feed
- `PTZPanel` — directional buttons that emit `move_requested` signal
- `NetworkScanDialog` — ONVIF device discovery
- `style.py` — dark theme (GitHub-style: `#0d1117`, `#161b22`, green `#2ea043`)
