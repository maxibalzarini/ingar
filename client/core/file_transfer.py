"""
Ingar - Transferencia de archivos sobre la sesión WebSocket.

Protocolo:
  file_start  { filename, size }
  file_chunk  { filename, index, data: base64 }
  file_end    { filename }
"""

import base64
import logging
import os
import threading
from typing import Callable

logger = logging.getLogger("ingar.filetransfer")

CHUNK_SIZE = 65_536  # 64 KB por fragmento


class FileTransfer:
    def __init__(self, send_fn: Callable[[dict], None]):
        """
        send_fn: función que acepta un dict y lo envía por WebSocket
                 (normalmente ConnectionManager.send).
        """
        self._send = send_fn

        # Estado de recepción activa: filename → { data, size, received }
        self._receiving: dict[str, dict] = {}

        # Callbacks opcionales
        self.on_receive_complete: Callable[[str, bytes], None] | None = None
        self.on_progress: Callable[[str, int, int], None] | None = None

    # ------------------------------------------------------------------
    # Envío
    # ------------------------------------------------------------------

    def send_file(self, filepath: str) -> None:
        """Envía un archivo al peer en un hilo de fondo."""
        if not os.path.isfile(filepath):
            logger.error("Archivo no encontrado: %s", filepath)
            return
        threading.Thread(
            target=self._send_worker,
            args=(filepath,),
            daemon=True,
            name="ingar-filesend",
        ).start()

    def _send_worker(self, filepath: str) -> None:
        filename = os.path.basename(filepath)
        filesize = os.path.getsize(filepath)

        logger.info("Enviando archivo '%s' (%d bytes)", filename, filesize)
        self._send({"type": "file_start", "filename": filename, "size": filesize})

        sent = 0
        with open(filepath, "rb") as fh:
            index = 0
            while True:
                chunk = fh.read(CHUNK_SIZE)
                if not chunk:
                    break
                self._send({
                    "type": "file_chunk",
                    "filename": filename,
                    "index": index,
                    "data": base64.b64encode(chunk).decode(),
                })
                sent += len(chunk)
                index += 1
                if self.on_progress:
                    self.on_progress(filename, sent, filesize)

        self._send({"type": "file_end", "filename": filename})
        logger.info("Archivo '%s' enviado", filename)

    # ------------------------------------------------------------------
    # Recepción
    # ------------------------------------------------------------------

    def handle_message(self, data: dict) -> None:
        """Procesa un mensaje entrante de transferencia de archivos."""
        msg_type = data.get("type")

        if msg_type == "file_start":
            filename = data["filename"]
            self._receiving[filename] = {
                "data": bytearray(),
                "size": data.get("size", 0),
                "received": 0,
            }
            logger.info("Recibiendo archivo '%s' (%d bytes)", filename, data.get("size", 0))

        elif msg_type == "file_chunk":
            filename = data.get("filename", "")
            if filename not in self._receiving:
                return
            chunk = base64.b64decode(data["data"])
            rec = self._receiving[filename]
            rec["data"].extend(chunk)
            rec["received"] += len(chunk)
            if self.on_progress:
                self.on_progress(filename, rec["received"], rec["size"])

        elif msg_type == "file_end":
            filename = data.get("filename", "")
            if filename not in self._receiving:
                return
            file_bytes = bytes(self._receiving.pop(filename)["data"])
            logger.info("Archivo '%s' recibido (%d bytes)", filename, len(file_bytes))
            if self.on_receive_complete:
                self.on_receive_complete(filename, file_bytes)

    # ------------------------------------------------------------------
    # Guardar archivo recibido
    # ------------------------------------------------------------------

    @staticmethod
    def save_file(filename: str, data: bytes, directory: str = ".") -> str:
        """Guarda los datos en el directorio destino sin sobreescribir."""
        os.makedirs(directory, exist_ok=True)
        dest = os.path.join(directory, filename)
        base, ext = os.path.splitext(dest)
        counter = 1
        while os.path.exists(dest):
            dest = f"{base}_{counter}{ext}"
            counter += 1
        with open(dest, "wb") as fh:
            fh.write(data)
        return dest
