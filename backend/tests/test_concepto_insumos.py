"""Concepto 'insumos' + ejemplo Agripac (RN-09/RN-11).

Cubre: la migración crea el concepto en BDs existentes, crear un egreso
Agripac/insumos es válido y aparece en el flujo mensual con su concepto.
"""
from __future__ import annotations

from servicios import movimientos as srv_mov
from servicios.flujo import flujo_por_modo


def test_concepto_insumos_existe(con):
    nombres = {r[0] for r in con.execute("SELECT nombre FROM conceptos")}
    assert "insumos" in nombres


def test_egreso_agripac_insumos_en_flujo(con):
    mid = srv_mov.crear(con, {
        "fecha_pago": "2026-08-15", "tipo": "egreso", "tipo_pago": "transferencia",
        "entidad": "Agripac", "concepto_pago": "insumos", "banco": "Pichincha",
        "centro_costo": "", "valor_usd": 1000, "status": "realizado",
        "observacion": "[PRUEBA] ejemplo Agripac insumos"})
    assert isinstance(mid, int)
    prov = con.execute(
        "SELECT id FROM entidades WHERE nombre='Agripac' AND tipo='proveedor'").fetchone()
    assert prov is not None  # el egreso crea la entidad como proveedor
    r = flujo_por_modo(con, "mensual", {"anio": ["2026"]})
    ago = next(c for c in r["columnas"] if c["clave"] == "2026-08")
    assert ago["egr"] == 1000
    det = r["detalle_egresos"]["2026-08"]
    assert [(m["entidad"], m["concepto_pago"]) for m in det] == [("Agripac", "insumos")]
