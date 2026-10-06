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
  const BANCOS = ['Pichincha', 'Guayaquil', 'Internacional', 'Caja', 'PorDefinir', 'Produbanco'];
  // Logos por banco (RF-25): la ruta vive en datos, no en el código del front.
  const BANCOS_LOGO = { Pichincha: 'assets/bancos/pichincha.png',
    Internacional: 'assets/bancos/internacional.png',
    Produbanco: 'assets/bancos/produbanco.webp' };
  const TIPOS_PAGO = ['transferencia', 'transferencia', 'transferencia', 'efectivo', 'cheque'];
  const DIAS = ['Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb', 'Dom'];
  const MESES = ['Ene', 'Feb', 'Mar', 'Abr', 'May', 'Jun', 'Jul', 'Ago', 'Sep', 'Oct', 'Nov', 'Dic'];
  const SALDO_INICIAL_DEFAULT = 0;
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
  // Bitácora mock (misma forma que backend): solo vive en memoria para la demo.
  const bitacoraRows = [];
  let bitSeq = 1;
  const ahoraISO = () => new Date().toISOString().slice(0, 19).replace('T', ' ');
  function logMock(accion, detalle, anterior, nuevo) {
    bitacoraRows.unshift({ id: bitSeq++, fecha: ahoraISO(), accion,
      tabla: 'movimientos', registro_id: (nuevo && nuevo.id) || (anterior && anterior.id) || null,
      detalle: detalle || '', dato_anterior: JSON.stringify(anterior || ''),
      dato_nuevo: JSON.stringify(nuevo || ''), origen: 'UI' });
  }

  // Validación RN-09 (igual que backend/app.py: 400 si el catálogo no cuadra)
  function validarMov(d) {
    const errs = [];
    if (!['ingreso', 'egreso'].includes(d.tipo)) errs.push('tipo inválido (RN-09)');
    if (!['efectivo', 'transferencia', 'cheque'].includes(d.tipo_pago)) errs.push('tipo_pago inválido (RN-09)');
    if (!['nomina', 'prestamo', 'cobranza_clientes', 'pago_proveedores', 'comision', 'insumos'].includes(String(d.concepto_pago || '').toLowerCase())) errs.push('concepto_pago inválido (RN-09)');
    if (!['pendiente', 'aplazado', 'realizado', 'vencido'].includes(d.status)) errs.push('status inválido (RN-09)');
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
      const porConcepto = {};
      for (const m of ms) {
        const c = m.concepto_pago || '—';
        porConcepto[c] = porConcepto[c] || { n: 0, ultima: '' };
        porConcepto[c].n++;
        if (m.fecha_pago > porConcepto[c].ultima) porConcepto[c].ultima = m.fecha_pago;
      }
      const concepto = ms.length ? Object.entries(porConcepto).sort((a, b) =>
        b[1].n - a[1].n || (b[1].ultima < a[1].ultima ? -1 : 1))[0][0] : '—';
      return { nombre: n, tipo, total_usd: total, movimientos: ms.length, ultimo, concepto };
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
  function armarFlujo(cols, esMes, escenario = 'base') {
    const detI = {}, detE = {};
    const real = movs.filter((m) => m.status === 'realizado');
    const fac = { base: [1, 1], optimista: [1.15, 0.95], pesimista: [0.7, 1.1] }[escenario] || [1, 1];
    let prev = saldos.filter((s) => s.fecha < cols[0].clave);
    let a = prev.length ? prev[prev.length - 1].acumulado_usd : SALDO_INI;
    const out = cols.map((c) => {
      const ms = real.filter((m) => esMes ? m.fecha_pago.startsWith(c.clave) : m.fecha_pago === c.clave);
      const ing = +(ms.filter((m) => m.tipo === 'ingreso').reduce((s, m) => s + m.valor_usd, 0) * fac[0]).toFixed(2);
      const egr = +(ms.filter((m) => m.tipo === 'egreso').reduce((s, m) => s + m.valor_usd, 0) * fac[1]).toFixed(2);
      const ini = +a.toFixed(2);
      a = +(a + ing - egr).toFixed(2);
      detI[c.clave] = ms.filter((m) => m.tipo === 'ingreso');
      detE[c.clave] = ms.filter((m) => m.tipo === 'egreso');
      return { ...c, saldo_inicial: ini, ing, egr, neto: +(ing - egr).toFixed(2), acumulado: a };
    });
    return { escenario, columnas: out, detalle_ingresos: detI, detalle_egresos: detE };
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
    initVacio: async ({ saldo_inicial_usd = 0, fecha_inicio = '2026-01-05' } = {}) => {
      movs.length = 0;
      SALDO_INI = +saldo_inicial_usd || 0;
      saldos = computeSaldos();
      logMock('INIT_VACIO', 'arranque vacío con saldo ' + SALDO_INI + ' USD', null,
        { saldo_inicial_usd: SALDO_INI, fecha_inicio });
      return { ok: true, saldo_inicial_usd: SALDO_INI, fecha_inicio };
    },
    bitacora: async ({ accion = '', desde = '', hasta = '', q = '', page = 1, limit = 50 } = {}) => {
      let rows = bitacoraRows.slice();
      if (accion) rows = rows.filter((r) => r.accion === accion);
      if (desde) rows = rows.filter((r) => r.fecha.slice(0, 10) >= desde);
      if (hasta) rows = rows.filter((r) => r.fecha.slice(0, 10) <= hasta);
      if (q) rows = rows.filter((r) => (r.detalle + r.dato_nuevo + r.dato_anterior).toLowerCase().includes(q.toLowerCase()));
      return { total: rows.length, page, limit, rows: rows.slice((page - 1) * limit, page * limit) };
    },
    recursos: async () => ({ ultimo_excel: null, total_movimientos: movs.length,
      nota: 'Demo local: importa con el backend para ver el libro de origen.' }),
    flujo: async (modo, p = {}) => {
      let cols, esMes = false;
      const m = modo === 'semana' ? 'diario' : modo === 'anual' ? 'mensual' : modo;
      if (m === 'trimestre') { cols = columnasMeses(p.mes || '2026-01', 3); esMes = true; }
      else if (m === 'mensual') { cols = columnasMeses((p.anio || '2026') + '-01', 12); esMes = true; }
      else cols = columnasSemana(p.desde);
      return { modo: m, ...armarFlujo(cols, esMes, p.escenario || 'base') };
    },
    saldos: async (anio = '', escenario = 'base') => {
      const rows = anio ? saldos.filter((s) => s.fecha.startsWith(anio)) : saldos.slice();
      if (escenario === 'base' || !rows.length) return rows;
      const fac = MockApi.ESCENARIOS[escenario] || MockApi.ESCENARIOS.base;
      let a = rows[0].acumulado_usd - rows[0].neto;
      return rows.map((s) => {
        const ing = +(s.ing * fac.ing).toFixed(2);
        const egr = +(s.egr * fac.egr).toFixed(2);
        const neto = +(ing - egr).toFixed(2);
        a = +(a + neto).toFixed(2);
        return { ...s, ing, egr, neto, acumulado_usd: a };
      });
    },
    anios: async () => [...new Set(saldos.map((s) => s.fecha.slice(0, 4)))].sort(),
    notificaciones: async () => {
      const hoy = new Date().toISOString().slice(0, 10);
      const pend = movs.filter((m) => ['pendiente', 'aplazado', 'vencido'].includes(m.status));
      const grupos = { vencido: [], d7: [], d15: [], d30: [], d60: [], d90: [], mas90: [] };
      const bucket = (d) => d < 0 ? 'vencido' : d <= 7 ? 'd7' : d <= 15 ? 'd15'
        : d <= 30 ? 'd30' : d <= 60 ? 'd60' : d <= 90 ? 'd90' : 'mas90';
      for (const m of pend) {
        const dias = Math.round((new Date(m.fecha_pago + 'T12:00:00') - new Date(hoy + 'T12:00:00')) / 864e5) || 0;
        const b = bucket(dias);
        grupos[b].push({ ...m, dias, bucket: b, es_vencido: b === 'vencido' });
      }
      Object.values(grupos).forEach((g) => g.sort((a, b) => a.fecha_pago < b.fecha_pago ? -1 : 1));
      const resumen = Object.fromEntries(Object.entries(grupos).map(([k, v]) => [k, v.length]));
      return { hoy, badge: resumen.vencido + resumen.d7, resumen, grupos,
        total_vencido_usd: { n: grupos.vencido.length,
          ingreso: grupos.vencido.filter((m) => m.tipo === 'ingreso').reduce((s, m) => s + m.valor_usd, 0),
          egreso: grupos.vencido.filter((m) => m.tipo === 'egreso').reduce((s, m) => s + m.valor_usd, 0) } };
    },
    movimientos: async ({ tipo = '', status = '', q = '', page = 1, limit = 50 } = {}) => {
      let rows = movs.slice().reverse();
      if (tipo) rows = rows.filter((m) => m.tipo === tipo);
      if (status) rows = rows.filter((m) => m.status === status);
      if (q) rows = rows.filter((m) => (m.observacion + m.entidad).toLowerCase().includes(q.toLowerCase()));
      return { total: rows.length, page, limit, rows: rows.slice((page - 1) * limit, page * limit) };
    },
    entidades: async (tipo) => resumenEntidades(tipo || 'cliente'),
    cuentas: async () => BANCOS.map((b) => ({ banco: b, numero: b === 'Pichincha' ? '2100319432' : '',
      saldo_usd: 0, banco_dice: null, diferencia: null, tiene_extracto: 0,
      aviso: 'Sin extracto de agosto 2026 — saldo 0 referencial, no afecta el cuadre' })),
    // ---- bancos con extracto (RF-25/26, demo: se derivan de los movimientos) ----
    bancos: async () => {
      const conMov = [...new Set(movs.map((m) => m.banco))].filter((b) => BANCOS_LOGO[b]);
      return conMov.map((b) => {
        const ms = movs.filter((m) => m.banco === b && m.status === 'realizado');
        const saldo = ms.reduce((s, m) => s + (m.tipo === 'ingreso' ? m.valor_usd : -m.valor_usd), 0);
        const fechas = ms.map((m) => m.fecha_pago).sort();
        return { cuenta_id: BANCOS.indexOf(b) + 1, banco: b, numero: '',
          logo: BANCOS_LOGO[b], saldo, fecha_corte: fechas.length ? fechas[fechas.length - 1] : '',
          lineas: ms.length };
      });
    },
    bancoMeses: async (cuentaId) => {
      const b = BANCOS[(+cuentaId || 1) - 1];
      const grupos = {};
      for (const m of movs.filter((m) => m.banco === b && m.status === 'realizado')) {
        const mes = m.fecha_pago.slice(0, 7);
        grupos[mes] = (grupos[mes] || 0) + 1;
      }
      const N = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
        'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];
      return Object.keys(grupos).sort().reverse().map((mes) => ({
        mes, etiqueta: N[+mes.slice(5, 7) - 1] + ' ' + mes.slice(0, 4), lineas: grupos[mes] }));
    },
    bancoExtracto: async (cuentaId, p = {}) => {
      const b = BANCOS[(+cuentaId || 1) - 1];
      const mes = p.mes || '';
      const limite = Math.min(Math.max(+p.limite || 50, 1), 100);
      const pagina = Math.max(+p.pagina || 1, 1);
      let ms = movs.filter((m) => m.banco === b && m.status === 'realizado')
        .sort((x, y) => x.fecha_pago < y.fecha_pago ? -1 : 1);
      if (mes) ms = ms.filter((m) => m.fecha_pago.startsWith(mes));
      let acum = 0;
      const rows = ms.map((m) => {
        const monto = m.tipo === 'ingreso' ? m.valor_usd : -m.valor_usd;
        acum = Math.round((acum + monto) * 100) / 100;
        return { fecha: m.fecha_pago, referencia: (m.observacion || '').slice(0, 60),
          descripcion: (m.entidad || '') + ' · ' + (m.concepto_pago || ''),
          monto, saldo: acum };
      });
      const paginas = Math.max(1, Math.ceil(rows.length / limite));
      const pg = Math.min(pagina, paginas);
      return { total: rows.length, pagina: pg, paginas, limite,
        rows: rows.slice((pg - 1) * limite, pg * limite) };
    },
    // Validación previa demo (el backend hace la estricta por contenido).
    validarCarga: async (archivos) => {
      const NOMBRE = { pichincha: 'Pichincha', internacional: 'Internacional',
        produbanco: 'Produbanco', cxc: 'CxC / CxP' };
      const DET = { pichincha: 'un estado de cuenta de Pichincha',
        internacional: 'un estado de cuenta de Internacional',
        produbanco: 'un estado de cuenta de Produbanco',
        cxc: 'un archivo de CxC / CxP', desconocido: 'un archivo no reconocido' };
      const resultados = [];
      for (const [campo, file] of Object.entries(archivos)) {
        if (!file) continue;
        const buf = new Uint8Array(await file.slice(0, 4).arrayBuffer());
        const hex = [...buf].map((x) => x.toString(16).padStart(2, '0')).join('').toUpperCase();
        const head = (await file.slice(0, 8192).text()).toLowerCase();
        let tipo = 'desconocido';
        if (head.includes('<table') && (head.includes('saldo anterior') || head.includes('detalle de movimientos')))
          tipo = 'pichincha';
        else if (hex.startsWith('D0CF11E0')) tipo = 'internacional';
        else if (hex.startsWith('504B0304'))
          tipo = campo === 'cxc' ? 'cxc' : 'produbanco';
        else if (head.includes('entidad') && head.includes('valor') && head.includes('fecha'))
          tipo = 'cxc';
        const ok = tipo === campo;
        resultados.push({ campo, ok, tipo_detectado: tipo,
          motivo: ok ? 'Verificado (demo local): el contenido corresponde al campo.'
            : (tipo === 'desconocido'
              ? 'Este archivo no parece ' + DET[campo] + '. Revise que esté en el campo correcto.'
              : 'Este archivo parece ' + DET[tipo] + ', pero está en el campo de ' +
                NOMBRE[campo] + '. Cámbialo al campo correcto.'),
          hojas: [] });
      }
      return { ok: !!resultados.length && resultados.every((r) => r.ok), resultados };
    },
    importarLote: async () => {
      throw new Error('sin backend: la importación múltiple requiere API');
    },
    // Extractos solo en Entidades > Bancos; sin conciliación ni cuadre.
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
      logMock('CREAR', m.tipo + ' ' + m.valor_usd + ' USD ' + m.fecha_pago, null, m);
      return { ok: true, id: m.id };
    },
    actualizar: async (id, d) => {
      const m = movs.find((x) => x.id === +id);
      if (!m) throw new Error('Movimiento no encontrado');
      if (!/^\d{4}-\d{2}-\d{2}$/.test(d.fecha_pago || '')) throw new Error('fecha_pago inválida');
      // Solo fecha y observación son editables; mover la fecha lo pasa a aplazado.
      const antes = { ...m };
      m.fecha_pago = d.fecha_pago;
      m.observacion = d.observacion || '';
      m.status = 'aplazado';
      movs.sort((a, b) => a.fecha_pago < b.fecha_pago ? -1 : a.fecha_pago > b.fecha_pago ? 1 : a.id - b.id);
      saldos = computeSaldos();
      logMock('EDITAR', 'fecha ' + antes.fecha_pago + '→' + m.fecha_pago, antes, { ...m });
      return { ok: true };
    },
    marcarRealizado: async (id, hoy) => {
      const m = movs.find((x) => x.id === +id);
      if (!m) throw new Error('Movimiento no encontrado');
      const fecha = hoy || new Date().toISOString().slice(0, 10);
      const antes = { ...m };
      m.status = 'realizado';
      m.fecha_pago = fecha;
      movs.sort((a, b) => a.fecha_pago < b.fecha_pago ? -1 : a.fecha_pago > b.fecha_pago ? 1 : a.id - b.id);
      saldos = computeSaldos();
      logMock('REALIZADO', 'marcado realizado el ' + fecha, antes, { ...m });
      return { ok: true, fecha_pago: fecha };
    },
    eliminar: async (id) => {
      const i = movs.findIndex((x) => x.id === +id);
      if (i < 0) throw new Error('Movimiento no encontrado');
      const antes = { ...movs[i] };
      movs.splice(i, 1);
      saldos = computeSaldos();
      logMock('ELIMINAR', 'eliminado ' + antes.tipo + ' ' + antes.valor_usd + ' USD', antes, null);
      return { ok: true };
    },
    // Borrado total RN-13 (igual que DELETE /api/datos): vuelve al primer arranque.
    borrarDatos: async (clave) => {
      if (clave !== 'admin123') throw new Error('clave de administrador inválida');
      movs.length = 0;
      SALDO_INI = SALDO_INICIAL_DEFAULT;
      saldos = computeSaldos();
      logMock('BORRADO_TOTAL', 'borrado total de datos (demo)', null, null);
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
  importar: async (f, hoja = '') => {
    const fd = new FormData();
    fd.append('archivo', f, f.name);
    if (hoja) fd.append('hoja', hoja);
    const r = await jfetch('/api/importar', { method: 'POST', body: fd });
    if (!r.filas_ok && r.errores && r.errores.length)
      throw new Error(r.errores.slice(0, 3).join(' · '));
    return r;
  },
  flujo: (modo, p = {}) => jfetch('/api/flujo?' + _qs({ modo, desde: p.desde, mes: p.mes, anio: p.anio, escenario: p.escenario || 'base' })),
  previewImportar: async (f, hoja = '') => {
    const fd = new FormData();
    fd.append('archivo', f, f.name);
    if (hoja) fd.append('hoja', hoja);
    return jfetch('/api/importar/preview', { method: 'POST', body: fd });
  },
  importarExtracto: async (f, banco) => {
    const fd = new FormData();
    fd.append('archivo', f, f.name);
    fd.append('banco', banco);
    const r = await jfetch('/api/extractos/importar', { method: 'POST', body: fd });
    return r;
  },
  validarCarga: async (fd) => {
    const r = await fetch('/api/importar/validar', { method: 'POST', body: fd });
    let data = null;
    try { data = await r.json(); }
    catch (e) { throw new Error('respuesta inválida del servidor (' + r.status + ')'); }
    if (!r.ok && !(data && data.resultados)) throw new Error((data && data.error) || ('error ' + r.status));
    return data;
  },
  importarLote: async (fd) => {
    const r = await fetch('/api/importar/lote', { method: 'POST', body: fd });
    let data = null;
    try { data = await r.json(); }
    catch (e) { throw new Error('respuesta inválida del servidor (' + r.status + ')'); }
    if (!r.ok) {
      const e = new Error((data && data.error) || ('error ' + r.status));
      e.resultados = (data && data.resultados) || [];
      throw e;
    }
    return data;
  },
  bancos: () => jfetch('/api/bancos').then((r) => r.rows || []),
  bancoMeses: (id) => jfetch('/api/bancos/' + id + '/meses').then((r) => r.rows || []),
  bancoExtracto: (id, p = {}) => jfetch('/api/bancos/' + id + '/extracto?' + _qs(p)),
  saldos: (anio = '', escenario = 'base') => jfetch('/api/saldos?' + _qs({ anio, escenario })),
  anios: () => jfetch('/api/anios'),
  notificaciones: () => jfetch('/api/notificaciones'),
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
  bitacora: (p = {}) => jfetch('/api/bitacora?' + _qs(p)),
  recursos: () => jfetch('/api/recursos'),
  exportFlujo: async (modo, p = {}, formato = 'csv') => {
    const r = await fetch('/api/flujo/export?' + _qs({
      modo, desde: p.desde, mes: p.mes, anio: p.anio,
      escenario: p.escenario || 'base', formato }));
    if (!r.ok) {
      let msg = 'error ' + r.status;
      try { msg = (await r.json()).error || msg; } catch (e) { /* binario */ }
      throw new Error(msg);
    }
    const blob = await r.blob();
    const cd = r.headers.get('Content-Disposition') || '';
    const m = /filename=([^\s;]+)/.exec(cd);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = m ? m[1] : ('flujo_' + modo + '.' + formato);
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    return { ok: true };
  },
  exportLogsTxt: async (p = {}) => {
    const r = await fetch('/api/bitacora/export?' + _qs(p));
    if (!r.ok) {
      let msg = 'error ' + r.status;
      try { msg = (await r.json()).error || msg; } catch (e) { /* texto */ }
      throw new Error(msg);
    }
    const blob = await r.blob();
    const cd = r.headers.get('Content-Disposition') || '';
    const m = /filename=([^\s;]+)/.exec(cd);
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = m ? m[1] : 'bitacora.txt';
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    return { ok: true };
  },
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
    importar: async (f, hoja = '') => {
      await sondear();
      if (modo !== 'real')
        throw new Error('sin backend: abre la app desde el ejecutable o el servidor con API');
      return RealApi.importar(f, hoja);
    },
    flujo: usar('flujo'),
    previewImportar: async (f, hoja) => {
      await sondear();
      if (modo !== 'real') throw new Error('sin backend: la vista previa requiere API');
      return RealApi.previewImportar(f, hoja);
    },
    importarExtracto: async (f, banco) => {
      await sondear();
      if (modo !== 'real')
        throw new Error('sin backend: abre la app desde el ejecutable o el servidor con API');
      return RealApi.importarExtracto(f, banco);
    },
    saldos: usar('saldos'),
    anios: usar('anios'),
    notificaciones: usar('notificaciones'),
    movimientos: usar('movimientos'),
    entidades: usar('entidades'),
    cuentas: usar('cuentas'),
    bancos: usar('bancos'),
    bancoMeses: usar('bancoMeses'),
    bancoExtracto: usar('bancoExtracto'),
    validarCarga: async (archivos) => {
      // archivos: {campo: File}. Con backend se envía FormData; en demo,
      // olfato local por contenido (el backend hace la validación estricta).
      await sondear();
      if (modo !== 'real') return MockApi.validarCarga(archivos);
      const fd = new FormData();
      for (const [campo, f] of Object.entries(archivos)) if (f) fd.append(campo, f, f.name);
      return RealApi.validarCarga(fd);
    },
    importarLote: async (archivos, hojaCxc = '') => {
      await sondear();
      if (modo !== 'real')
        throw new Error('sin backend: abre la app desde el ejecutable o el servidor con API');
      const fd = new FormData();
      for (const [campo, f] of Object.entries(archivos)) if (f) fd.append(campo, f, f.name);
      if (hojaCxc) fd.append('hoja_cxc', hojaCxc);
      return RealApi.importarLote(fd);
    },
    crear: usar('crear'),
    actualizar: usar('actualizar'),
    marcarRealizado: usar('marcarRealizado'),
    eliminar: usar('eliminar'),
    borrarDatos: usar('borrarDatos'),
    bitacora: usar('bitacora'),
    recursos: usar('recursos'),
    exportFlujo: async (flujoModo, p = {}, formato = 'csv') => {
      const m = await sondear();
      if (m === 'real') return RealApi.exportFlujo(flujoModo, p, formato);
      // Demo: CSV en el cliente desde el mock.
      if (formato !== 'csv') throw new Error('sin backend: en demo solo CSV');
      const r = await MockApi.flujo(flujoModo, p);
      const filas = [['clave', 'titulo', 'subtitulo', 'saldo_inicial',
        'ingresos', 'egresos', 'neto', 'acumulado']];
      for (const c of r.columnas)
        filas.push([c.clave, c.titulo, c.subtitulo || '', c.saldo_inicial,
          c.ing, c.egr, c.neto, c.acumulado]);
      const blob = new Blob(['\ufeff' + filas.map((f) => f.join(',')).join('\n')],
        { type: 'text/csv;charset=utf-8' });
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = 'flujo_' + (r.modo || flujoModo) + '_' + (r.escenario || 'base') + '.csv';
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 4000);
      return { ok: true };
    },
  exportLogsTxt: async (p = {}) => {
      await sondear();
      if (modo !== 'real') {
        // Demo: genera el .txt en el cliente desde la bitácora mock.
        const r = await MockApi.bitacora({ ...p, page: 1, limit: 5000 });
        const lineas = ['BITACORA — reporte de acciones (demo local)',
          'Total de eventos: ' + r.total, '-' .repeat(60)];
        for (const e of r.rows.slice().reverse()) {
          lineas.push('[' + e.fecha + '] ' + e.accion + ' ' + e.tabla +
            (e.registro_id ? '#' + e.registro_id : '') + ' — ' + e.detalle);
        }
        const blob = new Blob([lineas.join('\n') + '\n'], { type: 'text/plain;charset=utf-8' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob); a.download = 'bitacora_demo.txt';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
        return { ok: true };
      }
      return RealApi.exportLogsTxt(p);
    },
  };
})();
