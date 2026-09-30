"""importar.py — ETL: Excel fuente -> SQLite portable (USD).

Solo se ejecuta al importar (primer arranque o re-importación).
En runtime la app NUNCA lee el .xlsx: consulta la BD vía API.

Formato aceptado (hoja 'Movimientos', RF-10 / RN-09):
  banco | fecha_pago | tipo | tipo_pago | entidad | concepto_pago | centro_costo | valor_usd | status | observacion

Catálogos cerrados:
  tipo: ingreso, egreso
  tipo_pago: efectivo, transferencia, cheque
  concepto_pago: nomina, prestamo (extensible solo por migración)
  status: pendiente, aplazado, realizado (solo 'realizado' suma al flujo)

Uso (desde backend/):
  python -m etl.importar plantilla.xlsx --db ..\\database\\tesoreria.db
  python -m etl.importar --plantilla  (genera database\\plantilla_flujo.xlsx)
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from datetime import date, datetime
from pathlib import Path

from etl.plantilla import crear_plantilla
from nucleo.basedatos import conectar
from nucleo.rutas import DB_DIR

COLUMNAS = ["banco", "fecha_pago", "tipo", "tipo_pago", "entidad",
            "concepto_pago", "centro_costo", "valor_usd", "status", "observacion"]
TIPOS = {"ingreso", "egreso"}
TIPOS_PAGO = {"efectivo", "transferencia", "cheque"}
STATUS = {"pendiente", "aplazado", "realizado", "vencido"}


def _norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _fecha(v) -> str:
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    s = _norm(v)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    raise ValueError(f"fecha_pago inválida: {v!r} (use YYYY-MM-DD o DD/MM/YYYY)")


def leer_filas(excel_path: Path) -> list[dict]:
    try:
        from openpyxl import load_workbook
    except ImportError:
        sys.exit("Falta openpyxl: pip install openpyxl")
    wb = load_workbook(str(excel_path), data_only=True)
    if "Movimientos" not in wb.sheetnames:
        sys.exit(f"Hoja 'Movimientos' no encontrada en {excel_path.name}. "
                 "Descargue la plantilla con: python -m etl.importar --plantilla")
    ws = wb["Movimientos"]
    header = [_norm(c.value).lower() for c in next(ws.iter_rows(min_row=1, max_row=1))]
    if header[:10] != COLUMNAS:
        sys.exit(f"Columnas inválidas: {header[:10]}. Esperadas: {COLUMNAS}")
    filas = []
    for i, row in enumerate(ws.iter_rows(min_row=2, values_only=True), start=2):
        if all(v in (None, "") for v in row):
            continue
        d = dict(zip(COLUMNAS, list(row) + [""] * (len(COLUMNAS) - len(row))))
        d["_fila"] = i
        filas.append(d)
    return filas


def validar(d: dict) -> list[str]:
    err = []
    f = d["_fila"]
    try:
        _fecha(d["fecha_pago"])
    except ValueError as e:
        err.append(f"{e} (fila {f})")
    if _norm(d["tipo"]).lower() not in TIPOS:
        err.append(f"tipo debe ser ingreso/egreso (fila {f})")
    if _norm(d["tipo_pago"]).lower() not in TIPOS_PAGO:
        err.append(f"tipo_pago debe ser efectivo/transferencia/cheque (fila {f})")
    if not _norm(d["concepto_pago"]):
        err.append(f"concepto_pago vacío (fila {f})")
    if _norm(d["status"]).lower() not in STATUS:
        err.append(f"status debe ser pendiente/aplazado/realizado/vencido (fila {f})")
    try:
        m = float(str(d["valor_usd"]).replace(",", "").replace("$", ""))
        if m <= 0:
            err.append(f"valor_usd debe ser > 0 (fila {f})")
    except (ValueError, TypeError):
        err.append(f"valor_usd inválido (fila {f})")
    if not _norm(d["banco"]):
        err.append(f"banco vacío (fila {f})")
    return err


def importar(excel_path: Path, db_path: Path, nombre_original: str | None = None) -> dict:
    filas = leer_filas(excel_path)
    mostrado = nombre_original or excel_path.name
    con = conectar(db_path)
    ok, errores = 0, []
    with con:
        for d in filas:
            err = validar(d)
            if err:
                errores.extend(err)
                continue
            fecha = _fecha(d["fecha_pago"])
            tipo = _norm(d["tipo"]).lower()
            tipo_pago = _norm(d["tipo_pago"]).lower()
            concepto = _norm(d["concepto_pago"]).lower()
            status = _norm(d["status"]).lower() or "pendiente"
            con.execute("INSERT OR IGNORE INTO conceptos (nombre) VALUES (?)", (concepto,))
            con_id = con.execute("SELECT id FROM conceptos WHERE nombre=?", (concepto,)).fetchone()[0]
            ent_id = None
            if _norm(d["entidad"]):
                et = "cliente" if tipo == "ingreso" else "proveedor"
                con.execute("INSERT OR IGNORE INTO entidades (tipo, nombre) VALUES (?,?)",
                            (et, _norm(d["entidad"])))
                ent_id = con.execute("SELECT id FROM entidades WHERE nombre=?",
                                     (_norm(d["entidad"]),)).fetchone()[0]
            banco = _norm(d["banco"])
            cta = con.execute("SELECT id FROM cuentas WHERE banco=?",
                              (banco,)).fetchone()
            if cta is None:
                con.execute("INSERT INTO cuentas (banco) VALUES (?)", (banco,))
                cta_id = con.execute("SELECT id FROM cuentas WHERE banco=?",
                                     (banco,)).fetchone()[0]
            else:
                cta_id = cta[0]
            valor = float(str(d["valor_usd"]).replace(",", "").replace("$", ""))
            dup = con.execute(
                "SELECT 1 FROM movimientos WHERE fecha_pago=? AND tipo=? AND concepto_id=? "
                "AND IFNULL(entidad_id,-1)=IFNULL(?, -1) AND cuenta_id=? AND valor_usd=?"
                " AND centro_costo=? AND observacion=?",
                (fecha, tipo, con_id, ent_id, cta_id, valor,
                 _norm(d["centro_costo"]), _norm(d["observacion"]))).fetchone()
            if dup:
                continue
            con.execute(
                "INSERT INTO movimientos (fecha_pago, tipo, tipo_pago, concepto_id, entidad_id,"
                " cuenta_id, centro_costo, valor_usd, status, observacion)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (fecha, tipo, tipo_pago, con_id, ent_id, cta_id,
                 _norm(d["centro_costo"]), valor, status, _norm(d["observacion"])))
            ok += 1
        con.execute("INSERT INTO import_log (archivo, filas_ok, filas_error) VALUES (?,?,?)",
                    (mostrado, ok, len(errores)))
    recalcular_saldos(con)
    con.close()
    return {"filas_ok": ok, "errores": errores, "archivo": mostrado}


def recalcular_saldos(con: sqlite3.Connection) -> None:
    """Reconstruye saldos_diarios desde movimientos REALIZADOS + saldo inicial."""
    saldo_ini = float(con.execute("SELECT valor FROM config WHERE clave='saldo_inicial_usd'").fetchone()[0])
    con.execute("DELETE FROM saldos_diarios")
    cur = con.execute(
        "SELECT fecha_pago, SUM(CASE WHEN tipo='ingreso' THEN valor_usd ELSE 0 END) ing,"
        " SUM(CASE WHEN tipo='egreso' THEN valor_usd ELSE 0 END) egr"
        " FROM movimientos WHERE status='realizado' GROUP BY fecha_pago ORDER BY fecha_pago")
    primero = True
    acum = saldo_ini
    for fecha, ing, egr in cur.fetchall():
        neto = (ing or 0) - (egr or 0)
        acum = saldo_ini + neto if primero else acum + neto
        primero = False
        con.execute("INSERT INTO saldos_diarios (fecha, ing, egr, neto, acumulado_usd)"
                    " VALUES (?,?,?,?,?)", (fecha, ing or 0, egr or 0, neto, acum))
    con.commit()
    recalcular_saldos_cuenta(con)


def recalcular_saldos_cuenta(con: sqlite3.Connection) -> None:
    """Reconstruye saldos_diarios_cuenta: apertura 31-jul + realizados por cuenta."""
    con.execute("DELETE FROM saldos_diarios_cuenta")
    for cta in con.execute("SELECT id, saldo_apertura_usd FROM cuentas").fetchall():
        apertura = cta["saldo_apertura_usd"] or 0
        cur = con.execute(
            "SELECT fecha_pago, SUM(CASE WHEN tipo='ingreso' THEN valor_usd ELSE 0 END) ing,"
            " SUM(CASE WHEN tipo='egreso' THEN valor_usd ELSE 0 END) egr"
            " FROM movimientos WHERE status='realizado' AND cuenta_id=?"
            " GROUP BY fecha_pago ORDER BY fecha_pago", (cta["id"],))
        acum = apertura
        for fecha, ing, egr in cur.fetchall():
            neto = (ing or 0) - (egr or 0)
            acum = round(acum + neto, 2)
            con.execute("INSERT INTO saldos_diarios_cuenta"
                        " (fecha, cuenta_id, ing, egr, neto, acumulado_usd)"
                        " VALUES (?,?,?,?,?,?)",
                        (fecha, cta["id"], ing or 0, egr or 0, neto, acum))
    con.commit()


def main() -> None:
    ap = argparse.ArgumentParser(description="ETL Excel -> SQLite (USD)")
    ap.add_argument("excel", nargs="?", help="Archivo .xlsx a importar")
    ap.add_argument("--db", default=str(DB_DIR / "tesoreria.db"))
    ap.add_argument("--plantilla", action="store_true", help="Generar plantilla_flujo.xlsx")
    args = ap.parse_args()
    if args.plantilla:
        out = crear_plantilla(DB_DIR / "plantilla_flujo.xlsx")
        print(f"Plantilla generada: {out}")
        return
    if not args.excel:
        ap.error("Indique el .xlsx o use --plantilla")
    res = importar(Path(args.excel), Path(args.db))
    print(f"OK: {res['filas_ok']} filas importadas.")
    for e in res["errores"][:20]:
        print("  !", e)
    if len(res["errores"]) > 20:
        print(f"  ... y {len(res['errores']) - 20} errores más.")


if __name__ == "__main__":
    main()
