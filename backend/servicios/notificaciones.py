"""notificaciones.py — vencidos y próximos a vencer (campana, sin cron).

Cálculo al vuelo sobre `movimientos`: nada se actualiza en BD, el tramo
`<=7 días` cambia solo cada día porque `hoy` se evalúa por request.
`solo alerta`: vencido NO suma al flujo (saldos_diarios solo usa realizado).

Buckets:
  vencido  -> fecha_pago < hoy y status en (pendiente, aplazado, vencido)
  d7       -> 0 <= dias <= 7    (revisión diaria)
  d15      -> 8 <= dias <= 15
  d30      -> 16 <= dias <= 30
  d60      -> 31 <= dias <= 60
  d90      -> 61 <= dias <= 90
  mas90    -> dias > 90
Realizados nunca notifican.
"""
from __future__ import annotations

import sqlite3
from datetime import date

from servicios.flujo import MOV_SELECT

PENDIENTES = ("pendiente", "aplazado", "vencido")


def bucket_de(dias: int) -> str:
    if dias < 0:
        return "vencido"
    if dias <= 7:
        return "d7"
    if dias <= 15:
        return "d15"
    if dias <= 30:
        return "d30"
    if dias <= 60:
        return "d60"
    if dias <= 90:
        return "d90"
    return "mas90"


def _hoy(hoy: str | None) -> str:
    return hoy or date.today().strftime("%Y-%m-%d")


def listar(con: sqlite3.Connection, hoy: str | None = None) -> dict:
    h = _hoy(hoy)
    rows = [dict(r) for r in con.execute(
        MOV_SELECT + " WHERE m.status IN (?,?,?)"
        " ORDER BY m.fecha_pago, m.id",
        PENDIENTES).fetchall()]
    grupos: dict[str, list] = {
        "vencido": [], "d7": [], "d15": [],
        "d30": [], "d60": [], "d90": [], "mas90": [],
    }
    tot_venc = {"ing": 0.0, "egr": 0.0, "n": 0}
    for m in rows:
        dias = (date.fromisoformat(m["fecha_pago"]) - date.fromisoformat(h)).days \
            if len(m["fecha_pago"]) == 10 else 0
        b = bucket_de(dias)
        m["dias"] = dias
        m["bucket"] = b
        m["es_vencido"] = b == "vencido"
        grupos[b].append(m)
        if b == "vencido":
            tot_venc["n"] += 1
            tot_venc["ing" if m["tipo"] == "ingreso" else "egr"] += m["valor_usd"]
    resumen = {k: len(v) for k, v in grupos.items()}
    # Badge de la campana: vencidos + vence en ≤7 días (lo que exige revisión diaria)
    badge = resumen["vencido"] + resumen["d7"]
    return {"hoy": h, "badge": badge, "resumen": resumen,
            "total_vencido_usd": {"ingreso": round(tot_venc["ing"], 2),
                                  "egreso": round(tot_venc["egr"], 2),
                                  "n": tot_venc["n"]},
            "grupos": grupos}
