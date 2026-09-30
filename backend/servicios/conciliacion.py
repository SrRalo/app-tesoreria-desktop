"""conciliacion.py — amarre automático extracto <-> movimiento (por fecha).

Regla del dueño: match si misma fecha (fecha_pago == fecha valor del banco)
+ mismo valor + misma cuenta. FIFO si hay varios candidatos.

- Línea de comisión (COM-/IVA-/TARIFA/...) → no se concilia: genera egreso
  realizado con concepto 'comision' (decisión §4).
- Línea matcheada → el movimiento pasa a 'realizado' conservando su fecha
  de pago (fecha del banco) y se registra el amarre 'auto'.
- Línea sin match → genera el movimiento realizado ('generado') con
  cobranza_clientes / pago_proveedores; la entidad se deduce si el nombre
  de un cliente/proveedor aparece en la descripción, si no queda vacía.
"""
from __future__ import annotations

import sqlite3

from etl.extractos.base import es_comision, norm

PENDIENTES = ("pendiente", "aplazado", "vencido")


def _concepto(con: sqlite3.Connection, nombre: str) -> int:
    con.execute("INSERT OR IGNORE INTO conceptos (nombre) VALUES (?)", (nombre,))
    return con.execute("SELECT id FROM conceptos WHERE nombre=?",
                       (nombre,)).fetchone()[0]


def _entidad_en_descripcion(con: sqlite3.Connection, tipo: str,
                            descripcion: str) -> int | None:
    """Deduce entidad si su nombre aparece tal cual en la descripción."""
    desc = norm(descripcion).upper()
    mejor = None
    for r in con.execute("SELECT id, nombre FROM entidades WHERE tipo=?", (tipo,)):
        n = norm(r["nombre"]).upper()
        if n and len(n) >= 4 and n in desc:
            if mejor is None or len(n) > len(norm(mostrar(con, mejor)).upper()):
                mejor = r["id"]
    return mejor


def mostrar(con: sqlite3.Connection, entidad_id: int) -> str:
    r = con.execute("SELECT nombre FROM entidades WHERE id=?", (entidad_id,)).fetchone()
    return r["nombre"] if r else ""


def _tipo_pago(descripcion: str, referencia: str) -> str:
    t = (norm(descripcion) + " " + norm(referencia)).upper()
    if "CHEQUE" in t or t.startswith("CQ ") or " CH." in t or "CH " in t:
        return "cheque"
    return "transferencia"


