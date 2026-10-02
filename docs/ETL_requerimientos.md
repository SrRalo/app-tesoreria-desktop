Aquí tienes la especificación técnica de requerimientos para actualizar y refactorizar el pipeline ETL, garantizando cero pérdida de información, mapeo preciso a la base de datos SQLite (v3) y soporte completo para la conciliación de datos históricos.

---

## 1. Requerimientos de Lectura y Extracción (Extraction)

| ID | Requerimiento | Descripción Técnica / Criterio de Aceptación |
| --- | --- | --- |
| **RF-ETL-01** | **Soporte Multiformato y Múltiples Hojas** | El parser debe procesar archivos `.xlsx`, `.xls` y `.csv`, permitiendo al usuario seleccionar la pestaña u hoja de cálculo específica a importar. |
| **RF-ETL-02** | **Detección Dinámica de Encabezados** | Identificar dinámicamente la fila de inicio de la tabla (omitir filas de títulos, logos o celdas combinadas en las primeras filas del Excel). |
| **RF-ETL-03** | **Separación Estricta de Pipelines** | Dividir la lógica de importación en dos sub-módulos independientes:<br>

<br>1. *ETL Movimientos Internos* (Excel CxC / CxP $\rightarrow$ `movimientos`).<br>

<br>2. *ETL Extractos Bancarios* (Estado de cuenta $\rightarrow$ `extracto_lineas`). |

---

## 2. Requerimientos de Transformación y Limpieza (Transformation)

| ID | Requerimiento | Descripción Técnica / Criterio de Aceptación |
| --- | --- | --- |
| **RF-ETL-04** | **Parseo Robusto de Fechas** | Convertir múltiples formatos de fecha (`DD/MM/YYYY`, `MM/DD/YYYY`, `YYYY-MM-DD` y seriales numéricos de Excel como `46244`) al estándar **ISO `YYYY-MM-DD**`. Si falla, la fecha debe enviarse a revisión sin descartar el registro. |
| **RF-ETL-05** | **Sanitización Moneda / Flotantes** | Convertir cadenas de texto con símbolos (`$`, `USD`, `,`) a valores numéricos `REAL` con 2 decimales. Manejar correctamente la distinción entre signo negativo, columnas separadas de Débito/Crédito y comas/puntos decimales. |
| **RF-ETL-06** | **Normalización de Cadenas de Texto** | Aplicar `strip()` a todos los campos, eliminar caracteres invisibles/unicode de control y convertir textos de referencias a mayúsculas limpias. |

---

## 3. Requerimientos de Mapeo e Integridad Relacional (Mapping)

| ID | Requerimiento | Descripción Técnica / Criterio de Aceptación |
| --- | --- | --- |
| **RF-ETL-07** | **Buscador/Mapeador con Fuzzy Matching (Entidades)** | Al asociar un cliente/proveedor desde Excel hacia la tabla `entidades`, aplicar coincidencia por similitud de texto (ej. *Levenshtein distance* $\ge 85\%$). Si no hay coincidencia exacta o cercana, asignar la entidad por defecto `entidad_id = NULL` o `Por Definir`. |
| **RF-ETL-08** | **Estrategia Antipérdida ("Fallback Defaults")** | **Regla de oro:** Ninguna fila se desecha por falta de un dato secundario. Si falta el concepto, asignar `concepto_id` de `por_definir`. Si falta el banco, asignar `cuenta_id` de `PorDefinir`. Guardar los valores originales no mapeados dentro de la columna `observacion`. |
| **RF-ETL-09** | **Mapeo Unívoco de Cuentas Bancarias** | Cruzar el nombre o número de cuenta de la fuente contra la tabla `cuentas` usando alias (ej. "Pichincha CTA CTE", "2100319432", "Pichincha" $\rightarrow$ `cuenta_id = 1`). |

---

## 4. Requerimientos de Control, Idempotencia y Auditoría (Validation)

| ID | Requerimiento | Descripción Técnica / Criterio de Aceptación |
| --- | --- | --- |
| **RF-ETL-10** | **Deduplicación por Hash Único (Idempotencia)** | Para `extracto_lineas`, generar el identificador único:<br>

<br>`hash_unico = SHA256(cuenta_id | fecha | debito_usd | credito_usd | referencia)`<br>

<br>Si el hash ya existe en la BD, la fila se omite sin detener el proceso y se contabiliza como duplicada. |
| **RF-ETL-11** | **Modo Pre-flight / Vista Previa (Dry Run)** | Antes de guardar en la BD, la UI debe mostrar una tabla borrador con:<br>

<br>- Filas $100\%$ Válidas.<br>

<br>- Filas con Advertencias (ej. "Entidad no encontrada, se asignará 'Por Definir'").<br>

<br>- Filas Duplicadas (a ignorar). |
| **RF-ETL-12** | **Registro en Bitácora e Import Log** | Al finalizar cada importación, registrar una fila en `import_log` (filas OK, filas error, archivo) y una entrada en `bitacora` con el JSON de auditoría y `origen = 'IMPORT'`. |

---

## 5. Requerimientos de Carga y Rendimiento (Loading)

| ID | Requerimiento | Descripción Técnica / Criterio de Aceptación |
| --- | --- | --- |
| **RF-ETL-13** | **Transaccionalidad Atómica (Todo o Nada)** | La ejecución de la inserción debe envolverse en un bloque `BEGIN TRANSACTION` / `COMMIT`. Si ocurre una falla irrecuperable a mitad de proceso, ejecutar `ROLLBACK` total para evitar estados inconsistentes. |
| **RF-ETL-14** | **Operaciones Batch / Inserción Masiva** | Utilizar inserciones vectorizadas (`executemany` en Python/SQLite) para cargar bloques de datos en subsegundos. |

---

## 6. Requerimientos Post-Procesamiento (Post-Processing)

| ID | Requerimiento | Descripción Técnica / Criterio de Aceptación |
| --- | --- | --- |
| **RF-ETL-15** | **Auto-Conciliación Inmediata** | Tras completar la importación de extractos/movimientos de un mes (ej. Agosto), invocar automáticamente el script de matcheo en `conciliacion`: emparejar registros con idéntico `cuenta_id`, valor exacto y `fecha` en ventana $\pm 3$ días hábiles. |
| **RF-ETL-16** | **Recálculo de Tablas Precargadas** | Ejecutar la rutina de actualización para `saldos_diarios` y `saldos_diarios_cuenta` inmediatamente después del `COMMIT`, garantizando que el Dashboard refleje los saldos en libros y bancarios corregidos al instante. |

---

### Flujo de Datos Recomendado para el Desarrollo del Script ETL

```
[Archivo Excel / CSV]
       │
       ▼
[1. Lectura & Parsing] ─── (Falla fecha/formato) ───► [Reporte de Errores UI]
       │
       ▼
[2. Normalización & Hash Deduplicación] ── (Hash Existe) ──► [Ignorar / Incrementar Duplicados]
       │
       ▼
[3. Mapeo Cuentas / Entidades / Conceptos]
       ├─► Coincidencia 100% / Fuzzy ──► Asignar ID
       └─► Sin Coincidencia ──────────► Asignar Fallback (ID Default + Nota en Observación)
       │
       ▼
[4. Transacción SQLite: BEGIN]
       ├── INSERT INTO movimientos / extracto_lineas
       ├── INSERT INTO import_log & bitacora
       └── Recálculo de saldos_diarios y saldos_diarios_cuenta
[COMMIT]
       │
       ▼
[5. Ejecución Motor de Conciliación Automática (RN-15)]

```