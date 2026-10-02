"""configuracion.py — zona de peligro: borrado total protegido por clave admin (RN-13).

borrar_todo() vacía movimientos, saldos, log, entidades, cuentas y config, y
reaplica los seeds del schema (conceptos, cuentas base, saldo por defecto).
La app vuelve al estado de primer arranque (necesita_import=true).

La clave por defecto es 'admin123'; se puede overriding con la variable de
entorno FLOWTREASURY_ADMIN sin cambiar código.
"""
from __future__ import annotations

import os
import sqlite3

from nucleo.rutas import SCHEMA

CLAVE_ADMIN = os.environ.get("FLOWTREASURY_ADMIN", "admin123")


class ClaveInvalida(PermissionError):
    """Clave de administrador incorrecta → HTTP 403."""


def verificar_clave(clave: str | None) -> None:
    if (clave or "") != CLAVE_ADMIN:
        raise ClaveInvalida("clave de administrador inválida")


def borrar_todo(con: sqlite3.Connection, clave: str | None) -> dict:
    verificar_clave(clave)
    with con:
        con.execute("DELETE FROM conciliacion")
        con.execute("DELETE FROM extracto_lineas")
        con.execute("DELETE FROM cortes_bancarios")
        con.execute("DELETE FROM saldos_diarios_cuenta")
        con.execute("DELETE FROM movimientos")
        con.execute("DELETE FROM saldos_diarios")
        con.execute("DELETE FROM import_log")
        con.execute("DELETE FROM clientes")
        con.execute("DELETE FROM proveedores")
        con.execute("DELETE FROM entidades")
        con.execute("DELETE FROM cuentas")
        con.execute("DELETE FROM bancos")
        con.execute("DELETE FROM config")
        # La bitácora se preserva para auditoría post-fallo (v3).
        con.executescript(SCHEMA.read_text(encoding="utf-8"))
        # v4: el seed del schema no fija banco_id (compat v3); se rellena aquí
        # porque borrar_todo no pasa por conectar()/_migrar_v4().
        from nucleo.basedatos import _migrar_v4
        _migrar_v4(con)
        from servicios.bitacora import registrar
        registrar(con, "BORRADO_TOTAL", "sistema", None,
                  "borrado total de datos (bitácora preservada)",
                  anterior=None, nuevo=None, origen="UI")
    return {"ok": True}
