"""mapeo.py — entidades/cuentas/conceptos con fuzzy rápido (RF-ETL-07/08/09).

Estrategia antipérdida: ninguna fila se descarta por mapeo; se asigna
fallback (PorDefinir / por_definir / NULL) + aviso + original en observación.

Velocidad: catálogos se cargan UNA vez a memoria (dict normalizado);
exacto O(1) -> contiene-subcadena -> difflib solo contra candidatos con
misma inicial/longitud parecida. Cache por nombre en el lote.
"""
from __future__ import annotations

import re
import sqlite3
from difflib import SequenceMatcher

from etl.normalizar import limpiar_texto

UMBRAL = 0.85

# alias banco -> nombre canónico en cuentas (número o apodo del extracto)
_ALIAS_BANCO = {
    "pichincha": "Pichincha", "bco pichincha": "Pichincha",
    "bco. pichincha": "Pichincha", "cta pichincha": "Pichincha",
    "guayaquil": "Guayaquil", "bco guayaquil": "Guayaquil",
    "internacional": "Internacional", "bco internacional": "Internacional",
    "bco. internacional": "Internacional", "inter": "Internacional",
    "produbanco": "Produbanco", "produ": "Produbanco", "bco produbanco": "Produbanco",
    "caja": "Caja", "caja chica": "Caja", "efectivo": "Caja",
    "pordefinir": "PorDefinir", "por definir": "PorDefinir", "sin definir": "PorDefinir",
}
_RUIDO_CUENTA = re.compile(r"\b(cta|cte|cuenta|bco|banco|nro|no|#)\b\.?", re.IGNORECASE)


def canon_banco(s: str) -> str:
    t = limpiar_texto(s).lower()
    t = _RUIDO_CUENTA.sub("", t)
    t = re.sub(r"\s+", " ", t).strip(" .-")
    return _ALIAS_BANCO.get(t, "")


class Catalogo:
    """Catálogo en memoria con resolución rápida."""

    def __init__(self):
        self.ent_por_tipo: dict[str, dict[str, int]] = {"cliente": {}, "proveedor": {}}
        self.ent_nombres: dict[str, list[tuple[str, int]]] = {"cliente": [], "proveedor": []}
        self.cta_exact: dict[str, int] = {}      # numero limpio -> id
        self.cta_banco: dict[str, list[int]] = {}  # banco canon lower -> [ids]
        self.cta_nombres: list[tuple[str, int]] = []
        self.conceptos: dict[str, int] = {}
        self.cache: dict[tuple, tuple] = {}
        self.id_pordefinir_cta: int | None = None
        self.id_por_definir_con: int | None = None

    @staticmethod
    def norm(s: str) -> str:
        return limpiar_texto(s).upper()

    @classmethod
    def cargar(cls, con: sqlite3.Connection) -> "Catalogo":
        c = cls()
        for r in con.execute("SELECT id, tipo, nombre FROM entidades"):
            n = cls.norm(r["nombre"])
            c.ent_por_tipo.setdefault(r["tipo"], {})[n] = r["id"]
            c.ent_nombres.setdefault(r["tipo"], []).append((n, r["id"]))
        for r in con.execute("SELECT id, banco, numero FROM cuentas"):
            num = re.sub(r"\D", "", str(r["numero"] or ""))
            if num:
                c.cta_exact.setdefault(num, r["id"])
            c.cta_banco.setdefault(cls.norm(r["banco"]), []).append(r["id"])
            c.cta_nombres.append((cls.norm(r["banco"]), r["id"]))
            if cls.norm(r["banco"]) == "PORDEFINIR":
                c.id_pordefinir_cta = r["id"]
        for r in con.execute("SELECT id, nombre FROM conceptos"):
            c.conceptos[cls.norm(r["nombre"])] = r["id"]
            if cls.norm(r["nombre"]) == "POR_DEFINIR":
                c.id_por_definir_con = r["id"]
        return c

    def asegurar_fallbacks(self, con: sqlite3.Connection) -> None:
        # v4: el fallback cuelga del banco maestro (banco_id) + texto deprecated.
        con.execute("INSERT OR IGNORE INTO bancos (nombre) VALUES ('PorDefinir')")
        banco_id = con.execute("SELECT id FROM bancos WHERE nombre='PorDefinir'").fetchone()[0]
        if self.id_pordefinir_cta is None:
            con.execute(
                "INSERT OR IGNORE INTO cuentas (banco, banco_id, numero)"
                " VALUES ('PorDefinir',?, '')", (banco_id,))
            con.execute("UPDATE cuentas SET banco_id=? WHERE banco='PorDefinir'"
                        " AND banco_id IS NULL", (banco_id,))
            self.id_pordefinir_cta = con.execute(
                "SELECT id FROM cuentas WHERE banco='PorDefinir'").fetchone()[0]
            self.cta_banco.setdefault("PORDEFINIR", []).append(self.id_pordefinir_cta)
        if self.id_por_definir_con is None:
            con.execute("INSERT OR IGNORE INTO conceptos (nombre) VALUES ('por_definir')")
            self.id_por_definir_con = con.execute(
                "SELECT id FROM conceptos WHERE nombre='por_definir'").fetchone()[0]
            self.conceptos["POR_DEFINIR"] = self.id_por_definir_con


