# Requisitos — flow-treasury

> Stack: front HTML + CSS + JS vanilla + backend Python. UI en español (es-MX), saldos en USD.
> Flujo de trabajo: el dueño da las historias de usuario (HU) y el asistente las traduce a requisitos funcionales (RF) en la tabla §5. No se escriben HU en este archivo.

## 1. Información general

| Campo | Descripción |
|---|---|
| Proyecto | App flujo de tesorería (front + backend Python) |
| Entrypoint | `frontend/index.html` (+ `frontend/styles.css`, `frontend/app.js`, `frontend/data.js` solo como mock fallback sin backend) |
| Front | HTML + CSS + JS vanilla. Sin `package.json`, sin bundlers, sin frameworks. CDN solo con justificación |
| Backend | Python: lógica de negocio, lectura de Excel como fuente de datos, importación a BD relacional, API JSON |
| BD | SQLite portable monousuario (`tesoreria.db` junto al `.exe`). Relacional generada desde el Excel. En runtime el front consulta la BD vía API, nunca el `.xlsx` directo. Solo Windows 10/11 64-bit |
| Despliegue | Carpeta portable que se mueve con todo: `.exe + tesoreria.db + front embebido`. Build con `PyInstaller --onefile`. Sin Python en destino |
| Layout | Una sola pantalla con barra lateral (sidebar) fija y 4 vistas sin recargar (ver §5 RF-07–RF-11) |
| Moneda / idioma | es-MX, USD (`Intl.NumberFormat('en-US',{style:'currency',currency:'USD'})`) |
| Verificación | Front: abrir `frontend/index.html` o servir `frontend/` con `python3 -m http.server 8000`. Con backend: correr API Python y apuntar el front a la API. Consola sin errores, usable en desktop y móvil |

## 2. Objetivos

1. OBJ-01: administrar el flujo de caja de una empresa
2. OBJ-02: poder hacer proyecciones en cuanto los saldos ingresados, responder preguntas como: cuando tendre dinero? cuanto dinero tendre en esa fecha? estas preguntas se responderan en un dashboard

## 3. Alcance

### 3.1 Sí incluye

- [ ] Sidebar lateral con 4 vistas sin recargar: Dashboard Principal, Vista de Flujo, Movimientos, Entidades
- [ ] Matriz de flujo horizontal con scroll-x (días como columnas) en Vista de Flujo
- [ ] Cálculos: ingreso, egreso, saldo inicial, flujo neto, flujo acumulado, saldo líquido (USD)
- [ ] Desglose de ingresos / egresos por categoría
- [ ] Panel de proyección + alerta de déficit
- [ ] Movimientos con CRUD completo + recálculo instantáneo
- [ ] Entidades (clientes, proveedores, bancos/cuentas) solo lectura
- [ ] Gráfico `<canvas>`/SVG vanilla + KPIs
- [ ] Backend con Python para manejar lógica de negocio
- [ ] Soportar Excel como fuente de datos (carga inicial + validación)
- [ ] BD relacional generada desde el Excel para consultas rápidas
- [ ] Exportación de archivos .xlsx

### 3.2 No incluye (fuera de alcance)

- [ ] login y registro
- [ ] exportación a PDF
- [ ] frameworks de javascript
- [ ] despliegue en nube

## 4. Actores / usuarios

| Actor | Descripción | Necesidad principal |
|---|---|---|
| Tesorero / dueño | Usuario principal | Ver saldo diario (USD) y simular futuro en el Dashboard |

## 5. Requisitos funcionales

Formato de ID: `RF-01`, `RF-02`… Prioridad: `Alta / Media / Baja`. Estado: `Propuesto / Aprobado / Hecho`.
Las HU las provee el dueño; el asistente las traduce a filas RF en esta tabla.

