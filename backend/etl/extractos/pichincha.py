"""pichincha.py — estado de cuenta Pichincha (.xls que en realidad es HTML).

Secciones: encabezado de corte (Saldo Anterior / Depósitos / Cheques /
Saldo Actual), RESUMEN DE CHEQUES (informativo, no se importa: esos débitos
ya vienen en el detalle) y DETALLE DE MOVIMIENTOS
(FECHA | OFIC | N.DOC | DESCRIPCION | DEBITO | CREDITO | SALDO).
"""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from etl.extractos.base import MESES_ES, norm, num


class _Tablas(HTMLParser):
    def __init__(self):
        super().__init__()
        self.filas: list[list[str]] = []
        self._fila: list[str] | None = None
        self._celda: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._fila = []
        elif tag == "td" and self._fila is not None:
            self._celda = []

    def handle_data(self, data):
        if self._celda is not None:
            self._celda.append(data)

    def handle_endtag(self, tag):
        if tag == "td" and self._fila is not None and self._celda is not None:
            self._fila.append(norm("".join(self._celda)))
            self._celda = None
        elif tag == "tr" and self._fila is not None:
            self.filas.append(self._fila)
            self._fila = None


def _fecha(det: str, anio: int = 2026) -> str | None:
    m = re.match(r"(\d{1,2})-([a-zñ]{3})\.?", det.lower())
    if not m:
        return None
    mes = MESES_ES.get(m.group(2)[:3])
    if not mes:
        return None
    return f"{anio}-{mes:02d}-{int(m.group(1)):02d}"


def parsear(path: Path) -> dict:
    texto = Path(path).read_text(encoding="utf-8", errors="replace")
    p = _Tablas()
    p.feed(texto)
    filas = p.filas

    def buscar(etiqueta: str) -> float:
        for f in filas:
            for i, c in enumerate(f):
                if etiqueta.lower() in c.lower() and i + 1 < len(f):
                    return num(f[i + 1])
        return 0.0

    saldo_anterior = buscar("Saldo Anterior")
    depositos = buscar("Depositos")
    retiros = buscar("Cheques")
    saldo_actual = buscar("Saldo Actual")

    numero, periodo_fin = "", "2026-08-31"
    for f in filas:
        for i, c in enumerate(f):
            if "cuenta" in c.lower() and i + 1 < len(f) and re.search(r"\d{6,}", f[i + 1]):
                numero = re.search(r"\d{6,}", f[i + 1]).group(0)
            if "fecha este corte" in c.lower() and i + 1 < len(f):
                m = re.match(r"(\d{2})-(\d{2})-(\d{4})", f[i + 1])
                if m:
                    periodo_fin = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    anio = int(periodo_fin[:4])

    # Solo el DETALLE mueve saldo; el RESUMEN DE CHEQUES es informativo.
    en_detalle = False
    lineas = []
    for f in filas:
        if any("DETALLE DE MOVIMIENTOS" in c for c in f):
            en_detalle = True
            continue
        if not en_detalle or len(f) < 7:
            continue
        fecha = _fecha(f[0], anio)
        if not fecha:
            continue  # encabezado FECHA/OFFIC/... u otras secciones
        debito, credito, saldo = num(f[4]), num(f[5]), num(f[6])
        if debito == 0 and credito == 0:
            continue
        lineas.append({"fecha": fecha, "descripcion": f[3],
                       "referencia": f[2], "debito": debito,
                       "credito": credito, "saldo_banco": saldo})

    periodo_inicio = periodo_fin[:8] + "01"
    return {"banco": "Pichincha", "numero": numero,
            "periodo_inicio": periodo_inicio, "periodo_fin": periodo_fin,
            "saldo_anterior": saldo_anterior, "saldo_actual": saldo_actual,
            "depositos": depositos, "retiros": retiros, "lineas": lineas}
