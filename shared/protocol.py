"""
Ingar - Protocolo de mensajes compartido entre servidor y cliente.

Todos los mensajes se envían como JSON con un campo 'type'.
"""

import json


class MessageType:
    # Registro y autenticación
    REGISTER = "register"
    REGISTER_ACK = "register_ack"

    # Gestión de conexión entre peers
    CONNECT_REQUEST = "connect_request"
    CONNECT_ACCEPT = "connect_accept"
    CONNECT_REJECT = "connect_reject"
    DISCONNECT = "disconnect"

    # Sesión de escritorio remoto
    SCREEN_FRAME = "screen_frame"
    INPUT_EVENT = "input_event"

    # Chat
    CHAT_MESSAGE = "chat_message"

    # Transferencia de archivos
    FILE_START = "file_start"
    FILE_CHUNK = "file_chunk"
    FILE_END = "file_end"

    # Utilidades
    PING = "ping"
    PONG = "pong"
    ERROR = "error"

    # Eventos internos del cliente (no se envían por red)
    CONNECTION_ERROR = "connection_error"


def build(msg_type: str, **kwargs) -> str:
    """Construye un mensaje JSON listo para enviar."""
    return json.dumps({"type": msg_type, **kwargs})


def parse(raw: str) -> dict:
    """Parsea un mensaje JSON recibido."""
    return json.loads(raw)


def format_id(raw_id: str) -> str:
    """Formatea un ID de 9 dígitos como XXX XXX XXX."""
    digits = raw_id.replace(" ", "")
    if len(digits) == 9:
        return f"{digits[:3]} {digits[3:6]} {digits[6:]}"
    return raw_id
