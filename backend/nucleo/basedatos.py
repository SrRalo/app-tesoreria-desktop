"""basedatos.py — conexión SQLite + aplicación del schema.

Movido sin cambios desde app.py (Fase 0). Cada conexión aplica el schema
(CREATE TABLE IF NOT EXISTS + seeds RN-09), así que una BD vacía queda lista.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from nucleo.rutas import SCHEMA


def conectar(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    return con
