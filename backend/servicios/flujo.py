"""flujo.py — cálculo de la Vista de Flujo (RN-10/RN-11, sin paginación).

Movido sin cambios desde app.py (Fase 1). Lee movimientos con
status='realizado' + saldos precalculados; pendiente/aplazado no suma.

MOV_SELECT vive aquí porque el detalle de subfilas lo necesita; la Fase 2
(servicios/movimientos.py) lo reutiliza para no duplicarlo.
"""
from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta

DIAS = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
         "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]

MOV_SELECT = ("SELECT m.id, m.fecha_pago, m.tipo, m.tipo_pago, c.nombre AS concepto_pago,"
              " e.nombre AS entidad, cu.banco, m.centro_costo, m.valor_usd, m.status,"
              " m.observacion FROM movimientos m"
              " JOIN conceptos c ON c.id=m.concepto_id"
              " LEFT JOIN entidades e ON e.id=m.entidad_id"
              " JOIN cuentas cu ON cu.id=m.cuenta_id")


def _parse_ym(s: str) -> tuple[int, int]:
    y, m = s.split("-")[:2]
    return int(y), int(m)


def _sum_meses(y: int, m: int, n: int) -> list[tuple[int, int]]:
    out = []
    for _ in range(n):
        out.append((y, m))
        m += 1
        if m > 12:
            m, y = 1, y + 1
    return out


def saldos(con: sqlite3.Connection, anio: str = "") -> list[dict]:
    """Saldos diarios precalculados para el Dashboard (solo 'realizado').

    Con anio='2026' filtra a ese año para el selector de año del Dashboard.
    """
    if anio and len(anio) == 4 and anio.isdigit():
        return [dict(r) for r in con.execute(
            "SELECT * FROM saldos_diarios WHERE fecha LIKE ? ORDER BY fecha",
            (anio + "-%",)).fetchall()]
    return [dict(r) for r in con.execute(
        "SELECT * FROM saldos_diarios ORDER BY fecha").fetchall()]


def anios(con: sqlite3.Connection) -> list[str]:
    """Años con datos (movimientos o saldos) para poblar los selectores de año."""
    fechas: set[str] = set()
    for tabla, col in (("movimientos", "fecha_pago"), ("saldos_diarios", "fecha")):
        try:
            for (f,) in con.execute(
                    f"SELECT DISTINCT substr({col},1,4) y FROM {tabla} ORDER BY y"):
                if f and len(f) == 4 and f.isdigit():
                    fechas.add(f)
        except Exception:
            continue
    try:
        ini = con.execute("SELECT valor FROM config WHERE clave='fecha_inicio'").fetchone()
        if ini and str(ini[0])[:4].isdigit():
            fechas.add(str(ini[0])[:4])
    except Exception:
        pass
    return sorted(fechas) or [date.today().strftime("%Y")]


def flujo_por_modo(con: sqlite3.Connection, modo: str, q: dict) -> dict:
    """Arma columnas + filas + detalle para la Vista de Flujo (RN-10/RN-11, sin paginar)."""
    saldo_ini = float(con.execute(
        "SELECT valor FROM config WHERE clave='saldo_inicial_usd'").fetchone()[0])
    saldos = {r["fecha"]: dict(r) for r in
              con.execute("SELECT * FROM saldos_diarios").fetchall()}
    movs = [dict(r) for r in con.execute(
        MOV_SELECT + " WHERE m.status='realizado' ORDER BY m.fecha_pago, m.id").fetchall()]

    if modo == "trimestre":
        base = q.get("mes", [date.today().strftime("%Y-%m")])[0]
        y, m = _parse_ym(base)
        periodos = [("%04d-%02d" % ym, "%s %d" % (MESES[ym[1] - 1], ym[0]), "")
                    for ym in _sum_meses(y, m, 3)]
        def en_col(f: str, clave: str) -> bool:
            return f.startswith(clave)
    elif modo == "anual":
        anio = int(q.get("anio", [str(date.today().year)])[0])
        periodos = [("%04d-%02d" % (anio, m), "%s %d" % (MESES[m - 1], anio), "")
                    for m in range(1, 13)]
        def en_col(f: str, clave: str) -> bool:
            return f.startswith(clave)
    else:  # semana: 7 días desde 'desde' (default: hoy)
        d0 = q.get("desde", [date.today().strftime("%Y-%m-%d")])[0]
        base = datetime.strptime(d0, "%Y-%m-%d").date()
        periodos = [((base + timedelta(days=i)).strftime("%Y-%m-%d"),
                     DIAS[(base + timedelta(days=i)).weekday()],
                     (base + timedelta(days=i)).strftime("%d/%m"))
                    for i in range(7)]
        def en_col(f: str, clave: str) -> bool:
            return f == clave

    # Acumulado previo al primer periodo (arrastre)
    primera = periodos[0][0]
    prev = [s for f, s in saldos.items() if f < primera]
    arrastre = max(prev, key=lambda s: s["fecha"])["acumulado_usd"] if prev else saldo_ini

    columnas, ing, egr, det_ing, det_egr = [], [], [], {}, {}
    acum = arrastre
    for clave, titulo, subtitulo in periodos:
        col_movs = [x for x in movs if en_col(x["fecha_pago"], clave)]
        i = sum(x["valor_usd"] for x in col_movs if x["tipo"] == "ingreso")
        e = sum(x["valor_usd"] for x in col_movs if x["tipo"] == "egreso")
        neto = i - e
        acum = acum + neto
        columnas.append({"clave": clave, "titulo": titulo, "subtitulo": subtitulo,
                         "saldo_inicial": round(acum - neto, 2), "ing": round(i, 2),
                         "egr": round(e, 2), "neto": round(neto, 2),
                         "acumulado": round(acum, 2)})
        ing.append(i)
        egr.append(e)
        det_ing[clave] = [x for x in col_movs if x["tipo"] == "ingreso"]
        det_egr[clave] = [x for x in col_movs if x["tipo"] == "egreso"]
    return {"modo": modo, "columnas": columnas,
            "detalle_ingresos": det_ing, "detalle_egresos": det_egr}
