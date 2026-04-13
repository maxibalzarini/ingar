"""
Ingar - Captura de pantalla y decodificación de frames.

La captura usa mss para máxima velocidad.
Los frames se comprimen como JPEG y se codifican en base64 para
el transporte JSON.
"""

import base64
import io
import logging
import threading
import time
from typing import Callable

from PIL import Image

logger = logging.getLogger("ingar.screen")

# Resolución máxima de transmisión (ancho)
MAX_WIDTH = 1280
# Calidades JPEG predefinidas
QUALITY_MAP = {
    "Baja": 30,
    "Media": 55,
    "Alta": 80,
}
DEFAULT_QUALITY = "Media"


class ScreenCapture:
    """Captura la pantalla del equipo local y llama a un callback con cada frame."""

    def __init__(self, fps: int = 15, quality: str = DEFAULT_QUALITY):
        self.fps = fps
        self.quality_name = quality
        self._running = False
        self._thread: threading.Thread | None = None
        self._callback: Callable | None = None

    # ------------------------------------------------------------------
    # Control
    # ------------------------------------------------------------------

    def start(self, callback: Callable[[str], None]) -> None:
        """Inicia la captura. callback(frame_b64) se llama por cada frame."""
        self._callback = callback
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="ingar-capture")
        self._thread.start()
        logger.info("Captura de pantalla iniciada (%d fps, calidad=%s)", self.fps, self.quality_name)

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("Captura de pantalla detenida")

    def set_quality(self, quality_name: str) -> None:
        self.quality_name = quality_name

    # ------------------------------------------------------------------
    # Loop interno
    # ------------------------------------------------------------------

    def _loop(self) -> None:
        try:
            import mss
        except ImportError:
            logger.error("mss no está instalado: pip install mss")
            return

        interval = 1.0 / self.fps

        with mss.mss() as sct:
            monitor = sct.monitors[1]  # monitor primario

            while self._running:
                t0 = time.monotonic()
                try:
                    frame_b64 = self._capture_frame(sct, monitor)
                    if frame_b64 and self._callback:
                        self._callback(frame_b64)
                except Exception as exc:
                    logger.debug("Error capturando frame: %s", exc)

                elapsed = time.monotonic() - t0
                sleep_t = interval - elapsed
                if sleep_t > 0:
                    time.sleep(sleep_t)

    def _capture_frame(self, sct, monitor: dict) -> str | None:
        screenshot = sct.grab(monitor)

        # Convertir BGRA → RGB
        img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

        # Escalar si es demasiado grande
        w, h = img.size
        if w > MAX_WIDTH:
            scale = MAX_WIDTH / w
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)

        # Comprimir a JPEG
        quality = QUALITY_MAP.get(self.quality_name, 55)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        return base64.b64encode(buf.getvalue()).decode()

    # ------------------------------------------------------------------
    # Utilidad estática
    # ------------------------------------------------------------------

    @staticmethod
    def decode_frame(frame_b64: str) -> Image.Image:
        """Decodifica un frame base64 a PIL.Image."""
        data = base64.b64decode(frame_b64)
        return Image.open(io.BytesIO(data))

    @staticmethod
    def get_screen_size() -> tuple[int, int]:
        """Devuelve (ancho, alto) del monitor primario."""
        try:
            import mss
            with mss.mss() as sct:
                m = sct.monitors[1]
                return m["width"], m["height"]
        except Exception:
            return 1920, 1080
