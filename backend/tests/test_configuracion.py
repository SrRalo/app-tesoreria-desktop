"""Tests — servicios/configuracion.py: borrado total con clave admin (RN-13)."""
from __future__ import annotations

import pytest

from servicios import configuracion as cfg
from servicios.arranque import estado


def conteos(con):
    return {t: con.execute(f"SELECT COUNT(*) c FROM {t}").fetchone()["c"]
            for t in ("movimientos", "saldos_diarios", "import_log",
                      "entidades", "cuentas", "conceptos")}


class TestBorrado:
    def test_clave_invalida_no_borra(self, con_seed):
        con, _ = con_seed
        antes = conteos(con)
        with pytest.raises(cfg.ClaveInvalida):
            cfg.borrar_todo(con, "incorrecta")
        with pytest.raises(cfg.ClaveInvalida):
            cfg.borrar_todo(con, "")
        with pytest.raises(cfg.ClaveInvalida):
            cfg.borrar_todo(con, None)
        assert conteos(con) == antes

    def test_clave_ok_vacia_y_reseedea(self, con_seed):
        con, _ = con_seed
        assert cfg.borrar_todo(con, "admin123") == {"ok": True}
        despues = conteos(con)
        assert despues["movimientos"] == 0
        assert despues["saldos_diarios"] == 0
        assert despues["import_log"] == 0
        assert despues["entidades"] == 0
        assert despues["conceptos"] == 7 and despues["cuentas"] == 6  # seeds RN-09 + v3 (comision, Produbanco) + insumos + por_definir (RF-ETL-08)
        assert float(con.execute(
            "SELECT valor FROM config WHERE clave='saldo_inicial_usd'").fetchone()[0]) == 0
        # v3: la bitácora se preserva y registra el borrado
        nbit = con.execute("SELECT COUNT(*) c FROM bitacora").fetchone()["c"]
        assert nbit >= 1
        assert con.execute(
            "SELECT COUNT(*) c FROM bitacora WHERE accion='BORRADO_TOTAL'").fetchone()["c"] == 1

    def test_despues_vuelve_a_primer_arranque(self, con_seed):
        con, _ = con_seed
        cfg.borrar_todo(con, "admin123")
        assert estado(con)["necesita_import"] is True
