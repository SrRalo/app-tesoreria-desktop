"""lectura.py — lectura multiformato del ETL (RF-ETL-01/02).

Soporta .xlsx (openpyxl), .xls BIFF real (xlrd) y .csv (; o ,).
Hoja seleccionable + detección dinámica de encabezados (primeras 20 filas)
+ filtro de subtotales/vacías. Rápido: openpyxl read_only, xlrd on_demand.
"""
from __future__ import annotations

import csv
import io
from pathlib import Path

from etl.normalizar import es_fila_total, es_fila_vacia, limpiar_texto

COLUMNAS = ["banco", "fecha_pago", "tipo", "tipo_pago", "entidad",
            "concepto_pago", "centro_costo", "valor_usd", "status", "observacion"]

# alias comunes en archivos reales (títulos con mayúsculas, tildes, espacios)
_ALIAS = {
    "banco": {"banco", "cuenta", "banco/cuenta", "bank"},
    "fecha_pago": {"fecha_pago", "fecha pago", "fecha", "fecha_pago_", "fecha vence",
                   "fecha_vence", "fec_pago", "f. pago", "vencimiento"},
    "tipo": {"tipo", "tipo mov", "movimiento", "ingreso/egreso", "d/c"},
    "tipo_pago": {"tipo_pago", "tipo pago", "tipo_pago_", "forma pago", "forma_pago"},
    "entidad": {"entidad", "cliente", "proveedor", "cliente/proveedor", "nombre",
                "tercero", "beneficiario"},
    "concepto_pago": {"concepto_pago", "concepto pago", "concepto", "detalle",
                      "descripcion", "descripción"},
    "centro_costo": {"centro_costo", "centro costo", "centro c.", "centro",
                     "proyecto", "c.costo"},
    "valor_usd": {"valor_usd", "valor", "monto", "importe", "saldo", "total",
                  "valor usd", "monto usd"},
    "status": {"status", "estado", "situacion", "situación"},
    "observacion": {"observacion", "observación", "obs", "nota", "notas",
                    "referencia", "comentario"},
    "debito": {"debito", "débito", "debitos", "retiros", "egreso", "cargo"},
    "credito": {"credito", "crédito", "creditos", "depositos", "depósitos",
                "ingreso", "abono"},
}


def _canon(header: str) -> str | None:
    t = limpiar_texto(header).lower()
    for canon, variantes in _ALIAS.items():
        if t in variantes:
            return canon
    return None


def detectar_header(filas_muestra: list[list]) -> tuple[int, dict[int, str]] | tuple[None, None]:
    """Busca la fila de encabezado en las primeras 20 filas.

    Devuelve (idx_fila, {col_idx: nombre_canonico}). Exige >=5 canónicas
    con al menos fecha y valor para no engancharse con un título.
    """
    for i, fila in enumerate(filas_muestra[:20]):
        mapa: dict[int, str] = {}
        for j, celda in enumerate(fila):
            c = _canon(limpiar_texto(celda))
            if c and c not in mapa.values():
                mapa[j] = c
        canonicos = set(mapa.values())
        tiene_base = (len(canonicos) >= 5
                      and "fecha_pago" in canonicos
                      and ("valor_usd" in canonicos or "debito" in canonicos
                           or "credito" in canonicos))
        if tiene_base:
            return i, mapa
    return None, None


def _filas_desde_matriz(matriz: list[list]) -> tuple[list[dict], str]:
    hi, mapa = detectar_header(matriz)
    if hi is None:
        raise ValueError("no se encontró fila de encabezados "
                         "(se buscaron banco/fecha/valor en las primeras 20 filas)")
    inv = {v: k for k, v in mapa.items()}
    filas: list[dict] = []
    for n, fila in enumerate(matriz[hi + 1:], start=hi + 2):
        fila = list(fila) + [""] * (max(mapa) + 1 - len(fila)) if len(fila) <= max(mapa) else list(fila)
        vals = [fila[k] for k in sorted(mapa)]
        if es_fila_vacia(vals) or es_fila_total([fila[inv.get("entidad", 0)] if inv.get("entidad") is not None else ""] + vals):
            # totales: basta con que alguna celda diga total/subtotal
            if es_fila_total(fila):
                continue
            if es_fila_vacia(vals):
                continue
        d: dict = {"_fila": n}
        for canon, col in inv.items():
            d[canon] = fila[col] if col < len(fila) else ""
        # débito/crédito separados -> valor único con signo (crédito - débito)
        if "valor_usd" not in inv and ("debito" in inv or "credito" in inv):
            from etl.normalizar import parse_monto
            val, _ = parse_monto(None, debito=d.get("debito"), credito=d.get("credito"))
            d["valor_usd"] = val
        for c in COLUMNAS:
            d.setdefault(c, "")
        filas.append(d)
    hoja_info = f"header fila {hi + 1}, {len(filas)} filas útiles"
    return filas, hoja_info


