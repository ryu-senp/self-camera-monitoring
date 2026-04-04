from __future__ import annotations
import os
from datetime import datetime
import cv2
import numpy as np


class Recorder:
    def __init__(self, camera_id: str, output_dir: str, fps: float, size: tuple):
        self._camera_id = camera_id
        self._output_dir = output_dir
        self._fps = fps
        self._size = size
        self._writer: cv2.VideoWriter | None = None

    def start(self):
        os.makedirs(self._output_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = os.path.join(self._output_dir, f"{self._camera_id}_{timestamp}.mp4")
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(path, fourcc, self._fps, self._size)

    def write_frame(self, frame: np.ndarray):
        if self._writer:
            self._writer.write(frame)

    def stop(self):
        if self._writer:
            self._writer.release()
            self._writer = None

    def is_recording(self) -> bool:
        return self._writer is not None
