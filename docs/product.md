# PRODUCT.md — Demo Flujo de Tesorería (single-file HTML)

## 1. Visión
Plataforma web demo (un solo archivo `flujo-demo-2026.html`) que replica y moderniza el libro `flujo de caja diario DP020924.xlsx` para llevar el **flujo de tesorería diario** y hacer **proyecciones de operaciones económicas**. Sin backend, con datos mockup, partiendo de cero en 2026, moneda USD.

## 2. Usuario y contexto
- Tesorero / dueño de empresa camaronera (clientes y proveedores del Excel original).
- Uso: ver día a día cuánto entra, cuánto sale, cuál es el saldo y simular el futuro.
- Demo: debe impresionar en 3 minutos, funcionar con doble clic, sin instalar nada.

## 3. Alcance de la demo (lo que SÍ incluye)
1. Matriz de flujo horizontal con scroll hacia la derecha (días como columnas).
2. Operaciones básicas: ingreso, egreso, saldo inicial, flujo neto diario, flujo acumulado diario, saldo líquido en bancos.
3. Desglose de ingresos: Por Ventas (por cliente) + Por Bancos.
4. Desglose de egresos en 9 categorías: CORRIENTES/NÓMINA, LARVAS, INSUMOS, COSTOS DE FABRICACIÓN, GASTOS ADM, GASTOS VTA, BANCOS (préstamos), ACTIVOS, INESPERADOS.
5. Panel de proyección: horizonte 14/30/90 días, 3 escenarios (pesimista/base/optimista), alerta de déficit.
6. CRUD mínimo en memoria (agregar ingreso/egreso mock) + recalculo instantáneo.
7. Gráfico de flujo acumulado + KPIs.
8. Formato USD en todo.

Lo que NO incluye (fuera de demo): login, multi-empresa, BD real, conciliación bancaria automática, importación Excel, reportes PDF.

## 4. Lógica de negocio (extraída del Excel, simplificada para 2026)
Reglas a implementar en JS puro:
- `fecha(d+1) = fecha(d) + 1 día`. Rango demo: 05/01/2026 al 05/04/2026 (90 días), editable con date-picker de inicio.
- `INGRESO_VENTAS(d) = SUM CobrosCliente(cliente, vence=d)`
- `INGRESO_BANCOS(d) = SUM CobrosBanco(banco, vence=d)`
- `TOTAL_INGRESOS(d) = INGRESO_VENTAS(d) + INGRESO_BANCOS(d)`
- `CATEGORIA_EGRESO(d) = SUM Pagos(beneficiario, categoria, fecha_pago=d)` para cada una de las 9 categorías.
- `TOTAL_EGRESOS(d) = SUM(9 categorías)`
- `FLUJO_NETO(d) = TOTAL_INGRESOS(d) - TOTAL_EGRESOS(d)`
- `SALDO_INICIAL(d0) = 5_000 USD (param editable). SALDO_INICIAL(d+1) = FLUJO_ACUMULADO(d)` (arrastre).
- `FLUJO_ACUMULADO(d) = SALDO_INICIAL(d) + FLUJO_NETO(d)`
- `SALDO_LIQUIDO_BANCOS(d) = SUM saldos cuentas (Bco Pichincha, Bco Guayaquil, Bco Internacional, Caja)`. En demo: arranca igual al acumulado y permite ajuste manual para mostrar conciliación.
- Escenarios: `base=100% cobros/pagos, optimista=cobros*1.15 + pagos*0.95, pesimista=cobros*0.70 + pagos puntuales + 10% inesperados`.

## 5. Datos mockup 2026 (partimos de cero)
- Saldo inicial: $5,000 el 05/01/2026.
- 8 clientes: ACUICOLA ROMAR, AGROCAMARON, ARGUDO ZAMBRANO, CABRERA DAVILA, CAMARONERA CAMANMOR, PACIFICCAM, PRODUMAR, EXPORCAMBRIT. 2-3 cobros semanales de $2,500–$18,000.
- 4 cuentas: Pichincha Cte 11111, Guayaquil, Internacional, Caja chica.
- Egresos: NÓMINA quincenal $11,000; LARVAS semanal $4,200; INSUMOS $3,800; FABRICACIÓN $2,500; GASTOS ADM $1,200; GASTOS VTA $900; Préstamos: PICH 400K $1,850/mes, PICH 700K $2,900/mes, INTER 60K $850/mes; ACTIVOS puntual; INESPERADOS 5% aleatorio.
- Incluir al menos 1 semana con flujo neto negativo para mostrar alerta (ej. semana 3 de enero con nómina + préstamos el mismo día).

## 6. Diseño UX/UI — flujo horizontal hacia la derecha
- Layout: header sticky con KPIs (Saldo inicial, Total ing, Total egr, Neto, Acumulado) + selector rango + selector escenario + botón +Ingreso / +Egreso.
- Cuerpo: tabla matriz con primera columna (concepto) sticky-left, columnas-día con scroll-x hacia la derecha. Fila de fechas sticky-top con día letra (L M X J V S D) + dd/mm.
- Jerarquía visual: filas totales (TOTAL INGRESOS / TOTAL EGRESOS / FLUJO NETO / FLUJO ACUMULADO) con fondo distinto; categorías colapsables (accordion); valores negativos en rojo, positivos en verde; acumulado con sparkline.
- Panel derecho o drawer: detalle del día clicado + simulador (mover un pago ±7 días y ver impacto).
- Gráfico superior: línea de flujo acumulado 90 días + barras neto diario (canvas puro o Chart.js por CDN).
- Todo USD: `Intl.NumberFormat('en-US',{style:'currency',currency:'USD'})`.
- Responsive: en móvil la matriz sigue con scroll-x, KPIs en carrusel.
- Estilo: fintech limpio, modo claro, tipografía Inter/system, alto contraste para números tabulares (`font-variant-numeric: tabular-nums`).

## 7. Requerimientos técnicos (single-file)
- Un único archivo `flujo-demo-2026.html`, CSS en `<style>`, JS en `<script>`, sin build. Se permite CDN (Tailwind y/o Chart.js) pero con fallback a CSS/JS puro si no hay internet.
- JS vanilla, estado en objeto `state`, funciones puras `calcDay(), calcRange(), applyScenario()`. Recalculo <50ms para 90 días.
- Botones: exportar CSV, resetear mockup, cambiar fecha inicio, cambiar saldo inicial.
- Código comentado en español, secciones: DATA MOCK / MOTOR CÁLCULO / RENDER MATRIZ / GRÁFICO / EVENTOS.

## 8. Criterios de aceptación demo
1. Abre con doble clic y muestra enero–abril 2026 en USD.
2. Scroll horizontal fluido hacia la derecha con columna concepto fija.
3. `FLUJO_ACUMULADO(d) = SALDO_INICIAL(d) + TOTAL_ING(d) - TOTAL_EGR(d)` verificable en 3 días aleatorios.
4. `SALDO_INICIAL(d+1) === FLUJO_ACUMULADO(d)`.
5. Cambiar escenario recalcula todo y cambia color de alerta si acumulado < 0.
6. Agregar un egreso mueve el neto y el acumulado de ese día en adelante.
7. Gráfico refleja la tabla.

## 9. Roadmap post-demo (no construir ahora)
Conexión a backend, importación del xlsx real, multi-cuenta, roles, conciliación, proyecciones ML.
