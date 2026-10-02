"""Carga de archivos + bancos (RF-23/24/25/26).

Cubre: validación previa por contenido (incluido caso cruzado),
veredictos sin ETL parcial, y endpoints de bancos/meses/extracto.
"""
from __future__ import annotations

import io
import threading
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

from api.servidor import Handler
from etl.validar import detectar_tipo, validar_campo
from nucleo.basedatos import conectar
from servicios import bancos as srv_bancos
from tests.test_api import llamar


def _xlsx_minimo(fecha="Fecha", monto="Valor", saldo="Saldo Contable"):
    """XLSX con encabezados de extracto (huella Produbanco)."""
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["CUENTA: 02006198356"])
    for _ in range(10):
        ws.append([""])
    ws.append([fecha, "Referencia", "Transacción", "Signo", monto, saldo])
    ws.append(["2026-08-05", "REF1", "DEPOSITO", "(+)", 100, 1000])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _xlsx_cartera():
    from openpyxl import Workbook
    wb = Workbook()
    ws = wb.active
    ws.append(["banco", "fecha_pago", "tipo", "entidad", "valor_usd", "status"])
    ws.append(["Pichincha", "2026-09-01", "ingreso", "ACME", 500, "pendiente"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


PICHINCHA_HTML = """<html><body><table>
<tr><td>Saldo Anterior</td><td>1000.00</td></tr>
<tr><td>DETALLE DE MOVIMIENTOS</td></tr>
<tr><td>FECHA</td><td>OFIC</td><td>N.DOC</td><td>DESCRIPCION</td>
<td>DEBITO</td><td>CREDITO</td><td>SALDO</td></tr>
<tr><td>05-ago.</td><td>001</td><td>123</td><td>DEPOSITO</td>
<td></td><td>100.00</td><td>1100.00</td></tr>
</table></body></html>""".encode("utf-8")


def test_detectar_pichincha_por_contenido():
    tipo, _ = detectar_tipo(PICHINCHA_HTML, "cualquier_nombre.dat")
    assert tipo == "pichincha"


def test_campo_cruzado_produbanco_en_pichincha():
    raw = _xlsx_minimo()
    assert raw[:4] == b"PK\x03\x04"
    v = validar_campo("pichincha", raw, "estado.xlsx")
    assert v["ok"] is False
    assert v["tipo_detectado"] == "produbanco"
    assert "Produbanco" in v["motivo"] and "Pichincha" in v["motivo"]


def test_extracto_en_campo_cxc_se_rechaza():
    v = validar_campo("cxc", PICHINCHA_HTML, "cuentas.xlsx")
    assert v["ok"] is False
    assert "Pichincha" in v["motivo"]


def test_cxc_valido_pasa():
    v = validar_campo("cxc", _xlsx_cartera(), "cartera.xlsx")
    assert v["ok"] is True
    assert v["tipo_detectado"] == "cxc"


def test_desconocido_en_campo_banco():
    v = validar_campo("internacional", b"hola mundo", "nota.txt")
    assert v["ok"] is False
    assert v["tipo_detectado"] == "desconocido"


def _sembrar_banco(con):
    cta = con.execute("SELECT id FROM cuentas WHERE banco='Pichincha'").fetchone()
    cid = cta["id"]
    with con:
        con.execute(
            "INSERT INTO extracto_lineas (cuenta_id, fecha, descripcion, referencia,"
            " debito_usd, credito_usd, saldo_banco_usd, hash_unico)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (cid, "2026-08-05", "DEPOSITO", "R1", 0, 100, 1100, "h1"))
        con.execute(
            "INSERT INTO extracto_lineas (cuenta_id, fecha, descripcion, referencia,"
            " debito_usd, credito_usd, saldo_banco_usd, hash_unico)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (cid, "2026-09-02", "RETIRO", "R2", 50, 0, 1050, "h2"))
        con.execute(
            "INSERT INTO cortes_bancarios (cuenta_id, fecha_corte, saldo_anterior,"
            " depositos, retiros, saldo_actual, archivo) VALUES (?,?,?,?,?,?,?)",
            (cid, "2026-09-30", 1000, 100, 50, 1050, "sep.html"))
    return cid


def test_bancos_solo_con_extracto(con):
    cid = _sembrar_banco(con)
    rows = srv_bancos.listar_bancos(con)
    assert [r["cuenta_id"] for r in rows] == [cid]
    b = rows[0]
    assert b["saldo"] == 1050 and b["fecha_corte"] == "2026-09-30"
    assert b["logo"] == "assets/bancos/pichincha.png"


def test_bancos_meses_y_paginado(con):
    cid = _sembrar_banco(con)
    meses = srv_bancos.meses_con_extracto(con, cid)
    assert [m["mes"] for m in meses] == ["2026-09", "2026-08"]
    assert meses[0]["etiqueta"] == "Septiembre 2026"
    pag = srv_bancos.extracto_paginado(con, cid, mes="2026-08", pagina=1, limite=50)
    assert pag["total"] == 1
    fila = pag["rows"][0]
    assert (fila["fecha"], fila["referencia"], fila["descripcion"],
            fila["monto"], fila["saldo"]) == ("2026-08-05", "R1", "DEPOSITO", 100, 1100)
    assert "estado" not in " ".join(fila)  # sin conciliación en la fila


def test_api_validar_y_bancos(tmp_path):
    db = tmp_path / "api2.db"
    conectar(db).close()
    anterior = Handler.db
    Handler.db = db
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    try:
        base = f"http://127.0.0.1:{srv.server_port}"

        def multipart(campos: dict[str, tuple[bytes, str]]):
            b = "BND"
            cuerpo = b""
            for campo, (raw, nombre) in campos.items():
                cuerpo += (f'--{b}\r\nContent-Disposition: form-data; name="{campo}";'
                           f' filename="{nombre}"\r\n\r\n').encode() + raw + b"\r\n"
            cuerpo += f"--{b}--\r\n".encode()
            return cuerpo, f"multipart/form-data; boundary={b}"

        # Caso cruzado: Produbanco en campo Pichincha -> 422 y sin ETL.
        cuerpo, ctype = multipart({"pichincha": (_xlsx_minimo(), "x.xlsx")})
        req = urllib.request.Request(base + "/api/importar/validar", data=cuerpo,
                                     headers={"Content-Type": ctype}, method="POST")
        try:
            urllib.request.urlopen(req)
            raise AssertionError("debió fallar con 422")
        except Exception as e:
            assert "422" in str(e)
        status, res, _ = llamar(base, "GET", "/api/bancos")
        assert status == 200 and res["total"] == 0

        # Correcto en su campo -> 200.
        cuerpo, ctype = multipart({"pichincha": (PICHINCHA_HTML, "estado.html"),
                                   "cxc": (_xlsx_cartera(), "cartera.xlsx")})
        status, res, _ = llamar(base, "POST", "/api/importar/validar", cuerpo, ctype)
        assert status == 200 and res["ok"] is True
    finally:
        srv.shutdown()
        srv.server_close()
        Handler.db = anterior


def test_zip_sin_encabezados_no_es_produbanco():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<a/>")
        z.writestr("x.txt", "hola")
    tipo, _ = detectar_tipo(buf.getvalue(), "raro.xlsx")
    assert tipo != "produbanco"
