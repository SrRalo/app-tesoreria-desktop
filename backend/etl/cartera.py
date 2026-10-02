"""cartera.py — conversor CXP/CXC (antigüedad de cartera) -> plantilla/BD.

Lee los libros de LARDEMA (`31082026CXC 306090.xls` y `31082026CXP 306090.xls`,
que son .xlsx renombrados) y genera filas con el formato de `importar.py`
(banco|fecha_pago|tipo|tipo_pago|entidad|concepto|centro_costo|valor|status|obs).

Mapeo (ver informe_atributos_CXP_CXC.md §5):
  Nombre -> entidad | Fecha Vence -> fecha_pago | abs(Saldo) -> valor_usd
  CXC -> ingreso/cobranza_clientes | CXP -> egreso/pago_proveedores
  banco=PorDefinir | tipo_pago=transferencia | Centro C. -> centro_costo
  Numero/Cod Asiento/Fecha/Proyecto/Bucket -> observacion
  Vendedor y col. vacía se descartan | última fila (totales) se filtra.

Uso (desde backend/):
  python -m etl.cartera CXC.xls CXP.xls --corte 2026-08-31 --out plantilla_cargada.xlsx
  python -m etl.cartera CXC.xls CXP.xls --corte 2026-08-31 --db ..\\database\\tesoreria.db
"""
from __future__ import annotations

import argparse
import io
import re
from datetime import date, datetime
from pathlib import Path

from etl.normalizar import limpiar_texto as _norm, parse_fecha, parse_monto

BANCO_DEFAULT = "PorDefinir"
TIPO_PAGO_DEFAULT = "transferencia"
CONCEPTO_CXC = "cobranza_clientes"
CONCEPTO_CXP = "pago_proveedores"


def _fecha_iso(v) -> str:
    iso, _ = parse_fecha(v)
    if not iso or iso == "1900-01-01":
        raise ValueError(f"fecha inválida: {v!r}")
    return iso


def _num(v) -> float:
    n, _ = parse_monto(v)
    return n


def _es_totales(nombre, numero) -> bool:
    t = (_norm(nombre) + " " + _norm(numero)).lower()
    return "total" in t and _norm(numero) == ""


def leer_cartera(path: Path, tipo: str, corte: str,
                 status_vencido: str = "vencido") -> tuple[list[dict], list[str]]:
    """Lee un libro CXP/CXC (.xlsx o .xls BIFF real) y devuelve filas + errores."""
    raw = Path(path).read_bytes()
    suf = Path(path).suffix.lower()
    nombre = Path(path).name
    filas, errores = [], []
    concepto = CONCEPTO_CXC if tipo == "ingreso" else CONCEPTO_CXP

    def _procesa(matriz: list[list], hoja: str):
        nonlocal filas, errores
        # salta títulos: primera fila con "nombre"-like en col 0 dentro de las 5 primeras
        inicio = 0
        for i, r in enumerate(matriz[:5]):
            t = _norm((r[0] if r else "")).lower()
            if t in ("nombre", "cliente", "proveedor", "nombre cliente"):
                inicio = i + 1
                break
        else:
            inicio = 2  # formato clásico: 2 filas de título
        for i, row in enumerate(matriz[inicio:], start=inicio + 1):
            vals = list(row) + [None] * (17 - len(list(row)))
            nombre = _norm(vals[0])
            if not nombre or _es_totales(vals[0], vals[4]):
                continue  # título/total o fila vacía
            try:
                fecha_vence = _fecha_iso(vals[7])
                saldo = _num(vals[9])
                if saldo == 0:
                    continue
                vencido = _num(vals[10])
                por_vencer = _num(vals[11])
                buckets = {"30": _num(vals[12]), "60": _num(vals[13]),
                           "90": _num(vals[14]), "120": _num(vals[15])}
                bucket = next((k for k, v in buckets.items() if abs(v) > 0.005), "")
                # signo invertido: anticipo cliente (CXC negativo) o pago a favor (CXP positivo)
                ajuste = ""
                if (tipo == "ingreso" and saldo < 0) or (tipo == "egreso" and saldo > 0):
                    ajuste = " AJUSTE-SIGNO"
                obs = (f"[{'CXC' if tipo == 'ingreso' else 'CXP'}]"
                       f" Num:{_norm(vals[4]) or '—'} Asi:{_norm(vals[5]) or '—'}"
                       f" Emi:{_norm(vals[6]) or '—'}"
                       f" Proy:{_norm(vals[2]) or '—'}"
                       + (f" Bucket:{bucket}d" if bucket else "") + ajuste)
                status = "pendiente"
                if fecha_vence <= corte:
                    status = status_vencido if status_vencido in ("vencido", "realizado", "pendiente") else "vencido"
                filas.append({
                    "banco": BANCO_DEFAULT, "fecha_pago": fecha_vence, "tipo": tipo,
                    "tipo_pago": TIPO_PAGO_DEFAULT, "entidad": nombre,
                    "concepto_pago": concepto, "centro_costo": _norm(vals[1]),
                    "valor_usd": round(abs(saldo), 2), "status": status,
                    "observacion": obs[:500],
                    "_vencido": vencido, "_por_vencer": por_vencer,
                })
            except Exception as e:
                errores.append(f"{nombre} fila {i} ({nombre}): {e}")

    # .xls BIFF real (xlrd) o .xlsx renombrado (openpyxl); xls próximos del banco
    try:
        if suf == ".xls":
            try:
                import xlrd
                bk = xlrd.open_workbook(file_contents=raw, on_demand=True)
                try:
                    sh = bk.sheet_by_name("Sheet" if "Sheet" in bk.sheet_names() else bk.sheet_names()[0])
                    matriz = [[sh.cell(r, c).value for c in range(sh.ncols)]
                              for r in range(sh.nrows)]
                finally:
                    bk.release_resources()
                _procesa(matriz, "Sheet")
            except ImportError:
                errores.append(f"{nombre}: falta xlrd para .xls real (pip install xlrd)")
        else:
            from openpyxl import load_workbook
            wb = load_workbook(io.BytesIO(raw), data_only=True, read_only=True)
            try:
                ws = wb["Sheet" if "Sheet" in wb.sheetnames else wb.sheetnames[0]]
                _procesa([list(r) for r in ws.iter_rows(values_only=True)], ws.title)
            finally:
                wb.close()
    except Exception as e:
        return [], [f"{nombre}: no se pudo abrir ({e})"]
    return filas, errores


