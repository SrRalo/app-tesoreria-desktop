"""validar.py — verificación previa al ETL (RF-23).

Comprueba que cada archivo corresponde al campo donde fue cargado.
No se fía de la extensión ni del nombre: inspecciona el contenido.

Huellas mínimas por tipo:
- Pichincha: HTML parseable con las columnas del estado de cuenta.
- Internacional: firma BIFF/OLE (D0 CF 11 E0) y se abre como libro .xls.
- Produbanco: contenedor .xlsx (ZIP con [Content_Types].xml) con
  encabezados de extracto (fecha, referencia, débito/crédito o monto, saldo).
- CxC/CxP: hoja de cálculo o CSV con encabezados de cartera
  (entidad, valor, fecha de pago o vencimiento) y NO parece extracto.

Si algún campo falla, el llamador NO debe ejecutar ningún ETL
(no hay importación parcial en la tentativa).
"""
from __future__ import annotations

import io
import tempfile
import zipfile
from html.parser import HTMLParser
from pathlib import Path

OLE_MAGIC = bytes.fromhex("D0CF11E0")
ZIP_MAGIC = b"PK\x03\x04"

CAMPOS = ("pichincha", "internacional", "produbanco", "cxc")

NOMBRE_CAMPO = {
    "pichincha": "Pichincha",
    "internacional": "Internacional",
    "produbanco": "Produbanco",
    "cxc": "CxC / CxP",
}

NOMBRE_TIPO = {
    "pichincha": "un estado de cuenta de Pichincha",
    "internacional": "un estado de cuenta de Internacional",
    "produbanco": "un estado de cuenta de Produbanco",
    "cxc": "un archivo de CxC / CxP",
    "desconocido": "un archivo no reconocido",
}


class _Celdas(HTMLParser):
    """Extrae el texto de cada celda para buscar columnas sin dependencias."""

    def __init__(self):
        super().__init__()
        self.celdas: list[str] = []
        self._buf: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag in ("td", "th"):
            self._buf = []

    def handle_data(self, data):
        if self._buf is not None:
            self._buf.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self._buf is not None:
            self.celdas.append(" ".join("".join(self._buf).split()))
            self._buf = None


def _es_html_con_columnas(raw: bytes) -> tuple[bool, str]:
    """Pichincha: HTML parseable con columnas del estado de cuenta."""
    try:
        texto = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        try:
            texto = raw.decode("latin-1")
        except Exception:
            return False, "no es texto HTML legible"
    bajo = texto.lower()
    if "<table" not in bajo and "<tr" not in bajo:
        return False, "no contiene tablas HTML"
    p = _Celdas()
    try:
        p.feed(texto)
    except Exception:
        return False, "HTML no parseable"
    juntas = " ".join(p.celdas).lower()
    sellos = ("saldo anterior" in juntas or "saldos" in juntas,
              "detalle de movimientos" in juntas or "descripcion" in juntas,
              "debito" in juntas or "débito" in juntas,
              "credito" in juntas or "crédito" in juntas)
    if sum(sellos) >= 2:
        return True, "HTML con columnas de estado de cuenta (saldo/detalle/débito/crédito)"
    return False, "HTML sin las columnas del estado de cuenta Pichincha"


def _es_ole(raw: bytes) -> bool:
    return raw[:4] == OLE_MAGIC


def _es_zip_con_content_types(raw: bytes) -> bool:
    if raw[:4] != ZIP_MAGIC:
        return False
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            return "[Content_Types].xml" in z.namelist()
    except Exception:
        return False


def _hojas_de(bytes_datos: bytes, suf: str) -> list[str]:
    """Hojas del libro (para el selector, RF-ETL-01). Vacío si no aplica."""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suf) as tmp:
            tmp.write(bytes_datos)
            tmppath = Path(tmp.name)
        try:
            from etl.lectura import hojas_disponibles
            return hojas_disponibles(tmppath)
        finally:
            tmppath.unlink(missing_ok=True)
    except Exception:
        return []


def _chequeo_internacional(raw: bytes) -> tuple[bool, str]:
    if not _es_ole(raw):
        return False, "no tiene la firma BIFF/OLE (D0 CF 11 E0)"
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xls") as tmp:
            tmp.write(raw)
            tmppath = Path(tmp.name)
        try:
            import xlrd
            bk = xlrd.open_workbook(str(tmppath))
            sh = bk.sheet_by_index(0)
            texto = " ".join(str(sh.cell(r, c).value)
                              for r in range(min(20, sh.nrows))
                              for c in range(sh.ncols)).lower()
            if "fecha" in texto and ("bito" in texto or "dito" in texto):
                return True, "libro .xls con encabezado Fecha/Débito/Crédito"
            return False, "el libro .xls no trae el encabezado del extracto Internacional"
        finally:
            tmppath.unlink(missing_ok=True)
    except Exception as e:
        return False, f"no se abre como libro .xls ({e})"


