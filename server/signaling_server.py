"""
Ingar - Servidor de señalización WebSocket.

Responsabilidades:
  - Asignar un ID único de 9 dígitos a cada cliente que se conecta.
  - Generar y almacenar (hasheada) la contraseña de cada cliente.
  - Autenticar solicitudes de conexión entre peers.
  - Retransmitir mensajes de sesión entre peers emparejados.
"""

import asyncio
import hashlib
import json
import logging
import random
import string

import websockets
from websockets.server import WebSocketServerProtocol

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("ingar.server")

# ---------------------------------------------------------------------------
# Servidor
# ---------------------------------------------------------------------------

RELAY_TYPES = {
    "screen_frame",
    "input_event",
    "chat_message",
    "file_start",
    "file_chunk",
    "file_end",
}


class IngarServer:
    def __init__(self):
        # client_id -> WebSocket
        self._clients: dict[str, WebSocketServerProtocol] = {}
        # client_id -> hashed password
        self._passwords: dict[str, str] = {}
        # client_id -> peer_id  (sesión activa)
        self._sessions: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _new_id(self) -> tuple[str, str]:
        """Genera un ID de 9 dígitos único y su versión formateada."""
        for _ in range(1000):
            raw = str(random.randint(100_000_000, 999_999_999))
            if raw not in self._clients:
                formatted = f"{raw[:3]} {raw[3:6]} {raw[6:]}"
                return raw, formatted
        raise RuntimeError("No se pudo generar un ID único")

    @staticmethod
    def _new_password(length: int = 8) -> str:
        alphabet = string.ascii_lowercase + string.digits
        return "".join(random.choices(alphabet, k=length))

    @staticmethod
    def _hash(value: str) -> str:
        return hashlib.sha256(value.encode()).hexdigest()

    async def _send(self, ws: WebSocketServerProtocol, payload: dict) -> None:
        try:
            await ws.send(json.dumps(payload))
        except websockets.exceptions.ConnectionClosed:
            pass

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------

    async def _register(self, ws: WebSocketServerProtocol) -> str:
        client_id, formatted_id = self._new_id()
        password = self._new_password()

        self._clients[client_id] = ws
        self._passwords[client_id] = self._hash(password)

        await self._send(ws, {
            "type": "register_ack",
            "id": client_id,
            "formatted_id": formatted_id,
            "password": password,
        })

        logger.info("Registrado: %s", formatted_id)
        return client_id

    # ------------------------------------------------------------------
    # Enrutamiento de mensajes
    # ------------------------------------------------------------------

    async def _handle(
        self,
        ws: WebSocketServerProtocol,
        client_id: str,
        raw: str,
    ) -> None:
        try:
            data: dict = json.loads(raw)
        except json.JSONDecodeError:
            return

        msg_type = data.get("type")

        # ---- solicitud de conexión ----
        if msg_type == "connect_request":
            target_id = data.get("target_id", "").replace(" ", "")
            password = data.get("password", "")

            if target_id not in self._clients:
                await self._send(ws, {"type": "error", "message": "ID no encontrado"})
                return

            if self._hash(password) != self._passwords.get(target_id, ""):
                await self._send(ws, {"type": "error", "message": "Contraseña incorrecta"})
                return

            if target_id in self._sessions:
                await self._send(ws, {"type": "error", "message": "El dispositivo ya está en sesión"})
                return

            await self._send(self._clients[target_id], {
                "type": "connect_request",
                "from_id": client_id,
            })

        # ---- aceptar conexión ----
        elif msg_type == "connect_accept":
            target_id = data.get("target_id", "")
            if target_id not in self._clients:
                return

            self._sessions[client_id] = target_id
            self._sessions[target_id] = client_id

            await self._send(self._clients[target_id], {
                "type": "connect_accept",
                "from_id": client_id,
            })
            logger.info("Sesión iniciada: %s <-> %s", client_id, target_id)

        # ---- rechazar conexión ----
        elif msg_type == "connect_reject":
            target_id = data.get("target_id", "")
            if target_id in self._clients:
                await self._send(self._clients[target_id], {
                    "type": "connect_reject",
                    "from_id": client_id,
                })

        # ---- mensajes de sesión (relay directo) ----
        elif msg_type in RELAY_TYPES:
            peer_id = self._sessions.get(client_id)
            if peer_id and peer_id in self._clients:
                try:
                    await self._clients[peer_id].send(raw)
                except websockets.exceptions.ConnectionClosed:
                    pass

        # ---- desconexión ----
        elif msg_type == "disconnect":
            await self._close_session(client_id)

        # ---- ping / pong ----
        elif msg_type == "ping":
            await self._send(ws, {"type": "pong"})

    # ------------------------------------------------------------------
    # Sesión
    # ------------------------------------------------------------------

    async def _close_session(self, client_id: str) -> None:
        peer_id = self._sessions.pop(client_id, None)
        if peer_id:
            self._sessions.pop(peer_id, None)
            if peer_id in self._clients:
                await self._send(self._clients[peer_id], {
                    "type": "disconnect",
                    "from_id": client_id,
                })
            logger.info("Sesión cerrada: %s <-> %s", client_id, peer_id)

    # ------------------------------------------------------------------
    # Ciclo de vida de la conexión WebSocket
    # ------------------------------------------------------------------

    async def handler(self, ws: WebSocketServerProtocol) -> None:
        client_id = await self._register(ws)
        try:
            async for message in ws:
                await self._handle(ws, client_id, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            await self._close_session(client_id)
            self._clients.pop(client_id, None)
            self._passwords.pop(client_id, None)
            logger.info("Desconectado: %s", client_id)


# ---------------------------------------------------------------------------
# Puntos de entrada
# ---------------------------------------------------------------------------

async def main(host: str = "0.0.0.0", port: int = 8765) -> None:
    server = IngarServer()
    logger.info("Ingar Server escuchando en ws://%s:%d", host, port)
    async with websockets.serve(server.handler, host, port):
        await asyncio.Future()  # ejecutar indefinidamente


def main_sync() -> None:
    """Punto de entrada sincrónico para el script de consola."""
    asyncio.run(main())


if __name__ == "__main__":
    main_sync()
