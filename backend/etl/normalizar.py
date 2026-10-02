"""normalizar.py — limpieza compartida del ETL (RF-ETL-04/05/06).

Objetivo del dueño: normalizar y cargar la mayoría, cero pérdida.
Ninguna función lanza por dato sucio: devuelve (valor, aviso).

  parse_fecha(v) -> (iso YYYY-MM-DD | None, aviso | None)
  parse_monto(v, debito=None, credito=None) -> (float, aviso | None)
  limpiar_texto(s, upper=False) -> str
  es_fila_total(valores) / es_fila_vacia(valores) -> bool

Rápido: sin deps externas, sin regex pesadas en bucle.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta

# --- texto ---

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\u200b\u200c\u200d\ufeff]")
_ESP = re.compile(r"\s+")

PALABRAS_TOTAL = ("total", "subtotal", "saldo final", "saldo inicial",
                  "totales", "gran total")


def limpiar_texto(s, upper: bool = False) -> str:
    """strip + colapsa espacios + quita controles invisibles. upper solo refs."""
    if s is None:
        return ""
    t = str(s)
    # latin1 mal exportado (Antig�edad) -> intenta reparar barato
    if "�" in t:
        try:
            rep = t.encode("latin1", errors="ignore").decode("utf-8", errors="ignore")
            if rep.strip():
                t = rep
        except Exception:
            pass
    t = _CTRL.sub("", t)
    t = _ESP.sub(" ", t).strip()
    return t.upper() if upper else t


def es_fila_vacia(valores) -> bool:
    return all(v in (None, "") or (isinstance(v, str) and not v.strip())
               for v in valores)


def es_fila_total(valores) -> bool:
    """Filtra subtotales/totales de cartera y estados de cuenta."""
    for v in valores:
        t = limpiar_texto(v).lower()
        if t in PALABRAS_TOTAL or t.startswith("total "):
            return True
    return False


# --- fechas (RF-ETL-04) ---

_BASE_EXCEL = date(1899, 12, 30)  # epoch seriales Excel (46244 -> 2026-08-14)

_FORMATOS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y",
             "%Y/%m/%d", "%d.%m.%Y", "%Y.%m.%d", "%d %m %Y")


def _serial_a_iso(n: float) -> str | None:
    try:
        if 20000 <= n <= 60000:
            return (_BASE_EXCEL + timedelta(days=int(n))).strftime("%Y-%m-%d")
    except Exception:
        pass
    return None


def parse_fecha(v) -> tuple[str | None, str | None]:
    """Devuelve (iso, aviso). iso None = va a revisión, no se descarta."""
    if v is None or (isinstance(v, str) and not v.strip()):
        return None, "fecha vacía"
    if isinstance(v, datetime):
        return v.strftime("%Y-%m-%d"), None
    if isinstance(v, date):
        return v.strftime("%Y-%m-%d"), None
    if isinstance(v, (int, float)):
        iso = _serial_a_iso(float(v))
        if iso:
            return iso, None
        return None, f"serial Excel fuera de rango: {v!r}"
    s = limpiar_texto(v)
    # serial como texto ("46244" o "46244.0")
    try:
        f = float(s.replace(",", "."))
        if s.replace(".", "", 1).replace(",", "", 1).isdigit() and 20000 <= f <= 60000:
            iso = _serial_a_iso(f)
            if iso:
                return iso, None
    except ValueError:
        pass
    s10 = s[:10]
    for fmt in _FORMATOS:
        try:
            return datetime.strptime(s10, fmt).strftime("%Y-%m-%d"), None
        except ValueError:
            continue
    # intento con hora incluida ("2026-08-14 00:00:00")
    try:
        return datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S").strftime("%Y-%m-%d"), None
    except ValueError:
        pass
    return None, f"fecha no reconocida: {v!r}"


# --- montos (RF-ETL-05) ---

_VACIOS_MONTO = {"", "-", "—", "--", "–", "n/a", "na", "s/n"}


def _limpia_simbolos(s: str) -> tuple[str, bool]:
    """Quita $, USD, espacios/NBSP. Devuelve (núcleo, negativo_por_parentesis)."""
    t = s.replace("\u00a0", " ").strip()
    neg = t.startswith("(") and t.endswith(")")
    if neg:
        t = t[1:-1]
    tl = t.lower()
    for tok in ("usd", "us$", "u.s.", "$"):
        tl = tl.replace(tok, "")
        t = re.sub(re.escape(tok), "", t, flags=re.IGNORECASE)
    t = _ESP.sub("", t.strip())
    return t, neg


def _a_float_nucleo(t: str) -> float | None:
    """Resuelve coma/punto decimal: último separador = decimal."""
    if not t:
        return None
    neg = t.startswith("-")
    if neg:
        t = t[1:]
    if not re.fullmatch(r"[\d.,]+", t or ""):
        return None
    if "," in t and "." in t:
        # el último separador manda: 1,234.56 -> 1234.56 | 1.234,56 -> 1234.56
        if t.rfind(",") > t.rfind("."):
            t = t.replace(".", "").replace(",", ".")
        else:
            t = t.replace(",", "")
    elif "," in t:
        # "1,200" (miles, 3 dígitos) vs "12,50" (decimal, 2 dígitos)
        partes = t.split(",")
        if len(partes) == 2 and len(partes[1]) in (1, 2) and len(partes[0]) <= 6:
            t = partes[0] + "." + partes[1]
        else:
            t = t.replace(",", "")
    try:
        n = float(t)
    except ValueError:
        return None
    return -n if neg else n


def parse_monto(v, debito=None, credito=None) -> tuple[float, str | None]:
    """Acepta número, texto con símbolos, o par débito/crédito separados.

    Devuelve (valor_redondeado_2dec, aviso). Nunca lanza.
    """
    # columnas separadas Débito/Crédito (extractos y plantillas contables)
    if debito is not None or credito is not None:
        d, av1 = parse_monto(debito) if debito not in (None, "") else (0.0, None)
        c, av2 = parse_monto(credito) if credito not in (None, "") else (0.0, None)
        val = c - d if (c or d) else 0.0
        av = av1 or av2
        return round(val, 2), av
    if isinstance(v, (int, float)):
        return round(float(v), 2), None
    s = limpiar_texto(v).lower()
    if s in _VACIOS_MONTO:
        return 0.0, None
    nucleo, neg_par = _limpia_simbolos(s)
    n = _a_float_nucleo(nucleo)
    if n is None:
        return 0.0, f"monto no numérico: {v!r} (se toma 0, revisar)"
    if neg_par:
        n = -abs(n)
    return round(n, 2), None
