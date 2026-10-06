Tu documento de especificación **flow-treasury** está sumamente bien estructurado, claro y alineado con buenas prácticas de arquitectura (base de datos relacional SQLite portable, precálculo de saldos, arquitectura offline-first con backend Python).

Dado que **ya cuentas con un proceso de ETL, la base de datos y tienes marcados como "Hecho" los requisitos RF-19 y RF-20** (Importar extractos bancarios y Conciliar/Cuadrar), existen algunos desfases de documentación (desviación entre los RFs hechos y el alcance/esquema general) y oportunidades para robustecer el manejo de tesorería real.

A continuación te detallo **qué deberías reemplazar, agregar y corregir**, incluyendo los bloques exactos en Markdown para que los copies en tu archivo.

---

### 1. Incoherencias y Desfases a Corregir (Reemplazar)

#### A. Falta la vista de Conciliación en la UI (§3.1, §5 RF-07 e Iconos Sidebar)

* **El problema:** En RF-19 y RF-20 indicas que la app importa extractos bancarios y concilia. Sin embargo, en §3.1 (Alcance) y en RF-07 (Navegación) estableces que la app solo tiene **4 vistas** (*Dashboard Principal, Vista de Flujo, Movimientos, Entidades*). ¿Dónde visualiza el usuario el cuadre de bancos o resuelve diferencias manualmente?
* **Solución:** Ajusta a **5 vistas** o agrega el sub-módulo de **Conciliación Bancaria**.
> **Resolución (a6c416b): descartado.** Los extractos solo se consultan en Entidades > Bancos; la conciliación manual/automática se eliminó (endpoints retirados, `conciliacion.py` DEPRECATED). No se agrega vista ni 5ª entrada al sidebar.

#### B. Incompletitud en el Esquema de BD (§8.3)

* **El problema:** En RF-19 mencionas las tablas `extracto_lineas` y `cortes_bancarios`, pero en la sección **§8.3 Esquema BD relacional** solo aparecen las tablas básicas (`entidades`, `cuentas`, `categorias`, `movimientos`, `saldos_diarios`, etc.).
* **Solución:** Actualizar la sección §8.3 para reflejar las tablas reales del motor de conciliación.

---

### 2. Nuevas Reglas de Negocio a Agregar (Tesorería Real)

En tesorería existen **3 tipos de saldos por cuenta de banco** que debes explicitar para no confundir al usuario en el Dashboard ni en la Vista de Flujo:

1. **Saldo Real Bancario (Conciliado):** Lo que el banco dice que tienes a la fecha de corte del último extracto subido.
2. **Saldo en Libros / Disponible Hoy:** Saldo bancario + movimientos del sistema marcados como `realizado` que aún no se reflejan en extracto (o caja chica).
3. **Saldo Proyectado (Futuro):** Saldo en libros + todas las CxC (ingresos) pendientes menos las CxP (egresos) pendientes a una fecha futura $D$.

---

### 3. Cambios Específicos para Copiar y Pegar en tu Documento

> **NO APLICAR (descartado en a6c416b, ver §1.A):** los bloques de §3 que proponían la 5ª vista
> Conciliación Bancaria quedaron obsoletos. La 5ª vista real es **Configuración**
> (ya alineada en `requisitos.md` RF-07 + `AGENTS.md`). Se conservan abajo solo como
> historial, marcados como Descartado.

#### 🖊️ Reemplazar en **§3.1 Sí incluye** — DESCARTADO, NO APLICAR:

```markdown
- [ ] Sidebar lateral con 5 vistas sin recargar: Dashboard Principal, Vista de Flujo, Movimientos, Conciliación Bancaria, Entidades

```

#### 🖊️ Reemplazar **RF-07** en la tabla de §5 — DESCARTADO, NO APLICAR (RF-07 real = 5 vistas con Configuración, no con Conciliación):

| ID | Nombre | Descripción | Prioridad | Criterio de aceptación | Estado |
| --- | --- | --- | --- | --- | --- |
| RF-07 | Navegación lateral (1 pantalla) | Una sola pantalla con sidebar que conmuta entre las 5 vistas sin recargar, con icono acorde por vista y estado activo visible | Alta | Clic en cada item cambia de vista sin reload y marca el item activo; en móvil colapsa a iconos/drawer | Aprobado |

#### ➕ Agregar a la tabla de **Iconos sidebar** en §5 — DESCARTADO, NO APLICAR:

| Vista | Icono |
| --- | --- |
| Dashboard Principal | `LayoutDashboard` |
| Vista de Flujo | `ChartNoAxesCombined` |
| Movimientos | `ArrowDownLeft` (ingreso) / `ArrowUpRight` (egreso) |
| **Conciliación Bancaria** | **`CheckCheck` / `Scale**` |
| Entidades | `Building2`/`Users` (clientes/proveedores) + `Landmark` (bancos) |

#### ➕ Agregar a la tabla de Requisitos Funcionales (§5):

