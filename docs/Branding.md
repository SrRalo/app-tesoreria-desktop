# Branding — flow-treasury
> Sistema visual extraído de `tesoreriaapp-main` (React + Tailwind v4 + shadcn/new-york + Recharts + Lucide) y adaptado a este repo: front estático vanilla (`index.html` / `styles.css` / `app.js`), texto en español (es-MX), moneda MXN.

Fuente: `tesoreriaapp-main/app/globals.css`, `app/page.tsx`, `components/ui/*`, `lib/treasury.ts`, `public/favicon.svg`, `index.html` (`theme-color #123b64`).

---

## 1. Marca

| Atributo | Valor origen | Uso en flow-treasury |
|---|---|---|
| Nombre | **Tesorería** + caption `CONTROL FINANCIERO` | Mantener. Header: `Flujo de Tesorería` + sub `CONTROL FINANCIERO` |
| Logo | Cuadrado `38×40px`, `radius 7px`, fondo `#123b64`, icono blanco (barras + línea, Lucide `ChartNoAxesCombined`) | Reproducir en CSS puro o SVG inline. Ver `public/favicon.svg` origen: fondo `#123b64`, barras blancas, subrayado `#65c4ff` |
| Favicon | `rect rx=13 fill #123b64` + 3 barras blancas + línea `#65c4ff` | Copiar SVG tal cual a `favicon.svg` |
| `theme-color` | `#123b64` | Usar en `<meta name="theme-color">` |
| Tono de voz | Operativo, sobrio, estilo SAP/fintech. Eyebrow `GESTIÓN DE TESORERÍA`, títulos `Resumen de caja`, hints `Vencidos y próximos {n} días` | Mismo tono, en es-MX |

```svg
<!-- Logo/favicon (origen, reutilizable tal cual) -->
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="13" fill="#123b64"/><path d="M15 42V28h8v14zm13 0V20h8v22zm13 0V12h8v30z" fill="#fff"/><path d="M14 50h36" stroke="#65c4ff" stroke-width="4"/></svg>
```

---

## 2. Colores

### 2.1 Tokens base (`:root` en origen)

| Token | Hex | Rol |
|---|---|---|
| `--background` | `#f4f6f8` | Fondo app |
| `--foreground` | `#1d2d3e` | Texto principal |
| `--card` | `#ffffff` | Tarjetas / paneles |
| `--primary` | `#0070f2` | Acción principal, links, foco |
| `--primary-foreground` | `#fafafa` | Texto sobre primary |
| `--secondary` / `--muted` / `--accent` | `#f5f5f5` | Fondos secundarios, hover |
| `--muted-foreground` | `#737373` | Texto atenuado (shadcn) |
| `--destructive` | `#e7000b` | Peligro (shadcn) |
| `--border` / `--input` | `#e5e5e5` | Bordes base shadcn |
| `--ring` | `#0070f2` | Anillo de foco |
| `--radius` | `0.5rem` (8px) | Radio base |

### 2.2 Azul corporativo (identidad real, usado en layout)

| Uso | Hex |
|---|---|
| Marca / sidebar activa oscura / KPI primario / botón flotante IA / auth | `#123b64` (hover `#0d2c4d`) |
| Link / texto azul / nav activa | `#0064d9` / `#0068d7` / `#0070d9` |
| Fondo nav activa | `#eaf3ff` + `box-shadow: inset 3px 0 #0070f2` |
| Gráfico (línea + relleno) | `#0070f2` (relleno gradiente `0.18 → 0.01`) |
| Icono banco / entidad | fondo `#f0f5fa`, icono `#477291` |
| Perfil topbar | fondo `#edf4fa`, icono `#286495` |

### 2.3 Semánticos (texto + badges + banners)

| Estado | Texto | Fondo badge |
|---|---|---|
| Éxito / ingreso / `Por cobrar` | `#18845b` / `#187c53` | `#ebf7f0` / `#eaf6f1` |
| Advertencia / egreso / `Por pagar` | `#c77d0a` / `#a26d0d` / `#b47a29` | `#fff4d9` / `#fcf3e6` |
| Peligro / vencido | `#bb2435` / `#c2313c` / `#b5263d` / `#b32036` | `#ffebed` / `#fff0f1` |
| Neutro / info | `#3e6e97` | `#edf4fb` / `#edf5fc` |
| Texto muted operativo | `#607386` / `#687a8c` / `#637689` / `#718497` | — |
| Verde gráfico | `#16a34a` (origen demo) — en app real se usa `#0070f2` monocromo | — |