def hojas_disponibles(path: Path) -> list[str]:
    """Lista hojas sin cargar todo el libro (para el selector de la UI)."""
    suf = Path(path).suffix.lower()
    if suf == ".csv":
        return ["datos"]
    if suf == ".xls":
        import xlrd
        bk = xlrd.open_workbook(str(path), on_demand=True)
        try:
            return list(bk.sheet_names())
        finally:
            bk.release_resources()
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=True)
    try:
        return list(wb.sheetnames)
    finally:
        wb.close()


def leer_archivo(path: Path, hoja: str | None = None) -> tuple[list[dict], dict]:
    """Lee xlsx/xls/csv -> filas dict + meta {hoja, header_info, formato}."""
    p = Path(path)
    suf = p.suffix.lower()
    if suf == ".csv":
        return _leer_csv(p)
    if suf == ".xls":
        return _leer_xls(p, hoja)
    if suf == ".xlsx":
        return _leer_xlsx(p, hoja)
    raise ValueError(f"formato no soportado: {suf} (use .xlsx, .xls o .csv)")


def _leer_xlsx(path: Path, hoja: str | None) -> tuple[list[dict], dict]:
    from openpyxl import load_workbook
    wb = load_workbook(str(path), read_only=True, data_only=True)
    try:
        nombre = hoja or ("Movimientos" if "Movimientos" in wb.sheetnames else wb.sheetnames[0])
        if nombre not in wb.sheetnames:
            raise ValueError(f"hoja {nombre!r} no existe. Hojas: {wb.sheetnames}")
        ws = wb[nombre]
        matriz = [list(r) for r in ws.iter_rows(values_only=True)]
    finally:
        wb.close()
    filas, info = _filas_desde_matriz(matriz)
    return filas, {"hoja": nombre, "header_info": info, "formato": ".xlsx"}


def _leer_xls(path: Path, hoja: str | None) -> tuple[list[dict], dict]:
    import xlrd
    bk = xlrd.open_workbook(str(path), on_demand=True)
    try:
        nombre = hoja or ("Movimientos" if "Movimientos" in bk.sheet_names() else bk.sheet_names()[0])
        if nombre not in bk.sheet_names():
            raise ValueError(f"hoja {nombre!r} no existe. Hojas: {bk.sheet_names()}")
        sh = bk.sheet_by_name(nombre)
        matriz = [[_celda_xls(sh.cell(r, c)) for c in range(sh.ncols)]
                  for r in range(sh.nrows)]
    finally:
        bk.release_resources()
    # xlrd ya convierte fechas a número? no: datemode -> las deja como float;
    # normalizar.parse_fecha resuelve seriales. Celdas fecha reales vienen
    # como tupla con ctype==3: convertir aquí para no perder el tipo.
    filas, info = _filas_desde_matriz(matriz)
    return filas, {"hoja": nombre, "header_info": info, "formato": ".xls"}


def _celda_xls(cell) -> object:
    # ctype 2 = number, 3 = date. Devolver el valor crudo; fechas numéricas
    # las resuelve parse_fecha como serial. xlrd con formatting_info=False
    # no da datetime, así que el float serial es lo esperado.
    return cell.value


def _leer_csv(path: Path) -> tuple[list[dict], dict]:
    raw = Path(path).read_bytes()
    texto = None
    for enc in ("utf-8-sig", "utf-8", "latin1"):
        try:
            texto = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if texto is None:
        raise ValueError("no se pudo decodificar el CSV (pruebe UTF-8 o Latin1)")
    muestra = texto[:4096]
    sep = ";" if muestra.count(";") > muestra.count(",") else ","
    matriz = list(csv.reader(io.StringIO(texto), delimiter=sep))
    filas, info = _filas_desde_matriz(matriz)
    return filas, {"hoja": "datos", "header_info": info, "formato": ".csv"}
