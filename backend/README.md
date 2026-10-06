# Backend — flow-treasury (Python + SQLite portable)

Front vanilla + API Python stdlib. BD SQLite monousuario (`tesoreria.db` junto al `.exe`).
El Excel es solo fuente de carga: se importa una vez, en runtime todo es SQL + JSON.

## Dev (Windows PowerShell, Python 3.11 o 3.12)

> `app.py` usa el módulo `cgi` (eliminado en Python 3.13). Para dev y build use Python 3.11/3.12.

```powershell
cd backend
pip install -r requirements.txt

# 1. Generar plantilla con formato válido
python -m etl.plantilla ..\database\plantilla_flujo.xlsx

# 2. Importar un Excel a la BD de dev
python -m etl.importar ..\database\plantilla_flujo.xlsx --db ..\database\tesoreria.db

# 3. Correr la app (abre el navegador solo)
python run.py --db ..\database\tesoreria.db --port 8000
# -> http://127.0.0.1:8000
```

Estructura: `run.py` (entrypoint), `api/` (servidor HTTP), `nucleo/` (rutas, BD,
catálogos), `servicios/` (flujo, movimientos, entidades, arranque), `etl/`
(importar, plantilla), `tests/` (pytest: `pip install -r requirements-dev.txt`
y `pytest tests/ -v`). `app.py` es un shim compatible que delega en `run.py`.

Endpoints: `GET /api/estado`, `POST /api/init-vacio`, `POST /api/importar`
(multipart campo `archivo`), `GET /api/plantilla`,
`GET /api/flujo?modo=diario|trimestre|mensual` (diario: `&desde=YYYY-MM-DD` → 7 días;
trimestre: `&mes=YYYY-MM` → ese + 2 siguientes; mensual: `&anio=YYYY` → 12 meses. Alias de compatibilidad: `semana`→`diario`, `anual`→`mensual`),
`GET /api/flujo/export?modo=&formato=csv|xlsx` (mismo periodo + `&escenario=`; RF-05),
`GET /api/saldos?anio=&escenario=base|optimista|pesimista` (RF-03, RN-04),
`GET/POST /api/movimientos` (filtros `tipo,status,q,page,limit`), `GET /api/entidades`, `GET /api/cuentas`,
`DELETE /api/datos` (borrado total con header `X-Admin-Clave`, RN-13).

Estados de cuenta (RF-19, solo lectura en Entidades > Bancos):

```powershell
cd backend
# Importar un estado de cuenta (pichincha|internacional|produbanco)
python -m etl.extractos.importar_extracto "..\..\fuente de datos\01 31 agosto Pichiccha.xls" pichincha --db ..\database\tesoreria.db
```

o por HTTP: `POST /api/extractos/importar` (multipart `archivo` + `banco`).
Los extractos NO generan movimientos ni entran al Flujo; solo se consultan
en `GET /api/bancos`, `GET /api/bancos/<id>/meses` y
`GET /api/bancos/<id>/extracto`. Reimportar no duplica (hash).

## Primer arranque (app empaquetada)

1. La app detecta DB vacía (`GET /api/estado -> necesita_import=true`) y muestra modal:
   - (a) **Seleccionar Excel** → `POST /api/importar` → valida e importa.
   - (b) **Iniciar vacío** → `POST /api/init-vacio {saldo_inicial_usd, fecha_inicio}`.
2. Botón extra: **Descargar plantilla** → `GET /api/plantilla`.

## Build ejecutable portable (solo Windows 10/11 64-bit)

```powershell
cd backend
pip install -r requirements.txt
pyinstaller --onefile --windowed --name FlowTreasury `
  --icon "assets\icon.ico" `
  --add-data "..\frontend;frontend" `
  --add-data "..\database\schema.sql;database" `
  run.py
```

Icono: `assets/icon.ico` (generado desde el SVG de la marca del sidebar).

Entregar carpeta portable (el front y el schema viajan embebidos en el `.exe`):

```
FlowTreasury\
  FlowTreasury.exe
  tesoreria.db           (se crea al primer arranque si no existe)
  plantilla_flujo.xlsx   (se genera con GET /api/plantilla si no existe)
```

Doble clic → abre `http://127.0.0.1:8000` en el navegador. Sin Python instalado.
La carpeta se mueve completa a otra PC.

## Notas

- Solo stdlib en runtime (`http.server + sqlite3`): el `.exe` no carga pandas.
  `openpyxl` solo se usa en `etl/importar.py`/`etl/plantilla.py`.
  Para importar dentro del exe, incluya `openpyxl` en el build o importe en dev.
- Saldos: `saldos_diarios` se recalcula solo al importar o CRUD (ver `etl.importar.recalcular_saldos`).
- Todo en USD. Fechas `YYYY-MM-DD`.
