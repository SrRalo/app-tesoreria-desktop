"""run.py — entrypoint de FlowTreasury (dev y build .exe).

Uso:
  python run.py --db ..\\database\\tesoreria.db --port 8000
PyInstaller empaqueta este archivo (ver README.md).
"""
from __future__ import annotations

from api.servidor import main

if __name__ == "__main__":
    main()
