"""Fase 2 — servicios/movimientos.py: CRUD + RN-09/RN-12 + recálculo de saldos."""
from __future__ import annotations

from datetime import date

import pytest

from servicios import movimientos as mov


def saldo(con, fecha):
    return con.execute("SELECT * FROM saldos_diarios WHERE fecha=?", (fecha,)).fetchone()


def por_id(con, mid):
    return con.execute("SELECT * FROM movimientos WHERE id=?", (mid,)).fetchone()


NUEVO = {"fecha_pago": "2026-01-08", "tipo": "egreso", "tipo_pago": "efectivo",
         "entidad": "ACME", "concepto_pago": "nomina", "banco": "Caja",
         "centro_costo": "planta", "valor_usd": 1200, "status": "pendiente",
         "observacion": "Bono"}


class TestListar:
    def test_total_y_orden_desc(self, con_seed):
        con, _ = con_seed
        res = mov.listar(con)
        assert res["total"] == 3
        assert [r["fecha_pago"] for r in res["rows"]] == ["2026-01-07", "2026-01-06", "2026-01-05"]

    def test_filtro_tipo(self, con_seed):
        con, _ = con_seed
        assert mov.listar(con, tipo="ingreso")["total"] == 1
        assert mov.listar(con, tipo="egreso")["total"] == 2

    def test_filtro_status(self, con_seed):
        con, _ = con_seed
        assert mov.listar(con, status="pendiente")["total"] == 1
        assert mov.listar(con, status="realizado")["total"] == 2

    def test_busqueda_por_observacion_y_entidad(self, con_seed):
        con, _ = con_seed
        assert mov.listar(con, texto="Quincena")["total"] == 1
        assert mov.listar(con, texto="PACIFICCAM")["total"] == 1

    def test_paginacion(self, con_seed):
        con, _ = con_seed
        p1 = mov.listar(con, limit=2, page=1)
        p2 = mov.listar(con, limit=2, page=2)
        assert (p1["total"], len(p1["rows"]), p1["page"]) == (3, 2, 1)
        assert (len(p2["rows"]), p2["page"]) == (1, 2)

    def test_limites_clamp(self, con_seed):
        con, _ = con_seed
        assert mov.listar(con, limit=999)["limit"] == 200
        assert mov.listar(con, page=0)["page"] == 1

    def test_filtro_invalido_se_ignora(self, con_seed):
        con, _ = con_seed
        assert mov.listar(con, tipo="otro")["total"] == 3


class TestCrear:
    def test_crear_ok_y_entidad_auto(self, con_seed):
        con, _ = con_seed
        mid = mov.crear(con, dict(NUEVO))
        assert isinstance(mid, int)
        assert mov.listar(con)["total"] == 4
        ent = con.execute("SELECT tipo FROM entidades WHERE nombre='ACME'").fetchone()
        assert ent["tipo"] == "proveedor"  # egreso -> proveedor

    def test_ingreso_crea_cliente(self, con_seed):
        con, _ = con_seed
        d = dict(NUEVO, tipo="ingreso", entidad="Cliente Nuevo", banco="Pichincha",
                 concepto_pago="prestamo")
        mov.crear(con, d)
        ent = con.execute("SELECT tipo FROM entidades WHERE nombre='Cliente Nuevo'").fetchone()
        assert ent["tipo"] == "cliente"

    def test_status_ausente_se_rechaza(self, con_seed):
        # Comportamiento original: status es obligatorio (el front siempre lo envía).
        con, _ = con_seed
        d = dict(NUEVO)
        del d["status"]
        with pytest.raises(mov.ErrorValidacion):
            mov.crear(con, d)

    def test_pendiente_no_suma_a_saldos(self, con_seed):
        con, _ = con_seed
        mov.crear(con, dict(NUEVO))
        assert saldo(con, "2026-01-08") is None

    def test_realizado_suma_a_saldos(self, con_seed):
        con, _ = con_seed
        mov.crear(con, dict(NUEVO, status="realizado"))
        assert saldo(con, "2026-01-08")["egr"] == 1200

    @pytest.mark.parametrize("cambio", [
        {"tipo": "otro"}, {"tipo_pago": "tarjeta"}, {"status": "aplazado"},
        {"concepto_pago": "otro"}, {"banco": "Banco X"}, {"fecha_pago": ""},
        {"fecha_pago": "08/01/2026"}, {"valor_usd": 0}, {"valor_usd": -5},
        {"valor_usd": "mucho"},
    ])
    def test_crear_rechaza_rn09_rn12(self, con_seed, cambio):
        con, _ = con_seed
        with pytest.raises(mov.ErrorValidacion):
            mov.crear(con, {**NUEVO, **cambio})
        assert mov.listar(con)["total"] == 3  # nada a medias