| ID | Nombre | Descripción | Prioridad | Criterio de aceptación | Estado |
|---|---|---|---|---|---|
| RF-01 | Ver matriz de flujo | Ver tabla con conceptos en filas y días en columnas, scroll horizontal, primera columna y fila de fechas fijas | Alta | Muestra 90 días, columna concepto fija, fila de fechas fija | Propuesto |
| RF-02 | Calcular flujo diario | El sistema calcula por día: `TOTAL_ING - TOTAL_EGR = FLUJO_NETO`; `SALDO_INICIAL + FLUJO_NETO = FLUJO_ACUMULADO`; `SALDO_INICIAL(d+1) = FLUJO_ACUMULADO(d)` en USD | Alta | Verificable en 3 días aleatorios sin errores de redondeo | Propuesto |
| RF-03 | Proyección por escenarios | Cambiar entre pesimista / base / optimista y horizonte 14/30/90 días para simular el futuro | Media | Cambiar escenario recalcula todo; si acumulado < 0 muestra alerta roja | Propuesto |
| RF-04 | Gráfico + KPIs | Ver KPIs (saldo inicial, total ing, total egr, neto, acumulado) y gráfico de acumulado + neto diario que refleje la tabla | Media | Gráfico coincide con la tabla; negativos en rojo, positivos en verde | Propuesto |
| RF-05 | Exportar / resetear | Exportar a CSV/XLSX, cambiar fecha de inicio y saldo inicial (USD), y resetear el mock | Baja | XLSX/CSV descarga correcto; reset restaura saldo $5,000 USD y datos iniciales | Propuesto |
| RF-06 | — (reservado) | Copia esta fila para un RF nuevo. Una fila = una sola acción verificable | — | ... | Propuesto |
| RF-07 | Navegación lateral (1 pantalla) | Una sola pantalla con sidebar que conmuta entre las 4 vistas sin recargar, con icono acorde por vista y estado activo visible | Alta | Clic en cada item cambia de vista sin reload y marca el item activo; en móvil colapsa a iconos/drawer | Propuesto |
| RF-08 | Dashboard Principal | Responder ¿cuándo tendré dinero? y ¿cuánto tendré en esa fecha? con KPIs, gráfico de acumulado y alertas de déficit | Alta | Muestra saldo actual, próximo déficit y proyección; montos en USD | Propuesto |
| RF-09 | Vista de Flujo | Matriz con 5 filas fijas (Saldo inicial, Total Ingresos desglosable en subfilas, Total Egresos desglosable en subfilas, Flujo neto diario, Flujo acumulado diario) y filtro de periodo: semana (7 días con nombre + fecha), trimestre (3 meses: se elige 1 mes y auto los 2 siguientes), anual (12 meses). Sin paginación, solo scroll-x | Alta | Totales coinciden con Movimientos; el desglose abre subfilas por movimiento; trimestre con 1 mes elegido muestra ese + 2 siguientes | Propuesto |
| RF-10 | Movimientos (CRUD) | Botón único "+ Movimiento" (tipo se elige dentro del formulario de 9 campos). Filtros por solo ingresos / solo egresos + status + búsqueda. Editar solo permite mover fecha y observación (pasa a aplazado auto). Acción "Realizado" en fila para pendientes/aplazados con fecha de hoy | Alta | Crear con aplazado se rechaza; editar bloquea 7 campos; Realizado estampa hoy y recalcula | Propuesto |
| RF-11 | Entidades (lectura) | Ver clientes, proveedores y bancos/cuentas (nombre, tipo, saldo) solo como lectura, para asociar a movimientos | Media | Lista las 3 categorías; sin botones crear/editar/eliminar; bancos muestran saldo USD | Propuesto |
| RF-12 | Importar Excel (backend) | Backend Python lee el Excel fuente, valida y lo importa a la BD relacional con reporte de errores y sin duplicar | Alta | Reimportar el mismo archivo no duplica; filas inválidas se reportan y no rompen la carga | Propuesto |
| RF-13 | API de consultas (backend) | El front consulta la BD vía API JSON paginada; nunca lee el `.xlsx` directo por request | Alta | Con el Excel cerrado/borrado la app sigue mostrando y filtrando datos | Propuesto |
| RF-14 | Primer arranque + plantilla | Con DB vacía la app ofrece (a) seleccionar Excel o (b) iniciar vacío con saldo inicial USD; además ofrece descargar `plantilla_flujo.xlsx` con formato válido | Alta | App nueva muestra el selector; (b) entra vacío; plantilla importada sin errores | Propuesto |

