"""Tests — servicios/bitacora.py: auditoría CRUD + sistema con antes/después."""
from __future__ import annotations

from servicios import bitacora as bit
from servicios import movimientos as mov


def test_crear_registra_con_nuevo(con_seed):
    con, _ = con_seed
    d = {"fecha_pago": "2026-01-08", "tipo": "egreso", "tipo_pago": "efectivo",
         "entidad": "ACME", "concepto_pago": "nomina", "banco": "Caja",
         "centro_costo": "", "valor_usd": 100, "status": "pendiente", "observacion": ""}
    mid = mov.crear(con, d)
    filas = bit.listar(con, accion="CREAR")["rows"]
    assert len(filas) == 1 and filas[0]["registro_id"] == mid
    assert "100" in filas[0]["dato_nuevo"]


def test_editar_guarda_antes_despues(con_seed):
    con, _ = con_seed
    mid = con.execute("SELECT id FROM movimientos WHERE status='pendiente'").fetchone()["id"]
    mov.editar(con, mid, "2026-01-20", "reprog")
    f = bit.listar(con, accion="EDITAR")["rows"][0]
    assert "2026-01-20" in f["dato_nuevo"] and "aplazado" in f["dato_nuevo"]
    assert "pendiente" in f["dato_anterior"]


def test_realizado_y_eliminar_registran(con_seed):
    con, _ = con_seed
    mid = con.execute("SELECT id FROM movimientos WHERE status='pendiente'").fetchone()["id"]
    mov.marcar_realizado(con, mid, "2026-01-10")
    mov.eliminar(con, mid)
    accs = [r["accion"] for r in bit.listar(con, limit=10)["rows"]]
    assert "REALIZADO" in accs and "ELIMINAR" in accs


def test_filtros_y_paginacion(con_seed):
    con, _ = con_seed
    mov.crear(con, {"fecha_pago": "2026-01-08", "tipo": "ingreso", "tipo_pago": "transferencia",
                    "entidad": "CLI", "concepto_pago": "prestamo", "banco": "Pichincha",
                    "valor_usd": 50, "status": "pendiente"})
    assert bit.listar(con, accion="CREAR")["total"] == 1
    assert bit.listar(con, accion="ELIMINAR")["total"] == 0
    assert bit.listar(con, texto="CLI")["total"] >= 1
    p = bit.listar(con, limit=1, page=1)
    assert p["limit"] == 1 and p["page"] == 1


def test_generar_txt_formato():
    filas = [{"fecha": "2026-01-08 10:00:00", "accion": "CREAR", "tabla": "movimientos",
              "registro_id": 1, "detalle": "ingreso 50 USD", "dato_anterior": "",
              "dato_nuevo": '{"valor_usd": 50}', "origen": "UI"}]
    txt = bit.generar_txt(filas, {"accion": "CREAR"})
    assert "BITACORA" in txt and "[2026-01-08 10:00:00] CREAR movimientos#1" in txt
    assert "despues:" in txt


def test_arranque_y_borrado_registran(con):
    from servicios.arranque import init_vacio
    from servicios.configuracion import borrar_todo
    init_vacio(con, 1000, "2026-01-05")
    assert bit.listar(con, accion="INIT_VACIO")["total"] == 1
    borrar_todo(con, "admin123")
    # La bitácora se preserva y suma el evento de borrado
    assert bit.listar(con, accion="BORRADO_TOTAL")["total"] == 1
    assert bit.listar(con)["total"] >= 2
