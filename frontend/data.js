/* data.js — mock local + API real (mismo origen) con selección automática.
   Si el backend responde (/api/estado), se usa la BD real; si no (abrir el
   archivo suelto o servidor estático sin API), se usa el mock de demo.
   La app siempre habla con `Api`; `MockApi` es solo el fallback. */
'use strict';

const MockApi = (() => {
  // RNG determinista: el mock siempre muestra los mismos números.
  function mulberry32(a) {
    return function () {
      a |= 0; a = (a + 0x6D2B79F5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }
  const rnd = mulberry32(20260105);
  const pick = (arr) => arr[Math.floor(rnd() * arr.length)];
  const money = (min, max) => Math.round((min + rnd() * (max - min)) / 50) * 50;

  const CLIENTES = ['ACUICOLA ROMAR', 'AGROCAMARON', 'ARGUDO ZAMBRANO', 'CABRERA DAVILA',
    'CAMARONERA CAMANMOR', 'PACIFICCAM', 'PRODUMAR', 'EXPORCAMBRIT'];
  const PROVEEDORES = ['Nómina Planta', 'Larvas del Golfo', 'Insumos Marinos SA', 'Fábrica Pro',
    'Servicios Adm', 'Logística VTA', 'Banco Pichincha', 'Banco Internacional'];
  const BANCOS = ['Pichincha', 'Guayaquil', 'Internacional', 'Caja'];
  const TIPOS_PAGO = ['transferencia', 'transferencia', 'transferencia', 'efectivo', 'cheque'];
  const DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
  const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
  const SALDO_INICIAL_DEFAULT = 5000;
  let SALDO_INI = SALDO_INICIAL_DEFAULT;
  const INICIO = '2026-01-05';
  const NDIAS = 150;

  const fmtD = (d) => d.toISOString().slice(0, 10);
  const d0 = new Date(INICIO + 'T12:00:00');

  // ---- movimientos ----
  const movs = [];
  let seq = 1;
  const add = (fecha, tipo, tipo_pago, concepto, entidad, banco, cc, valor, status, obs) =>
    movs.push({ id: seq++, fecha_pago: fecha, tipo, tipo_pago, concepto_pago: concepto,
      entidad: entidad || '', banco, centro_costo: cc || '', valor_usd: valor,
      status, observacion: obs || '' });

  // Cartera inicial: la empresa arranca operando, no en cero
  add(INICIO, 'ingreso', 'transferencia', 'prestamo', 'PACIFICCAM', 'Pichincha', '', 12000, 'realizado', 'Cobro inicial cartera');
  add('2026-01-06', 'ingreso', 'transferencia', 'prestamo', 'PRODUMAR', 'Pichincha', '', 9500, 'realizado', 'Cobro inicial cartera');

  for (let i = 0; i < NDIAS; i++) {
    const f = new Date(d0.getTime() + i * 864e5);
    const fecha = fmtD(f);
    const dow = f.getDay(); // 0 dom
    const recien = i > NDIAS - 20;

    // Cobros: 2-3 por semana (lun/mié/vie), USD 2,500–8,000
    if ([1, 3, 5].includes(dow) && rnd() < 0.7) {
      const n = rnd() < 0.25 ? 2 : 1;
      for (let k = 0; k < n; k++)
        add(fecha, 'ingreso', pick(TIPOS_PAGO), 'prestamo', pick(CLIENTES), pick(BANCOS), '',
          money(2500, 8000), recien && rnd() < 0.4 ? 'pendiente' : 'realizado', 'Cobro factura ' + (100 + seq));
    }
    // Nómina quincenal (días 5 y 20 aprox): USD 5,500
    if (f.getDate() === 5 || f.getDate() === 20)
      add(fecha, 'egreso', 'transferencia', 'nomina', 'Nómina Planta', 'Pichincha', 'planta',
        5500, 'realizado', 'Quincena');
    // Larvas semanal (lunes), insumos (miércoles)
    if (dow === 1) add(fecha, 'egreso', 'transferencia', 'nomina', 'Larvas del Golfo', 'Guayaquil', '', 4200, 'realizado', 'Siembra semanal');
    if (dow === 3 && rnd() < 0.8) add(fecha, 'egreso', pick(TIPOS_PAGO), 'nomina', 'Insumos Marinos SA', pick(BANCOS), '', money(3000, 6000), 'realizado', 'Insumos');
    // Préstamos día 20: 1,850 + 2,900 + 850 (semana 3 de enero = neto negativo)
    if (f.getDate() === 20) {
      add(fecha, 'egreso', 'transferencia', 'prestamo', 'Banco Pichincha', 'Pichincha', '', 1850, 'realizado', 'Préstamo PICH 400K');
      add(fecha, 'egreso', 'transferencia', 'prestamo', 'Banco Pichincha', 'Pichincha', '', 2900, 'realizado', 'Préstamo PICH 700K');
      add(fecha, 'egreso', 'transferencia', 'prestamo', 'Banco Internacional', 'Internacional', '', 850, recien ? 'pendiente' : 'realizado', 'Préstamo INTER 60K');
    }
    // Inesperados ~5%
    if (rnd() < 0.05)
      add(fecha, 'egreso', 'efectivo', 'nomina', pick(PROVEEDORES), 'Caja', '', money(300, 1500),
        rnd() < 0.3 ? 'aplazado' : 'realizado', 'Gasto inesperado');
  }
  movs.sort((a, b) => a.fecha_pago < b.fecha_pago ? -1 : a.fecha_pago > b.fecha_pago ? 1 : a.id - b.id);

  // ---- saldos (solo realizado, igual que backend; se recalculan tras cada CRUD) ----
  function computeSaldos() {
    const porFecha = {};
    for (const m of movs) {
      if (m.status !== 'realizado') continue;
      porFecha[m.fecha_pago] = porFecha[m.fecha_pago] || { ing: 0, egr: 0 };
      if (m.tipo === 'ingreso') porFecha[m.fecha_pago].ing += m.valor_usd;
      else porFecha[m.fecha_pago].egr += m.valor_usd;
    }
    const out = [];
    let acum = SALDO_INI, primero = true;
    for (const fecha of Object.keys(porFecha).sort()) {
      const { ing, egr } = porFecha[fecha];
      const neto = ing - egr;
      acum = primero ? SALDO_INI + neto : acum + neto;
      primero = false;
      out.push({ fecha, ing, egr, neto, acumulado_usd: acum });
    }
    return out;
  }
  let saldos = computeSaldos();

  // Validación RN-09 (igual que backend/app.py: 400 si el catálogo no cuadra)
  function validarMov(d) {
    const errs = [];
    if (!['ingreso', 'egreso'].includes(d.tipo)) errs.push('tipo inválido (RN-09)');
    if (!['efectivo', 'transferencia', 'cheque'].includes(d.tipo_pago)) errs.push('tipo_pago inválido (RN-09)');
    if (!['nomina', 'prestamo'].includes(String(d.concepto_pago || '').toLowerCase())) errs.push('concepto_pago inválido (RN-09)');
    if (!['pendiente', 'aplazado', 'realizado'].includes(d.status)) errs.push('status inválido (RN-09)');
    if (!BANCOS.includes(d.banco)) errs.push('banco desconocido');
    if (!(+d.valor_usd > 0)) errs.push('valor_usd debe ser > 0');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(d.fecha_pago || '')) errs.push('fecha_pago inválida');
    return errs;
  }

  // ---- entidades / cuentas ----
  function resumenEntidades(tipo) {
    const nombres = tipo === 'cliente' ? CLIENTES : PROVEEDORES;
    return nombres.map((n) => {
      const ms = movs.filter((m) => m.entidad === n && m.status === 'realizado');
      const total = ms.reduce((s, m) => s + (m.tipo === 'ingreso' ? m.valor_usd : -m.valor_usd), 0);
      const ultimo = ms.length ? ms[ms.length - 1].fecha_pago : '—';
      return { nombre: n, tipo, total_usd: total, movimientos: ms.length, ultimo };
    }).filter((e) => e.movimientos > 0);
  }

  // ---- API (misma forma que backend/app.py) ----
  function columnasSemana(desde) {
    const base = new Date((desde || saldos[saldos.length - 6].fecha) + 'T12:00:00');
    const cols = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(base.getTime() + i * 864e5);
      cols.push({ clave: fmtD(d), titulo: DIAS[(d.getDay() + 6) % 7],
        subtitulo: String(d.getDate()).padStart(2, '0') + '/' + String(d.getMonth() + 1).padStart(2, '0') });
    }
    return cols;
  }
  function columnasMeses(ym, n) {
    let [y, m] = ym.split('-').map(Number);
    const cols = [];
    for (let i = 0; i < n; i++) {
      cols.push({ clave: y + '-' + String(m).padStart(2, '0'),
        titulo: MESES[m - 1] + ' ' + y, subtitulo: '' });
      m++; if (m > 12) { m = 1; y++; }
    }
    return cols;
  }
  function armarFlujo(cols, esMes) {
    const detI = {}, detE = {};
    const real = movs.filter((m) => m.status === 'realizado');
    let prev = saldos.filter((s) => s.fecha < cols[0].clave);
    let a = prev.length ? prev[prev.length - 1].acumulado_usd : SALDO_INI;
    const out = cols.map((c) => {
      const ms = real.filter((m) => esMes ? m.fecha_pago.startsWith(c.clave) : m.fecha_pago === c.clave);
      const ing = ms.filter((m) => m.tipo === 'ingreso').reduce((s, m) => s + m.valor_usd, 0);
      const egr = ms.filter((m) => m.tipo === 'egreso').reduce((s, m) => s + m.valor_usd, 0);
      const ini = a;
      a = a + ing - egr;
      detI[c.clave] = ms.filter((m) => m.tipo === 'ingreso');
      detE[c.clave] = ms.filter((m) => m.tipo === 'egreso');
      return { ...c, saldo_inicial: ini, ing, egr, neto: ing - egr, acumulado: a };
    });
    return { columnas: out, detalle_ingresos: detI, detalle_egresos: detE };
  }

  return {
    estado: async () => {
      // ?demo=alta fuerza el primer arranque para probar el modal RF-14.
      const forzado = typeof location !== 'undefined' && /[?&]demo=alta/.test(location.search);
      return { db_lista: true, movimientos: movs.length,
        necesita_import: forzado || movs.length === 0, mock: true,
        saldo_inicial_usd: SALDO_INI };
    },
    // Iniciar vacío RF-14 (igual que POST /api/init-vacio): limpia y fija saldo+fecha.
    initVacio: async ({ saldo_inicial_usd = 5000, fecha_inicio = '2026-01-05' } = {}) => {
      movs.length = 0;
      SALDO_INI = +saldo_inicial_usd || 0;
      saldos = computeSaldos();
      return { ok: true, saldo_inicial_usd: SALDO_INI, fecha_inicio };
    },
    flujo: async (modo, p = {}) => {
      let cols, esMes = false;
      if (modo === 'trimestre') { cols = columnasMeses(p.mes || '2026-01', 3); esMes = true; }
      else if (modo === 'anual') { cols = columnasMeses((p.anio || '2026') + '-01', 12); esMes = true; }
      else cols = columnasSemana(p.desde);
      return { modo, ...armarFlujo(cols, esMes) };
    },
    saldos: async () => saldos,
    movimientos: async ({ tipo = '', status = '', q = '', page = 1, limit = 50 } = {}) => {
      let rows = movs.slice().reverse();
      if (tipo) rows = rows.filter((m) => m.tipo === tipo);
      if (status) rows = rows.filter((m) => m.status === status);
      if (q) rows = rows.filter((m) => (m.observacion + m.entidad).toLowerCase().includes(q.toLowerCase()));
      return { total: rows.length, page, limit, rows: rows.slice((page - 1) * limit, page * limit) };
    },
    entidades: async (tipo) => resumenEntidades(tipo || 'cliente'),
    cuentas: async () => BANCOS.map((b) => ({ banco: b, numero: b === 'Pichincha' ? 'Cte 11111' : '', saldo_usd: 0 })),
    // CRUD (misma forma que POST/PUT/DELETE /api/movimientos; recalcula saldos)
    // Reglas: al crear solo pendiente/realizado; al editar solo fecha+obs y pasa a aplazado.
    crear: async (d) => {
      const errs = validarMov(d);
      if (errs.length) throw new Error(errs.join(' · '));
      if (d.status === 'aplazado') throw new Error('al crear solo se permite pendiente o realizado');
      const m = { id: seq++, fecha_pago: d.fecha_pago, tipo: d.tipo, tipo_pago: d.tipo_pago,
        concepto_pago: String(d.concepto_pago).toLowerCase(), entidad: d.entidad || '',
        banco: d.banco, centro_costo: d.centro_costo || '', valor_usd: +d.valor_usd,
        status: d.status, observacion: d.observacion || '' };
      movs.push(m);
      movs.sort((a, b) => a.fecha_pago < b.fecha_pago ? -1 : a.fecha_pago > b.fecha_pago ? 1 : a.id - b.id);
      saldos = computeSaldos();
      return { ok: true, id: m.id };
    },
    actualizar: async (id, d) => {
      const m = movs.find((x) => x.id === +id);
      if (!m) throw new Error('Movimiento no encontrado');
      if (!/^\d{4}-\d{2}-\d{2}$/.test(d.fecha_pago || '')) throw new Error('fecha_pago inválida');
      // Solo fecha y observación son editables; mover la fecha lo pasa a aplazado.
      m.fecha_pago = d.fecha_pago;
      m.observacion = d.observacion || '';
      m.status = 'aplazado';
      movs.sort((a, b) => a.fecha_pago < b.fecha_pago ? -1 : a.fecha_pago > b.fecha_pago ? 1 : a.id - b.id);
      saldos = computeSaldos();
      return { ok: true };
    },
    marcarRealizado: async (id, hoy) => {
      const m = movs.find((x) => x.id === +id);
      if (!m) throw new Error('Movimiento no encontrado');
      const fecha = hoy || new Date().toISOString().slice(0, 10);
      m.status = 'realizado';
      m.fecha_pago = fecha;
      movs.sort((a, b) => a.fecha_pago < b.fecha_pago ? -1 : a.fecha_pago > b.fecha_pago ? 1 : a.id - b.id);
      saldos = computeSaldos();
      return { ok: true, fecha_pago: fecha };
    },
    eliminar: async (id) => {
      const i = movs.findIndex((x) => x.id === +id);
      if (i < 0) throw new Error('Movimiento no encontrado');
      movs.splice(i, 1);
      saldos = computeSaldos();
      return { ok: true };
    },
    // Borrado total RN-13 (igual que DELETE /api/datos): vuelve al primer arranque.
    borrarDatos: async (clave) => {
      if (clave !== 'admin123') throw new Error('clave de administrador inválida');
      movs.length = 0;
      SALDO_INI = SALDO_INICIAL_DEFAULT;
      saldos = computeSaldos();
      return { ok: true };
    },
    // Escenarios RN-04 (se aplican en el front sobre el flujo base)
    ESCENARIOS: {
      base: { ing: 1, egr: 1, nombre: 'Base' },
      optimista: { ing: 1.15, egr: 0.95, nombre: 'Optimista' },
      pesimista: { ing: 0.70, egr: 1.10, nombre: 'Pesimista' },
    },
  };
})();

