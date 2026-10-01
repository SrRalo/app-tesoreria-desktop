"""bancos.py — subpestañas de bancos en Entidades (RF-25, RF-26).

Solo lectura: logo + total de saldo del último corte + meses con
extracto + líneas del extracto tal como se cargó (sin conciliación).
"""
from __future__ import annotations

import sqlite3

# Logos servidos por el front desde frontend/assets/bancos/. La ruta vive
# en datos (aquí), no en el código del front; si falta, el front usa
# el icono Landmark + nombre como respaldo.
LOGOS = {
    "pichincha": "assets/bancos/pichincha.png",
    "internacional": "assets/bancos/internacional.png",
    "produbanco": "assets/bancos/produbanco.webp",
}

MESES_ES = ["", "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
            "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre",
            "Diciembre"]


def _logo_para(banco: str) -> str | None:
    return LOGOS.get((banco or "").strip().lower())


def etiqueta_mes(ym: str) -> str:
    """'2026-08' -> 'Agosto 2026'."""
    try:
        anio, mes = ym.split("-")
        return f"{MESES_ES[int(mes)]} {anio}"
    except (ValueError, IndexError):
        return ym


def listar_bancos(con: sqlite3.Connection) -> list[dict]:
    """Bancos con estado de cuenta cargado: logo + saldo del último corte."""
    rows = con.execute(
        "SELECT id, banco, numero FROM cuentas WHERE activo=1 ORDER BY banco"
    ).fetchall()
    out = []
    for r in rows:
        corte = con.execute(
            "SELECT saldo_actual, fecha_corte FROM cortes_bancarios"
            " WHERE cuenta_id=? ORDER BY fecha_corte DESC LIMIT 1",
            (r["id"],)).fetchone()
        if corte is None:
            continue  # sin extracto no hay pestaña (Guayaquil/Caja)
        n = con.execute("SELECT COUNT(*) c FROM extracto_lineas WHERE cuenta_id=?",
                        (r["id"],)).fetchone()["c"]
        out.append({"cuenta_id": r["id"], "banco": r["banco"],
                    "numero": r["numero"] or "",
                    "logo": _logo_para(r["banco"]),
                    "saldo": round(corte["saldo_actual"], 2),
                    "fecha_corte": corte["fecha_corte"],
                    "lineas": n})
    return out


def meses_con_extracto(con: sqlite3.Connection, cuenta_id: int) -> list[dict]:
    """Meses con estado de cuenta, del más reciente al más antiguo."""
    rows = con.execute(
        "SELECT substr(fecha,1,7) mes, COUNT(*) lineas FROM extracto_lineas"
        " WHERE cuenta_id=? GROUP BY mes ORDER BY mes DESC",
        (cuenta_id,)).fetchall()
    if not rows:
        existe = con.execute("SELECT 1 FROM cuentas WHERE id=?",
                             (cuenta_id,)).fetchone()
        if existe is None:
            raise LookupError(f"cuenta #{cuenta_id} no existe")
    return [{"mes": r["mes"], "etiqueta": etiqueta_mes(r["mes"]),
             "lineas": r["lineas"]} for r in rows]


def extracto_paginado(con: sqlite3.Connection, cuenta_id: int, mes: str = "",
                      pagina: int = 1, limite: int = 50) -> dict:
    """Líneas del extracto tal como se cargó (sin conciliación).

    Columnas: fecha, referencia, descripcion, monto, saldo.
    Orden cronológico igual al del extracto.
    """
    limite = min(max(int(limite or 50), 1), 100)
    pagina = max(int(pagina or 1), 1)
    existe = con.execute("SELECT 1 FROM cuentas WHERE id=?",
                         (cuenta_id,)).fetchone()
    if existe is None:
        raise LookupError(f"cuenta #{cuenta_id} no existe")
    args: list = [cuenta_id]
    filtro = ""
    if mes:
        filtro = " AND substr(fecha,1,7)=?"
        args.append(mes)
    total = con.execute("SELECT COUNT(*) c FROM extracto_lineas"
                        f" WHERE cuenta_id=?{filtro}", args).fetchone()["c"]
    paginas = max(1, (total + limite - 1) // limite)
    pagina = min(pagina, paginas)
    rows = con.execute(
        "SELECT fecha, referencia, descripcion,"
        " (credito_usd - debito_usd) monto, saldo_banco_usd saldo"
        " FROM extracto_lineas"
        f" WHERE cuenta_id=?{filtro} ORDER BY fecha, id"
        " LIMIT ? OFFSET ?", (*args, limite, (pagina - 1) * limite)).fetchall()
    return {"total": total, "pagina": pagina, "paginas": paginas,
            "limite": limite,
            "rows": [{"fecha": r["fecha"], "referencia": r["referencia"] or "",
                      "descripcion": r["descripcion"] or "",
                      "monto": round(r["monto"] or 0, 2),
                      "saldo": (round(r["saldo"], 2)
                                if r["saldo"] is not None else None)}
                     for r in rows]}
