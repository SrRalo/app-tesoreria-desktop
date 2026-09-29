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


def init_vacio(con: sqlite3.Connection, saldo_inicial_usd=5000,
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
        from servicios.bitacora import registrar
        registrar(con, "INIT_VACIO", "config", None,
                  f"arranque vacío con saldo {saldo} USD"
                  + (f" desde {fecha_inicio}" if fecha_inicio else ""),
                  anterior=None,
                  nuevo={"saldo_inicial_usd": saldo, "fecha_inicio": fecha_inicio or ""},
                  origen="UI")
    return {"ok": True}


def importar_archivo(xlsx: Path, db: Path, nombre_original: str | None = None) -> dict:
    from nucleo.basedatos import conectar
    res = importar(Path(xlsx), Path(db), nombre_original=nombre_original)
    con = conectar(Path(db))
    try:
        from servicios.bitacora import registrar
        registrar(con, "IMPORTAR", "import_log", None,
                  f"{res.get('archivo', xlsx.name)}: {res['filas_ok']} ok,"
                  f" {len(res['errores'])} errores",
                  anterior=None,
                  nuevo={"archivo": res.get("archivo", xlsx.name),
                         "filas_ok": res["filas_ok"],
                         "filas_error": len(res["errores"])},
                  origen="IMPORT", commit=True)
    finally:
        con.close()
    return {"ok": True, **res}


def recursos(con: sqlite3.Connection) -> dict:
    """Último Excel cargado (nombre + fecha + resultado) para vista Recursos."""
    row = con.execute("SELECT archivo, filas_ok, filas_error, fecha FROM import_log"
                      " ORDER BY id DESC LIMIT 1").fetchone()
    n = con.execute("SELECT COUNT(*) c FROM movimientos").fetchone()["c"]
    ultimo = dict(row) if row else None
    return {"ultimo_excel": ultimo, "total_movimientos": n}


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
