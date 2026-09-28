"""entidades.py — lectura de clientes, proveedores y bancos/cuentas.

Movido sin cambios desde app.py (Fase 3). Solo SELECT: este servicio
nunca escribe (las entidades se crean automáticamente al crear movimientos).
"""
from __future__ import annotations

import sqlite3

from nucleo import catalogos


def listar_entidades(con: sqlite3.Connection, tipo: str = "") -> list[dict]:
    if tipo in catalogos.TIPOS_ENTIDAD:
        rows = con.execute(
            "SELECT * FROM entidades WHERE tipo=? ORDER BY nombre", (tipo,)).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM entidades ORDER BY tipo, nombre").fetchall()
    return [dict(r) for r in rows]


def listar_cuentas(con: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in
            con.execute("SELECT * FROM cuentas ORDER BY banco").fetchall()]