def _chequeo_produbanco(raw: bytes) -> tuple[bool, str]:
    if not _es_zip_con_content_types(raw):
        return False, "no es un contenedor .xlsx válido (ZIP con [Content_Types].xml)"
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
            tmp.write(raw)
            tmppath = Path(tmp.name)
        try:
            from openpyxl import load_workbook
            wb = load_workbook(str(tmppath), read_only=True, data_only=True)
            try:
                ws = wb[wb.sheetnames[0]]
                texto = " ".join(str(ws.cell(r, c).value or "")
                                 for r in range(1, 21)
                                 for c in range(1, 15)).lower()
                tiene_fecha = "fecha" in texto
                tiene_monto = ("valor" in texto or "monto" in texto
                               or "bito" in texto or "dito" in texto)
                tiene_saldo = "saldo" in texto
                if tiene_fecha and tiene_monto and tiene_saldo:
                    return True, "libro .xlsx con encabezados de extracto (fecha/monto/saldo)"
                faltan = [n for n, ok in (("fecha", tiene_fecha),
                                          ("monto/valor", tiene_monto),
                                          ("saldo", tiene_saldo)) if not ok]
                return False, "al .xlsx le faltan encabezados de extracto: " + ", ".join(faltan)
            finally:
                wb.close()
        finally:
            tmppath.unlink(missing_ok=True)
    except Exception as e:
        return False, f"no se abre como .xlsx ({e})"


def _chequeo_cxc(raw: bytes, nombre: str) -> tuple[bool, str]:
    suf = Path(nombre).suffix.lower() or ".xlsx"
    if suf not in (".xlsx", ".xls", ".csv"):
        return False, f"formato {suf or '?'} no soportado (use .xlsx, .xls o .csv)"
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suf) as tmp:
            tmp.write(raw)
            tmppath = Path(tmp.name)
        try:
            from etl.lectura import leer_archivo
            filas, meta = leer_archivo(tmppath, None)
        finally:
            tmppath.unlink(missing_ok=True)
    except ValueError as e:
        return False, f"sin encabezados de cartera ({e})"
    except Exception as e:
        return False, f"no se pudo leer ({e})"
    if not filas:
        return False, "sin filas de datos"
    claves = set()
    for f in filas[:5]:
        claves.update(k for k in f if f[k] not in (None, ""))
    tiene_entidad = "entidad" in claves
    tiene_valor = "valor_usd" in claves
    tiene_fecha = "fecha_pago" in claves
    if tiene_entidad and tiene_valor and tiene_fecha:
        return True, (f"cartera con entidad/valor/fecha "
                      f"({len(filas)} filas, hoja {meta.get('hoja')})")
    faltan = [n for n, ok in (("entidad", tiene_entidad),
                              ("valor", tiene_valor),
                              ("fecha de pago/vencimiento", tiene_fecha)) if not ok]
    return False, "le faltan columnas de cartera: " + ", ".join(faltan)


def detectar_tipo(raw: bytes, nombre: str) -> tuple[str, str]:
    """Devuelve (tipo, detalle). tipo en pichincha|internacional|produbanco|cxc|desconocido."""
    ok, det = _es_html_con_columnas(raw)
    if ok:
        return "pichincha", det
    ok, det_i = _chequeo_internacional(raw)
    if ok:
        return "internacional", det_i
    # Produbanco solo si el ZIP trae encabezados de extracto (un CxC .xlsx
    # también es ZIP válido y no debe confundirse).
    ok, det_p = _chequeo_produbanco(raw)
    if ok:
        return "produbanco", det_p
    ok, det_c = _chequeo_cxc(raw, nombre)
    if ok:
        return "cxc", det_c
    # Si nada cuadra, conservar la pista más útil para el motivo.
    if _es_ole(raw):
        return "desconocido", "parece un .xls BIFF pero " + det_i
    if _es_zip_con_content_types(raw):
        return "desconocido", "parece un .xlsx pero " + det_p
    return "desconocido", det_c


def validar_campo(campo: str, raw: bytes, nombre: str) -> dict:
    """Veredicto por campo: {campo, ok, motivo, tipo_detectado, hojas?}."""
    esperado = NOMBRE_CAMPO.get(campo, campo)
    tipo, detalle = detectar_tipo(raw, nombre)
    hojas: list[str] = []
    if campo == "cxc" and Path(nombre).suffix.lower() in (".xlsx", ".xls"):
        hojas = _hojas_de(raw, Path(nombre).suffix.lower())
    if tipo == campo or (campo == "cxc" and tipo == "cxc"):
        return {"campo": campo, "ok": True,
                "motivo": f"Verificado: {detalle}.",
                "tipo_detectado": tipo, "hojas": hojas}
    if tipo == "desconocido":
        motivo = (f"Este archivo no parece {NOMBRE_TIPO.get(campo, campo)} "
                  f"({detalle}). Revise que esté en el campo correcto.")
    else:
        motivo = (f"Este archivo parece {NOMBRE_TIPO[tipo]}, "
                  f"pero está en el campo de {esperado}. "
                  f"Cámbialo al campo correcto ({detalle}).")
    return {"campo": campo, "ok": False, "motivo": motivo,
            "tipo_detectado": tipo, "hojas": hojas}


def validar_tentativa(archivos: dict[str, tuple[bytes, str]]) -> dict:
    """Valida todos los campos presentes. {ok, resultados:[...]}.

    archivos: {campo: (bytes, nombre_original)}. Los vacíos se ignoran.
    """
    resultados = [validar_campo(c, raw, nom)
                  for c, (raw, nom) in archivos.items() if raw]
    return {"ok": bool(resultados) and all(r["ok"] for r in resultados),
            "resultados": resultados}
