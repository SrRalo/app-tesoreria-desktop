"""conciliacion.py — DEPRECATED (congelado, sin uso).

La conciliación manual/automática se eliminó: los extractos ya no generan
movimientos ni cambian status; solo se consultan en Entidades > Bancos.
Se conserva el archivo y la tabla `conciliacion` por compatibilidad, pero
ningún ETL ni endpoint lo llama.
"""
from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from etl.extractos.base import es_comision, norm

PENDIENTES = ("pendiente", "aplazado", "vencido")
TOL_USD = 5.0
TOL_PCT = 0.02


def ventana_habil(fecha_iso: str, n: int = 3) -> list[str]:
    """Fechas ISO en [d-n, d+n] días hábiles (lun-vie), ordenadas por cercanía."""
    base = date.fromisoformat(fecha_iso)
    dias = [base]
    d = base
    for _ in range(n):
        d += timedelta(days=1)
        while d.weekday() >= 5:
            d += timedelta(days=1)
        dias.append(d)
    d = base
    for _ in range(n):
        d -= timedelta(days=1)
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        dias.append(d)
    dias.sort(key=lambda x: (abs((x - base).days), x))
    return [x.isoformat() for x in dias]


def dentro_tolerancia(valor_banco: float, valor_mov: float) -> bool:
    dif = abs(valor_banco - valor_mov)
    return 0 < dif <= max(TOL_USD, round(abs(valor_mov) * TOL_PCT, 2))


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
    """Concilia líneas sin amarre. Devuelve {auto, generados, comisiones, tolerancia}.

    Rápido: 1 query de líneas + 1 de pendientes por cuenta; match en memoria.
    """
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

    # pendientes por cuenta en memoria: {(cuenta, fecha): [movs]} + lista por cuenta
    movq = ("SELECT m.* FROM movimientos m LEFT JOIN conciliacion c "
            "ON c.movimiento_id=m.id WHERE m.status IN (?,?,?) AND c.movimiento_id IS NULL")
    margs: list = list(PENDIENTES)
    if cuenta_id is not None:
        movq += " AND m.cuenta_id=?"
        margs.append(cuenta_id)
    movq += " ORDER BY m.id"
    pend: dict[int, list[dict]] = {}
    for r in con.execute(movq, margs).fetchall():
        pend.setdefault(r["cuenta_id"], []).append(dict(r))
    usados: set[int] = set()

    auto = generados = comisiones = tolerados = 0
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

            cand = _buscar(pend.get(ln["cuenta_id"], []), usados, tipo, valor,
                           ventana_habil(ln["fecha"]))
            if cand is not None:
                usados.add(cand["id"])
                con.execute("UPDATE movimientos SET status='realizado' WHERE id=?", (cand["id"],))
                con.execute("INSERT INTO conciliacion (movimiento_id, extracto_id,"
                            " tipo_match) VALUES (?,?,?)", (cand["id"], ln["id"], "auto"))
                _bitacora(con, "REALIZADO", cand["id"],
                          f"conciliado con extracto {banco} del {ln['fecha']}",
                          {"status": "realizado", "fecha_pago": ln["fecha"]})
                auto += 1
                continue

            # RN-16: diferencia pequeña por comisión/retención -> concilia + egreso dif
            tole = _buscar_tol(pend.get(ln["cuenta_id"], []), usados, tipo, valor,
                               ventana_habil(ln["fecha"]))
            if tole is not None:
                usados.add(tole["id"])
                dif = round(abs(valor - tole["valor_usd"]), 2)
                con.execute("UPDATE movimientos SET status='realizado' WHERE id=?", (tole["id"],))
                con.execute("INSERT INTO conciliacion (movimiento_id, extracto_id,"
                            " tipo_match) VALUES (?,?,?)", (tole["id"], ln["id"], "auto"))
                mid = _crear_realizado(con, ln["fecha"], "egreso", banco, None,
                                       "comision", dif,
                                       f"[COMISION-AUTO] dif. extracto {banco} {ln['fecha']} "
                                       f"mov#{tole['id']}" + (f" Ref:{norm(ln['referencia'])[:60]}"
                                       if norm(ln["referencia"]) else ""))
                _bitacora(con, "REALIZADO", tole["id"],
                          f"conciliado con tolerancia {dif:.2f} USD ({banco} {ln['fecha']})",
                          {"status": "realizado", "comision_mov_id": mid})
                auto += 1
                tolerados += 1
                comisiones += 1
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
    return {"auto": auto, "generados": generados, "comisiones": comisiones,
            "tolerancia": tolerados}


