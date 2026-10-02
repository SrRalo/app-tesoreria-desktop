"""basedatos.py — conexión SQLite + aplicación del schema.

Cada conexión aplica el schema (CREATE TABLE IF NOT EXISTS + seeds RN-09),
así que una BD vacía queda lista. Además corre las migraciones v2→v3
(columnas de apertura en cuentas) y v3→v4 (bancos + clientes/proveedores)
para BDs creadas con schemas anteriores.
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
            # v4: movimientos ya no tiene cuenta_id (RN-05/09): solo
            # re-apuntar tablas que aún cuelgan de cuentas.
            for tabla in ("extracto_lineas",):
                con.execute(f"UPDATE {tabla} SET cuenta_id=? WHERE cuenta_id=?",
                            (keeper["id"], perdedora["id"]))
            con.execute("DELETE FROM cuentas WHERE id=?", (perdedora["id"],))
    # Legado: 'Cte 11111' era el número de ejemplo; el real es 2100319432.
    # Se renombra al final (ya sin gemelos) para que el seed no genere
    # un duplicado en cada conexión (UNIQUE es banco+numero).
    con.execute("UPDATE cuentas SET numero='2100319432' WHERE banco='Pichincha'"
                " AND numero='Cte 11111'")
    # v4: tras fusionar, re-enlaza banco_id por si alguna perdedora aportó el keeper.
    try:
        con.execute(
            "UPDATE cuentas SET banco_id = "
            "(SELECT id FROM bancos WHERE bancos.nombre = cuentas.banco)"
            " WHERE banco_id IS NULL")
    except Exception:
        pass  # bancos aún no existe en migraciones muy viejas: lo hace _migrar_v4


def _migrar_hash256(con: sqlite3.Connection) -> None:
    """Re-hashea extracto_lineas de SHA1 (40 hex) a SHA256 (64 hex, RF-ETL-10).

    Los campos origen siguen guardados, así que el re-hash es determinista.
    Idempotente: solo toca filas con hash de 40 caracteres.
    """
    from etl.extractos.base import hash_linea
    viejas = con.execute(
        "SELECT id, cuenta_id, fecha, debito_usd, credito_usd,"
        " IFNULL(referencia,''), IFNULL(descripcion,'')"
        " FROM extracto_lineas WHERE length(hash_unico)=40").fetchall()
    for r in viejas:
        nuevo = hash_linea(r[1], r[2], r[3] or 0, r[4] or 0, r[5], r[6])
        try:
            con.execute("UPDATE extracto_lineas SET hash_unico=? WHERE id=?",
                        (nuevo, r[0]))
        except Exception:
            pass  # colisión improbable: conserva el hash viejo (sigue UNIQUE)
    if viejas:
        con.commit()


def _migrar_v3(con: sqlite3.Connection) -> None:
    """Agrega columnas v3 a cuentas si la BD viene del schema v2."""
    cols = _columnas(con, "cuentas")
    if "saldo_apertura_usd" not in cols:
        con.execute("ALTER TABLE cuentas ADD COLUMN saldo_apertura_usd REAL NOT NULL DEFAULT 0")
    if "fecha_apertura" not in cols:
        con.execute("ALTER TABLE cuentas ADD COLUMN fecha_apertura TEXT DEFAULT '2026-07-31'")
    if "tiene_extracto" not in cols:
        con.execute("ALTER TABLE cuentas ADD COLUMN tiene_extracto INTEGER NOT NULL DEFAULT 0")


def _migrar_v4(con: sqlite3.Connection) -> None:
    """Migración v3→v4: bancos + clientes/proveedores (sin campos extra).

    Idempotente: CREATE TABLE IF NOT EXISTS + backfills con INSERT OR IGNORE /
    UPDATE solo donde falta. No borra columnas (cuentas.banco queda deprecated).
    """
    con.execute(
        "CREATE TABLE IF NOT EXISTS bancos ("
        " id INTEGER PRIMARY KEY AUTOINCREMENT,"
        " nombre TEXT NOT NULL UNIQUE,"
        " logo TEXT NOT NULL DEFAULT '',"
        " activo INTEGER NOT NULL DEFAULT 1)")
    con.execute(
        "CREATE TABLE IF NOT EXISTS clientes ("
        " entidad_id INTEGER PRIMARY KEY REFERENCES entidades(id) ON DELETE CASCADE)")
    con.execute(
        "CREATE TABLE IF NOT EXISTS proveedores ("
        " entidad_id INTEGER PRIMARY KEY REFERENCES entidades(id) ON DELETE CASCADE)")
    if "banco_id" not in _columnas(con, "cuentas"):
        con.execute("ALTER TABLE cuentas ADD COLUMN banco_id INTEGER REFERENCES bancos(id)")
    # Backfill bancos: base primero (BD fresca vacía) + texto legado de cuentas v3.
    for nombre in ("Pichincha", "Guayaquil", "Internacional", "Caja",
                   "PorDefinir", "Produbanco"):
        con.execute("INSERT OR IGNORE INTO bancos (nombre) VALUES (?)", (nombre,))
    for (nombre,) in con.execute("SELECT DISTINCT banco FROM cuentas"):
        if nombre:
            con.execute("INSERT OR IGNORE INTO bancos (nombre) VALUES (?)", (nombre,))
    con.execute(
        "UPDATE cuentas SET banco_id = "
        "(SELECT id FROM bancos WHERE bancos.nombre = cuentas.banco)"
        " WHERE banco_id IS NULL")
    # Backfill hijas desde la madre.
    con.execute("INSERT OR IGNORE INTO clientes (entidad_id)"
                " SELECT id FROM entidades WHERE tipo='cliente'")
    con.execute("INSERT OR IGNORE INTO proveedores (entidad_id)"
                " SELECT id FROM entidades WHERE tipo='proveedor'")
    con.execute(
        "CREATE VIEW IF NOT EXISTS v_clientes AS"
        " SELECT e.id, e.nombre, e.activo FROM entidades e"
        " JOIN clientes c ON c.entidad_id = e.id WHERE e.tipo = 'cliente'")
    con.execute(
        "CREATE VIEW IF NOT EXISTS v_proveedores AS"
        " SELECT e.id, e.nombre, e.activo FROM entidades e"
        " JOIN proveedores p ON p.entidad_id = e.id WHERE e.tipo = 'proveedor'")
    con.execute(
        "CREATE VIEW IF NOT EXISTS v_cuentas AS"
        " SELECT c.id, c.numero, c.saldo_inicial_usd, c.activo,"
        " c.saldo_apertura_usd, c.fecha_apertura, c.tiene_extracto,"
        " c.banco_id, COALESCE(b.nombre, c.banco) AS banco"
        " FROM cuentas c LEFT JOIN bancos b ON b.id = c.banco_id")


def _migrar_concepto_insumos(con: sqlite3.Connection) -> None:
    """Asegura el concepto 'insumos' (RN-09) en BDs creadas antes de su alta."""
    con.execute("INSERT OR IGNORE INTO conceptos (nombre) VALUES ('insumos')")


def conectar(db: Path) -> sqlite3.Connection:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(SCHEMA.read_text(encoding="utf-8"))
    _migrar_v3(con)
    _migrar_v4(con)
    _migrar_hash256(con)
    _migrar_concepto_insumos(con)
    _dedup_cuentas(con)
    con.commit()
    return con