### 2.4 Bordes y superficies

```
Borde panel/filtro:  #dfe5ec / #dfe6ed
Borde tabla:         #e9edf2 (filas), header tabla #f8fafc
Inputs:              #bccbd9 (form), #ccd7e2 (búsqueda), #b9c8d6 (auth)
Sidebar:             border-right #dce3ea
Banner info:         fondo #edf5fc, borde #dce6f0, texto #345e80
Banner vencidos:     fondo #fff9eb, borde #f2e1b9, texto #8a641d
Banner error:        fondo #fff0f1, texto #b32036
Review card:         fondo #f2f7fc, borde #c9d8e6, título #123b64
Review lock:         fondo #fff8e6, borde #ecd9a0, texto #8a6d1a
Charts (origen):     --chart-1 #f54900, --chart-2 #009689, --chart-3 #104e64, --chart-4 #ffb900, --chart-5 #fe9a00
Grid gráfico:        #e4e9ef, ticks #64748b
```

### 2.5 Regla de uso
- Un solo azul de acción (`#0070f2`) + un solo azul marca (`#123b64`). No introducir azules intermedios.
- Verde = dinero que entra / OK. Naranja = dinero que sale / pendiente. Rojo = vencido / déficit / destructivo. No mezclar.
- Números financieros siempre `tabular-nums`, alineados a la derecha, rojo si `< 0`.

---

## 3. Tipografía

- **Familia:** `Arial, Helvetica, sans-serif` (origen; sin webfont). Mono solo para código: `ui-monospace, Menlo, Monaco, Consolas, monospace`.
- **Escala (origen):** `h1 29px / 650 / -0.7px`, `h2 16px/600`, `h3 17px/600`, `body 14px`, `small 12px #687a8c lh 1.65`, eyebrow `10px / 600 / 1.6px #7c8c9c`, KPI `clamp(22px,2.1vw,31px) / 600 / -0.6px`, balance banco `29px / -0.8px`.
- En flow-treasury (vanilla) mantener la pila del sistema; si se quiere Inter, es solo progresivo: `font-family: "Inter", Arial, Helvetica, sans-serif`.

---

## 4. Layout (extraído de `page.tsx` + `globals.css`)

```
+--------+------------------------------------------------+
| side   | topbar (62px, #fff, border #dfe6ed)            |
| bar    +------------------------------------------------+
| 280px  | eyebrow + h1 + descripción + acciones (37px)    |
| nav    +------------------------------------------------+
|        | filtros (card #fff, radius 7px)                |
|        +------------------------------------------------+
|        | KPIs ×4  |  panel gráfico | panel cuentas    |
+--------+------------------------------------------------+
```

- **Sidebar:** fondo `#fff`, `border-right #dce3ea`. Brand `22px/700` + `small 9px ls 1.7px`. Items `44px, radius 6px, #475a6d`; activo: fondo `#eaf3ff`, texto `#0064d9`, `inset 3px 0 #0070f2`. Caption `10px ls 1.4px #7a8b9c`. Colapsada a solo icono.
- **Topbar:** `Finanzas › Tesorería` + derecha: `USD · Dólar` (aquí: `MXN · Peso mexicano`), refresh, avatar/PWA.
- **Main:** `max-width 1750px`, `padding 30px 32px`, `h1` + párrafo gris + botones a la derecha.
- **Filtros:** barra blanca con icono + selects sin borde (`Empresa / Cuenta / Próximos 30-60-90 días`) + fecha a la derecha.
- **KPIs:** 4 tarjetas blancas `radius 8px, borde #dfe5ec, shadow 0 2px 3px #152e4210, padding 21px 22px`. Primera destacada: fondo `#123b64`, texto blanco. Label con icono a la derecha, valor grande, subtítulo gris.
- **Paneles:** `#fff, borde #dfe5ec, radius 8px, shadow 0 2px 3px #152e4208`. Heading `20px 23px, border-bottom #edf0f4`. Foot `14px 22px, border-top, #718497` con link a la derecha.