### Iconos sidebar (Lucide 18–23px)

| Vista | Icono |
|---|---|
| Dashboard Principal | `LayoutDashboard` |
| Vista de Flujo | `ChartNoAxesCombined` |
| Movimientos | `ArrowDownLeft` (ingreso) / `ArrowUpRight` (egreso) |
| Entidades | `Building2`/`Users` (clientes/proveedores) + `Landmark` (bancos) |

### Plantilla vacía para copiar

```md
| RF-__ | ... | Como ... quiero ... para ... | Alta/Media/Baja | ... | Propuesto |
```

## 6. Reglas de negocio

- RN-01: `fecha(d+1) = fecha(d) + 1 día`. Rango demo: 05/01/2026 al 05/04/2026 (90 días).
- RN-02: `TOTAL_INGRESOS(d) = INGRESO_VENTAS(d) + INGRESO_BANCOS(d)`.
- RN-03: `TOTAL_EGRESOS(d) = suma de las 9 categorías de egreso`.
- RN-04: Escenarios: base = 100%; optimista = cobros ×1.15 + pagos ×0.95; pesimista = cobros ×0.70 + pagos puntuales + 10% inesperados.
- RN-05: Entidades (clientes, proveedores, bancos/cuentas) son solo lectura en la app.
- RN-06: Movimientos son CRUD; crear/editar/eliminar recalcula neto y acumulado desde ese día en adelante.
- RN-07: El Excel es solo fuente de carga. La verdad en runtime es la BD relacional.
- RN-08: Todos los saldos y montos se manejan y muestran en USD.
- RN-09: Catálogos cerrados (selects, sin texto libre): `tipo_pago` = efectivo, transferencia, cheque; `concepto_pago` = nomina, prestamo (extensible solo por migración); `status` = pendiente, aplazado, realizado. `centro_costo` = texto libre por ahora. Se aplican igual a ingresos y egresos hasta que el dueño indique omisiones por tipo.
- RN-10: Vista de Flujo por periodo: semana = 7 columnas día (nombre + fecha); trimestre = se elige 1 mes y automáticamente son ese + los 2 siguientes; anual = 12 columnas mes. En mes/año los valores se suman por grupo y el acumulado arrastra el cierre anterior. Sin paginación.
- RN-11: Desglose de Total Ingresos / Total Egresos = subfilas dentro de la matriz (una por movimiento: entidad + banco + monto, sin mostrar el concepto). Cada subfila tiene botón ⋯ que abre el detalle completo del movimiento (9 campos) con salto a Movimientos.
- RN-12: Ciclo de vida del movimiento: al crear status solo pendiente/realizado (nunca aplazado); al editar solo fecha_pago y observación son editables y el status pasa a aplazado automáticamente; la acción "Realizado" (solo si pendiente/aplazado) estampa la fecha actual y status realizado.

## 7. Requisitos no funcionales

| ID | Tipo | Descripción | Verificación |
|---|---|---|---|
| RNF-01 | Rendimiento | Recálculo de 90 días < 50ms (demo local); consultas API paginadas (50–100 filas) | Medir en consola / percibir instantáneo |
| RNF-02 | Usabilidad | Una sola pantalla + sidebar 280px desktop (colapsable a iconos/drawer en ≤767px); matriz con scroll-x, KPIs en grid en móvil | Probar 1366px y 390px |
| RNF-03 | Accesibilidad | Foco visible, labels en inputs, tablas semánticas, `prefers-reduced-motion` | Revisión manual |
| RNF-04 | Estilo | Seguir `Branding.md` (tokens, colores `#123b64`/`#0070f2`, `tabular-nums` en montos USD, iconos §5) | Revisión visual |
| RNF-05 | Restricción técnica | Front: un solo CSS y un solo JS mientras sea legible; gráficos `<canvas>`/SVG vanilla. Backend: ETL en `etl/importar.py` + `etl/plantilla.py`, lógica en `servicios/`, API en `app.py` | Revisión de archivos |

