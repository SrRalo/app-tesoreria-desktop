"""Fase 3 — servicios/entidades.py: lectura clientes/proveedores/cuentas."""
from __future__ import annotations

from servicios.entidades import listar_cuentas, listar_entidades


def conteos(con):
    return {t: con.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            for t in ("entidades", "cuentas", "movimientos")}


class TestEntidades:
    def test_clientes(self, con_seed):
        con, _ = con_seed
        rows = listar_entidades(con, "cliente")
        assert [r["nombre"] for r in rows] == ["PACIFICCAM"]

    def test_proveedores(self, con_seed):
        con, _ = con_seed
        rows = listar_entidades(con, "proveedor")
        assert [r["nombre"] for r in rows] == ["Proveedor XYZ"]

    def test_sin_filtro_ordena_por_tipo_y_nombre(self, con_seed):
        con, _ = con_seed
        rows = listar_entidades(con)
        assert [(r["tipo"], r["nombre"]) for r in rows] == [
            ("cliente", "PACIFICCAM"), ("proveedor", "Proveedor XYZ")]

    def test_tipo_invalido_devuelve_todo(self, con_seed):
        con, _ = con_seed
        assert len(listar_entidades(con, "otro")) == 2

    def test_solo_lectura(self, con_seed):
        con, _ = con_seed
        antes = conteos(con)
        listar_entidades(con)
        listar_entidades(con, "cliente")
        assert conteos(con) == antes


class TestCuentas:
    def test_bancos_ordenados(self, con_seed):
        con, _ = con_seed
        rows = listar_cuentas(con)
        assert [r["banco"] for r in rows] == ["Caja", "Guayaquil", "Internacional", "Pichincha", "PorDefinir", "Produbanco"]

    def test_solo_lectura(self, con_seed):
        con, _ = con_seed
        antes = conteos(con)
        listar_cuentas(con)
        assert conteos(con) == antes
