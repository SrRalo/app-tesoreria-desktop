"""basedatos.py — conexión SQLite + aplicación del schema.

Cada conexión aplica el schema (CREATE TABLE IF NOT EXISTS + seeds RN-09),
así que una BD vacía queda lista. Además corre la migración v2→v3
(columnas de apertura en cuentas) para BDs creadas con el schema anterior.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from nucleo.rutas import SCHEMA


def _columnas(con: sqlite3.Connection, tabla: str) -> set[str]:
    return {r[1] for r in con.execute(f"PRAGMA table_info({tabla})")}


def _dedup_cuentas(con: sqlite3.Connection) -> None:
    """Fusiona filas duplicadas por banco (legado v2: numero '' vs real).

    Conserva la fila con extracto/apertura/número y re-apunta las tablas
    hijas antes de borrar las perdedoras. Sin huérfanos: movimientos,
    extracto_lineas, cortes y saldos siempre quedan en la ganadora.
    Además renombra el legado 'Cte 11111' al número real de Pichincha.
    """
    dup = [r[0] for r in con.execute(
        "SELECT banco FROM cuentas GROUP BY banco HAVING COUNT(*) > 1")]
    for banco in dup:
        filas = [dict(r) for r in con.execute(
            "SELECT * FROM cuentas WHERE banco=? ORDER BY id", (banco,))]
        def puntaje(c):
            return (1 if c["tiene_extracto"] else 0,
                    1 if (c["saldo_apertura_usd"] or 0) != 0 else 0,
                    1 if (c["numero"] or "") != "" else 0,
                    -c["id"])
        filas.sort(key=puntaje)
        keeper = filas[-1]
        for perdedora in filas[:-1]:
            # Cortes: conservar en la ganadora los que no tenga.
            for r in con.execute("SELECT * FROM cortes_bancarios WHERE cuenta_id=?",
                                 (perdedora["id"],)):
                con.execute("INSERT OR IGNORE INTO cortes_bancarios (cuenta_id,"
                            " fecha_corte, saldo_anterior, depositos, retiros,"
                            " saldo_actual, archivo) VALUES (?,?,?,?,?,?,?)",
                            (keeper["id"], r["fecha_corte"], r["saldo_anterior"],
                             r["depositos"], r["retiros"], r["saldo_actual"],
                             r["archivo"]))
            con.execute("DELETE FROM cortes_bancarios WHERE cuenta_id=?",
                        (perdedora["id"],))
            # Saldos por cuenta: se recalculan solos en el próximo
            # importar/CRUD (recalcular_saldos_cuenta); aquí solo se borran.
            con.execute("DELETE FROM saldos_diarios_cuenta WHERE cuenta_id=?",
                        (perdedora["id"],))
            for tabla in ("movimientos", "extracto_lineas"):
                con.execute(f"UPDATE {tabla} SET cuenta_id=? WHERE cuenta_id=?",
                            (keeper["id"], perdedora["id"]))
            con.execute("DELETE FROM cuentas WHERE id=?", (perdedora["id"],))
    # Legado: 'Cte 11111' era el número de ejemplo; el real es 2100319432.
    # Se renombra al final (ya sin gemelos) para que el seed no genere
    # un duplicado en cada conexión (UNIQUE es banco+numero).
    con.execute("UPDATE cuentas SET numero='2100319432' WHERE banco='Pichincha'"
                " AND numero='Cte 11111'")


def _migrar_v3(con: sqlite3.Connection) -> None:
    """Agrega columnas v3 a cuentas si la BD viene del schema v2."""
    cols = _columnas(con, "cuentas")
    if "saldo_apertura_usd" not in cols:
        con.execute("ALTER TABLE cuentas ADD COLUMN saldo_apertura_usd REAL NOT NULL DEFAULT 0")
    if "fecha_apertura" not in cols:
        con.execute("ALTER TABLE cuentas ADD COLUMN fecha_apertura TEXT DEFAULT '2026-07-31'")
    if "tiene_extracto" not in cols:
        con.execute("ALTER TABLE cuentas ADD COLUMN tiene_extracto INTEGER NOT NULL DEFAULT 0")


def conectar(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    _migrar_v3(con)
    _dedup_cuentas(con)
    con.commit()
    return con