def _buscar(pends: list[dict], usados: set[int], tipo: str,
            valor: float, ventana: list[str]) -> dict | None:
    """Match exacto (±0.01) en ventana, FIFO por cercanía de fecha."""
    for f in ventana:
        for m in pends:
            if (m["id"] not in usados and m["tipo"] == tipo
                    and m["fecha_pago"] == f and abs(m["valor_usd"] - valor) < 0.01):
                return m
    return None


def _buscar_tol(pends: list[dict], usados: set[int], tipo: str,
                valor: float, ventana: list[str]) -> dict | None:
    for f in ventana:
        for m in pends:
            if (m["id"] not in usados and m["tipo"] == tipo
                    and m["fecha_pago"] == f
                    and dentro_tolerancia(valor, m["valor_usd"])):
                return m
    return None


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


class ErrorConciliacion(ValueError):
    """Manual inválido → HTTP 400."""


def _linea_y_mov(con: sqlite3.Connection, extracto_id: int,
                 movimiento_id: int) -> tuple[dict, dict]:
    ln = con.execute("SELECT e.*, cu.banco FROM extracto_lineas e "
                     "JOIN cuentas cu ON cu.id=e.cuenta_id WHERE e.id=?",
                     (extracto_id,)).fetchone()
    if ln is None:
        raise ErrorConciliacion(f"línea de extracto #{extracto_id} no existe")
    mv = con.execute("SELECT * FROM movimientos WHERE id=?", (movimiento_id,)).fetchone()
    if mv is None:
        raise ErrorConciliacion(f"movimiento #{movimiento_id} no existe")
    ln, mv = dict(ln), dict(mv)
    ya = con.execute("SELECT 1 FROM conciliacion WHERE extracto_id=?",
                     (extracto_id,)).fetchone()
    if ya:
        raise ErrorConciliacion(f"la línea #{extracto_id} ya está conciliada")
    ya2 = con.execute("SELECT 1 FROM conciliacion WHERE movimiento_id=?",
                      (movimiento_id,)).fetchone()
    if ya2:
        raise ErrorConciliacion(f"el movimiento #{movimiento_id} ya está conciliado")
    if mv["cuenta_id"] != ln["cuenta_id"]:
        raise ErrorConciliacion("cuentas distintas: elija la misma cuenta de banco")
    tipo_ln = "ingreso" if (ln["credito_usd"] or 0) > 0 else "egreso"
    if mv["tipo"] != tipo_ln:
        raise ErrorConciliacion("tipos distintos (ingreso vs egreso)")
    if mv["status"] not in PENDIENTES:
        raise ErrorConciliacion(f"movimiento en status '{mv['status']}' (debe estar pendiente/aplazado/vencido)")
    return ln, mv


def _valor_linea(ln: dict) -> float:
    return (ln["credito_usd"] or 0) if (ln["credito_usd"] or 0) > 0 else (ln["debito_usd"] or 0)