def auto_conciliar(con: sqlite3.Connection, cuenta_id: int | None = None) -> dict:
    """Concilia líneas sin amarre. Devuelve {auto, generados, comisiones}."""
    sql = ("SELECT e.*, cu.banco FROM extracto_lineas e "
           "JOIN cuentas cu ON cu.id=e.cuenta_id "
           "LEFT JOIN conciliacion c ON c.extracto_id=e.id "
           "WHERE c.extracto_id IS NULL")
    args: list = []
    if cuenta_id is not None:
        sql += " AND e.cuenta_id=?"
        args.append(cuenta_id)
    sql += " ORDER BY e.fecha, e.id"
    lineas = [dict(r) for r in con.execute(sql, args).fetchall()]

    auto = generados = comisiones = 0
    with con:
        for ln in lineas:
            valor = ln["credito_usd"] if ln["credito_usd"] > 0 else ln["debito_usd"]
            tipo = "ingreso" if ln["credito_usd"] > 0 else "egreso"
            banco = ln["banco"]
            obs = f"[EXT-{banco}] {norm(ln['descripcion'])[:200]}" \
                + (f" Ref:{norm(ln['referencia'])[:60]}" if norm(ln["referencia"]) else "")

            if es_comision(ln["descripcion"]) and tipo == "egreso":
                mid = _crear_realizado(con, ln["fecha"], tipo, banco, None,
                                       "comision", valor, obs)
                con.execute("INSERT INTO conciliacion (movimiento_id, extracto_id,"
                            " tipo_match) VALUES (?,?,?)", (mid, ln["id"], "generado"))
                _bitacora(con, "CREAR", mid,
                          f"comisión bancaria {valor:.2f} USD {ln['fecha']} ({banco})",
                          {"tipo": tipo, "valor_usd": valor, "fecha_pago": ln["fecha"]})
                generados += 1
                comisiones += 1
                continue

            cand = con.execute(
                "SELECT m.id FROM movimientos m "
                "LEFT JOIN conciliacion c ON c.movimiento_id=m.id "
                "WHERE m.cuenta_id=? AND m.fecha_pago=? AND m.tipo=? "
                "AND m.valor_usd=? AND m.status IN (?,?,?) "
                "AND c.movimiento_id IS NULL ORDER BY m.id LIMIT 1",
                (ln["cuenta_id"], ln["fecha"], tipo, valor, *PENDIENTES)).fetchone()
            if cand:
                mid = cand["id"]
                con.execute("UPDATE movimientos SET status='realizado' WHERE id=?", (mid,))
                con.execute("INSERT INTO conciliacion (movimiento_id, extracto_id,"
                            " tipo_match) VALUES (?,?,?)", (mid, ln["id"], "auto"))
                _bitacora(con, "REALIZADO", mid,
                          f"conciliado con extracto {banco} del {ln['fecha']}",
                          {"status": "realizado", "fecha_pago": ln["fecha"]})
                auto += 1
                continue

            concepto = "cobranza_clientes" if tipo == "ingreso" else "pago_proveedores"
            ent = _entidad_en_descripcion(
                con, "cliente" if tipo == "ingreso" else "proveedor",
                ln["descripcion"])
            mid = _crear_realizado(con, ln["fecha"], tipo, banco, ent, concepto,
                                   valor, obs, tipo_pago=_tipo_pago(
                                       ln["descripcion"], ln["referencia"]))
            con.execute("INSERT INTO conciliacion (movimiento_id, extracto_id,"
                        " tipo_match) VALUES (?,?,?)", (mid, ln["id"], "generado"))
            _bitacora(con, "CREAR", mid,
                      f"{tipo} {valor:.2f} USD {ln['fecha']} ({banco}) desde extracto",
                      {"tipo": tipo, "valor_usd": valor, "fecha_pago": ln["fecha"]})
            generados += 1
    return {"auto": auto, "generados": generados, "comisiones": comisiones}


def _crear_realizado(con: sqlite3.Connection, fecha: str, tipo: str, banco: str,
                     entidad_id: int | None, concepto: str, valor: float,
                     obs: str, tipo_pago: str = "transferencia") -> int:
    cid = _concepto(con, concepto)
    cta = con.execute("SELECT id FROM cuentas WHERE banco=?", (banco,)).fetchone()
    cur = con.execute(
        "INSERT INTO movimientos (fecha_pago, tipo, tipo_pago, concepto_id,"
        " entidad_id, cuenta_id, centro_costo, valor_usd, status, observacion)"
        " VALUES (?,?,?,?,?,?,?,?,?,?)",
        (fecha, tipo, tipo_pago, cid, entidad_id, cta["id"],
         "", round(valor, 2), "realizado", obs[:500]))
    return cur.lastrowid


def _bitacora(con: sqlite3.Connection, accion: str, registro_id: int,
              detalle: str, nuevo: dict) -> None:
    try:
        from servicios.bitacora import registrar
        registrar(con, accion, "movimientos", registro_id, detalle,
                  anterior=None, nuevo=nuevo, origen="IMPORT")
    except Exception:
        pass


def pendientes(con: sqlite3.Connection, cuenta_id: int | None = None,
               limit: int = 200) -> list[dict]:
    """Líneas de extracto aún sin amarre (para revisión manual)."""
    sql = ("SELECT e.*, cu.banco FROM extracto_lineas e "
           "JOIN cuentas cu ON cu.id=e.cuenta_id "
           "LEFT JOIN conciliacion c ON c.extracto_id=e.id "
           "WHERE c.extracto_id IS NULL")
    args: list = []
    if cuenta_id is not None:
        sql += " AND e.cuenta_id=?"
        args.append(cuenta_id)
    sql += " ORDER BY e.fecha, e.id LIMIT ?"
    args.append(limit)
    return [dict(r) for r in con.execute(sql, args).fetchall()]
