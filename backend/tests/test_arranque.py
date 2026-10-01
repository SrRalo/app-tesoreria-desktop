"""Fase 4 — servicios/arranque.py: estado, init_vacio, importar, plantilla."""
from __future__ import annotations

import pytest

from etl.plantilla import crear_plantilla
from nucleo.basedatos import conectar
from servicios.arranque import estado, importar_archivo, init_vacio, plantilla_asegurada, recursos
from servicios.movimientos import ErrorValidacion


class TestEstado:
    def test_db_vacia_necesita_import(self, con):
        assert estado(con) == {"db_lista": True, "movimientos": 0, "necesita_import": True}

    def test_db_con_movimientos_no_necesita(self, con_seed):
        con, _ = con_seed
        assert estado(con) == {"db_lista": True, "movimientos": 3, "necesita_import": False}


class TestInitVacio:
    def test_fija_saldo_y_fecha(self, con):
        assert init_vacio(con, 2500, "2026-03-01") == {"ok": True}
        assert float(con.execute(
            "SELECT valor FROM config WHERE clave='saldo_inicial_usd'").fetchone()[0]) == 2500
        assert con.execute(
            "SELECT valor FROM config WHERE clave='fecha_inicio'").fetchone()[0] == "2026-03-01"

    def test_saldo_invalido(self, con):
        with pytest.raises(ErrorValidacion):
            init_vacio(con, "mucho")


class TestImportarArchivo:
    def test_importa_plantilla_3_filas(self, tmp_path):
        xlsx = tmp_path / "fuente.xlsx"
        crear_plantilla(xlsx)
        db = tmp_path / "imp.db"
        res = importar_archivo(xlsx, db)
        assert res["ok"] is True and res["filas_ok"] == 3 and res["errores"] == []
        con2 = conectar(db)
        try:
            assert estado(con2)["movimientos"] == 3
        finally:
            con2.close()

    def test_reimportar_no_duplica(self, tmp_path):
        xlsx = tmp_path / "fuente.xlsx"
        crear_plantilla(xlsx)
        db = tmp_path / "imp.db"
        importar_archivo(xlsx, db)
        res2 = importar_archivo(xlsx, db)
        assert res2["filas_ok"] == 0  # antiduplicado


class TestPlantillaAsegurada:
    def test_genera_si_falta_y_reutiliza(self, tmp_path):
        dest = tmp_path / "plantilla_flujo.xlsx"
        out1 = plantilla_asegurada(dest)
        assert out1.exists()
        out2 = plantilla_asegurada(dest)
        assert out2 == out1


class TestRecursos:
    def test_historial_desglosa_archivos_y_tipos(self, tmp_path):
        xlsx = tmp_path / "fuente.xlsx"
        crear_plantilla(xlsx)
        db = tmp_path / "imp.db"
        importar_archivo(xlsx, db, nombre_original="fuente.xlsx")
        importar_archivo(xlsx, db, nombre_original="fuente.xlsx")
        con2 = conectar(db)
        try:
            cta = con2.execute("SELECT id FROM cuentas WHERE banco='Pichincha'").fetchone()[0]
            con2.execute("INSERT INTO cortes_bancarios (cuenta_id, fecha_corte,"
                         " saldo_actual, archivo) VALUES (?,?,?,?)",
                         (cta, "2026-08-31", 100.0, "estado_pichincha.html"))
            con2.execute("INSERT INTO import_log (archivo, filas_ok, filas_error)"
                         " VALUES (?,?,?)", ("estado_pichincha.html", 10, 0))
            con2.commit()
            rec = recursos(con2)
            assert rec["ultimo_excel"]["archivo"] == "estado_pichincha.html"
            assert len(rec["historial"]) == 3
            ext = next(h for h in rec["historial"] if h["archivo"] == "estado_pichincha.html")
            assert ext["tipo"] == "extracto" and ext["banco"] == "Pichincha"
            mov = next(h for h in rec["historial"] if h["archivo"] == "fuente.xlsx")
            assert mov["tipo"] == "movimientos"
        finally:
            con2.close()
