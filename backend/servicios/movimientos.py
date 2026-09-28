"""movimientos.py — CRUD de movimientos + reglas RN-09/RN-12.

Movido desde app.py (Fase 2) como funciones puras sobre una conexión:
devuelven datos o lanzan ErrorValidacion (→ HTTP 400) / NoEncontrado (→ HTTP 404).
Cada escritura recalcula saldos_diarios (solo 'realizado' suma al flujo).

Micro-correcciones sinceradas respecto al original (ver reporte Fase 2):
- crear sin fecha_pago o con valor_usd no numérico → ErrorValidacion (400)
  en vez de KeyError/ValueError sin manejar (500).
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime

from nucleo import catalogos
from servicios.flujo import MOV_SELECT


class ErrorValidacion(ValueError):
    """Regla de negocio violada (RN-09/RN-12) → HTTP 400."""


class NoEncontrado(LookupError):
    """Movimiento inexistente → HTTP 404."""


def _recalcular(con: sqlite3.Connection) -> None:
    # recalcular_saldos vive en etl/ desde la Fase 4.
    from etl.importar import recalcular_saldos
    recalcular_saldos(con)


def listar(con: sqlite3.Connection, tipo: str = "", status: str = "",
           texto: str = "", page: int = 1, limit: int = 50) -> dict:
    page = max(int(page), 1)
    limit = min(max(int(limit), 1), 200)
    off = (page - 1) * limit
    sql = MOV_SELECT + " WHERE 1=1"
    args: list = []
    if tipo in catalogos.TIPOS:
        sql += " AND m.tipo=?"; args.append(tipo)
    if status in catalogos.STATUS:
        sql += " AND m.status=?"; args.append(status)
    if texto:
        sql += " AND (m.observacion LIKE ? OR e.nombre LIKE ?)"
        args += [f"%{texto}%", f"%{texto}%"]
    total = con.execute(f"SELECT COUNT(*) c FROM ({sql})", args).fetchone()["c"]
    rows = [dict(r) for r in con.execute(
        sql + " ORDER BY m.fecha_pago DESC, m.id DESC LIMIT ? OFFSET ?",
        args + [limit, off]).fetchall()]
    return {"total": total, "page": page, "limit": limit, "rows": rows}


def crear(con: sqlite3.Connection, d: dict) -> int:
    for campo, vals in (
            ("tipo", catalogos.TIPOS),
            ("tipo_pago", catalogos.TIPOS_PAGO),
            ("status", catalogos.STATUS_CREACION)):  # al crear: sin aplazado
        if d.get(campo) not in vals:
            raise ErrorValidacion(f"{campo} inválido (RN-09/RN-12)")
    if not d.get("fecha_pago"):
        raise ErrorValidacion("fecha_pago requerida")
    try:
        datetime.strptime(d["fecha_pago"], "%Y-%m-%d")
    except ValueError:
        raise ErrorValidacion("fecha_pago inválida") from None
    try:
        valor = float(d.get("valor_usd", 0))
    except (TypeError, ValueError):
        raise ErrorValidacion("valor_usd debe ser número > 0") from None
    if valor <= 0:
        raise ErrorValidacion("valor_usd debe ser número > 0")
    with con:
        concepto = str(d.get("concepto_pago", "")).lower()
        row = con.execute("SELECT id FROM conceptos WHERE nombre=?",
                          (concepto,)).fetchone()
        if not row:
            raise ErrorValidacion("concepto_pago inválido (RN-09)")
        ent_id = None
        if d.get("entidad"):
            et = "cliente" if d["tipo"] == "ingreso" else "proveedor"
            con.execute("INSERT OR IGNORE INTO entidades (tipo, nombre) VALUES (?,?)",
                        (et, d["entidad"]))
            ent_id = con.execute("SELECT id FROM entidades WHERE nombre=?",
                                 (d["entidad"],)).fetchone()[0]
        cta = con.execute("SELECT id FROM cuentas WHERE banco=?",
                          (d.get("banco", ""),)).fetchone()
        if not cta:
            raise ErrorValidacion("banco desconocido")
        cur = con.execute(
            "INSERT INTO movimientos (fecha_pago, tipo, tipo_pago, concepto_id,"
            " entidad_id, cuenta_id, centro_costo, valor_usd, status, observacion)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (d["fecha_pago"], d["tipo"], d["tipo_pago"], row["id"], ent_id,
             cta["id"], d.get("centro_costo", ""), valor,
             d.get("status", "pendiente"), d.get("observacion", "")))
        _recalcular(con)
        return cur.lastrowid


def editar(con: sqlite3.Connection, mid, fecha_pago: str, observacion: str = "") -> str:
    # Edición limitada RN-12: solo fecha_pago + observacion; pasa a aplazado.
    if not fecha_pago:
        raise ErrorValidacion("fecha_pago requerida")
    try:
        datetime.strptime(fecha_pago, "%Y-%m-%d")
    except ValueError:
        raise ErrorValidacion("fecha_pago inválida") from None
    with con:
        cur = con.execute(
            "UPDATE movimientos SET fecha_pago=?, observacion=?, status='aplazado' WHERE id=?",
            (fecha_pago, observacion, mid))
        if not cur.rowcount:
            raise NoEncontrado("movimiento no encontrado")
        _recalcular(con)
    return "aplazado"


def marcar_realizado(con: sqlite3.Connection, mid, hoy: str | None = None) -> str:
    # RN-12: status=realizado con fecha de hoy.
    hoy = hoy or date.today().strftime("%Y-%m-%d")
    with con:
        cur = con.execute("UPDATE movimientos SET status='realizado', fecha_pago=? WHERE id=?",
                          (hoy, mid))
        if not cur.rowcount:
            raise NoEncontrado("movimiento no encontrado")
        _recalcular(con)
    return hoy


def eliminar(con: sqlite3.Connection, mid) -> None:
    with con:
        row = con.execute("SELECT fecha_pago FROM movimientos WHERE id=?",
                          (mid,)).fetchone()
        if not row:
            raise NoEncontrado("movimiento no encontrado")
        con.execute("DELETE FROM movimientos WHERE id=?", (mid,))
        _recalcular(con)