/* ===== API REAL (misma forma que MockApi, vía fetch al backend) ===== */
async function jfetch(url, opts = {}) {
  const r = await fetch(url, opts);
  let data = null;
  try { data = await r.json(); }
  catch (e) { throw new Error('respuesta inválida del servidor (' + r.status + ')'); }
  if (!r.ok) throw new Error((data && data.error) || ('error ' + r.status));
  return data;
}
const _qs = (p = {}) => Object.entries(p)
  .filter(([, v]) => v !== '' && v !== undefined && v !== null)
  .map(([k, v]) => encodeURIComponent(k) + '=' + encodeURIComponent(v)).join('&');
const RealApi = {
  estado: () => jfetch('/api/estado'),
  initVacio: (d = {}) => jfetch('/api/init-vacio', { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }),
  importar: async (f) => {
    const fd = new FormData();
    fd.append('archivo', f, f.name);
    const r = await jfetch('/api/importar', { method: 'POST', body: fd });
    if (!r.filas_ok && r.errores && r.errores.length)
      throw new Error(r.errores.slice(0, 3).join(' · '));
    return r;
  },
  flujo: (modo, p = {}) => jfetch('/api/flujo?' + _qs({ modo, desde: p.desde, mes: p.mes, anio: p.anio })),
  saldos: () => jfetch('/api/saldos'),
  movimientos: (p = {}) => jfetch('/api/movimientos?' + _qs(p)),
  entidades: (tipo) => jfetch('/api/entidades?' + _qs({ tipo: tipo || '' })),
  cuentas: () => jfetch('/api/cuentas'),
  crear: (d) => jfetch('/api/movimientos', { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }),
  actualizar: (id, d) => jfetch('/api/movimientos/' + id, { method: 'PUT',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(d) }),
  marcarRealizado: (id) => jfetch('/api/movimientos/' + id + '/realizado', { method: 'PUT' }),
  eliminar: (id) => jfetch('/api/movimientos/' + id, { method: 'DELETE' }),
  borrarDatos: (clave) => jfetch('/api/datos', { method: 'DELETE',
    headers: { 'X-Admin-Clave': clave || '' } }),
};

