"""conftest.py — fixtures compartidas: BD temporal (tempfile, fuera del repo) + seed.

La BD de cada test nace en %TEMP% y se elimina al terminar. Nunca toca
database/tesoreria.db. Ver plan Fase 0.
"""
from __future__ import annotations

import pytest

from nucleo.basedatos import conectar

# Movimientos semilla (mismo contenido que la plantilla de ejemplo):
# ingreso realizado + egreso realizado + egreso pendiente (no suma al flujo).
SEED_MOVS = [
    {"fecha_pago": "2026-01-05", "tipo": "ingreso", "tipo_pago": "transferencia",
     "entidad_tipo": "cliente", "entidad": "PACIFICCAM", "concepto_pago": "prestamo",
     "banco": "Pichincha", "centro_costo": "", "valor_usd": 8500,
     "status": "realizado", "observacion": "Cobro factura 101"},
    {"fecha_pago": "2026-01-06", "tipo": "egreso", "tipo_pago": "transferencia",
     "entidad_tipo": None, "entidad": "", "concepto_pago": "nomina",
     "banco": "Pichincha", "centro_costo": "planta", "valor_usd": 5500,
     "status": "realizado", "observacion": "Quincena"},
    {"fecha_pago": "2026-01-07", "tipo": "egreso", "tipo_pago": "cheque",
     "entidad_tipo": "proveedor", "entidad": "Proveedor XYZ", "concepto_pago": "prestamo",
     "banco": "Guayaquil", "centro_costo": "", "valor_usd": 1850,
     "status": "pendiente", "observacion": "Cuota préstamo"},
]


def sembrar(con):
    """Inserta el seed mínimo y devuelve {entidades, cuentas, conceptos} por nombre->id."""
    ids = {"entidades": {}, "cuentas": {}, "conceptos": {}}
    for m in SEED_MOVS:
        if m["entidad"]:
            con.execute("INSERT OR IGNORE INTO entidades (tipo, nombre) VALUES (?,?)",
                        (m["entidad_tipo"], m["entidad"]))
            # v4: mantiene la hija correspondiente (sin campos extra).
            hija = "clientes" if m["entidad_tipo"] == "cliente" else "proveedores"
            con.execute(f"INSERT OR IGNORE INTO {hija} (entidad_id)"
                        " SELECT id FROM entidades WHERE nombre=?", (m["entidad"],))
            con.execute(
                """INSERT INTO movimientos
                   (fecha_pago, tipo, tipo_pago, concepto_id, entidad_id,
                    centro_costo, valor_usd, status, observacion)
                   VALUES (?,?,?,
                     (SELECT id FROM conceptos WHERE nombre=?),
                     (SELECT id FROM entidades WHERE nombre=?),
                     ?,?,?,?)""",
                (m["fecha_pago"], m["tipo"], m["tipo_pago"], m["concepto_pago"],
                 m["entidad"] or None,
                 m["centro_costo"], m["valor_usd"], m["status"], m["observacion"]))
    for tabla, col in (("entidades", "nombre"), ("cuentas", "banco"), ("conceptos", "nombre")):
        clave = "entidades" if tabla == "entidades" else tabla
        ids[clave] = {r[col]: r["id"] for r in con.execute(f"SELECT id, {col} FROM {tabla}")}
    return ids


@pytest.fixture
def db(tmp_path):
    """Ruta a una BD SQLite temporal (se borra con tmp_path al terminar)."""
    return tmp_path / "test_tesoreria.db"


@pytest.fixture
def con(db):
    """Conexión abierta sobre BD temporal con schema aplicado (sin seed)."""
    c = conectar(db)
    yield c
    c.close()


@pytest.fixture
def con_seed(con):
    """Conexión sobre BD temporal con schema + seed; devuelve (con, ids)."""
    with con:
        ids = sembrar(con)
    yield con, ids
