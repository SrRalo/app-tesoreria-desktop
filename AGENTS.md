# AGENTS.md - flow-treasury

App de flujo de tesorería: front vanilla + backend Python con Excel como fuente de datos.

## Alcance
- Front: HTML + CSS + JS vanilla. Sin build, sin npm, sin frameworks.
- No agregar `package.json`, bundlers, ni dependencias externas salvo CDN con justificación.
- Backend: Python para lógica de negocio (leer Excel como fuente de datos, validar, importar a BD relacional, exponer API JSON). Sin frameworks JS.
- Contenido UI en español (es-MX). Moneda USD.
- Layout: una sola pantalla con barra lateral (sidebar) y 5 vistas sin recargar: Dashboard Principal, Vista de Flujo, Movimientos, Entidades, Configuración (zona de peligro RN-13).

## Estructura
- `frontend/` para el front: `index.html` (entrypoint único), `styles.css`, `app.js`, `data.js` (mocks solo para demo sin backend).
- `backend/` para código Python (ETL Excel → BD + API).
- `database/` para la BD relacional (`schema.sql`, `tesoreria.db` en dev) y la plantilla generada (`plantilla_flujo.xlsx`). El Excel fuente del usuario solo se usa al importar, no se consulta en runtime.
- `docs/` para documentación del proyecto (`requisitos.md`, `product.md`, `Branding.md`) y la demo anterior archivada (`flujo-demo-2026.html`, solo referencia).
- Este archivo `AGENTS.md` vive en la raíz (lo exige el tooling de agentes).
- Datos: Excel (`flujo de caja diario`) es solo fuente de carga. En runtime el front consulta la BD relacional vía API JSON. `data.js` mock solo como fallback de demo.
- Nunca consultar el `.xlsx` directo por request: importar una vez a BD, consultar con SQL paginado + saldos precalculados.
- BD: SQLite portable monousuario (`tesoreria.db` junto al `.exe`, en `database/` en dev). La app se mueve con todo: exe + db + front embebido. Solo Windows 10/11 64-bit por ahora.
- Primer arranque: la app detecta DB vacía y ofrece 2 caminos: (a) seleccionar Excel existente para importar, (b) iniciar vacío con saldo inicial USD. `backend/etl/plantilla.py` genera `database/plantilla_flujo.xlsx` con el formato exacto + validaciones para evitar errores de lectura.

## Ejecutar / verificar
- Front sin backend: abrir `frontend/index.html` en navegador o con servidor estático desde `frontend/`:
  `python3 -m http.server 8000`
- Con backend: correr API Python (ver `backend/README.md`) y abrir el front apuntando a la API.
- Distribución Windows: `PyInstaller --onefile` (`backend/README.md`). Se entrega carpeta portable con `.exe + tesoreria.db + front embebido`. Sin Python instalado en destino.
- Antes de dar por terminado: abrir la página y comprobar consola sin errores y layout usable en desktop y móvil.

## Convenciones
- Un solo archivo CSS y un solo JS mientras sea legible. No fragmentar prematuramente.
- Estilos inline en HTML solo para prototipado rápido; mover a `styles.css` al consolidar.
- Preferir tablas + tarjetas simples y gráficos con `<canvas>` vanilla o SVG. No librerías de charts salvo petición explícita.
- Backend Python: ETL en un paquete (`etl/importar.py` + `etl/plantilla.py`), lógica en servicios (`servicios/flujo.py`, `movimientos.py`, `entidades.py`, `arranque.py`), infra en `nucleo/`, API en `api/servidor.py` (entrypoint `run.py`; `app.py` es shim compatible), tests pytest en `tests/`. SQL con índice `idx_mov(fecha_pago, tipo, entidad_id, cuenta_id, status)` + tabla `saldos_diarios` precalculada (solo `realizado` suma al flujo). Catálogos cerrados RN-09. `GET /api/flujo?modo=diario|trimestre|mensual` sin paginación.

## Diseño
- Skill `impeccable` instalada en `.opencode/skills/impeccable` (comando `/impeccable`). Usar `init` antes de diseñar pantallas nuevas.
- En Windows PowerShell usar `impeccable.cmd` y `npx.cmd` (los `.ps1` están bloqueados por ExecutionPolicy).
- Iconos sidebar (Lucide, 18–23px): Dashboard Principal `LayoutDashboard`, Vista de Flujo `ChartNoAxesCombined`, Movimientos `ArrowDownLeft/ArrowUpRight`, Entidades `Building2/Users` + bancos `Landmark`, Configuración `Settings`.
