"""
Ingar - Gestor de conexión WebSocket del cliente.

Ejecuta el loop de asyncio en un hilo de fondo para no bloquear la GUI.
Expone una API sincrónica sencilla para enviar mensajes y registrar callbacks.
"""

import asyncio
import json
import logging
import threading
from typing import Callable

import websockets

logger = logging.getLogger("ingar.connection")

DEFAULT_SERVER = "ws://localhost:8765"


class ConnectionManager:
    def __init__(self, server_url: str = DEFAULT_SERVER):
        self.server_url = server_url

        # Estado del cliente registrado
        self.client_id: str | None = None
        self.formatted_id: str | None = None
        self.password: str | None = None
        self.peer_id: str | None = None

        # Estado de conexión
        self.connected: bool = False

        # Internos
        self._ws = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._callbacks: dict[str, Callable] = {}

    # ------------------------------------------------------------------
    # Registro de callbacks
    # ------------------------------------------------------------------

    def on(self, message_type: str, callback: Callable) -> None:
        """Registra un callback para un tipo de mensaje."""
        self._callbacks[message_type] = callback

    def _dispatch(self, data: dict) -> None:
        msg_type = data.get("type", "")
        cb = self._callbacks.get(msg_type)
        if cb:
            try:
                cb(data)
            except Exception as exc:
                logger.error("Error en callback '%s': %s", msg_type, exc)

    # ------------------------------------------------------------------
    # Ciclo de vida
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Inicia la conexión en un hilo de fondo."""
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._run, daemon=True, name="ingar-ws")
        self._thread.start()

    def _run(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._connect())

    async def _connect(self) -> None:
        try:
            async with websockets.connect(self.server_url) as ws:
                self._ws = ws
                self.connected = True
                logger.info("Conectado al servidor: %s", self.server_url)
                async for raw in ws:
                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        continue

                    # Cachear datos de registro
                    if data.get("type") == "register_ack":
                        self.client_id = data.get("id")
                        self.formatted_id = data.get("formatted_id")
                        self.password = data.get("password")

                    self._dispatch(data)

        except (websockets.exceptions.ConnectionClosed,
                OSError, ConnectionRefusedError) as exc:
            logger.warning("Conexión WebSocket perdida: %s", exc)
        finally:
            self.connected = False
            self._ws = None
            self._dispatch({"type": "connection_error", "message": str(exc if 'exc' in dir() else "Desconectado")})

    # ------------------------------------------------------------------
    # Envío de mensajes (API sincrónica)
    # ------------------------------------------------------------------

    def send(self, data: dict) -> None:
        """Envía un mensaje JSON al servidor de forma no bloqueante."""
        if self._ws and self.connected and self._loop:
            asyncio.run_coroutine_threadsafe(
                self._send_raw(json.dumps(data)),
                self._loop,
            )

    async def _send_raw(self, raw: str) -> None:
        if self._ws:
            try:
                await self._ws.send(raw)
            except websockets.exceptions.ConnectionClosed:
                pass

    # ------------------------------------------------------------------
    # Métodos de alto nivel
    # ------------------------------------------------------------------

    def request_connect(self, target_id: str, password: str) -> None:
        self.send({
            "type": "connect_request",
            "target_id": target_id.replace(" ", ""),
            "password": password,
        })

    def accept_connection(self, from_id: str) -> None:
        self.peer_id = from_id
        self.send({"type": "connect_accept", "target_id": from_id})

    def reject_connection(self, from_id: str) -> None:
        self.send({"type": "connect_reject", "target_id": from_id})

    def send_screen_frame(self, frame_b64: str) -> None:
        self.send({"type": "screen_frame", "data": frame_b64})

    def send_input_event(self, event: dict) -> None:
        self.send({"type": "input_event", **event})

    def send_chat(self, message: str) -> None:
        self.send({"type": "chat_message", "message": message})

    def disconnect_peer(self) -> None:
        self.send({"type": "disconnect"})
        self.peer_id = None

    def close(self) -> None:
        if self._ws and self._loop:
            asyncio.run_coroutine_threadsafe(self._ws.close(), self._loop)