## 8. Datos y backend

### 8.1 Datos mock (para `data.js`, fallback sin backend)

| Dato | Ejemplo | Notas |
|---|---|---|
| Saldo inicial | $5,000 USD el 05/01/2026 (editable) | Parámetro global |
| Clientes | 8 clientes, 2-3 cobros/semana $2,500–$18,000 USD | Por ventas |
| Proveedores | Lista solo lectura asociada a egresos | Solo lectura |
| Bancos/cuentas | Pichincha, Guayaquil, Internacional, Caja chica | Saldo líquido = suma, USD |
| Egresos | Nómina quincenal, larvas semanal, insumos, etc. | 9 categorías |
| Caso de alerta | 1 semana con neto negativo (nómina + préstamos mismo día) | Para probar alerta |

### 8.2 Estrategia de consultas rápidas (sin consultar el Excel en runtime)

El `.xlsx` nunca se lee por request. Flujo:

1. **ETL una sola vez (Python `openpyxl`):** lee la hoja `Movimientos` de la plantilla → normaliza a `entidades`, `cuentas`, `movimientos` → guarda en SQLite portable (`tesoreria.db` junto al exe).
2. **Índices SQL:** `CREATE INDEX idx_mov ON movimientos(fecha, tipo, entidad_id, cuenta_id)` para filtros instantáneos.
3. **Saldos precalculados:** tabla `saldos_diarios(fecha, ing, egr, neto, acumulado)` recalculada solo al importar o al hacer CRUD en Movimientos. Dashboard y Vista de Flujo leen esta tabla (O(1) por día), no suman miles de filas cada vez.
4. **API paginada:** `GET /api/flujo?modo=semana|trimestre|anual&...`, `GET /api/movimientos?tipo=&q=&page=&limit=50`, `GET /api/entidades?tipo=`. Filtros con `WHERE + LIMIT/OFFSET` y agregados con `SUM/GROUP BY` en SQL, no en JS. La matriz de Flujo no pagina: usa scroll-x.
5. **Caché:** `saldos_diarios` + caché en memoria (`dict`/`lru_cache`, Redis si crece), invalidada solo al importar o modificar un movimiento.
6. **Escenarios:** se calculan sobre `saldos_diarios`, no sobre el Excel.

Resultado: <50ms en 90 días y tablas de miles de filas sin lag, aunque el Excel original sea pesado.

### 8.3 Esquema BD relacional (SQLite portable, ver `database/schema.sql`)

Tablas (monousuario, sin login):

- `entidades(id, tipo ['cliente','proveedor'], nombre UNIQUE, activo)` — clientes y proveedores, solo lectura en UI.
- `cuentas(id, banco, numero, saldo_inicial_usd, activo)` — ej: Pichincha, Guayaquil, Internacional, Caja. Solo lectura en UI.
- `categorias(id, nombre UNIQUE, grupo ['ingreso','egreso'])` — 9 de egreso: NOMINA, LARVAS, INSUMOS, FABRICACION, GASTOS_ADM, GASTOS_VTA, BANCOS, ACTIVOS, INESPERADOS.
- `movimientos(id, fecha_pago, tipo ['ingreso','egreso'], tipo_pago ['efectivo','transferencia','cheque'], concepto_pago ['nomina','prestamo', extensible], entidad_id FK NULL, cuenta_id FK (banco), centro_costo TEXT, valor_usd, status ['pendiente','aplazado','realizado'], observacion, created_at)` + `INDEX idx_mov(fecha_pago, tipo, entidad_id, cuenta_id, status)` — única tabla con CRUD. El formulario de ingreso y egreso usa los mismos 9 campos (banco, fecha de pago, tipo de pago, entidad, concepto, centro de costo, valor, status, observación).
- `saldos_diarios(fecha PK, ing, egr, neto, acumulado_usd)` — precalculada; se recalcula solo al importar o CRUD.
- `config(clave PK, valor)` — `saldo_inicial_usd`, `fecha_inicio`.
- `import_log(id, archivo, filas_ok, filas_error, fecha)` — auditoría de cada importación.

