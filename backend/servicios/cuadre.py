"""cuadre.py — compara lo operado en la app contra el corte del banco.

Por cuenta: calculado = apertura 31-jul + realizados hasta el corte.
Se compara contra cortes_bancarios.saldo_actual; la diferencia debe ser 0.
Cuentas sin extracto (Guayaquil/Caja) quedan en cero con aviso en la UI.
"""
from __future__ import annotations

import sqlite3

AVISO_SIN_EXTRACTO = ("Sin extracto de agosto 2026 — saldo 0 referencial, "
                      "no afecta el cuadre")


def cuadre_mes(con: sqlite3.Connection, mes: str = "2026-08") -> dict:
    """Cuadre del mes (YYYY-MM). Incluye total y detalle por cuenta."""
    cuentas = [dict(r) for r in con.execute(
        "SELECT * FROM cuentas ORDER BY banco").fetchall()]
    det = []
    tot = {"apertura": 0.0, "ing": 0.0, "egr": 0.0,
           "calculado": 0.0, "banco_dice": 0.0, "diferencia": 0.0}
    for c in cuentas:
        corte = con.execute(
            "SELECT * FROM cortes_bancarios WHERE cuenta_id=? "
            "AND substr(fecha_corte,1,7)=? ORDER BY fecha_corte DESC LIMIT 1",
            (c["id"], mes)).fetchone()
        fin = corte["fecha_corte"] if corte else mes + "-31"
        mov = con.execute(
            "SELECT SUM(CASE WHEN tipo='ingreso' THEN valor_usd ELSE 0 END) ing,"
            " SUM(CASE WHEN tipo='egreso' THEN valor_usd ELSE 0 END) egr"
            " FROM movimientos WHERE cuenta_id=? AND status='realizado'"
            " AND fecha_pago<=?",
            (c["id"], fin)).fetchone()
        ing, egr = mov["ing"] or 0, mov["egr"] or 0
        apertura = c["saldo_apertura_usd"] or 0
        calculado = round(apertura + ing - egr, 2)
        banco_dice = round(corte["saldo_actual"], 2) if corte else None
        diferencia = round(calculado - banco_dice, 2) if banco_dice is not None else None
        aviso = None if c["tiene_extracto"] else AVISO_SIN_EXTRACTO
        det.append({"banco": c["banco"], "numero": c["numero"] or "",
                    "tiene_extracto": bool(c["tiene_extracto"]),
                    "fecha_apertura": c["fecha_apertura"] or "",
                    "apertura": round(apertura, 2),
                    "ing": round(ing, 2), "egr": round(egr, 2),
                    "calculado": calculado, "banco_dice": banco_dice,
                    "diferencia": diferencia, "aviso": aviso,
                    "archivo": corte["archivo"] if corte else ""})
        tot["apertura"] += apertura
        tot["ing"] += ing
        tot["egr"] += egr
        tot["calculado"] += calculado
        if banco_dice is not None:
            tot["banco_dice"] += banco_dice
    tot = {k: round(v, 2) for k, v in tot.items()}
    tot["diferencia"] = round(tot["calculado"] - tot["banco_dice"], 2)
    return {"mes": mes, "cuadra": tot["diferencia"] == 0,
            "total": tot, "cuentas": det}
