"""produbanco.py — estado de cuenta Produbanco (.xlsx moderno).

Hoja ReporteDetalleCuentaSC: encabezado en fila 13
(Fecha | Referencia | Transacción | Signo (+/-) | Valor | Saldo Contable).
Sin corte explícito de apertura: se infiere del primer saldo.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from etl.extractos.base import norm, num


def _fecha(v) -> str | None:
    if isinstance(v, (datetime, date)):
        return v.strftime("%Y-%m-%d")
    s = norm(v)
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(s[:10], fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parsear(path: Path) -> dict:
    from openpyxl import load_workbook
    wb = load_workbook(str(path), data_only=True, read_only=True)
    ws = wb[wb.sheetnames[0]]

    numero = ""
    for r in range(1, 13):
        vals = [norm(ws.cell(r, c).value) for c in range(1, 15)]
        fila = " ".join(vals)
        if fila.startswith("CUENTA:"):
            for v in vals:
                d = "".join(ch for ch in v if ch.isdigit())
                if len(d) >= 6:
                    numero = d
                    break

    # Encabezado real (Fecha/Referencia/Transacción/Signo/Valor/Saldo).
    h = None
    for r in range(1, 20):
        vals = [norm(ws.cell(r, c).value).lower() for c in range(1, 15)]
        if any(v == "fecha" for v in vals) and any("saldo" in v for v in vals):
            h = r
            break
    if h is None:
        raise ValueError("No se encontró el encabezado del reporte Produbanco")

    head = [norm(ws.cell(h, c).value).lower() for c in range(1, 15)]

    def col(*nombres):
        for i, c in enumerate(head, start=1):
            if any(n in c for n in nombres):
                return i
        return -1

    i_fec, i_ref = col("fecha"), col("referencia")
    i_des = col("transacci")
    i_sig = col("signo")
    i_val = col("valor")
    i_sal = col("saldo")

    lineas = []
    for r in range(h + 1, ws.max_row + 1):
        fecha = _fecha(ws.cell(r, i_fec).value) if i_fec > 0 else None
        if not fecha:
            continue
        valor = num(ws.cell(r, i_val).value) if i_val > 0 else 0.0
        if valor == 0:
            continue
        signo = norm(ws.cell(r, i_sig).value) if i_sig > 0 else ""
        credito = valor if signo.startswith("(+)") else 0.0
        debito = valor if signo.startswith("(-)") else 0.0
        if debito == 0 and credito == 0:  # sin signo: por descripción
            continue
        saldo = num(ws.cell(r, i_sal).value) if i_sal > 0 else 0.0
        lineas.append({
            "fecha": fecha,
            "descripcion": norm(ws.cell(r, i_ref).value) + " " + norm(ws.cell(r, i_des).value),
            "referencia": norm(ws.cell(r, i_ref).value),
            "debito": debito, "credito": credito,
            "saldo_banco": saldo or None})

    if not lineas:
        raise ValueError("Sin movimientos en el extracto Produbanco")

    primero = lineas[0]
    saldo_anterior = round(primero["saldo_banco"] - (primero["credito"] - primero["debito"]), 2)
    saldo_actual = lineas[-1]["saldo_banco"]
    periodo_fin = max(ln["fecha"] for ln in lineas)
    periodo_inicio = periodo_fin[:8] + "01"
    depositos = round(sum(ln["credito"] for ln in lineas), 2)
    retiros = round(sum(ln["debito"] for ln in lineas), 2)
    return {"banco": "Produbanco", "numero": numero,
            "periodo_inicio": periodo_inicio, "periodo_fin": periodo_fin,
            "saldo_anterior": saldo_anterior, "saldo_actual": saldo_actual,
            "depositos": depositos, "retiros": retiros, "lineas": lineas}
