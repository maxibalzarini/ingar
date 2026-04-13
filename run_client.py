"""
Ingar – Lanzador rápido del cliente.

Uso:
    python run_client.py [--server ws://host:8765]
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from client.main import main

if __name__ == "__main__":
    main()
