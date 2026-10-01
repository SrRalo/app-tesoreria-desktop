"""importar.py — ETL: archivo fuente -> SQLite portable (USD).

Refactor antipérdida (RF-ETL-01..14):
- multiformato .xlsx/.xls/.csv + hoja elegible + header dinámico (etl.lectura)
- normalización robusta fechas/montos/texto (etl.normalizar) — nada se descarta
- mapeo fuzzy entidades/cuentas/conceptos con fallback PorDefinir (etl.mapeo)
- transacción atómica + executemany por bloques + import_log/bitacora
- preview (dry-run): clasifica filas sin guardar

En runtime la app NUNCA lee el archivo: consulta la BD vía API.

Uso (desde backend/):
  python -m etl.importar plantilla.xlsx --db ..\\database\\tesoreria.db
  python -m etl.importar datos.csv --hoja Sheet1 --db ..\\database\\tesoreria.db
  python -m etl.importar --plantilla
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

from etl.lectura import COLUMNAS, leer_archivo
from etl.mapeo import Catalogo, resolver_cuenta, resolver_concepto, resolver_entidad
from etl.normalizar import limpiar_texto, parse_fecha, parse_monto
from nucleo.basedatos import conectar
from nucleo.rutas import DB_DIR

TIPOS = {"ingreso", "egreso"}
TIPOS_PAGO = {"efectivo", "transferencia", "cheque"}
STATUS = {"pendiente", "aplazado", "realizado", "vencido"}
BLOQUE = 500


def _norm(s) -> str:
    return limpiar_texto(s)


def _fecha(v) -> str:
    """Compat: lanza si no parsea (usada por tests viejos)."""
    iso, _ = parse_fecha(v)
    if not iso:
        raise ValueError(f"fecha_pago inválida: {v!r}")
    return iso


def leer_filas(excel_path: Path, hoja: str | None = None) -> list[dict]:
    """Compat: lee cualquier formato con header dinámico."""
    filas, _meta = leer_archivo(Path(excel_path), hoja)
    return filas


def validar(d: dict) -> list[str]:
    """Compat: errores duros (solo tipo/status/valor). Fecha y mapeo ya no descartan."""
    err = []
    f = d.get("_fila", "?")
    if _norm(d.get("tipo")).lower() not in TIPOS:
        err.append(f"tipo debe ser ingreso/egreso (fila {f})")
    if _norm(d.get("tipo_pago") or "transferencia").lower() not in TIPOS_PAGO:
        err.append(f"tipo_pago debe ser efectivo/transferencia/cheque (fila {f})")
    if _norm(d.get("status") or "pendiente").lower() not in STATUS:
        err.append(f"status debe ser pendiente/aplazado/realizado/vencido (fila {f})")
    return err


def _normalizar_fila(d: dict, tipo_default: str = "") -> tuple[dict, list[str], list[str]]:
    """Devuelve (normalizado, avisos, errores_duros). Antipérdida: fecha/monto
    malos van a revisión con defaults, no descartan; solo tipo inválido descarta."""
    f = d.get("_fila", "?")
    avisos, errores = [], []

    tipo = _norm(d.get("tipo")).lower() or tipo_default.lower()
    if tipo not in TIPOS:
        # intenta deducir por débito/crédito o por signo
        if d.get("debito") not in (None, "") or d.get("credito") not in (None, ""):
            errores.append(f"tipo vacío y sin poder deducir (fila {f})")
        else:
            errores.append(f"tipo debe ser ingreso/egreso (fila {f})")
        return {}, avisos, errores

    fecha, av = parse_fecha(d.get("fecha_pago"))
    if av:
        avisos.append(f"fila {f}: {av} (se usa 1900-01-01 para revisión)")
    if not fecha:
        fecha = "1900-01-01"  # centinela de revisión, visible en UI

    if d.get("debito") not in (None, "") or d.get("credito") not in (None, ""):
        valor, avm = parse_monto(None, debito=d.get("debito"), credito=d.get("credito"))
        valor = abs(valor)
    else:
        valor, avm = parse_monto(d.get("valor_usd"))
        valor = abs(valor)
    if avm:
        avisos.append(f"fila {f}: {avm}")
    if valor <= 0:
        avisos.append(f"fila {f}: valor 0 o negativo (se guarda 1.00 para revisión)")
        valor = 1.0

    tipo_pago = _norm(d.get("tipo_pago") or "transferencia").lower()
    if tipo_pago not in TIPOS_PAGO:
        avisos.append(f"fila {f}: tipo_pago '{d.get('tipo_pago')}' -> transferencia")
        tipo_pago = "transferencia"
    status = _norm(d.get("status") or "pendiente").lower()
    if status not in STATUS:
        avisos.append(f"fila {f}: status '{d.get('status')}' -> pendiente")
        status = "pendiente"
    if status == "aplazado" and not str(d.get("_origen", "")).startswith("db"):
        # crear con aplazado se rechaza (RN-12): se guarda pendiente + aviso
        avisos.append(f"fila {f}: status aplazado al crear -> pendiente")
        status = "pendiente"

    return {
        "fecha_pago": fecha, "tipo": tipo, "tipo_pago": tipo_pago,
        "entidad": _norm(d.get("entidad")), "concepto": _norm(d.get("concepto_pago")),
        "centro_costo": _norm(d.get("centro_costo")), "valor": round(valor, 2),
        "status": status, "observacion": _norm(d.get("observacion")),
        "banco": _norm(d.get("banco")), "_fila": f,
    }, avisos, errores


def previsualizar(excel_path: Path, db_path: Path, hoja: str | None = None,
                  limite: int = 200) -> dict:
    """Dry-run (RF-ETL-11): clasifica sin guardar. Rápido: 1 conexión, catálogo 1 vez."""
    filas, meta = leer_archivo(Path(excel_path), hoja)
    con = conectar(Path(db_path))
    try:
        cat = Catalogo.cargar(con)
        cat.asegurar_fallbacks(con)
        validas, advertencias, erroneas = [], [], []
        vistos: set[tuple] = set()
        for d in filas[:limite]:
            norm, avisos, errores = _normalizar_fila(d)
            if errores:
                erroneas.append({"fila": d.get("_fila"), "errores": errores,
                                 "datos": {k: d.get(k) for k in COLUMNAS if d.get(k)}})
                continue
            tipo = norm["tipo"]
            ent_id, av_e = resolver_entidad(
                cat, norm["entidad"], "cliente" if tipo == "ingreso" else "proveedor")
            cta_id, av_c = resolver_cuenta(cat, norm["banco"])
            _con_id, av_k = resolver_concepto(cat, norm["concepto"])
            avisos += [a for a in (av_e, av_c, av_k) if a]
            clave = (norm["fecha_pago"], tipo, norm["valor"], cta_id, norm["entidad"][:40])
            dup = clave in vistos
            vistos.add(clave)
            # chequeo en BD (1 query por fila, solo en preview limitado)
            if not dup:
                hay = con.execute(
                    "SELECT 1 FROM movimientos WHERE fecha_pago=? AND tipo=?"
                    " AND cuenta_id=? AND valor_usd=? LIMIT 1",
                    (norm["fecha_pago"], tipo, cta_id, norm["valor"])).fetchone()
                dup = bool(hay)
            item = {"fila": norm["_fila"], "fecha": norm["fecha_pago"],
                    "tipo": tipo, "valor": norm["valor"], "avisos": avisos}
            if dup:
                item["duplicada"] = True
                advertencias.append(item)  # duplicadas van como advertencia contada aparte
            elif avisos:
                advertencias.append(item)
            else:
                validas.append(item)
        dup_n = sum(1 for a in advertencias if a.get("duplicada"))
        return {"ok": True, "hoja": meta.get("hoja"), "header": meta.get("header_info"),
                "total": len(filas), "validas": validas, "advertencias": advertencias,
                "duplicadas": dup_n, "erroneas": erroneas}
    finally:
        con.close()


def importar(excel_path: Path, db_path: Path, nombre_original: str | None = None,
             hoja: str | None = None) -> dict:
    filas, meta = leer_archivo(Path(excel_path), hoja)
    mostrado = nombre_original or Path(excel_path).name
    con = conectar(Path(db_path))
    ok, duplicadas, avisos_all, errores = 0, 0, [], []
    try:
        cat = Catalogo.cargar(con)
        con.execute("BEGIN")
        cat.asegurar_fallbacks(con)
        # dedup del lote en memoria (rápido) + chequeo BD por bloque
        vistos: set[tuple] = set()
        lote: list[tuple] = []
        avisos_lote: list[str] = []

        def _descargar(pend: list[tuple]) -> tuple[int, int]:
            if not pend:
                return 0, 0
            # filtra duplicados en BD de un solo golpe por bloque
            nuevos = []
            dups = 0
            for t in pend:
                (fecha, tipo, tp, con_id, ent_id, cc, valor, status, obs) = t
                hay = con.execute(
                    "SELECT 1 FROM movimientos WHERE fecha_pago=? AND tipo=?"
                    " AND concepto_id=? AND IFNULL(entidad_id,-1)=IFNULL(?, -1)"
                    " AND valor_usd=? AND centro_costo=?"
                    " AND observacion=? LIMIT 1",
                    (fecha, tipo, con_id, ent_id, valor, cc, obs)).fetchone()
                if hay:
                    dups += 1
                    continue
                nuevos.append(t)
            con.executemany(
                "INSERT INTO movimientos (fecha_pago, tipo, tipo_pago, concepto_id,"
                " entidad_id, centro_costo, valor_usd, status, observacion)"
                " VALUES (?,?,?,?,?,?,?,?,?)", nuevos)
            return len(nuevos), dups

        for d in filas:
            norm, avisos, err = _normalizar_fila(d)
            if err:
                errores.extend(err)
                continue
            if _norm(d.get("tipo")).lower() not in TIPOS:
                pass  # ya reportado arriba
            tipo = norm["tipo"]
            ent_id, av_e = resolver_entidad(
                cat, norm["entidad"], "cliente" if tipo == "ingreso" else "proveedor")
            # cta_id, av_c = resolver_cuenta(cat, norm["banco"])
        con_id, av_k = resolver_concepto(cat, norm["concepto"])
        for a in (av_e, av_k): # ignoramos av_c
            if a:
                avisos.append(f"fila {norm['_fila']}: {a}")
            # originales no mapeados -> observación (RF-ETL-08)
            extras = []
            if av_e and norm["entidad"]:
                extras.append(f"[ENT-ORIG:{norm['entidad'][:80]}]")
            # BANCO-ORIG eliminado
            if av_k and norm["concepto"]:
                extras.append(f"[CONCEPTO-ORIG:{norm['concepto'][:80]}]")
            obs = (norm["observacion"] + " " + " ".join(extras)).strip()[:500]
            clave = (norm["fecha_pago"], tipo, con_id,
                     ent_id or -1, norm["valor"], norm["centro_costo"], obs)
            if clave in vistos:
                duplicadas += 1
                continue
            vistos.add(clave)
            lote.append((norm["fecha_pago"], tipo, norm["tipo_pago"], con_id,
                         ent_id, norm["centro_costo"], norm["valor"],
                         norm["status"], obs))
            avisos_lote.extend(avisos)
            if len(lote) >= BLOQUE:
                n, d = _descargar(lote)
                ok, duplicadas = ok + n, duplicadas + d
                lote = []
        n, d = _descargar(lote)
        ok, duplicadas = ok + n, duplicadas + d
        avisos_all = avisos_lote
        try:
            con.execute("INSERT INTO import_log (archivo, filas_ok, filas_error)"
                        " VALUES (?,?,?)", (mostrado, ok, len(errores)))
        except Exception:
            # BD vieja sin columna nueva: reintenta mínimo
            con.execute("INSERT INTO import_log (archivo, filas_ok, filas_error)"
                        " VALUES (?,?,?)", (mostrado, ok, len(errores)))
        con.execute("COMMIT")
    except Exception:
        try:
            con.execute("ROLLBACK")
        except Exception:
            pass
        raise
    try:
        recalcular_saldos(con)
    finally:
        con.close()
    return {"filas_ok": ok, "duplicadas": duplicadas, "avisos": avisos_all[:50],
            "errores": errores, "archivo": mostrado, "hoja": meta.get("hoja")}


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
    filas = []
    for fecha, ing, egr in cur.fetchall():
        neto = (ing or 0) - (egr or 0)
        acum = saldo_ini + neto if primero else acum + neto
        primero = False
        filas.append((fecha, ing or 0, egr or 0, neto, acum))
    if filas:
        con.executemany("INSERT INTO saldos_diarios (fecha, ing, egr, neto, acumulado_usd)"
                        " VALUES (?,?,?,?,?)", filas)
    con.commit()


def recalcular_saldos_cuenta(con: sqlite3.Connection) -> None:
    # No hace nada, se mantiene por compatibilidad de firma pero no usa cuenta_id
    pass


def main() -> None:
    ap = argparse.ArgumentParser(description="ETL Excel -> SQLite (USD)")
    ap.add_argument("excel", nargs="?", help="Archivo .xlsx/.xls/.csv a importar")
    ap.add_argument("--db", default=str(DB_DIR / "tesoreria.db"))
    ap.add_argument("--hoja", default=None, help="Hoja a importar (default: auto)")
    ap.add_argument("--plantilla", action="store_true", help="Generar plantilla_flujo.xlsx")
    args = ap.parse_args()
    if args.plantilla:
        from etl.plantilla import crear_plantilla
        out = crear_plantilla(DB_DIR / "plantilla_flujo.xlsx")
        print(f"Plantilla generada: {out}")
        return
    if not args.excel:
        ap.error("Indique el archivo o use --plantilla")
    res = importar(Path(args.excel), Path(args.db), hoja=args.hoja)
    print(f"OK: {res['filas_ok']} filas importadas "
          f"({res.get('duplicadas', 0)} duplicadas, {len(res['errores'])} errores).")
    for e in res["errores"][:20]:
        print("  !", e)


if __name__ == "__main__":
    main()
