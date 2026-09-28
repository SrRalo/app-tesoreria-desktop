"""servidor.py — API JSON + front estático (solo stdlib, portable a .exe).

Movido sin cambios desde app.py (Fase 5). Capa delgada: parsea HTTP,
delega en servicios/ y traduce el resultado a JSON + códigos de estado.

Endpoints:
  GET  /                       -> frontend/index.html
  GET  /api/estado             -> {db_lista, movimientos, necesita_import}
  POST /api/init-vacio         -> {saldo_inicial_usd, fecha_inicio}
  POST /api/importar           -> multipart con campo 'archivo' (.xlsx)
  GET  /api/plantilla          -> descarga plantilla_flujo.xlsx (la genera si falta)
  GET  /api/flujo?modo=semana&desde=YYYY-MM-DD   -> 7 columnas día (nombre + fecha)
  GET  /api/flujo?modo=trimestre&mes=YYYY-MM     -> 3 columnas mes (el elegido + 2 siguientes)
  GET  /api/flujo?modo=anual&anio=YYYY           -> 12 columnas mes
  (cada columna: saldo_inicial, ing, egr, neto, acumulado + detalle de movimientos para subfilas)
  GET  /api/saldos               -> [{fecha, ing, egr, neto, acumulado_usd}] (Dashboard)
  GET  /api/movimientos?tipo=&status=&q=&page=&limit= -> lista paginada
  POST /api/movimientos -> crear (status solo pendiente|realizado)
  PUT  /api/movimientos/<id> -> editar fecha_pago+observacion (pasa a aplazado)
  PUT  /api/movimientos/<id>/realizado -> marcar realizado con fecha de hoy
  DELETE /api/movimientos/<id> -> eliminar
  GET  /api/entidades?tipo=    -> clientes/proveedores (lectura)
  GET  /api/cuentas            -> bancos/cuentas (lectura)

Uso dev:
  python run.py --db ..\\database\\tesoreria.db --port 8000
Build exe: ver README.md
"""
from __future__ import annotations

import argparse
import cgi
import json
import mimetypes
import tempfile
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from nucleo.basedatos import conectar
from nucleo.rutas import db_default, front_file
from servicios import movimientos as srv_mov
from servicios.arranque import estado, importar_archivo, init_vacio, plantilla_asegurada
from servicios.entidades import listar_cuentas, listar_entidades
from servicios.flujo import flujo_por_modo, saldos


