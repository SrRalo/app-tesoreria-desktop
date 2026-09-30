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
