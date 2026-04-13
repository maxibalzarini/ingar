"""
Ingar – Lanzador rápido del servidor de señalización.

Uso:
    python run_server.py [--host 0.0.0.0] [--port 8765]
"""

import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server.signaling_server import main as server_main


def parse_args():
    parser = argparse.ArgumentParser(description="Ingar – Servidor de señalización")
    parser.add_argument("--host", default="0.0.0.0", help="Dirección IP de escucha")
    parser.add_argument("--port", type=int, default=8765, help="Puerto de escucha")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    asyncio.run(server_main(host=args.host, port=args.port))
