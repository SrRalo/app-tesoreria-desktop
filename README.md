# FlowTreasury — Flujo de tesorería

App de una sola pantalla para visualizar y gestionar el flujo de caja diario:
sidebar con 4 vistas sin recargar — **Dashboard Principal**, **Vista de Flujo**,
**Movimientos** y **Entidades**. Contenido en español (es-MX), moneda USD.

- **Front**: HTML + CSS + JS vanilla, sin build ni frameworks (`frontend/`).
- **Backend**: Python stdlib (API JSON + ETL) + SQLite portable (`backend/`, `database/`).
- **Dato fuente**: un Excel (`flujo de caja diario`) que se importa **una sola vez**
  a la BD relacional; en runtime todo se consulta por SQL, nunca el `.xlsx` directo.
- **Distribución**: carpeta portable Windows 10/11 64-bit (`.exe + tesoreria.db + front`),
  sin Python instalado en destino.

## Estructura

```
flow-treasury/
  README.md            ← este archivo
  AGENTS.md            ← reglas del proyecto para agentes
  frontend/            ← index.html, styles.css, app.js, data.js (mock demo)
  backend/             ← app.py (API), nucleo/, servicios/, etl/,
                         requirements.txt, README.md
  database/            ← schema.sql, tesoreria.db (dev), plantilla_flujo.xlsx
  docs/                ← requisitos.md, product.md, Branding.md,
                         flujo-demo-2026.html (demo anterior, referencia)
```

## Uso rápido

**Solo front (demo con datos simulados):**

```powershell
cd frontend
python -m http.server 8000
# -> http://127.0.0.1:8000
```

**Con backend (Windows PowerShell, Python 3.11 o 3.12):**

```powershell
cd backend
pip install -r requirements.txt
python -m etl.plantilla ..\database\plantilla_flujo.xlsx
python -m etl.importar ..\database\plantilla_flujo.xlsx --db ..\database\tesoreria.db
python run.py --db ..\database\tesoreria.db --port 8000
# -> http://127.0.0.1:8000 (sirve API + front)
```

Detalle de endpoints, primer arranque y build del `.exe`: ver `backend/README.md`.
Requisitos funcionales y reglas de negocio: ver `docs/requisitos.md`.