class TestEditar:
    def test_editar_pasa_a_aplazado(self, con_seed):
        con, _ = con_seed
        mid = con.execute("SELECT id FROM movimientos WHERE status='pendiente'").fetchone()["id"]
        assert mov.editar(con, mid, "2026-01-20", "Reprogramado") == "aplazado"
        row = por_id(con, mid)
        assert (row["fecha_pago"], row["observacion"], row["status"]) == \
            ("2026-01-20", "Reprogramado", "aplazado")

    def test_editar_realizado_lo_saca_del_flujo(self, con_seed):
        con, _ = con_seed
        from etl.importar import recalcular_saldos
        recalcular_saldos(con)
        assert saldo(con, "2026-01-05")["ing"] == 8500
        mid = con.execute("SELECT id FROM movimientos WHERE fecha_pago='2026-01-05'").fetchone()["id"]
        mov.editar(con, mid, "2026-01-05", "se mueve")
        assert saldo(con, "2026-01-05") is None  # aplazado ya no suma

    def test_editar_sin_fecha_o_invalida(self, con_seed):
        con, _ = con_seed
        mid = con.execute("SELECT id FROM movimientos LIMIT 1").fetchone()["id"]
        with pytest.raises(mov.ErrorValidacion):
            mov.editar(con, mid, "")
        with pytest.raises(mov.ErrorValidacion):
            mov.editar(con, mid, "20-01-2026")

    def test_editar_inexistente(self, con_seed):
        con, _ = con_seed
        with pytest.raises(mov.NoEncontrado):
            mov.editar(con, 9999, "2026-01-20")


class TestRealizado:
    def test_marcar_realizado_estampa_fecha(self, con_seed):
        con, _ = con_seed
        mid = con.execute("SELECT id FROM movimientos WHERE status='pendiente'").fetchone()["id"]
        assert mov.marcar_realizado(con, mid, "2026-01-10") == "2026-01-10"
        row = por_id(con, mid)
        assert (row["status"], row["fecha_pago"]) == ("realizado", "2026-01-10")
        assert saldo(con, "2026-01-10")["egr"] == 1850  # entra al flujo

    def test_marcar_realizado_default_hoy(self, con_seed):
        con, _ = con_seed
        mid = con.execute("SELECT id FROM movimientos WHERE status='pendiente'").fetchone()["id"]
        assert mov.marcar_realizado(con, mid) == date.today().strftime("%Y-%m-%d")

    def test_marcar_realizado_inexistente(self, con_seed):
        con, _ = con_seed
        with pytest.raises(mov.NoEncontrado):
            mov.marcar_realizado(con, 9999, "2026-01-10")


class TestEliminar:
    def test_eliminar_recalcula(self, con_seed):
        con, _ = con_seed
        from etl.importar import recalcular_saldos
        recalcular_saldos(con)
        mid = con.execute("SELECT id FROM movimientos WHERE fecha_pago='2026-01-05'").fetchone()["id"]
        mov.eliminar(con, mid)
        assert mov.listar(con)["total"] == 2
        assert saldo(con, "2026-01-05") is None

    def test_eliminar_inexistente(self, con_seed):
        con, _ = con_seed
        with pytest.raises(mov.NoEncontrado):
            mov.eliminar(con, 9999)
