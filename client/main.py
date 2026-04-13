"""
Ingar – Punto de entrada del cliente.

Uso:
    python -m client.main
    python client/main.py [--server ws://host:port]
"""

import argparse
import os
import sys

# Asegura que la raíz del proyecto esté en sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client.gui.main_window import MainWindow


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingar – Cliente de acceso remoto")
    parser.add_argument(
        "--server",
        default="ws://localhost:8765",
        help="URL del servidor Ingar (default: ws://localhost:8765)",
    )
    args = parser.parse_args()

    app = MainWindow(server_url=args.server)
    app.run()


if __name__ == "__main__":
    main()
