"""Fase 5 — api/servidor.py: humo HTTP real (puerto efímero, BD temporal).

Cubre: estáticos, estado, CRUD por HTTP, importar multipart, 404 y CORS.
"""
from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from datetime import date
from http.server import ThreadingHTTPServer

import pytest

from api.servidor import Handler
from etl.plantilla import crear_plantilla
from nucleo.basedatos import conectar


def llamar(base, metodo, ruta, cuerpo=None, ctype="application/json"):
    data = None
    headers = {}
    if cuerpo is not None:
        data = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo).encode("utf-8")
        headers["Content-Type"] = ctype
    req = urllib.request.Request(base + ruta, data=data, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req) as r:
            raw = r.read()
            try:
                return r.status, json.loads(raw.decode("utf-8")), r.headers
            except ValueError:
                return r.status, raw, r.headers
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8")), e.headers
        except ValueError:
            return e.code, raw, e.headers


def multipart_xlsx(xlsx_bytes, nombre="f.xlsx"):
    b = "TESTBOUNDARY"
    head = (f"--{b}\r\nContent-Disposition: form-data; name=\"archivo\"; "
            f"filename=\"{nombre}\"\r\nContent-Type: "
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            f"\r\n\r\n").encode()
    return b"".join([head, xlsx_bytes, f"\r\n--{b}--\r\n".encode()]), \
        f"multipart/form-data; boundary={b}"


@pytest.fixture
def base(tmp_path):
    db = tmp_path / "api.db"
    conectar(db).close()
    anterior = Handler.db
    Handler.db = db
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    hilo = threading.Thread(target=srv.serve_forever, daemon=True)
    hilo.start()
    yield f"http://127.0.0.1:{srv.server_port}", tmp_path
    srv.shutdown()
    srv.server_close()
    Handler.db = anterior


def test_raiz_sirve_index(base):
    url, _ = base
    status, cuerpo, headers = llamar(url, "GET", "/")
    assert status == 200
    assert "text/html" in headers.get("Content-Type", "")
    assert b"Flujo de Tesorer" in cuerpo or b"flow" in cuerpo.lower()


def test_estatico_css(base):
    url, _ = base
    status, cuerpo, _ = llamar(url, "GET", "/styles.css")
    assert status == 200 and len(cuerpo) > 1000


def test_404_json(base):
    url, _ = base
    status, cuerpo, _ = llamar(url, "GET", "/no-existe")
    assert status == 404 and cuerpo["error"] == "no encontrado"


def test_cors_y_options(base):
    url, _ = base
    _, _, headers = llamar(url, "GET", "/api/estado")
    assert headers.get("Access-Control-Allow-Origin") == "*"
    status, _, headers = llamar(url, "OPTIONS", "/api/movimientos")
    assert status == 204
    assert "PUT" in headers.get("Access-Control-Allow-Methods", "")


def test_ciclo_arranque(base):
    url, _ = base
    _, est, _ = llamar(url, "GET", "/api/estado")
    assert est["necesita_import"] is True
    status, res, _ = llamar(url, "POST", "/api/init-vacio",
                            {"saldo_inicial_usd": 2500, "fecha_inicio": "2026-03-01"})
    assert status == 200 and res["ok"] is True


def test_crud_completo_por_http(base):
    url, _ = base
    nuevo = {"fecha_pago": "2026-02-02", "tipo": "ingreso", "tipo_pago": "transferencia",
             "entidad": "CLI1", "concepto_pago": "prestamo", "banco": "Pichincha",
             "valor_usd": 1000, "status": "pendiente"}
    status, res, _ = llamar(url, "POST", "/api/movimientos", nuevo)
    assert status == 201 and isinstance(res["id"], int)
    mid = res["id"]

    _, lista, _ = llamar(url, "GET", "/api/movimientos?tipo=ingreso")
    assert lista["total"] == 1

    _, res, _ = llamar(url, "PUT", f"/api/movimientos/{mid}",
                       {"fecha_pago": "2026-02-03", "observacion": "reprog"})
    assert res == {"ok": True, "status": "aplazado"}

    _, res, _ = llamar(url, "PUT", f"/api/movimientos/{mid}/realizado")
    assert res == {"ok": True, "fecha_pago": date.today().strftime("%Y-%m-%d")}

    _, res, _ = llamar(url, "DELETE", f"/api/movimientos/{mid}")
    assert res == {"ok": True}
    _, lista, _ = llamar(url, "GET", "/api/movimientos")
    assert lista["total"] == 0