/* ===== Api unificado: real si hay backend, mock si no ===== */
const Api = (() => {
  let modo = 'mock', sonda = null;
  function sondear() {
    if (!sonda) sonda = (async () => {
      try {
        const ctl = new AbortController();
        const t = setTimeout(() => ctl.abort(), 2500);
        const r = await fetch('/api/estado', { signal: ctl.signal, cache: 'no-store' });
        clearTimeout(t);
        if (r.ok) modo = 'real';
      } catch (e) { modo = 'mock'; }
      const pill = document.getElementById('apiMode');
      if (pill) {
        pill.textContent = modo === 'real' ? 'EN VIVO · API' : 'DEMO local';
        pill.dataset.modo = modo;
      }
      return modo;
    })();
    return sonda;
  }
  const usar = (fn) => async (...a) => {
    await sondear();
    return (modo === 'real' ? RealApi[fn] : MockApi[fn])(...a);
  };
  return {
    modo: async () => { await sondear(); return modo; },
    ESCENARIOS: MockApi.ESCENARIOS,
    estado: usar('estado'),
    initVacio: usar('initVacio'),
    importar: async (f) => {
      await sondear();
      if (modo !== 'real')
        throw new Error('sin backend: abre la app desde el ejecutable o el servidor con API');
      return RealApi.importar(f);
    },
    flujo: usar('flujo'),
    saldos: usar('saldos'),
    movimientos: usar('movimientos'),
    entidades: usar('entidades'),
    cuentas: usar('cuentas'),
    crear: usar('crear'),
    actualizar: usar('actualizar'),
    marcarRealizado: usar('marcarRealizado'),
    eliminar: usar('eliminar'),
    borrarDatos: usar('borrarDatos'),
  };
})();