| ID | Nombre | Descripción | Prioridad | Criterio de aceptación | Estado |
| --- | --- | --- | --- | --- | --- |
| RF-21 | Vista de Conciliación Manual (Doble Panel) | Pantalla para comparar extractos bancarios sin conciliar vs movimientos pendientes de la app. Permite vincular manualmente un movimiento con una línea de extracto o aplicar diferencias por comisión bancaria. **Descartado en a6c416b (ver nota en §1.A): no se implementa.** | Alta | Selección manual aplica vínculo, actualiza estado a `realizado`/`conciliado` y recalcula diferencia a 0 | Descartado |
| RF-22 | Desglose de Saldos en Dashboard/Entidades | Mostrar para cada cuenta bancaria tres valores: Saldo Real Extracto, Saldo en Libros (Ejecutado) y Saldo Proyectado a 30 días | Media | Tarjetas de cuentas en Entidades y Dashboard diferencian entre saldo real de banco y saldo proyectado | Propuesto |

#### ➕ Agregar en **§6 Reglas de negocio**:

```markdown
- RN-14: Tipos de saldos por cuenta bancaria: 
  a) Saldo Real Conciliado = último saldo reportado en extracto bancario oficial (`cortes_bancarios`).
  b) Saldo Disponible/Libros = Saldo Real + movimientos con status `realizado` no conciliados.
  c) Saldo Proyectado(d) = Saldo Disponible + suma(CxC pendientes <= d) - suma(CxP pendientes <= d).
- RN-15: Margen de coincidencia en conciliación: La conciliación automática empareja cuando coinciden `cuenta_id`, `monto` exacto y la fecha del extracto se encuentra dentro de `fecha_pago ± 3 días hábiles` del movimiento registrado.
- RN-16: Ajuste por comisiones bancarias: Cuando el valor cobrado/pagado en banco diferir del valor esperado en la CxC/CxP por comisión o retención (diferencia <= $5 USD o <= 2%), la UI debe permitir conciliar la factura completa registrando automáticamente un movimiento de egreso por la diferencia bajo la categoría `BANCOS/COMISIONES`.

```

#### 🖊️ Actualizar en **§8.3 Esquema BD relacional** (para alinear con el ETL y BD real que ya posees):

Reemplaza o expande la lista de tablas en el texto con esto:

```markdown
Tablas (monousuario, sin login):

- `entidades(id, tipo ['cliente','proveedor'], nombre UNIQUE, activo)` — clientes y proveedores, solo lectura en UI.
- `cuentas(id, banco, numero, saldo_inicial_usd, activo)` — ej: Pichincha, Guayaquil, Internacional, Caja.
- `categorias(id, nombre UNIQUE, grupo ['ingreso','egreso'])` — 9 de egreso (NOMINA, LARVAS, INSUMOS, FABRICACION, GASTOS_ADM, GASTOS_VTA, BANCOS, ACTIVOS, INESPERADOS) + categorías de sistema (`comision`).
- `movimientos(id, fecha_pago, tipo ['ingreso','egreso'], tipo_pago, concepto_pago, entidad_id FK, cuenta_id FK, centro_costo, valor_usd, status ['pendiente','aplazado','realizado','conciliado'], observacion, created_at)` + `INDEX idx_mov(fecha_pago, tipo, entidad_id, cuenta_id, status)`.
- `extracto_lineas(id, cuenta_id FK, fecha, referencia, descripcion, monto, saldo_banco, estado_conciliacion ['SIN_CONCILIAR','CONCILIADO'], hash_linea UNIQUE)` — almacenamiento de movimientos importados de los 3 bancos.
- `cortes_bancarios(id, cuenta_id FK, mes, saldo_cierre_banco, saldo_cierre_app, diferencia)` — cierres mensuales por cuenta.
- `conciliaciones(id, extracto_linea_id FK, movimiento_id FK, monto_aplicado, fecha_conciliacion, tipo_cuadre ['AUTOMATICO','MANUAL'])` — relación M:N entre lo bancario real y lo proyectado/esperado.
- `saldos_diarios(fecha PK, ing, egr, neto, acumulado_usd)` — precalculada; se recalcula solo al importar o CRUD.
- `config(clave PK, valor)` — `saldo_inicial_usd`, `fecha_inicio`.
- `import_log(id, archivo, filas_ok, filas_error, fecha)`.
- `bitacora(id, fecha, accion, tabla, registro_id, detalle, dato_anterior JSON, dato_nuevo JSON, origen)`.

```

---

### Resumen de valor agregado con estos cambios:

1. **Coherencia Documental:** Resuelves el hueco donde RF-19 y RF-20 estaban marcados como "Hecho", pero no existía una pantalla definida en la UI ni las tablas en el esquema §8.3 para sostenerlo.
2. **Claridad Financiera:** Al definir los 3 tipos de saldos (Real, Libros y Proyectado) en la **RN-14**, el programador frontend sabrá exactamente qué valor mostrar en las tarjetas de bancos del Dashboard y en las filas de la Vista de Flujo.
3. **Casos de Uso Reales:** Con las **RN-15** y **RN-16**, la aplicación no se trancará cuando una transferencia llegue 1 día después o cuando Pichincha/Produbanco cobren una comisión pequeña de $0.50 o $1.00 USD por transferencia.


Checklist de verificación para tu backend/parser
Soporte de lectura flexible: Validar que la librería de parsing maneje buffers binarios .xls, .xlsx y estructuración desde HTML/TSV.

Detección dinámica de cabeceras: Escanear las filas hasta encontrar los campos obligatorios del modelo de datos.

Filtro de subtotales/totales: Ignorar filas con palabras clave como Total, Subtotal, Saldo Final en las tablas de movimientos o cartera.

Cast numérico robusto: Remover espacios, símbolos de moneda ($) y estandarizar puntos/comas decimales antes de convertir a float o decimal.s