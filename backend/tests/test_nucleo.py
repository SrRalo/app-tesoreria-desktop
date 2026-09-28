"""Fase 0 — nucleo/: rutas, BD y catálogos."""
from __future__ import annotations

import sqlite3

import pytest

from nucleo import basedatos, catalogos, rutas

TABLAS = {"entidades", "cuentas", "conceptos", "movimientos",
          "saldos_diarios", "config", "import_log"}


def tablas(con):
    return {r["name"] for r in
            con.execute("SELECT name FROM sqlite_master WHERE type='table'")}


class TestRutas:
    def test_schema_existe(self):
        assert rutas.SCHEMA.exists(), f"falta {rutas.SCHEMA}"

    def test_front_index_existe(self):
        assert rutas.front_file("index.html") is not None

    def test_front_inexistente_devuelve_none(self):
        assert rutas.front_file("no-existe-xyz.txt") is None

    def test_db_default_dev_apunta_a_database(self):
        assert rutas.db_default() == rutas.DB_DIR / "tesoreria.db"


class TestBaseDatos:
    def test_conectar_crea_todas_las_tablas(self, con):
        assert TABLAS <= tablas(con)

    def test_conectar_es_idempotente(self, db):
        c1 = basedatos.conectar(db)
        c1.close()
        c2 = basedatos.conectar(db)
        assert TABLAS <= tablas(c2)
        c2.close()

    def test_foreign_keys_activado(self, con):
        assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1

    def test_seed_catalogos_rn09(self, con):
        conceptos = {r["nombre"] for r in con.execute("SELECT nombre FROM conceptos")}
        assert {"nomina", "prestamo"} <= conceptos
        bancos = {r["banco"] for r in con.execute("SELECT banco FROM cuentas")}
        assert {"Pichincha", "Guayaquil", "Internacional", "Caja"} <= bancos
        saldo = con.execute(
            "SELECT valor FROM config WHERE clave='saldo_inicial_usd'").fetchone()[0]
        assert float(saldo) == 5000

    def test_fk_rechaza_movimiento_huerfano(self, con):
        with pytest.raises(sqlite3.IntegrityError):
            with con:
                con.execute(
                    "INSERT INTO movimientos (fecha_pago, tipo, tipo_pago, concepto_id,"
                    " cuenta_id, valor_usd, status) VALUES (?,?,?,?,?,?,?)",
                    ("2026-01-05", "ingreso", "transferencia", 9999, 1, 100, "pendiente"))


class TestCatalogos:
    def test_constantes_rn09(self):
        assert set(catalogos.TIPOS) == {"ingreso", "egreso"}
        assert set(catalogos.TIPOS_PAGO) == {"efectivo", "transferencia", "cheque"}
        assert set(catalogos.STATUS) == {"pendiente", "aplazado", "realizado"}

    def test_crear_no_permite_aplazado_rn12(self):
        assert "aplazado" not in catalogos.STATUS_CREACION
        assert set(catalogos.STATUS_CREACION) == {"pendiente", "realizado"}

    def test_en_catalogo(self):
        assert catalogos.en_catalogo("cheque", catalogos.TIPOS_PAGO)
        assert not catalogos.en_catalogo("tarjeta", catalogos.TIPOS_PAGO)
