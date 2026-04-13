"""
Ingar - Ventana principal de la aplicación.

Diseño visual inspirado en TeamViewer:
  - Panel izquierdo: "Permitir el control remoto" (tu ID y contraseña)
  - Panel derecho:  "Dispositivo de control remoto" (conectar a un peer)
  - Barra de estado inferior con indicador de conexión
"""

import logging
import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Optional

from client.core.connection import ConnectionManager
from client.core.file_transfer import FileTransfer
from client.core.input_handler import InputInjector
from client.core.screen_capture import ScreenCapture
from client.gui.chat_window import ChatWindow
from client.gui.remote_view import RemoteViewWindow
from shared.protocol import format_id

logger = logging.getLogger("ingar.mainwindow")

# ---------------------------------------------------------------------------
# Colores
# ---------------------------------------------------------------------------
C_BLUE       = "#003580"
C_BLUE_DARK  = "#1a237e"
C_BLUE_LIGHT = "#e8f0fe"
C_GREEN      = "#43a047"
C_RED        = "#c62828"
C_ORANGE     = "#e65100"
C_GRAY       = "#9e9e9e"
C_BG         = "#f5f5f5"
C_WHITE      = "#ffffff"
C_TEXT       = "#333333"
C_SUBTEXT    = "#666666"