class Handler(BaseHTTPRequestHandler):
    db: Path = db_default()
    server_version = "FlowTreasury/1.0"

    # --- utilidades ---
    def _json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _leer_json(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        return json.loads((self.rfile.read(n) or b"{}").decode("utf-8") or "{}")

    def log_message(self, *a):  # silencioso
        pass

    # --- estáticos ---
    def do_GET(self):
        u = urlparse(self.path)
        if u.path in ("/", "/index.html"):
            f = front_file("index.html")
            if not f:
                return self._json({"error": "index.html no encontrado"}, 404)
            body = f.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if u.path == "/api/estado":
            con = conectar(self.db)
            try:
                res = estado(con)
            finally:
                con.close()
            return self._json(res)
        if u.path == "/api/plantilla":
            out = plantilla_asegurada()
            body = out.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type",
                             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
            self.send_header("Content-Disposition",
                             "attachment; filename=plantilla_flujo.xlsx")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if u.path == "/api/flujo":
            q = parse_qs(u.query)
            modo = q.get("modo", ["semana"])[0]
            if modo not in ("semana", "trimestre", "anual"):
                return self._json({"error": "modo debe ser semana|trimestre|anual"}, 400)
            con = conectar(self.db)
            try:
                res = flujo_por_modo(con, modo, q)
            except (ValueError, KeyError) as e:
                return self._json({"error": f"parámetros inválidos: {e}"}, 400)
            finally:
                con.close()
            return self._json(res)
        if u.path == "/api/movimientos":
            q = parse_qs(u.query)
            con = conectar(self.db)
            try:
                res = srv_mov.listar(
                    con, tipo=q.get("tipo", [""])[0], status=q.get("status", [""])[0],
                    texto=q.get("q", [""])[0], page=q.get("page", ["1"])[0],
                    limit=q.get("limit", ["50"])[0])
            except ValueError as e:
                return self._json({"error": f"parámetros inválidos: {e}"}, 400)
            finally:
                con.close()
            return self._json(res)
        if u.path == "/api/entidades":
            q = parse_qs(u.query)
            con = conectar(self.db)
            try:
                res = listar_entidades(con, q.get("tipo", [""])[0])
            finally:
                con.close()
            return self._json(res)
        if u.path == "/api/cuentas":
            con = conectar(self.db)
            try:
                res = listar_cuentas(con)
            finally:
                con.close()
            return self._json(res)
        if u.path == "/api/saldos":
            con = conectar(self.db)
            try:
                res = saldos(con)
            finally:
                con.close()
            return self._json(res)
        # estático genérico (styles.css, app.js, data.js)
        rel = (u.path or "/").lstrip("/")
        if ".." not in rel and "/" not in rel:
            f = front_file(rel)
            if f:
                body = f.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type",
                                 mimetypes.guess_type(f.name)[0] or "application/octet-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
        return self._json({"error": "no encontrado"}, 404)

    def do_POST(self):
        u = urlparse(self.path)
        if u.path == "/api/init-vacio":
            d = self._leer_json()
            con = conectar(self.db)
            try:
                res = init_vacio(con, d.get("saldo_inicial_usd", 5000),
                                 d.get("fecha_inicio", ""))
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            finally:
                con.close()
            return self._json(res)
        if u.path == "/api/importar":
            ctype = self.headers.get("Content-Type", "")
            if "multipart" not in ctype:
                return self._json({"error": "envíe multipart con campo 'archivo'"}, 400)
            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers,
                                    environ={"REQUEST_METHOD": "POST"})
            if "archivo" not in form or not form["archivo"].filename:
                return self._json({"error": "campo 'archivo' vacío"}, 400)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp.write(form["archivo"].file.read())
                tmppath = Path(tmp.name)
            try:
                res = importar_archivo(tmppath, self.db)
            finally:
                tmppath.unlink(missing_ok=True)
            return self._json(res)
        if u.path == "/api/movimientos":
            d = self._leer_json()
            con = conectar(self.db)
            try:
                mid = srv_mov.crear(con, d)
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            finally:
                con.close()
            return self._json({"ok": True, "id": mid}, 201)
        return self._json({"error": "no encontrado"}, 404)

    def do_PUT(self):
        u = urlparse(self.path)
        # Marcar realizado: status=realizado con fecha de hoy (RN-12)
        if u.path.startswith("/api/movimientos/") and u.path.endswith("/realizado"):
            mid = u.path.split("/")[3]
            con = conectar(self.db)
            try:
                hoy = srv_mov.marcar_realizado(con, mid)
            except LookupError as e:
                return self._json({"error": str(e)}, 404)
            finally:
                con.close()
            return self._json({"ok": True, "fecha_pago": hoy})
        if u.path.startswith("/api/movimientos/"):
            mid = u.path.rsplit("/", 1)[-1]
            d = self._leer_json()
            # Edición limitada RN-12: solo fecha_pago + observacion; pasa a aplazado.
            con = conectar(self.db)
            try:
                status = srv_mov.editar(con, mid, d.get("fecha_pago", ""),
                                        d.get("observacion", ""))
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            except LookupError as e:
                return self._json({"error": str(e)}, 404)
            finally:
                con.close()
            return self._json({"ok": True, "status": status})
        return self._json({"error": "no encontrado"}, 404)

    def do_DELETE(self):
        u = urlparse(self.path)
        if u.path.startswith("/api/movimientos/"):
            mid = u.path.rsplit("/", 1)[-1]
            con = conectar(self.db)
            try:
                srv_mov.eliminar(con, mid)
            except LookupError as e:
                return self._json({"error": str(e)}, 404)
            finally:
                con.close()
            return self._json({"ok": True})
        return self._json({"error": "no encontrado"}, 404)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=str(db_default()))
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()
    Handler.db = Path(args.db)
    conectar(Handler.db).close()
    url = f"http://127.0.0.1:{args.port}"
    try:
        # En modo --windowed no hay consola (stdout es None): no debe tumbar el server.
        print(f"FlowTreasury en {url}  (DB: {Handler.db})")
    except Exception:
        pass
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    ThreadingHTTPServer(("127.0.0.1", args.port), Handler).serve_forever()