---

## 5. Componentes (recetas)

- **Botones:** shadcn `default (primary) / destructive / outline / secondary / ghost / link`; alturas `h-9 px-4` (sm `h-8`, lg `h-10`, icon `size-9`); `radius 6px`; primario `height 37px + shadow 0 1px 2px #122b4110`. Acción principal siempre sólida `#0070f2`; secundaria `outline`.
- **Badges:** `padding 4px 8px, radius 4px, 11px`: `success / warning / danger / neutral` (tabla §2.3).
- **Tablas:** header `43px, fondo #f8fafc, #687d90, 11px/500`; celdas `16px 20px, 13px`; `hover:bg-muted/50`; columna monto `.amount` (right + tabular-nums). Entidad con icono cuadrado `33px radius 6px`: ingreso `#198661/#eaf6f1`, egreso `#b47a29/#fcf3e6`.
- **Banners:** `.info-banner / .overdue-banner / .error-banner` (`13px, radius 6px, padding 13px 17px`, icono + acción a la derecha).
- **Modal:** `max-width 650px (import 860px)`, `border-top 4px #0070f2`, `padding 25px`, título `21px #1b3e5d`. Form grid 2 col, inputs `38px, borde #bccbd9, radius 5px`. Patrón obligatorio: **tarjeta de confirmación** (`.review-card`) + aviso `.review-lock` antes de guardar.
- **Empty states:** icono en círculo `54px #eff5fb/#7898b3`, `h3 16px`, `p 14px #708395`, acción `outline`.
- **Toast:** `sonner` (éxito/error al guardar, exportar, importar).
- **IA flotante:** círculo `52px #123b64`, `shadow 0 12px 30px #123b6455`, hero centrado + cards `radius 14px`, composer pill `radius 26px`. Opcional en demo; si se incluye, reutilizar estos estilos.

---

## 6. Iconografía
Lucide (`lucide-react`), `18–23px`, `flex-shrink: 0`: `LayoutDashboard, FolderOpen, ArrowDownLeft (cobro, verde), ArrowUpRight (pago, naranja), ChartNoAxesCombined (marca/proyección), Landmark (bancos), Building2, Users, Truck, Plus, Upload, Download, Search, Wallet, CalendarDays, RefreshCw, Pencil, Trash2, TriangleAlert, Info, ChevronRight, Cloud, MonitorSmartphone, LogOut, Sparkles`.

---

## 7. Gráficos
Recharts `AreaChart` monocromo: línea `#0070f2 2.5px`, relleno `linearGradient 0.18→0.01`, `CartesianGrid dashed 3 4 #e4e9ef`, ticks `12px #64748b`, tooltip con `money()`. En flow-treasury (sin deps): reproducir con `<canvas>`/SVG usando los mismos colores. Eje Y abreviado (`mil / M`).

---

## 8. Animaciones y motion (origen real)

| Elemento | Animación |
|---|---|
| `button, a, input` | `transition: background .15s, border-color .15s` |
| Botón shadcn | `transition-all`, `focus-visible:ring-[3px] ring/50`, iconos `size-4` |
| Dialog / AlertDialog | overlay `fade-in/out-0`; contenido `fade + zoom-in-95/out-95, duration-200`, centrado `translate -50%` |
| Popover / Select / Tooltip | `fade + zoom-95 + slide-in-from-{side}-2` |
| Sheet (drawer) | `ease-in-out, open 500ms / close 300ms` (slide lateral) |
| Sidebar | `transition [width] 200ms ease-linear`; colapso a iconos |
| Skeleton / loading | `animate-pulse`; spinner `animate-spin (Loader2)` |
| Toast (sonner) | slide + fade estándar de la lib |
| IA float | `ai-fade-in .45s ease` (sube 12px + escala .92→1); typing `ai-blink 1.1s infinite` (3 puntos, delays .18/.36s) |
| Tabla | `transition-colors, hover:bg-muted/50` |
| `tw-animate-css` | utilidades `fade/slide/zoom/shimmer/scroll-fade` disponibles (origen importa la lib; en vanilla replicar solo `fade + zoom 200ms`) |
| Foco accesible | `outline 2px #0070f2 offset 3px` en `button/input` |

