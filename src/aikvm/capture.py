"""Fresh desktop/UVC observations; one latest frame, no disk trace by default."""
from __future__ import annotations

import io
import threading
import time
import uuid
from dataclasses import dataclass

from PIL import Image


@dataclass
class Observation:
    id: str
    captured_at: float
    monotonic: float
    geometry: tuple
    image: Image.Image
    target: str
    source: str
    crop: tuple | None = None

    def metadata(self) -> dict:
        return {"frame_id": self.id, "target_id": self.target, "captured_at_unix": self.captured_at,
                "timestamp_basis": "host_read_completion",
                "width": self.image.width, "height": self.image.height, "geometry": self.geometry,
                "crop": self.crop, "source": self.source, "status": "frame_received",
                "signal_verified": self.source == "desktop"}

    def png(self) -> bytes:
        buf = io.BytesIO()
        self.image.save(buf, format="PNG")
        return buf.getvalue()


class Capture:
    def __init__(self, source="desktop", monitor=1, camera=0, target="bench"):
        if source not in ("desktop", "uvc"):
            raise ValueError("Capture source must be desktop or uvc")
        self.source, self.monitor, self.camera, self.target = source, monitor, camera, target
        self.last: Observation | None = None
        self._latest = None
        self._generation = 0
        self._error = "capture_not_started"
        self._lock = threading.Lock()
        self._quit = threading.Event()
        self._thread = None

    def _start_uvc(self):
        if self._thread:
            return
        self._thread = threading.Thread(target=self._read_uvc, daemon=True)
        self._thread.start()

    def _read_uvc(self):
        import cv2
        while not self._quit.is_set():
            cap = cv2.VideoCapture(self.camera, cv2.CAP_DSHOW)
            if not cap.isOpened():
                self._quit.wait(1)
                continue
            with self._lock:
                self._generation += 1
            try:
                while not self._quit.is_set():
                    ok, frame = cap.read()
                    if not ok:
                        with self._lock:
                            self._latest = None
                            self._error = "capture_read_failed"
                        break
                    image = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    with self._lock:
                        self._latest = (image, time.time(), time.monotonic(), self._generation)
                        self._error = None
            finally:
                cap.release()
            self._quit.wait(0.5)

    def grab(self, crop: tuple | None = None, after: float = 0) -> Observation:
        if self.source == "desktop":
            import mss
            with mss.mss() as screen:
                if self.monitor < 1 or self.monitor >= len(screen.monitors):
                    raise ValueError("Select an existing physical monitor starting at 1")
                bounds = screen.monitors[self.monitor]
                raw = screen.grab(bounds)
                image = Image.frombytes("RGB", raw.size, raw.rgb)
                geometry = (bounds["left"], bounds["top"], bounds["width"], bounds["height"], len(screen.monitors)-1)
            wall, mono = time.time(), time.monotonic()
        else:
            self._start_uvc()
            deadline = time.monotonic()+3
            while True:
                with self._lock:
                    latest = self._latest
                    detail = self._error
                if latest and latest[2] > after and time.monotonic()-latest[2] < 0.75:
                    image, wall, mono, generation = latest
                    image = image.copy()
                    geometry = (0, 0, image.width, image.height, generation)
                    break
                if time.monotonic() > deadline:
                    raise TimeoutError(f"No fresh UVC frame: {detail}. Dongle signal-loss screens can look like valid video.")
                time.sleep(0.03)
        if crop:
            x, y, w, h = crop
            if x < 0 or y < 0 or w < 1 or h < 1 or x+w > image.width or y+h > image.height:
                raise ValueError("Crop outside captured frame")
            image = image.crop((x,y,x+w,y+h))
        # Keep image and coordinates at native size; no hidden resize mapping.
        obs = Observation(uuid.uuid4().hex, wall, mono, geometry, image, self.target, self.source, crop)
        self.last = obs
        return obs

    def resolve_point(self, frame_id: str, x: int, y: int, max_age=5.0) -> tuple[int, int]:
        prior = self.last
        if not prior or prior.id != frame_id or time.monotonic()-prior.monotonic > max_age:
            raise ValueError("Observation missing or stale; observe again")
        if not 0 <= x < prior.image.width or not 0 <= y < prior.image.height:
            raise ValueError("Point outside observation")
        old_geometry = prior.geometry
        fresh = self.grab()
        if fresh.geometry != old_geometry:
            raise ValueError("Display geometry changed; observe again")
        if self.source == "desktop" and (self.monitor != 1 or old_geometry[4] != 1):
            raise ValueError("Absolute input bench requires one monitor; use relative movement otherwise")
        left, top = (prior.crop[0], prior.crop[1]) if prior.crop else (0, 0)
        return (round((x+left)*32767/max(1, old_geometry[2]-1)),
                round((y+top)*32767/max(1, old_geometry[3]-1)))

    def close(self):
        self._quit.set()