def _fuzzy(nombre_norm: str, candidatos: list[tuple[str, int]]) -> int | None:
    """Mejor coincidencia >= UMBRAL. Barato: filtra por inicial y longitud."""
    if not nombre_norm or not candidatos:
        return None
    ini = nombre_norm[0]
    mej, mej_score = None, 0.0
    for cand, cid in candidatos:
        if not cand or cand[0] != ini:
            continue
        if abs(len(cand) - len(nombre_norm)) > max(3, len(nombre_norm) // 3):
            continue
        s = SequenceMatcher(None, nombre_norm, cand, autojunk=False).ratio()
        if s >= UMBRAL and s > mej_score:
            mej, mej_score = cid, s
    if mej is not None:
        return mej
    # 2da pasada sin filtro de inicial (solo si hay pocos candidatos)
    if len(candidatos) < 500:
        for cand, cid in candidatos:
            s = SequenceMatcher(None, nombre_norm, cand, autojunk=False).ratio()
            if s >= UMBRAL and s > mej_score:
                mej, mej_score = cid, s
    return mej


def resolver_entidad(cat: Catalogo, nombre: str, tipo: str) -> tuple[int | None, str | None]:
    """(entidad_id, aviso). Vacío -> (None, None). Sin match -> (None, aviso)."""
    orig = limpiar_texto(nombre)
    if not orig:
        return None, None
    key = ("ent", tipo, cat.norm(orig))
    if key in cat.cache:
        return cat.cache[key]
    n = cat.norm(orig)
    tabla = cat.ent_por_tipo.get(tipo, {})
    if n in tabla:
        res = (tabla[n], None)
    else:
        fid = _fuzzy(n, cat.ent_nombres.get(tipo, []))
        res = ((fid, None) if fid is not None
               else (None, f"entidad '{orig}' no encontrada, se asigna Por Definir"))
    cat.cache[key] = res
    return res


def resolver_cuenta(cat: Catalogo, banco_fuente: str) -> tuple[int, str | None]:
    """Siempre devuelve un cuenta_id (fallback PorDefinir)."""
    orig = limpiar_texto(banco_fuente)
    if not orig:
        return cat.id_pordefinir_cta, "banco vacío, se asigna PorDefinir"
    key = ("cta", cat.norm(orig))
    if key in cat.cache:
        return cat.cache[key]
    num = re.sub(r"\D", "", orig)
    if num and num in cat.cta_exact:
        res = (cat.cta_exact[num], None)
    else:
        cb = canon_banco(orig)
        ids = cat.cta_banco.get(cat.norm(cb)) if cb else None
        if ids:
            res = (ids[0], None)
        else:
            n = cat.norm(orig)
            ids2 = cat.cta_banco.get(n)
            if ids2:
                res = (ids2[0], None)
            else:
                fid = _fuzzy(n, cat.cta_nombres)
                res = ((fid, None) if fid is not None
                       else (cat.id_pordefinir_cta,
                             f"banco '{orig}' no mapeado, se asigna PorDefinir"))
    cat.cache[key] = res
    return res


def resolver_concepto(cat: Catalogo, nombre: str) -> tuple[int, str | None]:
    orig = limpiar_texto(nombre).lower()
    if not orig:
        return cat.id_por_definir_con, "concepto vacío, se asigna por_definir"
    n = cat.norm(orig)
    if n in cat.conceptos:
        return cat.conceptos[n], None
    key = ("con", n)
    if key in cat.cache:
        return cat.cache[key]
    fid = _fuzzy(n, [(k, v) for k, v in cat.conceptos.items()])
    res = ((fid, None) if fid is not None
           else (cat.id_por_definir_con,
                 f"concepto '{orig}' no mapeado, se asigna por_definir"))
    cat.cache[key] = res
    return res