def vincular_manual(con: sqlite3.Connection, extracto_id: int,
                    movimiento_id: int) -> dict:
    """RF-21: vínculo manual exacto (mismo valor ±0.01). Recalcula el llamador."""
    ln, mv = _linea_y_mov(con, extracto_id, movimiento_id)
    if abs(_valor_linea(ln) - mv["valor_usd"]) >= 0.01:
        raise ErrorConciliacion(
            f"difieren en {abs(_valor_linea(ln) - mv['valor_usd']):.2f} USD: "
            "use conciliar con comisión si está dentro de tolerancia")
    with con:
        con.execute("UPDATE movimientos SET status='realizado' WHERE id=?", (mv["id"],))
        con.execute("INSERT INTO conciliacion (movimiento_id, extracto_id, tipo_match)"
                    " VALUES (?,?,?)", (mv["id"], ln["id"], "manual"))
        _bitacora(con, "REALIZADO", mv["id"],
                  f"conciliación manual con extracto {ln['banco']} del {ln['fecha']}",
                  {"status": "realizado", "extracto_id": ln["id"]})
    return {"ok": True, "movimiento_id": mv["id"], "extracto_id": ln["id"]}


def conciliar_con_comision(con: sqlite3.Connection, extracto_id: int,
                           movimiento_id: int) -> dict:
    """RF-21 + RN-16: concilia con diferencia pequeña y genera el egreso comisión."""
    ln, mv = _linea_y_mov(con, extracto_id, movimiento_id)
    vb, vm = _valor_linea(ln), mv["valor_usd"]
    if abs(vb - vm) < 0.01:
        return vincular_manual(con, extracto_id, movimiento_id)
    if not dentro_tolerancia(vb, vm):
        raise ErrorConciliacion(
            f"diferencia {abs(vb - vm):.2f} USD fuera de tolerancia "
            f"(máx {max(TOL_USD, round(abs(vm) * TOL_PCT, 2)):.2f} USD)")
    dif = round(abs(vb - vm), 2)
    with con:
        con.execute("UPDATE movimientos SET status='realizado' WHERE id=?", (mv["id"],))
        con.execute("INSERT INTO conciliacion (movimiento_id, extracto_id, tipo_match)"
                    " VALUES (?,?,?)", (mv["id"], ln["id"], "manual"))
        mid = _crear_realizado(
            con, ln["fecha"], "egreso", ln["banco"], None, "comision", dif,
            f"[COMISION-MANUAL] dif. extracto {ln['banco']} {ln['fecha']} mov#{mv['id']}"
            + (f" Ref:{norm(ln['referencia'])[:60]}" if norm(ln["referencia"]) else ""))
        _bitacora(con, "REALIZADO", mv["id"],
                  f"conciliación manual con comisión {dif:.2f} USD ({ln['banco']})",
                  {"status": "realizado", "extracto_id": ln["id"],
                   "comision_mov_id": mid})
    return {"ok": True, "movimiento_id": mv["id"], "extracto_id": ln["id"],
            "comision_mov_id": mid, "diferencia": dif}


def lineas_mes(con: sqlite3.Connection, cuenta_id: int | None = None,
               mes: str = "", estado: str = "") -> list[dict]:
    """Líneas de extracto con estado (para el doble panel RF-21)."""
    sql = ("SELECT e.*, cu.banco, c.movimiento_id, c.tipo_match FROM extracto_lineas e "
           "JOIN cuentas cu ON cu.id=e.cuenta_id "
           "LEFT JOIN conciliacion c ON c.extracto_id=e.id WHERE 1=1")
    args: list = []
    if cuenta_id is not None:
        sql += " AND e.cuenta_id=?"
        args.append(cuenta_id)
    if mes:
        sql += " AND substr(e.fecha,1,7)=?"
        args.append(mes)
    sql += " ORDER BY e.fecha, e.id"
    out = []
    for r in con.execute(sql, args).fetchall():
        d = dict(r)
        monto = (d["credito_usd"] or 0) - (d["debito_usd"] or 0)
        est = "CONCILIADO" if d["movimiento_id"] is not None else "SIN_CONCILIAR"
        if estado and est != estado:
            continue
        d["monto"] = round(monto, 2)
        d["estado_conciliacion"] = est
        out.append(d)
    return out


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