def test_errores_http(base):
    url, _ = base
    status, res, _ = llamar(url, "POST", "/api/movimientos", {"tipo": "ingreso"})
    assert status == 400 and "error" in res
    status, res, _ = llamar(url, "PUT", "/api/movimientos/9999/realizado")
    assert status == 404
    status, res, _ = llamar(url, "GET", "/api/flujo?modo=otro")
    assert status == 400


def test_importar_multipart(base):
    url, tmp = base
    xlsx = tmp / "subida.xlsx"
    crear_plantilla(xlsx)
    cuerpo, ctype = multipart_xlsx(xlsx.read_bytes())
    status, res, _ = llamar(url, "POST", "/api/importar", cuerpo, ctype)
    assert status == 200 and res["filas_ok"] == 3
    _, est, _ = llamar(url, "GET", "/api/estado")
    assert est == {"db_lista": True, "movimientos": 3, "necesita_import": False}
    _, flujo, _ = llamar(url, "GET", "/api/flujo?modo=diario&desde=2026-01-05")
    assert len(flujo["columnas"]) == 7 and flujo["columnas"][0]["ing"] == 8500


def test_cuentas_con_aviso_y_sin_cuadre(base):
    url, _ = base
    # La conciliación/cuadre se eliminó: estos endpoints ya no existen.
    status, _, _ = llamar(url, "GET", "/api/cuadre?mes=2026-08")
    assert status == 404
    status, _, _ = llamar(url, "GET", "/api/cuentas/saldos")
    assert status == 404
    status, _, _ = llamar(url, "GET", "/api/conciliacion/pendientes")
    assert status == 404
    _, cuentas, _ = llamar(url, "GET", "/api/cuentas")
    assert any("aviso" in c for c in cuentas)


def test_extracto_importar_y_pendientes(base):
    url, tmp = base
    html = tmp / "pich.xls"
    html.write_text(
        "<html><body><table>"
        "<tr><td><b>Saldo Anterior:</b></td><td>1000.00</td></tr>"
        "<tr><td><b>Saldo Actual:</b></td><td>1200.00</td></tr>"
        "<tr><td><b>Fecha este Corte:</b></td><td>31-08-2026</td></tr>"
        "<tr><td>DETALLE DE MOVIMIENTOS</td></tr>"
        "<tr><td>FECHA</td><td>OFIC.</td><td>N.DOC.</td><td>DESCRIPCION</td>"
        "<td>DEBITO</td><td>CREDITO</td><td>SALDO</td></tr>"
        "<tr><td>03-ago.</td><td>8386</td><td>D1</td><td>TRANSF RECIBIDA</td>"
        "<td>0.00</td><td>500.00</td><td>1500.00</td></tr>"
        "<tr><td>04-ago.</td><td>0012</td><td>D2</td><td>PAGO X</td>"
        "<td>300.00</td><td>0.00</td><td>1200.00</td></tr>"
        "</table></body></html>", encoding="utf-8")

    def multipart_archivo(path, banco):
        b = "BND"
        head = (f"--{b}\r\nContent-Disposition: form-data; name=\"archivo\"; "
                f"filename=\"{path.name}\"\r\nContent-Type: text/html\r\n\r\n").encode()
        mid = (f"\r\n--{b}\r\nContent-Disposition: form-data; name=\"banco\"\r\n\r\n"
               f"{banco}\r\n--{b}--\r\n").encode()
        return head + path.read_bytes() + mid, f"multipart/form-data; boundary={b}"

    cuerpo, ctype = multipart_archivo(html, "pichincha")
    status, res, _ = llamar(url, "POST", "/api/extractos/importar", cuerpo, ctype)
    assert status == 200 and res["lineas_nuevas"] == 2
    assert res["saldo_actual"] == 1200 and res["apertura_fijada"] == 1000
    assert "conciliacion" not in res  # sin conciliación: no genera movimientos
    # Reimportar no duplica
    cuerpo, ctype = multipart_archivo(html, "pichincha")
    status, res2, _ = llamar(url, "POST", "/api/extractos/importar", cuerpo, ctype)
    assert status == 200 and res2["lineas_nuevas"] == 0 and res2["duplicadas"] == 2
    # El extracto NO genera movimientos: el flujo sigue vacío
    _, movs, _ = llamar(url, "GET", "/api/movimientos")
    assert movs["total"] == 0
    # Pero el banco sí expone el extracto en sus subpestañas
    _, bancos, _ = llamar(url, "GET", "/api/bancos")
    assert bancos["total"] == 1 and bancos["rows"][0]["banco"] == "Pichincha"
    # Banco inválido se rechaza
    cuerpo, ctype = multipart_archivo(html, "otro")
    status, res3, _ = llamar(url, "POST", "/api/extractos/importar", cuerpo, ctype)
    assert status == 400 and "error" in res3