def convertir(cxc: Path | None, cxp: Path | None, corte: str = "2026-08-31",
              status_vencido: str = "vencido") -> tuple[list[dict], list[str]]:
    filas, errores = [], []
    if cxc:
        f, e = leer_cartera(cxc, "ingreso", corte, status_vencido)
        filas += f
        errores += e
    if cxp:
        f, e = leer_cartera(cxp, "egreso", corte, status_vencido)
        filas += f
        errores += e
    filas.sort(key=lambda d: (d["fecha_pago"], d["entidad"]))
    return filas, errores


def a_xlsx(filas: list[dict], destino: Path) -> Path:
    from openpyxl import Workbook
    from etl.importar import COLUMNAS
    wb = Workbook()
    ws = wb.active
    ws.title = "Movimientos"
    ws.append(COLUMNAS)
    for d in filas:
        ws.append([d[c] for c in COLUMNAS])
    destino = Path(destino)
    wb.save(str(destino))
    return destino


def main() -> None:
    ap = argparse.ArgumentParser(description="CXP/CXC -> plantilla/BD (USD)")
    ap.add_argument("cxc", nargs="?", help="Libro CXC (cobrar)")
    ap.add_argument("cxp", nargs="?", help="Libro CXP (pagar)")
    ap.add_argument("--corte", default="2026-08-31",
                    help="Fecha Vence <= corte se marca realizado (default 2026-08-31)")
    ap.add_argument("--status-vencido", default="vencido",
                    choices=["vencido", "realizado", "pendiente"],
                    help="Status para vencidos históricos (default vencido: solo alerta, no suma)")
    ap.add_argument("--out", default="plantilla_cargada.xlsx")
    ap.add_argument("--db", default=None, help="Si se indica, importa directo a la BD")
    args = ap.parse_args()
    if not args.cxc and not args.cxp:
        ap.error("Indique al menos un libro CXP o CXC")
    filas, errores = convertir(
        Path(args.cxc) if args.cxc else None,
        Path(args.cxp) if args.cxp else None,
        corte=args.corte, status_vencido=args.status_vencido)
    out = a_xlsx(filas, Path(args.out))
    print(f"OK: {len(filas)} filas -> {out}")
    for e in errores[:20]:
        print("  !", e)
    if len(errores) > 20:
        print(f"  ... y {len(errores) - 20} errores más.")
    if args.db:
        from etl.importar import importar
        res = importar(out, Path(args.db))
        print(f"Importadas {res['filas_ok']} filas a {args.db}.")


if __name__ == "__main__":
    main()
