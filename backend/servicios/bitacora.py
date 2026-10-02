"""bitacora.py — auditoría de acciones CRUD + sistema (v3).

Toda escritura (movimientos, importar, init-vacio, borrado, exportación de
logs) deja una fila aquí para consultas post-fallo. La tabla se preserva
ante el borrado total RN-13.
"""
from __future__ import annotations

import json
import sqlite3

ACCIONES = {"CREAR", "EDITAR", "REALIZADO", "ELIMINAR", "IMPORTAR",
            "INIT_VACIO", "BORRADO_TOTAL", "EXPORTAR_LOGS"}
ORIGENES = {"UI", "IMPORT", "SISTEMA"}


def _dump(obj) -> str:
    if obj is None:
        return ""
    if isinstance(obj, str):
        return obj
    try:
        return json.dumps(obj, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(obj)


def registrar(con: sqlite3.Connection, accion: str, tabla: str = "movimientos",
              registro_id=None, detalle: str = "",
              anterior=None, nuevo=None, origen: str = "UI",
              commit: bool = False) -> int:
    """Inserta un evento. No valida en exceso: tabla libre, acción cerrada."""
    if accion not in ACCIONES:
        raise ValueError(f"accion inválida: {accion}")
    if origen not in ORIGENES:
        raise ValueError(f"origen inválido: {origen}")
    cur = con.execute(
        "INSERT INTO bitacora (accion, tabla, registro_id, detalle,"
        " dato_anterior, dato_nuevo, origen)"
        " VALUES (?,?,?,?,?,?,?)",
        (accion, tabla or "movimientos", registro_id, detalle or "",
         _dump(anterior), _dump(nuevo), origen))
    if commit:
        con.commit()
    return cur.lastrowid


def listar(con: sqlite3.Connection, accion: str = "", tabla: str = "",
           desde: str = "", hasta: str = "", texto: str = "",
           page=1, limit=50) -> dict:
    page = max(int(page or 1), 1)
    limit = min(max(int(limit or 50), 1), 200)
    off = (page - 1) * limit
    sql = "SELECT * FROM bitacora WHERE 1=1"
    args: list = []
    if accion in ACCIONES:
        sql += " AND accion=?"; args.append(accion)
    if tabla:
        sql += " AND tabla=?"; args.append(tabla)
    if desde:
        sql += " AND date(fecha) >= date(?)"; args.append(desde)
    if hasta:
        sql += " AND date(fecha) <= date(?)"; args.append(hasta)
    if texto:
        sql += " AND (detalle LIKE ? OR dato_nuevo LIKE ? OR dato_anterior LIKE ?)"
        args += [f"%{texto}%"] * 3
    total = con.execute(f"SELECT COUNT(*) c FROM ({sql})", args).fetchone()["c"]
    rows = [dict(r) for r in con.execute(
        sql + " ORDER BY id DESC LIMIT ? OFFSET ?", args + [limit, off]).fetchall()]
    return {"total": total, "page": page, "limit": limit, "rows": rows}


def generar_txt(filas: list[dict], filtros: dict | None = None) -> str:
    """Reporte plano: cabecera + una línea por evento."""
    f = filtros or {}
    partes = [
        "BITACORA — reporte de acciones",
        f"Total de eventos: {len(filas)}",
        "Filtros: " + ", ".join(f"{k}={v}" for k, v in f.items() if v) if f else "Filtros: ninguno",
        "-" * 60,
    ]
    for r in filas:
        rid = f"#{r.get('registro_id')}" if r.get("registro_id") is not None else ""
        partes.append(
            f"[{r.get('fecha')}] {r.get('accion')} {r.get('tabla')}{rid}"
            f" ({r.get('origen')}) — {r.get('detalle') or ''}")
        if r.get("dato_anterior"):
            partes.append(f"  antes: {r.get('dato_anterior')}")
        if r.get("dato_nuevo"):
            partes.append(f"  despues: {r.get('dato_nuevo')}")
    partes.append("-" * 60)
    return "\n".join(partes) + "\n"
