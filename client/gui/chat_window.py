"""
Ingar - Ventana de chat en tiempo real.
"""

import tkinter as tk
from datetime import datetime
from tkinter import scrolledtext
from typing import Callable


class ChatWindow:
    def __init__(
        self,
        parent: tk.Misc,
        on_send: Callable[[str], None],
        on_close: Callable,
    ):
        self._parent = parent
        self._on_send = on_send
        self._on_close_cb = on_close
        self._window: tk.Toplevel | None = None

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def show(self) -> None:
        if self._window:
            self.focus()
            return

        self._window = tk.Toplevel(self._parent)
        self._window.title("Ingar – Chat")
        self._window.geometry("400x500")
        self._window.minsize(300, 350)
        self._window.protocol("WM_DELETE_WINDOW", self._on_close)
        self._build()

    def close(self) -> None:
        if self._window:
            self._window.destroy()
            self._window = None

    def focus(self) -> None:
        if self._window:
            self._window.lift()
            self._window.focus_set()

    # ------------------------------------------------------------------
    # API pública
    # ------------------------------------------------------------------

    def receive_message(self, text: str) -> None:
        self._append("Remoto", text, is_me=False)
        if self._window:
            self._window.lift()

    # ------------------------------------------------------------------
    # Construcción de la UI
    # ------------------------------------------------------------------

    def _build(self) -> None:
        win = self._window

        # Cabecera azul
        header = tk.Frame(win, bg="#003580", height=44)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(
            header, text="Chat", font=("Segoe UI", 11, "bold"),
            fg="white", bg="#003580",
        ).pack(side=tk.LEFT, padx=15, pady=10)

        # Área de mensajes
        self._msg_area = scrolledtext.ScrolledText(
            win, wrap=tk.WORD, font=("Segoe UI", 10),
            bg="#f9f9f9", fg="#333333",
            state=tk.DISABLED, padx=10, pady=10,
        )
        self._msg_area.pack(fill=tk.BOTH, expand=True, padx=6, pady=(6, 0))

        self._msg_area.tag_configure("sender_me",   foreground="#003580", font=("Segoe UI", 10, "bold"))
        self._msg_area.tag_configure("sender_them", foreground="#b71c1c", font=("Segoe UI", 10, "bold"))
        self._msg_area.tag_configure("timestamp",   foreground="#999999", font=("Segoe UI", 8))
        self._msg_area.tag_configure("body",        foreground="#333333")

        # Barra de entrada
        input_bar = tk.Frame(win, bg="#f0f0f0")
        input_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=6)

        self._input_var = tk.StringVar()
        entry = tk.Entry(
            input_bar, textvariable=self._input_var,
            font=("Segoe UI", 10), relief=tk.SOLID, bd=1,
        )
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 6))
        entry.bind("<Return>", lambda _e: self._send())
        entry.focus_set()

        tk.Button(
            input_bar, text="Enviar",
            font=("Segoe UI", 10), fg="white", bg="#003580",
            bd=0, padx=12, pady=4, cursor="hand2",
            command=self._send,
        ).pack(side=tk.RIGHT)

    # ------------------------------------------------------------------
    # Handlers
    # ------------------------------------------------------------------

    def _send(self) -> None:
        text = self._input_var.get().strip()
        if not text:
            return
        self._on_send(text)
        self._append("Yo", text, is_me=True)
        self._input_var.set("")

    def _on_close(self) -> None:
        self._on_close_cb()
        self.close()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _append(self, sender: str, text: str, is_me: bool) -> None:
        if not self._window:
            return
        self._msg_area.configure(state=tk.NORMAL)
        ts = datetime.now().strftime("%H:%M")
        tag = "sender_me" if is_me else "sender_them"
        self._msg_area.insert(tk.END, f"{sender} ", tag)
        self._msg_area.insert(tk.END, f"[{ts}]\n", "timestamp")
        self._msg_area.insert(tk.END, f"{text}\n\n", "body")
        self._msg_area.see(tk.END)
        self._msg_area.configure(state=tk.DISABLED)
