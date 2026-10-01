"""importar_extracto.py — estado de cuenta del banco -> BD (una sola vez).

Flujo: parsear (parser por banco) → validar cadena de saldos → guardar
líneas (idempotente por hash_unico) + corte → fijar apertura 31-jul si la
cuenta aún no tiene extracto → recalcular saldos por cuenta → bitácora.

Los extractos NO generan movimientos: solo se consultan en
Entidades > Bancos. La Vista de Flujo lee únicamente `movimientos`.

En runtime la app NUNCA lee el archivo: todo queda en SQLite.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from etl.extractos import internacional, pichincha, produbanco
from etl.extractos.base import hash_linea, validar_cadena
from nucleo.basedatos import conectar

PARSERS = {"pichincha": pichincha.parsear,
           "internacional": internacional.parsear,
           "produbanco": produbanco.parsear}

# banco normalizado en la app + número de cuenta real del estado de cuenta.
CUENTAS = {"pichincha": ("Pichincha", "2100319432"),
           "internacional": ("Internacional", "7100614609"),
           "produbanco": ("Produbanco", "02006198356")}


def parsear_extracto(path: Path, banco: str) -> dict:
    clave = banco.strip().lower()
    if clave not in PARSERS:
        raise ValueError(f"banco debe ser pichincha|internacional|produbanco (vino {banco!r})")
    return PARSERS[clave](Path(path))


def importar_extracto(path: Path, banco: str, db: Path,
                      nombre_original: str | None = None) -> dict:
    datos = parsear_extracto(path, banco)
    nombre_banco, numero = CUENTAS[banco.strip().lower()]
    mostrado = nombre_original or Path(path).name
    con = conectar(Path(db))
    try:
        with con:
            cta = con.execute("SELECT * FROM cuentas WHERE banco=?",
                              (nombre_banco,)).fetchone()
            if cta is None:
                con.execute("INSERT INTO cuentas (banco, numero) VALUES (?,?)",
                            (nombre_banco, numero or datos["numero"]))
                cta = con.execute("SELECT * FROM cuentas WHERE banco=?",
                                  (nombre_banco,)).fetchone()
            elif datos["numero"] and not cta["numero"]:
                con.execute("UPDATE cuentas SET numero=? WHERE id=?",
                            (datos["numero"], cta["id"]))
                cta = con.execute("SELECT * FROM cuentas WHERE id=?",
                                  (cta["id"],)).fetchone()
            cuenta_id = cta["id"]

            errores = validar_cadena(datos["lineas"], datos["saldo_anterior"])
            nuevas, duplicadas = 0, 0
            for ln in datos["lineas"]:
                h = hash_linea(cuenta_id, ln["fecha"], ln["debito"],
                               ln["credito"], ln["referencia"],
                               ln["descripcion"])
                cur = con.execute(
                    "INSERT OR IGNORE INTO extracto_lineas "
                    "(cuenta_id, fecha, descripcion, referencia, debito_usd,"
                    " credito_usd, saldo_banco_usd, hash_unico)"
                    " VALUES (?,?,?,?,?,?,?,?)",
                    (cuenta_id, ln["fecha"], ln["descripcion"][:300],
                     ln["referencia"][:120], ln["debito"], ln["credito"],
                     ln.get("saldo_banco"), h))
                if cur.rowcount:
                    nuevas += 1
                else:
                    duplicadas += 1

            con.execute(
                "INSERT OR REPLACE INTO cortes_bancarios "
                "(cuenta_id, fecha_corte, saldo_anterior, depositos, retiros,"
                " saldo_actual, archivo) VALUES (?,?,?,?,?,?,?)",
                (cuenta_id, datos["periodo_fin"], datos["saldo_anterior"],
                 datos["depositos"], datos["retiros"], datos["saldo_actual"],
                 mostrado))

            # Apertura 31-jul: solo la primera vez que entra extracto de la cuenta.
            apertura_fijada = None
            if not cta["tiene_extracto"] and not cta["saldo_apertura_usd"]:
                con.execute("UPDATE cuentas SET saldo_apertura_usd=?,"
                            " fecha_apertura=date(?, 'start of month', '-1 day'),"
                            " numero=CASE WHEN numero='' THEN ? ELSE numero END,"
                            " tiene_extracto=1 WHERE id=?",
                            (datos["saldo_anterior"], datos["periodo_inicio"],
                             datos["numero"], cuenta_id))
                apertura_fijada = datos["saldo_anterior"]
            else:
                con.execute("UPDATE cuentas SET tiene_extracto=1 WHERE id=?",
                            (cuenta_id,))

            cur = con.execute("INSERT INTO import_log (archivo, filas_ok, filas_error)"
                              " VALUES (?,?,?)",
                              (mostrado, nuevas, len(errores)))
            log_id = cur.lastrowid
            con.execute("UPDATE extracto_lineas SET import_log_id=? "
                        "WHERE cuenta_id=? AND import_log_id IS NULL",
                        (log_id, cuenta_id))

        from etl.importar import recalcular_saldos_cuenta
        recalcular_saldos_cuenta(con)
        try:
            from servicios.bitacora import registrar
            registrar(con, "IMPORTAR", "extracto_lineas", None,
                      f"{mostrado}: {nueva_lineas(nuevas, duplicadas)}, "
                      f"corte {datos['periodo_fin']} cierra en {datos['saldo_actual']:.2f} USD",
                      anterior=None,
                      nuevo={"archivo": mostrado, "banco": nombre_banco,
                             "lineas_nuevas": nuevas, "duplicadas": duplicadas,
                             "errores_cadena": len(errores)},
                      origen="IMPORT", commit=True)
        except Exception:
            pass
        return {"ok": True, "banco": nombre_banco, "archivo": mostrado,
                "lineas_nuevas": nuevas, "duplicadas": duplicadas,
                "errores_cadena": errores,
                "saldo_anterior": datos["saldo_anterior"],
                "saldo_actual": datos["saldo_actual"],
                "apertura_fijada": apertura_fijada}
    finally:
        con.close()


def nueva_lineas(nuevas: int, duplicadas: int) -> str:
    return f"{nuevas} líneas nuevas ({duplicadas} duplicadas ignoradas)"


def main() -> None:
    import argparse
    from nucleo.rutas import DB_DIR
    ap = argparse.ArgumentParser(description="Estado de cuenta -> BD (USD)")
    ap.add_argument("archivo", help="Estado de cuenta del banco")
    ap.add_argument("banco", choices=sorted(PARSERS),
                    help="pichincha|internacional|produbanco")
    ap.add_argument("--db", default=str(DB_DIR / "tesoreria.db"))
    args = ap.parse_args()
    res = importar_extracto(Path(args.archivo), args.banco, Path(args.db))
    print(f"OK: {nueva_lineas(res['lineas_nuevas'], res['duplicadas'])}.")
    print(f"Apertura: {res['saldo_anterior']:.2f} -> cierre banco: "
          f"{res['saldo_actual']:.2f} USD.")
    for e in res["errores_cadena"][:20]:
        print("  !", e)


if __name__ == "__main__":
    main()
