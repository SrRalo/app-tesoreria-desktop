"""Notificaciones: vencidos + buckets d7/d15/d30/d60/d90 (solo alerta, no suma)."""
from __future__ import annotations

from servicios import notificaciones as notif


def _mov(con, fecha, tipo="egreso", status="pendiente", valor=100):
    con.execute(
        "INSERT INTO movimientos (fecha_pago,tipo,tipo_pago,concepto_id,"
        " valor_usd,status,observacion) VALUES (?,?,?,?,?,?,?)",
        (fecha, tipo, "transferencia", 1, valor, status, "t"))


def test_buckets_y_badge(con):
    _mov(con, "2026-08-20", status="pendiente")   # vencido al 2026-08-31
    _mov(con, "2026-08-31", status="vencido")     # d7 (hoy)
    _mov(con, "2026-09-05", status="pendiente")   # d7
    _mov(con, "2026-09-15", status="pendiente")   # d15
    _mov(con, "2026-10-01", status="pendiente")   # d60
    con.commit()
    r = notif.listar(con, "2026-08-31")
    assert r["resumen"]["vencido"] == 1
    assert r["resumen"]["d7"] == 2
    assert r["resumen"]["d15"] == 1
    assert r["badge"] == 3  # vencido + d7
    assert r["total_vencido_usd"]["n"] == 1


def test_realizado_nunca_notifica(con):
    _mov(con, "2026-08-20", status="realizado")
    con.commit()
    r = notif.listar(con, "2026-08-31")
    assert r["badge"] == 0 and r["resumen"]["vencido"] == 0


def test_bucket_de():
    assert [notif.bucket_de(d) for d in (-1, 0, 7, 8, 15, 16, 30, 31, 60, 61, 90, 91)] == [
        "vencido", "d7", "d7", "d15", "d15", "d30", "d30",
        "d60", "d60", "d90", "d90", "mas90"]