class MainWindow:
    def __init__(self, server_url: str = "ws://localhost:8765"):
        self._root = tk.Tk()
        self._root.title("Ingar – Acceso Remoto")
        self._root.geometry("820x520")
        self._root.minsize(700, 460)
        self._root.configure(bg=C_BG)

        # Componentes core
        self._conn = ConnectionManager(server_url)
        self._capture = ScreenCapture()
        self._file_transfer: Optional[FileTransfer] = None
        self._injector: Optional[InputInjector] = None

        # Sub-ventanas
        self._remote_view: Optional[RemoteViewWindow] = None
        self._chat: Optional[ChatWindow] = None

        # Estado de sesión
        self._peer_id: Optional[str] = None
        self._is_controlling: bool = False   # somos el controlador
        self._is_controlled: bool = False    # nos están controlando

        self._setup_callbacks()
        self._build_ui()

        # Conectar al servidor en hilo de fondo
        self._conn.start()
        self._root.after(500, self._poll_registration)

        self._root.protocol("WM_DELETE_WINDOW", self._on_app_close)

    # ------------------------------------------------------------------
    # Callbacks de red
    # ------------------------------------------------------------------

    def _setup_callbacks(self) -> None:
        c = self._conn
        c.on("register_ack",     self._cb_registered)
        c.on("connect_request",  self._cb_incoming)
        c.on("connect_accept",   self._cb_accepted)
        c.on("connect_reject",   self._cb_rejected)
        c.on("screen_frame",     self._cb_frame)
        c.on("input_event",      self._cb_input)
        c.on("chat_message",     self._cb_chat)
        c.on("file_start",       self._cb_file)
        c.on("file_chunk",       self._cb_file)
        c.on("file_end",         self._cb_file)
        c.on("disconnect",       self._cb_disconnect)
        c.on("error",            self._cb_error)
        c.on("connection_error", self._cb_conn_error)

    # ------------------------------------------------------------------
    # Construcción de la UI
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        root = self._root

        # ======================== CABECERA ========================
        header = tk.Frame(root, bg=C_BLUE, height=58)
        header.pack(fill=tk.X)
        header.pack_propagate(False)

        tk.Label(
            header, text="  Ingar",
            font=("Segoe UI", 21, "bold"), fg=C_WHITE, bg=C_BLUE,
        ).pack(side=tk.LEFT, padx=14)

        self._lbl_header_status = tk.Label(
            header, text="Conectando…",
            font=("Segoe UI", 9), fg="#aaccff", bg=C_BLUE,
        )
        self._lbl_header_status.pack(side=tk.RIGHT, padx=14)

        # ======================== BARRA DE LICENCIA ========================
        lic_bar = tk.Frame(root, bg=C_BLUE_LIGHT, height=28)
        lic_bar.pack(fill=tk.X)
        lic_bar.pack_propagate(False)
        tk.Label(
            lic_bar,
            text="Licencia gratuita (solo para uso no comercial)",
            font=("Segoe UI", 9), fg=C_BLUE, bg=C_BLUE_LIGHT,
        ).pack(side=tk.LEFT, padx=14, pady=5)

        # ======================== CONTENIDO PRINCIPAL ========================
        content = tk.Frame(root, bg=C_BG)
        content.pack(fill=tk.BOTH, expand=True, padx=18, pady=10)

        # ---- Panel izquierdo ----
        self._build_left_panel(content)

        # ---- Panel derecho ----
        self._build_right_panel(content)

        # ======================== BARRA DE ESTADO INFERIOR ========================
        sbar = tk.Frame(root, bg="#e0e0e0", height=26)
        sbar.pack(fill=tk.X, side=tk.BOTTOM)
        sbar.pack_propagate(False)

        self._dot = tk.Canvas(sbar, width=12, height=12, bg="#e0e0e0", highlightthickness=0)
        self._dot.pack(side=tk.LEFT, padx=(10, 4), pady=7)
        self._dot_oval = self._dot.create_oval(1, 1, 11, 11, fill=C_GRAY, outline="")

        self._lbl_status = tk.Label(
            sbar, text="Sin conexión al servidor",
            font=("Segoe UI", 9), fg="#555555", bg="#e0e0e0",
        )
        self._lbl_status.pack(side=tk.LEFT)

        # Barra de progreso (transferencia de archivos)
        self._progress_var = tk.DoubleVar()
        self._progress_bar = ttk.Progressbar(sbar, variable=self._progress_var, maximum=100, length=160)

    def _build_left_panel(self, parent: tk.Frame) -> None:
        panel = tk.LabelFrame(
            parent, text="Permitir el control remoto",
            font=("Segoe UI", 10, "bold"), bg=C_BG, fg=C_TEXT,
            padx=18, pady=14,
        )
        panel.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 10))

        # Tu ID
        tk.Label(panel, text="Tu ID", font=("Segoe UI", 9),
                 fg=C_SUBTEXT, bg=C_BG).pack(anchor=tk.W)

        id_box = tk.Frame(panel, bg=C_WHITE, relief=tk.SOLID, bd=1)
        id_box.pack(fill=tk.X, pady=(2, 10))

        self._lbl_my_id = tk.Label(
            id_box, text="— — —",
            font=("Segoe UI", 22, "bold"), fg=C_BLUE, bg=C_WHITE, pady=8,
        )
        self._lbl_my_id.pack(side=tk.LEFT, padx=12)

        tk.Button(
            id_box, text="⎘", font=("Segoe UI", 13),
            fg=C_SUBTEXT, bg=C_WHITE, bd=0, cursor="hand2",
            command=self._copy_id,
        ).pack(side=tk.RIGHT, padx=6)

        # Contraseña
        tk.Label(panel, text="Contraseña", font=("Segoe UI", 9),
                 fg=C_SUBTEXT, bg=C_BG).pack(anchor=tk.W)

        pw_box = tk.Frame(panel, bg=C_WHITE, relief=tk.SOLID, bd=1)
        pw_box.pack(fill=tk.X, pady=(2, 12))

        self._lbl_my_pw = tk.Label(
            pw_box, text="—",
            font=("Segoe UI", 17), fg=C_BLUE, bg=C_WHITE, pady=6,
        )
        self._lbl_my_pw.pack(side=tk.LEFT, padx=12)

        tk.Button(
            pw_box, text="⎘", font=("Segoe UI", 13),
            fg=C_SUBTEXT, bg=C_WHITE, bd=0, cursor="hand2",
            command=self._copy_pw,
        ).pack(side=tk.RIGHT, padx=4)
        tk.Button(
            pw_box, text="↻", font=("Segoe UI", 13),
            fg=C_SUBTEXT, bg=C_WHITE, bd=0, cursor="hand2",
            command=self._refresh_credentials,
        ).pack(side=tk.RIGHT, padx=2)

        # Panel de sesión activa (oculto inicialmente)
        self._session_frame = tk.Frame(panel, bg="#e8f5e9", relief=tk.SOLID, bd=1)

        self._lbl_session = tk.Label(
            self._session_frame, text="",
            font=("Segoe UI", 9), fg="#2e7d32", bg="#e8f5e9",
            wraplength=260, justify=tk.LEFT,
        )
        self._lbl_session.pack(anchor=tk.W, padx=10, pady=(6, 4))

        btn_row = tk.Frame(self._session_frame, bg="#e8f5e9")
        btn_row.pack(fill=tk.X, padx=8, pady=(0, 8))

        self._btn_chat = self._make_btn(btn_row, "Chat", C_BLUE, self._open_chat, side=tk.LEFT)
        self._btn_file = self._make_btn(btn_row, "Enviar archivo", C_BLUE, self._send_file, side=tk.LEFT)
        self._btn_end  = self._make_btn(btn_row, "Terminar sesión", C_RED, self._end_session, side=tk.RIGHT)

    def _build_right_panel(self, parent: tk.Frame) -> None:
        panel = tk.LabelFrame(
            parent, text="Dispositivo de control remoto",
            font=("Segoe UI", 10, "bold"), bg=C_BG, fg=C_TEXT,
            padx=18, pady=14,
        )
        panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Modo de conexión
        self._mode_var = tk.StringVar(value="Control remoto")
        mode_btn = ttk.Menubutton(panel, textvariable=self._mode_var, direction="below")
        mode_menu = tk.Menu(mode_btn, tearoff=False)
        for mode in ("Control remoto", "Solo visualización", "Transferencia de archivos"):
            mode_menu.add_radiobutton(label=mode, variable=self._mode_var, value=mode)
        mode_btn["menu"] = mode_menu
        mode_btn.pack(anchor=tk.W, pady=(0, 12))

        # ID remoto
        tk.Label(panel, text="ID, dirección IP o nombre de host",
                 font=("Segoe UI", 9), fg=C_SUBTEXT, bg=C_BG).pack(anchor=tk.W)

        rid_box = tk.Frame(panel, bg=C_WHITE, relief=tk.SOLID, bd=1)
        rid_box.pack(fill=tk.X, pady=(2, 6))
        self._var_remote_id = tk.StringVar()
        self._entry_rid = tk.Entry(
            rid_box, textvariable=self._var_remote_id,
            font=("Segoe UI", 12), bd=0, bg=C_WHITE, fg=C_TEXT,
        )
        self._entry_rid.pack(fill=tk.X, padx=10, pady=8)
        self._entry_rid.bind("<Return>", lambda _e: self._connect())

        # Contraseña remota
        tk.Label(panel, text="Contraseña",
                 font=("Segoe UI", 9), fg=C_SUBTEXT, bg=C_BG).pack(anchor=tk.W)

        rpw_box = tk.Frame(panel, bg=C_WHITE, relief=tk.SOLID, bd=1)
        rpw_box.pack(fill=tk.X, pady=(2, 16))
        self._var_remote_pw = tk.StringVar()
        self._entry_rpw = tk.Entry(
            rpw_box, textvariable=self._var_remote_pw,
            font=("Segoe UI", 12), bd=0, bg=C_WHITE, fg=C_TEXT, show="*",
        )
        self._entry_rpw.pack(fill=tk.X, padx=10, pady=8)
        self._entry_rpw.bind("<Return>", lambda _e: self._connect())

        # Botón conectar
        self._btn_connect = tk.Button(
            panel, text="Conectar",
            font=("Segoe UI", 11, "bold"), fg=C_WHITE, bg=C_BLUE,
            bd=0, padx=20, pady=8, cursor="hand2",
            state=tk.DISABLED,
            command=self._connect,
        )
        self._btn_connect.pack(fill=tk.X)

    @staticmethod
    def _make_btn(parent, text, color, cmd, side=tk.LEFT) -> tk.Button:
        btn = tk.Button(
            parent, text=text,
            font=("Segoe UI", 9), fg=C_WHITE, bg=color,
            bd=0, padx=10, pady=3, cursor="hand2",
            command=cmd,
        )
        btn.pack(side=side, padx=3)
        return btn

    # ------------------------------------------------------------------
    # Polling de registro
    # ------------------------------------------------------------------

    def _poll_registration(self) -> None:
        if self._conn.formatted_id:
            self._update_credentials(
                self._conn.formatted_id,
                self._conn.password or "",
            )
        else:
            self._root.after(400, self._poll_registration)

    def _update_credentials(self, formatted_id: str, password: str) -> None:
        parts = formatted_id.replace(" ", "")
        display = f"{parts[:3]} {parts[3:6]} {parts[6:]}" if len(parts) == 9 else formatted_id
        self._lbl_my_id.configure(text=display)
        self._lbl_my_pw.configure(text=password)
        self._btn_connect.configure(state=tk.NORMAL)
        self._set_status("Listo para conectar (conexión segura)", "green")

    # ------------------------------------------------------------------
    # Callbacks de red (se llaman desde el hilo WebSocket)
    # ------------------------------------------------------------------

    def _cb_registered(self, data: dict) -> None:
        fid = data.get("formatted_id", "")
        pw  = data.get("password", "")
        self._root.after(0, lambda: self._update_credentials(fid, pw))

    def _cb_incoming(self, data: dict) -> None:
        from_id = data.get("from_id", "")
        self._root.after(0, lambda: self._show_incoming(from_id))

    def _cb_accepted(self, data: dict) -> None:
        from_id = data.get("from_id", "")
        self._peer_id = from_id
        self._conn.peer_id = from_id
        self._is_controlling = True
        self._root.after(0, lambda: self._open_remote_view(from_id))

    def _cb_rejected(self, _data: dict) -> None:
        self._root.after(0, lambda: messagebox.showinfo(
            "Conexión rechazada",
            "El dispositivo remoto rechazó la conexión.",
            parent=self._root,
        ))
        self._root.after(0, self._reset_connect_btn)

    def _cb_frame(self, data: dict) -> None:
        if self._remote_view:
            self._remote_view.update_frame(data.get("data", ""))

    def _cb_input(self, data: dict) -> None:
        if self._is_controlled and self._injector:
            self._injector.handle_event(data)

    def _cb_chat(self, data: dict) -> None:
        msg = data.get("message", "")
        if self._chat:
            self._root.after(0, lambda: self._chat.receive_message(msg))
        else:
            self._root.after(0, lambda: messagebox.showinfo(
                "Mensaje entrante",
                f"Mensaje del par:\n\n{msg}",
                parent=self._root,
            ))

    def _cb_file(self, data: dict) -> None:
        if self._file_transfer:
            self._file_transfer.handle_message(data)

    def _cb_disconnect(self, _data: dict) -> None:
        self._root.after(0, lambda: messagebox.showinfo(
            "Sesión terminada",
            "El dispositivo remoto cerró la sesión.",
            parent=self._root,
        ))
        self._root.after(0, self._cleanup_session)

    def _cb_error(self, data: dict) -> None:
        msg = data.get("message", "Error desconocido")
        self._root.after(0, lambda: messagebox.showerror("Error", msg, parent=self._root))
        self._root.after(0, self._reset_connect_btn)

    def _cb_conn_error(self, data: dict) -> None:
        msg = data.get("message", "")
        self._root.after(0, lambda: self._set_status(f"Sin conexión al servidor: {msg}", "red"))

    # ------------------------------------------------------------------
    # Acciones de UI
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        rid = self._var_remote_id.get().strip()
        rpw = self._var_remote_pw.get().strip()

        if not rid:
            messagebox.showwarning("Advertencia", "Ingresa el ID del dispositivo remoto.", parent=self._root)
            return
        if not rpw:
            messagebox.showwarning("Advertencia", "Ingresa la contraseña del dispositivo remoto.", parent=self._root)
            return

        self._btn_connect.configure(text="Conectando…", state=tk.DISABLED)
        self._set_status("Estableciendo conexión…", "orange")
        self._conn.request_connect(rid, rpw)

        # Reactivar si no hay respuesta en 12 s
        self._root.after(12_000, self._reset_connect_btn)

    def _reset_connect_btn(self) -> None:
        if not self._peer_id:
            self._btn_connect.configure(text="Conectar", state=tk.NORMAL)
            self._set_status("Listo para conectar", "green")

    def _show_incoming(self, from_id: str) -> None:
        display = format_id(from_id)
        allow = messagebox.askyesno(
            "Solicitud de conexión entrante",
            f"El dispositivo {display} quiere controlar este equipo.\n\n¿Permitir acceso?",
            parent=self._root,
        )
        if allow:
            self._conn.accept_connection(from_id)
            self._peer_id = from_id
            self._is_controlled = True
            self._start_being_controlled()
            self._show_session_banner(f"Sesión activa — {display}")
            self._set_status(f"Controlado por {display}", "green")
        else:
            self._conn.reject_connection(from_id)

    def _start_being_controlled(self) -> None:
        w, h = ScreenCapture.get_screen_size()
        self._injector = InputInjector(w, h)
        self._capture.start(self._conn.send_screen_frame)
        self._setup_file_transfer()

    def _open_remote_view(self, from_id: str) -> None:
        display = format_id(from_id)
        self._show_session_banner(f"Conectado a {display}")
        self._set_status(f"Sesión activa con {display}", "green")

        self._remote_view = RemoteViewWindow(
            self._root,
            on_input_event=self._conn.send_input_event,
            on_close=self._end_session,
            peer_id=display,
        )
        self._remote_view.show()
        self._setup_file_transfer()

    def _show_session_banner(self, text: str) -> None:
        self._lbl_session.configure(text=text)
        self._session_frame.pack(fill=tk.X, pady=4)
        self._btn_connect.configure(text="Sesión activa", state=tk.DISABLED)

    def _setup_file_transfer(self) -> None:
        self._file_transfer = FileTransfer(self._conn.send)
        self._file_transfer.on_receive_complete = self._on_file_received
        self._file_transfer.on_progress = self._on_file_progress

    def _end_session(self) -> None:
        if self._peer_id:
            self._conn.disconnect_peer()
        self._cleanup_session()

    def _cleanup_session(self) -> None:
        self._peer_id = None
        self._is_controlling = False
        self._is_controlled = False

        self._capture.stop()

        if self._remote_view:
            self._remote_view.close()
            self._remote_view = None

        if self._chat:
            self._chat.close()
            self._chat = None

        self._file_transfer = None
        self._injector = None

        self._session_frame.pack_forget()
        self._btn_connect.configure(text="Conectar", state=tk.NORMAL)
        self._set_status("Listo para conectar", "green")
        self._progress_bar.pack_forget()

    def _open_chat(self) -> None:
        if not self._chat:
            self._chat = ChatWindow(
                self._root,
                on_send=self._conn.send_chat,
                on_close=self._on_chat_closed,
            )
        self._chat.show()

    def _on_chat_closed(self) -> None:
        self._chat = None

    def _send_file(self) -> None:
        if not self._file_transfer:
            messagebox.showwarning("Sin sesión", "No hay sesión activa.", parent=self._root)
            return
        path = filedialog.askopenfilename(parent=self._root, title="Seleccionar archivo")
        if path:
            self._file_transfer.send_file(path)

    def _on_file_received(self, filename: str, data: bytes) -> None:
        save_dir = os.path.expanduser("~/Downloads")
        if not os.path.isdir(save_dir):
            save_dir = os.path.expanduser("~")
        saved = FileTransfer.save_file(filename, data, save_dir)
        self._root.after(0, lambda: messagebox.showinfo(
            "Archivo recibido",
            f"Archivo guardado en:\n{saved}",
            parent=self._root,
        ))

    def _on_file_progress(self, filename: str, received: int, total: int) -> None:
        if total > 0:
            pct = (received / total) * 100
            self._root.after(0, lambda p=pct: self._update_progress(p))

    def _update_progress(self, pct: float) -> None:
        self._progress_var.set(pct)
        if not self._progress_bar.winfo_ismapped():
            self._progress_bar.pack(side=tk.RIGHT, padx=10, pady=4)
        if pct >= 100:
            self._root.after(2000, self._progress_bar.pack_forget)

    # ------------------------------------------------------------------
    # Helpers de clipboard
    # ------------------------------------------------------------------

    def _copy_id(self) -> None:
        raw = self._lbl_my_id.cget("text").replace(" ", "")
        self._root.clipboard_clear()
        self._root.clipboard_append(raw)

    def _copy_pw(self) -> None:
        pw = self._lbl_my_pw.cget("text")
        self._root.clipboard_clear()
        self._root.clipboard_append(pw)

    def _refresh_credentials(self) -> None:
        # En una implementación completa se solicitaría al servidor
        # una nueva contraseña. Por ahora se muestra un aviso.
        messagebox.showinfo(
            "Actualizar contraseña",
            "Reinicia la aplicación para obtener una nueva contraseña.",
            parent=self._root,
        )

    # ------------------------------------------------------------------
    # Estado
    # ------------------------------------------------------------------

    def _set_status(self, text: str, level: str = "gray") -> None:
        colors = {"green": C_GREEN, "red": C_RED, "orange": C_ORANGE, "gray": C_GRAY}
        color = colors.get(level, C_GRAY)
        self._dot.itemconfig(self._dot_oval, fill=color)
        self._lbl_status.configure(text=text)
        self._lbl_header_status.configure(text=text)

    # ------------------------------------------------------------------
    # Cierre de la aplicación
    # ------------------------------------------------------------------

    def _on_app_close(self) -> None:
        if self._peer_id:
            self._conn.disconnect_peer()
        self._capture.stop()
        self._conn.close()
        self._root.destroy()

    # ------------------------------------------------------------------
    # Ejecutar
    # ------------------------------------------------------------------

    def run(self) -> None:
        self._root.mainloop()
