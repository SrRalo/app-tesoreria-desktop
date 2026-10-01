"""limpiar_generados.py — elimina del flujo los movimientos creados desde extractos.

La conciliación se eliminó: los estados de cuenta solo se consultan en
Entidades > Bancos (`extracto_lineas` + `cortes_bancarios`). Este script
borra una sola vez los movimientos generados (`[EXT-]` / `[COMISION-]` /
`conciliacion.tipo_match='generado'`) y vacía la tabla `conciliacion`
(congelada), conservando los movimientos CxC/manual y los extractos.
Luego recalcula `saldos_diarios` y `saldos_diarios_cuenta`.

Uso (desde backend/):
  py -3 -m etl.limpiar_generados --db ..\\database\\tesoreria.db
  py -3 -m etl.limpiar_generados --db ..\\database\\tesoreria.db --aplicar
Sin --aplicar es dry-run (no guarda).
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from nucleo.basedatos import conectar
from nucleo.rutas import DB_DIR


def detectar(con: sqlite3.Connection) -> dict:
    gen_ids = {r[0] for r in con.execute(
        "SELECT movimiento_id FROM conciliacion WHERE tipo_match='generado'"
        " AND movimiento_id IS NOT NULL")}
    obs_ids = {r[0] for r in con.execute(
        "SELECT id FROM movimientos WHERE observacion LIKE '%EXT-%'"
        " OR observacion LIKE '%COMISION-%'")}
    ids = gen_ids | obs_ids
    n_conc = con.execute("SELECT COUNT(*) FROM conciliacion").fetchone()[0]
    return {"movimientos_a_borrar": len(ids), "filas_conciliacion": n_conc, "ids": ids}


def limpiar(con: sqlite3.Connection) -> dict:
    det = detectar(con)
    ids = det["ids"]
    borrados = 0
    with con:
        if ids:
            bloques = list(ids)
            for i in range(0, len(bloques), 500):
                lote = bloques[i:i + 500]
                ph = ",".join("?" * len(lote))
                cur = con.execute(
                    f"DELETE FROM movimientos WHERE id IN ({ph})", lote)
                borrados += cur.rowcount
        con.execute("DELETE FROM conciliacion")
        try:
            from servicios.bitacora import registrar
            registrar(con, "BORRADO_TOTAL", "movimientos", None,
                      f"limpieza extractos: {borrados} movimientos generados eliminados, "
                      "conciliacion vaciada (extractos conservados en bancos)",
                      anterior=None,
                      nuevo={"borrados": borrados}, origen="SISTEMA")
        except Exception:
            pass
    from etl.importar import recalcular_saldos
    recalcular_saldos(con)
    n_mov = con.execute("SELECT COUNT(*) FROM movimientos").fetchone()[0]
    return {"borrados": borrados, "movimientos_restantes": n_mov,
            "filas_conciliacion": 0}


def main() -> None:
    ap = argparse.ArgumentParser(description="Limpia movimientos generados desde extractos")
    ap.add_argument("--db", default=str(DB_DIR / "tesoreria.db"))
    ap.add_argument("--aplicar", action="store_true", help="sin este flag es dry-run")
    args = ap.parse_args()
    con = conectar(Path(args.db))
    try:
        det = detectar(con)
        print(f"Movimientos a borrar: {det['movimientos_a_borrar']}")
        print(f"Filas en conciliacion: {det['filas_conciliacion']}")
        if not args.aplicar:
            print("Dry-run: sin cambios. Re-ejecute con --aplicar.")
            return
        res = limpiar(con)
        print(f"OK: {res['borrados']} eliminados, quedan {res['movimientos_restantes']} movimientos.")
        print("Conciliacion vaciada. Extractos y cortes intactos en Bancos.")
    finally:
        con.close()


if __name__ == "__main__":
    main()
