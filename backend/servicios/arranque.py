"""arranque.py — primer arranque e importación (RF-14).

Movido desde app.py (Fase 4) como funciones puras:
- estado(): ¿DB lista? ¿necesita importar?
- init_vacio(): alta vacía con saldo inicial USD + fecha de inicio.
- importar_archivo(): ETL de un .xlsx ya guardado en disco.
- plantilla_asegurada(): genera la plantilla si falta y devuelve su ruta.

Micro-corrección sincerada: init_vacio con saldo no numérico → ErrorValidacion
(400) en vez de ValueError sin manejar (500).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from etl.importar import importar
from etl.plantilla import crear_plantilla
from nucleo.rutas import DB_DIR
from servicios.movimientos import ErrorValidacion


def estado(con: sqlite3.Connection) -> dict:
    n = con.execute("SELECT COUNT(*) c FROM movimientos").fetchone()["c"]
    logs = con.execute("SELECT COUNT(*) c FROM import_log").fetchone()["c"]
    return {"db_lista": True, "movimientos": n, "necesita_import": n == 0 and logs == 0}


def init_vacio(con: sqlite3.Connection, saldo_inicial_usd=0,
               fecha_inicio: str = "") -> dict:
    try:
        saldo = float(saldo_inicial_usd)
    except (TypeError, ValueError):
        raise ErrorValidacion("saldo_inicial_usd debe ser número") from None
    with con:
        con.execute("INSERT OR REPLACE INTO config VALUES ('saldo_inicial_usd',?)",
                    (str(saldo),))
        if fecha_inicio:
            con.execute("INSERT OR REPLACE INTO config VALUES ('fecha_inicio',?)",
                        (str(fecha_inicio),))
    return {"ok": True}


def importar_archivo(xlsx: Path, db: Path) -> dict:
    res = importar(Path(xlsx), Path(db))
    return {"ok": True, **res}


def _destino_plantilla() -> Path:
    import sys
    if getattr(sys, "frozen", False):
        # En el .exe, _MEIPASS es temporal: la plantilla se genera junto al exe.
        return Path(sys.executable).resolve().parent / "plantilla_flujo.xlsx"
    return DB_DIR / "plantilla_flujo.xlsx"


def plantilla_asegurada(destino: Path | None = None) -> Path:
    out = Path(destino) if destino else _destino_plantilla()
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        crear_plantilla(out)
    return out
