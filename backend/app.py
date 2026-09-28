"""app.py — compatibilidad: el entrypoint ahora es run.py.

Este shim existe para no romper comandos existentes (`python app.py ...`).
Código real en api/servidor.py.
"""
from __future__ import annotations

from api.servidor import main

if __name__ == "__main__":
    main()
