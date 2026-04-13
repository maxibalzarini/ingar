"""
Ingar - Ventana de visualización y control del escritorio remoto.

Muestra los frames JPEG recibidos en un canvas de tkinter y
reenvía los eventos de ratón/teclado al peer cuando el modo de
captura está activado.
"""

import logging
import time
import tkinter as tk
from tkinter import ttk
from typing import Callable

from PIL import Image, ImageTk

from client.core.input_handler import InputCapture
from client.core.screen_capture import ScreenCapture

logger = logging.getLogger("ingar.remoteview")


class RemoteViewWindow:
    """Ventana de escritorio remoto."""

    def __init__(
        self,
        parent: tk.Misc,
        on_input_event: Callable[[dict], None],
        on_close: Callable,
        peer_id: str = "",
    ):
        self._parent = parent
        self._on_input_event = on_input_event
        self._on_close_cb = on_close
        self.peer_id = peer_id

        self._window: tk.Toplevel | None = None
        self._canvas: tk.Canvas | None = None
        self._photo: ImageTk.PhotoImage | None = None
        self._current_img: Image.Image | None = None

        # Posición de la imagen dentro del canvas
        self._img_x = 0
        self._img_y = 0
        self._img_w = 1280
        self._img_h = 720

        self._input_capture = InputCapture()
        self._capturing_input = False
        self._send_input_event = on_input_event  # guarda referencia limpia

        # Métricas de FPS
        self._frame_count = 0
        self._fps_tick = time.monotonic()

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def show(self) -> None:
        self._window = tk.Toplevel(self._parent)
        self._window.title(f"Ingar – Control Remoto: {self.peer_id}")
        self._window.geometry("1280x760")
        self._window.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()

    def close(self) -> None:
        if self._window:
            self._window.destroy()
            self._window = None

    def focus(self) -> None:
        if self._window:
            self._window.lift()

    # ------------------------------------------------------------------
    # Actualización de frame (llamado desde hilo de red)
    # ------------------------------------------------------------------

    def update_frame(self, frame_b64: str) -> None:
        if not self._window:
            return
        try:
            img = ScreenCapture.decode_frame(frame_b64)
            self._window.after(0, lambda: self._draw(img))

            # FPS
            self._frame_count += 1
            now = time.monotonic()
            if now - self._fps_tick >= 1.0:
                fps = self._frame_count
                self._frame_count = 0
                self._fps_tick = now
                if self._window:
                    self._window.after(0, lambda f=fps: self._lbl_fps.configure(text=f"{f} FPS"))
        except Exception as exc:
            logger.debug("Error actualizando frame: %s", exc)

    # ------------------------------------------------------------------
    # Construcción de UI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        win = self._window

        # ---- Barra de herramientas ----
        toolbar = tk.Frame(win, bg="#1a237e", height=44)
        toolbar.pack(fill=tk.X)
        toolbar.pack_propagate(False)

        tk.Label(
            toolbar, text=f"  Control Remoto — {self.peer_id}",
            font=("Segoe UI", 10, "bold"), fg="white", bg="#1a237e",
        ).pack(side=tk.LEFT, padx=8, pady=10)

        # Botón desconectar
        tk.Button(
            toolbar, text="Desconectar",
            font=("Segoe UI", 9), fg="white", bg="#c62828",
            bd=0, padx=12, pady=4, cursor="hand2",
            command=self._on_close,
        ).pack(side=tk.RIGHT, padx=10, pady=7)

        # Selector de calidad
        self._quality_var = tk.StringVar(value="Media")
        tk.Label(
            toolbar, text="Calidad:", font=("Segoe UI", 9),
            fg="white", bg="#1a237e",
        ).pack(side=tk.RIGHT, padx=(0, 4))
        ttk.Combobox(
            toolbar, textvariable=self._quality_var,
            values=["Baja", "Media", "Alta"],
            width=7, state="readonly",
        ).pack(side=tk.RIGHT, padx=(0, 8))

        # Toggle captura de entrada
        self._capture_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            toolbar,
            text="Capturar entrada",
            variable=self._capture_var,
            font=("Segoe UI", 9), fg="white", bg="#1a237e",
            selectcolor="#1a237e", activebackground="#1a237e",
            activeforeground="white",
            command=self._toggle_capture,
        ).pack(side=tk.LEFT, padx=16)

        # ---- Canvas ----
        self._canvas = tk.Canvas(win, bg="#0d0d1a", highlightthickness=0, cursor="crosshair")
        self._canvas.pack(fill=tk.BOTH, expand=True)

        # Texto de espera
        self._wait_text = self._canvas.create_text(
            640, 360,
            text="Esperando imagen del dispositivo remoto…",
            fill="#4455aa", font=("Segoe UI", 14),
            tags="wait",
        )

        # Bind de entrada
        self._canvas.bind("<Motion>",          self._input_capture.on_mouse_move)
        self._canvas.bind("<Button-1>",        lambda e: self._input_capture.on_mouse_press(e, "left"))
        self._canvas.bind("<ButtonRelease-1>", lambda e: self._input_capture.on_mouse_release(e, "left"))
        self._canvas.bind("<Button-3>",        lambda e: self._input_capture.on_mouse_press(e, "right"))
        self._canvas.bind("<ButtonRelease-3>", lambda e: self._input_capture.on_mouse_release(e, "right"))
        self._canvas.bind("<MouseWheel>",      self._input_capture.on_scroll)
        win.bind("<KeyPress>",   self._input_capture.on_key_press)
        win.bind("<KeyRelease>", self._input_capture.on_key_release)

        # ---- Barra de estado ----
        status_bar = tk.Frame(win, bg="#222233", height=22)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        status_bar.pack_propagate(False)

        tk.Label(
            status_bar, text="Conectado",
            font=("Segoe UI", 8), fg="#aaaacc", bg="#222233",
        ).pack(side=tk.LEFT, padx=10)

        self._lbl_fps = tk.Label(
            status_bar, text="",
            font=("Segoe UI", 8), fg="#aaaacc", bg="#222233",
        )
        self._lbl_fps.pack(side=tk.RIGHT, padx=10)

    # ------------------------------------------------------------------
    # Dibujado
    # ------------------------------------------------------------------

    def _draw(self, img: Image.Image) -> None:
        if not self._canvas:
            return

        cw = self._canvas.winfo_width()
        ch = self._canvas.winfo_height()
        if cw < 2 or ch < 2:
            return

        # Escalar manteniendo relación de aspecto
        iw, ih = img.size
        scale = min(cw / iw, ch / ih, 1.0)
        new_w, new_h = int(iw * scale), int(ih * scale)
        if scale < 0.999:
            img = img.resize((new_w, new_h), Image.LANCZOS)
        else:
            new_w, new_h = iw, ih

        # Centrar
        ox = (cw - new_w) // 2
        oy = (ch - new_h) // 2

        self._img_w, self._img_h = new_w, new_h
        self._img_x, self._img_y = ox, oy
        self._input_capture.update_image_info(new_w, new_h, ox, oy)

        self._photo = ImageTk.PhotoImage(img)
        self._canvas.delete("all")
        self._canvas.create_image(ox, oy, anchor=tk.NW, image=self._photo)

        self._current_img = img

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _toggle_capture(self) -> None:
        self._capturing_input = self._capture_var.get()
        cb = self._send_input_event if self._capturing_input else lambda _: None
        self._input_capture.attach(
            self._canvas,
            callback=cb,
            image_w=self._img_w,
            image_h=self._img_h,
            offset_x=self._img_x,
            offset_y=self._img_y,
        )

    def _on_close(self) -> None:
        self._on_close_cb()
