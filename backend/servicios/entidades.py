"""entidades.py — lectura de clientes, proveedores y bancos/cuentas.

Solo SELECT: este servicio nunca escribe (las entidades se crean
automáticamente al crear movimientos). listar_cuentas agrega el cuadre
por cuenta: apertura 31-jul + realizados vs corte del banco.
"""
from __future__ import annotations

import sqlite3

from nucleo import catalogos
from servicios.cuadre import AVISO_SIN_EXTRACTO


def listar_entidades(con: sqlite3.Connection, tipo: str = "") -> list[dict]:
    if tipo in catalogos.TIPOS_ENTIDAD:
        rows = con.execute(
            "SELECT * FROM entidades WHERE tipo=? ORDER BY nombre", (tipo,)).fetchall()
    else:
        rows = con.execute(
            "SELECT * FROM entidades ORDER BY tipo, nombre").fetchall()
    return [dict(r) for r in rows]


def listar_cuentas(con: sqlite3.Connection) -> list[dict]:
    out = []
    for c in con.execute("SELECT * FROM cuentas ORDER BY banco").fetchall():
        c = dict(c)
        mov = con.execute(
            "SELECT SUM(CASE WHEN tipo='ingreso' THEN valor_usd ELSE 0 END) ing,"
            " SUM(CASE WHEN tipo='egreso' THEN valor_usd ELSE 0 END) egr"
            " FROM movimientos WHERE cuenta_id=? AND status='realizado'",
            (c["id"],)).fetchone()
        ing, egr = mov["ing"] or 0, mov["egr"] or 0
        apertura = c.get("saldo_apertura_usd") or 0
        corte = con.execute(
            "SELECT saldo_actual, fecha_corte FROM cortes_bancarios"
            " WHERE cuenta_id=? ORDER BY fecha_corte DESC LIMIT 1",
            (c["id"],)).fetchone()
        banco_dice = round(corte["saldo_actual"], 2) if corte else None
        calculado = round(apertura + ing - egr, 2)
        c["saldo_usd"] = calculado
        c["banco_dice"] = banco_dice
        c["diferencia"] = round(calculado - banco_dice, 2) if banco_dice is not None else None
        c["aviso"] = None if c.get("tiene_extracto") else AVISO_SIN_EXTRACTO
        c["fecha_corte"] = corte["fecha_corte"] if corte else ""
        out.append(c)
    return out