def _importar_seed(url, tmp):
    xlsx = tmp / "seed.xlsx"
    crear_plantilla(xlsx)
    cuerpo, ctype = multipart_xlsx(xlsx.read_bytes())
    status, res, _ = llamar(url, "POST", "/api/importar", cuerpo, ctype)
    assert status == 200 and res["filas_ok"] == 3


def test_flujo_escenario_http(base):
    """RF-03 por HTTP: escenario válido reescala, inválido da 400."""
    url, tmp = base
    _importar_seed(url, tmp)
    _, b, _ = llamar(url, "GET", "/api/flujo?modo=diario&desde=2026-01-05&escenario=base")
    assert b["escenario"] == "base" and b["columnas"][0]["ing"] == 8500
    _, o, _ = llamar(url, "GET", "/api/flujo?modo=diario&desde=2026-01-05&escenario=optimista")
    assert o["escenario"] == "optimista" and o["columnas"][0]["ing"] == 9775.0
    _, p, _ = llamar(url, "GET", "/api/flujo?modo=diario&desde=2026-01-05&escenario=pesimista")
    assert p["escenario"] == "pesimista" and p["columnas"][0]["ing"] == 5950.0
    status, res, _ = llamar(url, "GET", "/api/flujo?modo=diario&escenario=otro")
    assert status == 400 and "error" in res
    _, s, _ = llamar(url, "GET", "/api/saldos?escenario=optimista")
    assert s[0]["ing"] == 9775.0
    status, res, _ = llamar(url, "GET", "/api/saldos?escenario=otro")
    assert status == 400 and "error" in res


def test_flujo_export_http(base):
    """RF-05 por HTTP: CSV descarga con cabecera; XLSX según openpyxl; formato malo da 400."""
    url, tmp = base
    _importar_seed(url, tmp)
    status, raw, headers = llamar(url, "GET", "/api/flujo/export?modo=diario&desde=2026-01-05&formato=csv")
    assert status == 200
    assert "text/csv" in headers.get("Content-Type", "")
    assert "attachment" in headers.get("Content-Disposition", "")
    texto = raw.decode("utf-8-sig")
    assert texto.splitlines()[0] == "clave,titulo,subtitulo,saldo_inicial,ingresos,egresos,neto,acumulado"
    assert "2026-01-05" in texto and "8500" in texto
    status, raw, _ = llamar(url, "GET",
                            "/api/flujo/export?modo=diario&desde=2026-01-05&formato=csv&escenario=pesimista")
    assert status == 200 and "5950" in raw.decode("utf-8-sig")
    status, res, _ = llamar(url, "GET", "/api/flujo/export?modo=diario&formato=otro")
    assert status == 400 and "error" in res
    pytest.importorskip("openpyxl")
    status, raw, headers = llamar(url, "GET", "/api/flujo/export?modo=mensual&anio=2026&formato=xlsx")
    assert status == 200
    assert "spreadsheetml" in headers.get("Content-Type", "")
    assert raw[:2] == b"PK"  # contenedor ZIP xlsx