Reglas: cada CRUD en `movimientos` dispara `recalcular_saldos_desde(fecha)`. La DB vive junto al exe (`tesoreria.db`); la app se mueve con todo.

### 8.4 Primer arranque + plantilla Excel

1. Al abrir por primera vez la app detecta DB vacía (`movimientos = 0` y sin `import_log`) y muestra 2 opciones:
   - (a) **Seleccionar Excel existente** → valida → importa → entra al Dashboard.
   - (b) **Iniciar vacío** → pide saldo inicial USD + fecha inicio → crea `config` y entra vacío.
2. Omitir es válido: (b) no exige ningún archivo.
3. Para evitar errores de lectura, la app ofrece descargar/generar `plantilla_flujo.xlsx` (`backend/etl/plantilla.py`): hoja `Movimientos` con columnas exactas `banco | fecha_pago | tipo | tipo_pago | entidad | concepto_pago | centro_costo | valor_usd | status | observacion` + listas desplegables (tipo; tipo_pago = efectivo, transferencia, cheque; concepto_pago = nomina, prestamo; status = pendiente, aplazado, realizado) + filas de ejemplo + hoja `Ayuda`. Solo ese formato se acepta; cualquier otra columna/hoja se rechaza con mensaje de error por fila.

## 9. Criterios de aceptación global

- [ ] App de una sola pantalla: la sidebar conmuta las 4 vistas sin recargar y marca la activa.
- [ ] Todos los montos en USD.
- [ ] `FLUJO_ACUMULADO(d) = SALDO_INICIAL(d) + TOTAL_ING(d) − TOTAL_EGR(d)` en 3 días aleatorios.
- [ ] `SALDO_INICIAL(d+1) === FLUJO_ACUMULADO(d)`.
- [ ] CRUD en Movimientos recalcula neto y acumulado de ese día en adelante.
- [ ] Selects solo aceptan catálogos RN-09 (tipo_pago, concepto, status inválidos se rechazan).
- [ ] Trimestre: elegir 1 mes muestra ese + los 2 siguientes; desglose en subfilas.
- [ ] Entidades (clientes, proveedores, bancos) no permiten crear/editar/eliminar.
- [ ] Gráfico refleja la tabla.
- [ ] Con el Excel cerrado la app sigue funcionando (lee BD/API, no el `.xlsx`).
- [ ] Primer arranque con DB vacía ofrece importar Excel o iniciar vacío; la plantilla oficial importa sin errores.
- [ ] La carpeta portable (exe + db + front) se mueve a otra PC Windows y arranca sin instalar nada.
- [ ] Usable en desktop (1366px) y móvil (390px), consola sin errores.

## 10. Glosario

| Término | Significado |
|---|---|
| Flujo neto | Total ingresos − total egresos del día (USD) |
| Flujo acumulado | Saldo inicial + flujo neto (arrastre al día siguiente) |
| Saldo líquido | Suma de saldos en cuentas bancarias + caja (USD) |
| Escenario | Simulación pesimista / base / optimista |
| ETL | Proceso Python que lee el Excel y lo carga a la BD |

## 11. Control de cambios

| Fecha | Autor | Cambio |
|---|---|---|
| 2026-09-28 | ... | Creación inicial |
| 2026-09-28 | ... | Vista Flujo 5 filas + periodos semana/trimestre/anual + subfilas; formularios Movimientos 9 campos; catálogos cerrados RN-09–RN-11; schema v2 y plantilla v2 |
| 2026-09-28 | ... | Moneda a USD, se elimina §HU (las da el dueño), 1 pantalla + sidebar 4 vistas, Movimientos CRUD, Entidades incluyen bancos, backend Python + Excel→BD + estrategia de consultas |
| 2026-09-28 | ... | BD SQLite portable monousuario + despliegue exe Windows, primer arranque (importar u omitir) + plantilla Excel, esquema §8.3–§8.4, RF-14 |
