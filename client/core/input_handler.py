"""
Ingar - Control de entrada remota (ratón y teclado).

InputInjector: inyecta eventos en el equipo controlado.
InputCapture : captura eventos en el equipo controlador y los envía al peer.
"""

import logging
from typing import Callable

logger = logging.getLogger("ingar.input")


# ---------------------------------------------------------------------------
# Inyector (máquina controlada)
# ---------------------------------------------------------------------------

class InputInjector:
    """Reproduce eventos de ratón y teclado recibidos desde el controlador."""

    def __init__(self, screen_width: int = 1920, screen_height: int = 1080):
        self.screen_width = screen_width
        self.screen_height = screen_height

        try:
            from pynput.mouse import Button, Controller as MouseCtrl
            from pynput.keyboard import Key, Controller as KeyCtrl
            self._mouse = MouseCtrl()
            self._keyboard = KeyCtrl()
            self._Button = Button
            self._Key = Key
            self._available = True
        except Exception as exc:
            logger.warning("pynput no disponible, inyección deshabilitada: %s", exc)
            self._available = False

    # ------------------------------------------------------------------

    def handle_event(self, event: dict) -> None:
        if not self._available:
            return

        etype = event.get("event_type")

        try:
            if etype == "mouse_move":
                x = int(event["x"] * self.screen_width)
                y = int(event["y"] * self.screen_height)
                self._mouse.position = (x, y)

            elif etype == "mouse_click":
                x = int(event["x"] * self.screen_width)
                y = int(event["y"] * self.screen_height)
                btn = (self._Button.left
                       if event.get("button") == "left"
                       else self._Button.right)
                self._mouse.position = (x, y)
                if event.get("pressed", True):
                    self._mouse.press(btn)
                else:
                    self._mouse.release(btn)

            elif etype == "mouse_scroll":
                x = int(event["x"] * self.screen_width)
                y = int(event["y"] * self.screen_height)
                self._mouse.position = (x, y)
                self._mouse.scroll(event.get("dx", 0), event.get("dy", 0))

            elif etype == "key_press":
                self._press_key(event.get("key", ""), press=True)

            elif etype == "key_release":
                self._press_key(event.get("key", ""), press=False)

        except Exception as exc:
            logger.debug("Error inyectando evento %s: %s", etype, exc)

    def _press_key(self, key_str: str, press: bool) -> None:
        try:
            # Teclas especiales: "Key.ctrl_l", "ctrl_l", etc.
            if key_str.startswith("Key."):
                key_name = key_str[4:]
            else:
                key_name = key_str

            key = getattr(self._Key, key_name, None)
            if key is None:
                # Carácter ordinario
                key = key_str if len(key_str) == 1 else None

            if key is None:
                return

            if press:
                self._keyboard.press(key)
            else:
                self._keyboard.release(key)
        except Exception as exc:
            logger.debug("Error con tecla '%s': %s", key_str, exc)


# ---------------------------------------------------------------------------
# Capturador (máquina controladora)
# ---------------------------------------------------------------------------

class InputCapture:
    """
    Captura ratón y teclado dentro de la ventana de vista remota y
    envía los eventos normalizados (coordenadas relativas 0-1) al peer.
    """

    def __init__(self):
        self._callback: Callable | None = None
        self._canvas_widget = None  # referencia al canvas de tkinter
        self._canvas_offset_x = 0
        self._canvas_offset_y = 0
        self._image_w = 1280
        self._image_h = 720

    def attach(
        self,
        canvas,
        callback: Callable[[dict], None],
        image_w: int,
        image_h: int,
        offset_x: int = 0,
        offset_y: int = 0,
    ) -> None:
        """
        Adjunta la captura al canvas de tkinter.
        Los eventos ya vienen en coordenadas del canvas, por lo que
        sólo hay que normalizar respecto al área de imagen.
        """
        self._callback = callback
        self._canvas_widget = canvas
        self._image_w = image_w
        self._image_h = image_h
        self._canvas_offset_x = offset_x
        self._canvas_offset_y = offset_y

    def update_image_info(self, w: int, h: int, ox: int, oy: int) -> None:
        self._image_w = w
        self._image_h = h
        self._canvas_offset_x = ox
        self._canvas_offset_y = oy

    # ------------------------------------------------------------------
    # Handlers invocados por el canvas de tkinter
    # ------------------------------------------------------------------

    def on_mouse_move(self, event) -> None:
        rx, ry = self._normalize(event.x, event.y)
        self._emit({"event_type": "mouse_move", "x": rx, "y": ry})

    def on_mouse_press(self, event, button: str) -> None:
        rx, ry = self._normalize(event.x, event.y)
        self._emit({"event_type": "mouse_click", "x": rx, "y": ry,
                    "button": button, "pressed": True})

    def on_mouse_release(self, event, button: str) -> None:
        rx, ry = self._normalize(event.x, event.y)
        self._emit({"event_type": "mouse_click", "x": rx, "y": ry,
                    "button": button, "pressed": False})

    def on_scroll(self, event) -> None:
        rx, ry = self._normalize(event.x, event.y)
        dy = getattr(event, "delta", 0) / 120
        self._emit({"event_type": "mouse_scroll", "x": rx, "y": ry,
                    "dx": 0, "dy": dy})

    def on_key_press(self, event) -> None:
        self._emit({"event_type": "key_press", "key": event.keysym})

    def on_key_release(self, event) -> None:
        self._emit({"event_type": "key_release", "key": event.keysym})

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize(self, cx: int, cy: int) -> tuple[float, float]:
        """Convierte coordenadas de canvas a relativas (0.0 - 1.0)."""
        rx = (cx - self._canvas_offset_x) / max(self._image_w, 1)
        ry = (cy - self._canvas_offset_y) / max(self._image_h, 1)
        return max(0.0, min(1.0, rx)), max(0.0, min(1.0, ry))

    def _emit(self, event: dict) -> None:
        if self._callback:
            try:
                self._callback(event)
            except Exception as exc:
                logger.debug("Error emitiendo evento: %s", exc)
