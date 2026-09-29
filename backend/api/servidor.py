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
   GET  /api/saldos?anio=YYYY          -> [{fecha, ing, egr, neto, acumulado_usd}] (Dashboard; sin anio = todo)
   GET  /api/anios                -> ["2025","2026",...] años con datos (selectores de año)
   GET  /api/notificaciones?hoy=  -> {hoy, badge, resumen, total_vencido_usd, grupos}
     (vencido + buckets d7/d15/d30/d60/d90/mas90; vencido solo alerta, no suma)
  GET  /api/movimientos?tipo=&status=&q=&page=&limit= -> lista paginada
  POST /api/movimientos -> crear (status solo pendiente|realizado)
  PUT  /api/movimientos/<id> -> editar fecha_pago+observacion (pasa a aplazado)
  PUT  /api/movimientos/<id>/realizado -> marcar realizado con fecha de hoy
  DELETE /api/movimientos/<id> -> eliminar
   DELETE /api/datos             -> borrado total con clave admin (header X-Admin-Clave, RN-13)
   GET  /api/entidades?tipo=    -> clientes/proveedores (lectura)
   GET  /api/cuentas            -> bancos/cuentas (lectura)
   GET  /api/bitacora?accion=&tabla=&desde=&hasta=&q=&page=&limit= -> auditoría paginada
   GET  /api/bitacora/export?accion=&tabla=&desde=&hasta=&q= -> reporte .txt (respeta filtros)
   GET  /api/recursos           -> último Excel cargado (nombre+fecha+filas) + conteo

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
from servicios.arranque import estado, importar_archivo, init_vacio, plantilla_asegurada, recursos
from servicios import bitacora as srv_bit
from servicios.configuracion import borrar_todo
from servicios.entidades import listar_cuentas, listar_entidades
from servicios.flujo import anios, flujo_por_modo, saldos


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

    def _txt(self, texto: str, nombre: str):
        body = texto.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Disposition", f"attachment; filename={nombre}")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

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
            q = parse_qs(u.query)
            con = conectar(self.db)
            try:
                res = saldos(con, q.get("anio", [""])[0])
            finally:
                con.close()
            return self._json(res)
        if u.path == "/api/anios":
            con = conectar(self.db)
            try:
                res = anios(con)
            finally:
                con.close()
            return self._json(res)
        if u.path == "/api/notificaciones":
            from servicios import notificaciones as srv_not
            q = parse_qs(u.query)
            con = conectar(self.db)
            try:
                res = srv_not.listar(con, q.get("hoy", [""])[0] or None)
            except ValueError as e:
                return self._json({"error": f"parámetros inválidos: {e}"}, 400)
            finally:
                con.close()
            return self._json(res)
        if u.path == "/api/bitacora":
            q = parse_qs(u.query)
            g = lambda k: q.get(k, [""])[0]
            con = conectar(self.db)
            try:
                res = srv_bit.listar(con, accion=g("accion"), tabla=g("tabla"),
                                     desde=g("desde"), hasta=g("hasta"),
                                     texto=g("q"), page=g("page") or 1,
                                     limit=g("limit") or 50)
            except ValueError as e:
                return self._json({"error": f"parámetros inválidos: {e}"}, 400)
            finally:
                con.close()
            return self._json(res)
        if u.path == "/api/bitacora/export":
            from datetime import datetime
            q = parse_qs(u.query)
            g = lambda k: q.get(k, [""])[0]
            filtros = {"accion": g("accion"), "tabla": g("tabla"),
                       "desde": g("desde"), "hasta": g("hasta"), "q": g("q")}
            con = conectar(self.db)
            try:
                completo = srv_bit.listar(con, accion=filtros["accion"],
                                          tabla=filtros["tabla"], desde=filtros["desde"],
                                          hasta=filtros["hasta"], texto=filtros["q"],
                                          page=1, limit=200)
                # Traer el resto si hay más de 200 (reporte completo, no paginado)
                total = completo["total"]
                filas = completo["rows"]
                if total > len(filas):
                    resto = srv_bit.listar(con, accion=filtros["accion"],
                                           tabla=filtros["tabla"], desde=filtros["desde"],
                                           hasta=filtros["hasta"], texto=filtros["q"],
                                           page=1, limit=total if total <= 5000 else 5000)
                    filas = resto["rows"]
                txt = srv_bit.generar_txt(list(reversed(filas)), filtros)
                srv_bit.registrar(con, "EXPORTAR_LOGS", "bitacora", None,
                                  f"reporte txt con {len(filas)} eventos",
                                  anterior=None, nuevo=dict(filtros), origen="UI",
                                  commit=True)
            finally:
                con.close()
            nombre = "bitacora_" + datetime.now().strftime("%Y%m%d_%H%M") + ".txt"
            return self._txt(txt, nombre)
        if u.path == "/api/recursos":
            con = conectar(self.db)
            try:
                res = recursos(con)
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
            nombre_orig = form["archivo"].filename
            with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as tmp:
                tmp.write(form["archivo"].file.read())
                tmppath = Path(tmp.name)
            try:
                res = importar_archivo(tmppath, self.db, nombre_original=nombre_orig)
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
        # Borrado total (zona de peligro, RN-13): vuelve al primer arranque.
        if u.path == "/api/datos":
            con = conectar(self.db)
            try:
                res = borrar_todo(con, self.headers.get("X-Admin-Clave", ""))
            except PermissionError as e:
                return self._json({"error": str(e)}, 403)
            finally:
                con.close()
            return self._json(res)
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
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Admin-Clave")
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
