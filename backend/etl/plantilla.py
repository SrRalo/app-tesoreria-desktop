"""plantilla.py — genera plantilla_flujo.xlsx con formato exacto + validaciones.

Columnas (RF-10 / RN-09):
  banco | fecha_pago | tipo | tipo_pago | entidad | concepto_pago | centro_costo | valor_usd | status | observacion

Uso (desde backend/):
  python -m etl.plantilla [destino]   (default: database/plantilla_flujo.xlsx)
"""
from __future__ import annotations

from pathlib import Path

from nucleo.rutas import DB_DIR

COLUMNAS = ["banco", "fecha_pago", "tipo", "tipo_pago", "entidad",
            "concepto_pago", "centro_costo", "valor_usd", "status", "observacion"]
TIPOS_PAGO = ["efectivo", "transferencia", "cheque"]
CONCEPTOS = ["nomina", "prestamo", "cobranza_clientes", "pago_proveedores", "comision", "insumos"]
STATUS = ["pendiente", "aplazado", "realizado", "vencido"]
EJEMPLOS = [
    ["Pichincha", "2026-01-05", "ingreso", "transferencia", "PACIFICCAM", "prestamo", "", 8500, "realizado", "Cobro factura 101"],
    ["Pichincha", "2026-01-06", "egreso", "transferencia", "", "nomina", "planta", 5500, "realizado", "Quincena"],
    ["Guayaquil", "2026-01-07", "egreso", "cheque", "Proveedor XYZ", "prestamo", "", 1850, "pendiente", "Cuota préstamo"],
]


def crear_plantilla(destino: Path) -> Path:
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
        from openpyxl.worksheet.datavalidation import DataValidation
    except ImportError:
        raise SystemExit("Falta openpyxl: pip install openpyxl")
    wb = Workbook()
    ws = wb.active
    ws.title = "Movimientos"
    head_fill = PatternFill("solid", fgColor="123B64")
    widths = [16, 14, 10, 15, 18, 15, 14, 12, 12, 28]
    for j, c in enumerate(COLUMNAS, 1):
        cell = ws.cell(row=1, column=j, value=c)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = head_fill
        ws.column_dimensions[cell.column_letter].width = widths[j - 1]
    for i, fila in enumerate(EJEMPLOS, 2):
        for j, v in enumerate(fila, 1):
            ws.cell(row=i, column=j, value=v)

    def lista(rango: str, opciones: list[str], titulo: str):
        dv = DataValidation(type="list", formula1='"%s"' % ",".join(opciones),
                            allow_blank=False, showErrorMessage=True,
                            errorTitle=titulo,
                            error=f"Use uno de: {', '.join(opciones)}.")
        ws.add_data_validation(dv)
        dv.sqref = rango

    # Columnas: A banco | B fecha_pago | C tipo | D tipo_pago | E entidad
    #           F concepto | G centro_costo libre | H valor | I status | J observación libre
    lista("C2:C1000", ["ingreso", "egreso"], "Tipo inválido")
    lista("D2:D1000", TIPOS_PAGO, "Tipo de pago inválido")
    lista("F2:F1000", CONCEPTOS, "Concepto inválido")
    lista("I2:I1000", STATUS, "Status inválido")

    ayuda = wb.create_sheet("Ayuda")
    ayuda["A1"] = "Cómo llenar la plantilla (USD)"
    ayuda["A1"].font = Font(bold=True, size=14)
    tips = [
        "1. Solo edite la hoja Movimientos. No cambie los nombres de columna.",
        "2. banco: Pichincha, Guayaquil, Internacional o Caja. fecha_pago: YYYY-MM-DD o DD/MM/YYYY.",
        "3. tipo: ingreso/egreso. tipo_pago: efectivo, transferencia, cheque.",
        "4. entidad: nombre del cliente (ingreso) o proveedor (egreso). Vacío = sin entidad.",
        "5. concepto_pago: nomina, prestamo, cobranza_clientes, pago_proveedores, comision (comisiones bancarias), insumos. centro_costo: texto libre (ej. planta).",
        "6. valor_usd: número > 0, sin $. Todo en USD. status: pendiente, aplazado, realizado, vencido.",
        "7. Solo status=realizado suma al flujo; pendiente/aplazado/vencido es proyección y alerta.",
        "8. Filas con error se reportan al importar y no rompen la carga.",
    ]
    for i, t in enumerate(tips, 3):
        ayuda.cell(row=i, column=1, value=t)
    ayuda.column_dimensions["A"].width = 95

    destino = Path(destino)
    wb.save(str(destino))
    return destino


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_DIR / "plantilla_flujo.xlsx"
    print(f"Plantilla generada: {crear_plantilla(out)}")
