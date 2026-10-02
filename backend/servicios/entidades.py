"""entidades.py — lectura de clientes, proveedores y bancos/cuentas.

Solo SELECT: este servicio nunca escribe (las entidades se crean
automáticamente al crear movimientos). listar_cuentas agrega el cuadre
por cuenta: apertura 31-jul + realizados vs corte del banco.
v4: entidades es la madre; clientes/proveedores son extensiones 1-a-1
(sin campos extra); bancos es la maestra de cuentas (cuentas.banco_id).
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


def listar_clientes(con: sqlite3.Connection) -> list[dict]:
    """v4: clientes vía vista de compat (madre + hija)."""
    return [dict(r) for r in con.execute(
        "SELECT * FROM v_clientes ORDER BY nombre").fetchall()]


def listar_proveedores(con: sqlite3.Connection) -> list[dict]:
    """v4: proveedores vía vista de compat (madre + hija)."""
    return [dict(r) for r in con.execute(
        "SELECT * FROM v_proveedores ORDER BY nombre").fetchall()]


def listar_bancos(con: sqlite3.Connection) -> list[dict]:
    """v4: maestra de bancos (catálogo, sin saldos; ver servicios/bancos.py)."""
    return [dict(r) for r in con.execute(
        "SELECT * FROM bancos ORDER BY nombre").fetchall()]


def listar_cuentas(con: sqlite3.Connection) -> list[dict]:
    out = []
    # v4: nombre canónico del banco vía JOIN; fallback al texto deprecated.
    # v4: movimientos ya no tiene cuenta_id (RN-05/09): el saldo por cuenta
    # es apertura + corte informativo; ing/egr por cuenta quedan en 0.
    sql = ("SELECT c.*, COALESCE(b.nombre, c.banco) AS banco FROM cuentas c"
           " LEFT JOIN bancos b ON b.id = c.banco_id ORDER BY banco")
    for c in con.execute(sql).fetchall():
        c = dict(c)
        ing, egr = 0, 0
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