```css
@keyframes ai-fade-in { from { opacity: 0; transform: translateY(12px) scale(.92); } to { opacity: 1; transform: none; } }
@keyframes ai-blink { 0%, 60%, 100% { opacity: .25; } 30% { opacity: 1; } }
@media (prefers-reduced-motion: reduce) { * { animation: none; transition: none; } }
```

---

## 9. Radius / sombras / bordes
- Radius: base `8px` (panels/KPI/cards), botones/nav `6px`, badges `4–5px`, pills IA `18–26px`, logo `7–8px`, favicon `13px`.
- Sombras: `KPI 0 2px 3px #152e4210`, `panel 0 2px 3px #152e4208`, `botón heading 0 1px 2px #122b4110`, `AI float 0 12px 30px #123b6455`, `auth 0 18px 48px #123b6420`, modal shadcn `shadow-lg`.
- Bordes: casi todo `1px #dfe5ec`; tablas `#e9edf2`; inputs `#bccbd9`.

---

## 10. Accesibilidad (no negociable, viene del origen)
- Foco visible `2–3px #0070f2` en todo interactivo; labels en cada input; `aria-label` en icon-buttons; tablas con `TableHead`; diálogos con título+descripción; `prefers-reduced-motion` desactiva animación; montos con `tabular-nums` y sin depender solo del color (badge con texto: `Completado / Pendiente / Vencido / Abono parcial`).

---

## 11. Responsive (breakpoints origen)
`1500px` (gráfico 270px) · `1250px` · `1000px` (KPIs 2 col, grids a 1 col) · `767px` (main `22px 16px`, topbar 55px, KPIs 2 col compactos, tablas con scroll-x, modales full-width) · `640px` (IA 1 col) · `520px` (auth). En móvil: KPIs en grid 2 col, matriz/tablas con `overflow-x: auto`, acciones a `width: 100%`.

---

## 12. Tokens CSS listos para `styles.css` (vanilla)

```css
:root {
  --bg: #f4f6f8; --card: #ffffff; --ink: #1d2d3e;
  --muted: #607386; --muted-2: #687a8c; --line: #dfe5ec; --line-soft: #e9edf2;
  --brand: #123b64; --brand-hover: #0d2c4d;
  --primary: #0070f2; --primary-ink: #0064d9; --nav-active-bg: #eaf3ff;
  --green: #18845b; --green-bg: #ebf7f0;
  --amber: #a26d0d; --amber-bg: #fff4d9;
  --red: #c2313c; --red-bg: #fff0f1; --destructive: #e7000b;
  --info-bg: #edf5fc; --info-bd: #dce6f0; --info-tx: #345e80;
  --warn-bg: #fff9eb; --warn-bd: #f2e1b9; --warn-tx: #8a641d;
  --input-bd: #bccbd9; --thead-bg: #f8fafc; --thead-tx: #687d90;
  --grid: #e4e9ef; --ticks: #64748b; --chart: #0070f2;
  --radius: 8px; --radius-sm: 6px;
  --shadow-card: 0 2px 3px #152e4210;
  --font: Arial, Helvetica, sans-serif;
}
```

---

## 13. Adaptaciones obligatorias a flow-treasury
1. **Moneda:** origen `money()` = `en-US USD 0 decimales`. Aquí: `es-MX MXN`: `new Intl.NumberFormat('es-MX',{style:'currency',currency:'MXN',maximumFractionDigits:0})`. Topbar: `MXN · Peso mexicano`.
2. **Stack:** sin Tailwind/shadcn/Recharts. Traducir clases a CSS vanilla con los tokens §12; gráfico en `<canvas>`/SVG con paleta §2 (línea `#0070f2`, grid `#e4e9ef`).
3. **Layout demo:** se permite simplificar sidebar → header sticky + KPIs + matriz (lo ya existente en `flujo-demo-2026.html`), pero conservando colores, badges, banners y motion de este documento.
4. **No agregar** `package.json`, bundlers ni dependencias salvo CDN justificado (ver `AGENTS.md`).
