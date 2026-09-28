"""rutas.py — rutas del proyecto y valores por defecto (dev vs .exe).

Movido sin cambios desde app.py (Fase 0). Única fuente de verdad para
dónde viven el front, la BD y el schema.
"""
from __future__ import annotations

from pathlib import Path

BASE = Path(__file__).resolve().parent.parent  # backend/
ROOT = BASE.parent                              # raíz del proyecto
FRONT = ROOT / "frontend"        # index.html + styles.css + app.js + data.js
DB_DIR = ROOT / "database"       # schema.sql + tesoreria.db (dev) + plantilla generada
SCHEMA = DB_DIR / "schema.sql"

import sys as _sys
if getattr(_sys, "frozen", False):
    # En el .exe, front + schema viajan embebidos (_MEIPASS); la BD y la
    # plantilla generada viven junto al exe (ver db_default y arranque).
    _MEI = Path(getattr(_sys, "_MEIPASS", Path(_sys.executable).parent))
    FRONT = _MEI / "frontend"
    SCHEMA = _MEI / "database" / "schema.sql"


def db_default() -> Path:
    # Portable: junto al exe en producción, en database/ en dev.
    import sys
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "tesoreria.db"
    return DB_DIR / "tesoreria.db"


def front_file(name: str) -> Path | None:
    import sys
    candidates = []
    if getattr(sys, "frozen", False):
        meipass = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        exe_dir = Path(sys.executable).resolve().parent
        candidates += [meipass / "frontend" / name, exe_dir / "frontend" / name,
                       meipass / name, exe_dir / name]
    candidates += [FRONT / name]
    for p in candidates:
        if p.exists():
            return p
    return None
