"""internacional.py — estado de cuenta Banco Internacional (BIFF .xls real).

Se lee con xlrd (openpyxl no abre BIFF). Hoja única, encabezado en la fila 4:
Fecha | Cod | Descripción | Referencia Adicional | Débito | Crédito | Saldo | Ciudad.
Sin encabezado de corte: la apertura se infiere del primer saldo.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from etl.extractos.base import norm, num


def _fecha(v) -> str | None:
    if isinstance(v, (int, float)):
        return None
    s = norm(v)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parsear(path: Path) -> dict:
    import xlrd
    bk = xlrd.open_workbook(str(path))
    sh = bk.sheet_by_index(0)

    numero = ""
    for r in range(min(4, sh.nrows)):
        for c in range(sh.ncols):
            s = norm(sh.cell(r, c).value)
            if "Cuenta" in s and c + 1 < sh.ncols:
                numero = norm(sh.cell(r, c + 1).value).split()[0]

    # Encabezado real (Fecha/Cod/Descripción/...) — no asumir número de fila.
    h = None
    for r in range(sh.nrows):
        row = [norm(sh.cell(r, c).value).lower() for c in range(sh.ncols)]
        if any("fecha" in c for c in row) and any("bito" in c or "dito" in c for c in row):
            h = r
            break
    if h is None:
        raise ValueError("No se encontró el encabezado Fecha/Cod/Descripción")

    head = [norm(sh.cell(h, c).value).lower() for c in range(sh.ncols)]

    def col(*nombres):
        for i, c in enumerate(head):
            if any(n in c for n in nombres):
                return i
        return -1

    i_fec, i_cod = col("fecha"), col("cod")
    i_des = col("descrip")
    i_ref = col("referencia", "adicional")
    i_deb = col("bito")
    i_cre = col("dito")
    i_sal = col("saldo")

    lineas = []
    for r in range(h + 1, sh.nrows):
        fecha = _fecha(sh.cell(r, i_fec).value) if i_fec >= 0 else None
        if not fecha:
            continue
        debito = num(sh.cell(r, i_deb).value) if i_deb >= 0 else 0.0
        credito = num(sh.cell(r, i_cre).value) if i_cre >= 0 else 0.0
        if debito == 0 and credito == 0:
            continue
        saldo = num(sh.cell(r, i_sal).value) if i_sal >= 0 else 0.0
        desc = norm(sh.cell(r, i_cod).value) + " " + norm(sh.cell(r, i_des).value)
        lineas.append({"fecha": fecha, "descripcion": desc.strip(),
                       "referencia": norm(sh.cell(r, i_ref).value) if i_ref >= 0 else "",
                       "debito": debito, "credito": credito,
                       "saldo_banco": saldo or None})

    if not lineas:
        raise ValueError("Sin movimientos en el extracto Internacional")

    # Apertura inferida: primer saldo menos su neto (no hay corte explícito).
    primero = lineas[0]
    saldo_anterior = round(primero["saldo_banco"] - (primero["credito"] - primero["debito"]), 2)
    saldo_actual = lineas[-1]["saldo_banco"]
    periodo_fin = max(ln["fecha"] for ln in lineas)
    periodo_inicio = periodo_fin[:8] + "01"
    depositos = round(sum(ln["credito"] for ln in lineas), 2)
    retiros = round(sum(ln["debito"] for ln in lineas), 2)
    return {"banco": "Internacional", "numero": numero,
            "periodo_inicio": periodo_inicio, "periodo_fin": periodo_fin,
            "saldo_anterior": saldo_anterior, "saldo_actual": saldo_actual,
            "depositos": depositos, "retiros": retiros, "lineas": lineas}
