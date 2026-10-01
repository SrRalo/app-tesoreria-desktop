"""migrar_sin_banco.py — Elimina `cuenta_id` de `movimientos` (RN-05/09).

Crea una nueva tabla `movimientos` sin `cuenta_id`, copia los datos,
elimina la vieja y renombra la nueva. Recrea los índices.

Uso (desde backend/):
  py -3 -m etl.migrar_sin_banco --db ..\\database\\tesoreria.db
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from nucleo.basedatos import conectar
from nucleo.rutas import DB_DIR


def migrar(con: sqlite3.Connection) -> None:
    with con:
        # 1. Crear tabla nueva
        con.execute("""
            CREATE TABLE IF NOT EXISTS movimientos_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              fecha_pago TEXT NOT NULL,
              tipo TEXT NOT NULL CHECK (tipo IN ('ingreso','egreso')),
              tipo_pago TEXT NOT NULL CHECK (tipo_pago IN ('efectivo','transferencia','cheque')),
              concepto_id INTEGER NOT NULL REFERENCES conceptos(id),
              entidad_id INTEGER REFERENCES entidades(id),
              centro_costo TEXT DEFAULT '',
              valor_usd REAL NOT NULL CHECK (valor_usd > 0),
              status TEXT NOT NULL DEFAULT 'pendiente'
                CHECK (status IN ('pendiente','aplazado','realizado','vencido')),
              observacion TEXT DEFAULT '',
              created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
        """)
        
        # 2. Copiar datos
        con.execute("""
            INSERT INTO movimientos_new 
            (id, fecha_pago, tipo, tipo_pago, concepto_id, entidad_id, centro_costo, valor_usd, status, observacion, created_at)
            SELECT id, fecha_pago, tipo, tipo_pago, concepto_id, entidad_id, centro_costo, valor_usd, status, observacion, created_at
            FROM movimientos
        """)
        
        # 3. Reemplazar
        con.execute("DROP TABLE movimientos")
        con.execute("ALTER TABLE movimientos_new RENAME TO movimientos")
        
        # 4. Recrear índices
        con.execute("""
            CREATE INDEX IF NOT EXISTS idx_mov
            ON movimientos(fecha_pago, tipo, entidad_id, status)
        """)
        
        print("Movimientos migrados: cuenta_id eliminado.")


def main() -> None:
    ap = argparse.ArgumentParser(description="Migra movimientos quitando cuenta_id")
    ap.add_argument("--db", default=str(DB_DIR / "tesoreria.db"))
    args = ap.parse_args()
    con = conectar(Path(args.db))
    try:
        migrar(con)
    finally:
        con.close()


if __name__ == "__main__":
    main()
