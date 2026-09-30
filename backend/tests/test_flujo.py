"""Fase 1 — servicios/flujo.py: diario/trimestre/mensual, arrastre, solo realizado."""
from __future__ import annotations

import pytest

from etl.importar import recalcular_saldos
from servicios.flujo import _parse_ym, _sum_meses, flujo_por_modo, saldos


@pytest.fixture
def con_flujo(con_seed):
    con, _ids = con_seed
    recalcular_saldos(con)
    return con


def col(res, clave):
    return next(c for c in res["columnas"] if c["clave"] == clave)


class TestHelpers:
    def test_parse_ym(self):
        assert _parse_ym("2026-01") == (2026, 1)

    def test_sum_meses_cruza_anio(self):
        assert _sum_meses(2025, 11, 3) == [(2025, 11), (2025, 12), (2026, 1)]


class TestDiario:
    def test_7_columnas_con_nombre_y_fecha(self, con_flujo):
        res = flujo_por_modo(con_flujo, "diario", {"desde": ["2026-01-05"]})
        assert res["modo"] == "diario"
        assert [c["clave"] for c in res["columnas"]] == [
            "2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08",
            "2026-01-09", "2026-01-10", "2026-01-11"]
        c0 = res["columnas"][0]
        assert (c0["titulo"], c0["subtitulo"]) == ("Lun", "05/01")

    def test_valores_dia_con_ingreso(self, con_flujo):
        c = col(flujo_por_modo(con_flujo, "diario", {"desde": ["2026-01-05"]}), "2026-01-05")
        assert (c["saldo_inicial"], c["ing"], c["egr"], c["neto"], c["acumulado"]) == \
            (0, 8500, 0, 8500, 8500)

    def test_valores_dia_con_egreso(self, con_flujo):
        c = col(flujo_por_modo(con_flujo, "diario", {"desde": ["2026-01-05"]}), "2026-01-06")
        assert (c["saldo_inicial"], c["ing"], c["egr"], c["neto"], c["acumulado"]) == \
            (8500, 0, 5500, -5500, 3000)

    def test_pendiente_no_suma_al_flujo(self, con_flujo):
        res = flujo_por_modo(con_flujo, "diario", {"desde": ["2026-01-05"]})
        c = col(res, "2026-01-07")
        assert (c["ing"], c["egr"], c["neto"], c["acumulado"]) == (0, 0, 0, 3000)
        assert res["detalle_egresos"]["2026-01-07"] == []

    def test_detalle_subfilas(self, con_flujo):
        res = flujo_por_modo(con_flujo, "diario", {"desde": ["2026-01-05"]})
        assert res["detalle_ingresos"]["2026-01-05"][0]["entidad"] == "PACIFICCAM"
        assert res["detalle_egresos"]["2026-01-06"][0]["observacion"] == "Quincena"

    def test_arrastre_acumulado_previo(self, con_flujo):
        res = flujo_por_modo(con_flujo, "diario", {"desde": ["2026-01-06"]})
        assert res["columnas"][0]["saldo_inicial"] == 8500

    def test_diario_sin_parametros_usa_hoy(self, con_flujo):
        assert len(flujo_por_modo(con_flujo, "diario", {})["columnas"]) == 7

    def test_alias_semana_y_anual_compatibles(self, con_flujo):
        assert len(flujo_por_modo(con_flujo, "semana", {"desde": ["2026-01-05"]})["columnas"]) == 7
        assert len(flujo_por_modo(con_flujo, "anual", {"anio": ["2026"]})["columnas"]) == 12


class TestSaldos:
    def test_solo_realizado_y_ordenado(self, con_flujo):
        rows = saldos(con_flujo)
        assert [(r["fecha"], r["ing"], r["egr"]) for r in rows] == [
            ("2026-01-05", 8500, 0), ("2026-01-06", 0, 5500)]
        assert rows[0]["acumulado_usd"] == 8500

    def test_db_vacia_sin_saldos(self, con):
        assert saldos(con) == []


class TestTrimestre:
    def test_mes_base_mas_2_siguientes(self, con_flujo):
        res = flujo_por_modo(con_flujo, "trimestre", {"mes": ["2026-01"]})
        assert [c["clave"] for c in res["columnas"]] == ["2026-01", "2026-02", "2026-03"]
        assert res["columnas"][0]["titulo"] == "Ene 2026"

    def test_enero_agrupa_todo_el_mes(self, con_flujo):
        c = col(flujo_por_modo(con_flujo, "trimestre", {"mes": ["2026-01"]}), "2026-01")
        assert (c["ing"], c["egr"], c["neto"], c["acumulado"]) == (8500, 5500, 3000, 3000)

    def test_trimestre_cruza_anio(self, con_flujo):
        res = flujo_por_modo(con_flujo, "trimestre", {"mes": ["2025-12"]})
        assert [c["clave"] for c in res["columnas"]] == ["2025-12", "2026-01", "2026-02"]
        assert col(res, "2026-01")["ing"] == 8500


class TestMensual:
    def test_12_meses(self, con_flujo):
        res = flujo_por_modo(con_flujo, "mensual", {"anio": ["2026"]})
        assert [c["clave"] for c in res["columnas"]] == [f"2026-{m:02d}" for m in range(1, 13)]

    def test_enero_y_arrastre_febrero(self, con_flujo):
        res = flujo_por_modo(con_flujo, "mensual", {"anio": ["2026"]})
        ene = col(res, "2026-01")
        assert (ene["ing"], ene["egr"], ene["acumulado"]) == (8500, 5500, 3000)
        feb = col(res, "2026-02")
        assert (feb["saldo_inicial"], feb["ing"], feb["acumulado"]) == (3000, 0, 3000)
