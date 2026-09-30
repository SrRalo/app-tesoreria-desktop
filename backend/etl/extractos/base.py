"""base.py — helpers compartidos: números, fechas, hash y validación encadenada."""
from __future__ import annotations

import hashlib
import re
from datetime import datetime

MESES_ES = {"ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
            "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12}


def num(v) -> float:
    """Parsea montos con $, comas y paréntesis contables."""
    if isinstance(v, (int, float)):
        return float(v)
    s = str(v or "").strip()
    if not s or s in ("-", "—", "--"):
        return 0.0
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()").replace("$", "").replace(",", "").strip()
    try:
        n = float(s)
    except ValueError:
        return 0.0
    return -n if neg else n


def norm(s) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


def hash_linea(cuenta_id: int, fecha: str, debito: float,
               credito: float, referencia: str, descripcion: str = "") -> str:
    # La descripción entra al hash: hay comisiones del mismo día, mismo valor
    # y sin referencia que colisionarían sin ella (39 líneas en Internacional).
    base = (f"{cuenta_id}|{fecha}|{debito:.2f}|{credito:.2f}"
            f"|{norm(referencia)}|{norm(descripcion)}")
    return hashlib.sha1(base.encode("utf-8")).hexdigest()


def validar_cadena(lineas: list[dict], saldo_inicial: float,
                   tol: float = 0.02) -> list[str]:
    """Verifica saldo[i] == saldo[i-1] - debito + credito en cada línea.

    Si el banco no trae columna de saldo, las líneas vienen con
    saldo_banco=None y no hay nada que validar.
    """
    errores = []
    esperado = saldo_inicial
    for i, ln in enumerate(lineas):
        esperado = esperado - ln["debito"] + ln["credito"]
        sb = ln.get("saldo_banco")
        if sb is not None and abs(sb - esperado) > tol:
            errores.append(
                f"línea {i + 1} ({ln['fecha']} {ln['descripcion'][:40]}): "
                f"el banco dice {sb:.2f} pero la cadena da {esperado:.2f}")
    return errores


def es_comision(descripcion: str) -> bool:
    """Comisiones bancarias → concepto 'comision' (decisión del dueño §4)."""
    d = norm(descripcion).upper()
    return d.startswith(("COM-", "COMISION", "COMISIÓN", "IVA-", "TARIFA",
                         "COSTO IVA", "COSTO ", "CNDP", "CIDP")) or \
        "COMISION" in d or "TARIFA" in d
