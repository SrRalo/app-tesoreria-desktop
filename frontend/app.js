/* app.js — flow-treasury · incremento 1 (shell + Dashboard)
   Secciones: UTILS / ROUTER / DASHBOARD / GRÁFICO / EVENTOS.
   Los escenarios RN-04 se aplican en el front sobre el flujo base del mock
   (base 100%, optimista cobros*1.15 + pagos*0.95, pesimista cobros*0.70 + egr*1.10). */
'use strict';

/* ===== UTILS ===== */
const $ = (s, r = document) => r.querySelector(s);
const fmtUSD = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const fmtUSD2 = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: 2 });
const fmtFecha = (iso) => { const [y, m, d] = iso.split('-'); return d + '/' + m + '/' + y; };
const fmtK = (v) => {
  const a = Math.abs(v);
  if (a >= 1e6) return (v / 1e6).toFixed(1) + ' M';
  if (a >= 1e3) return (v / 1e3).toFixed(0) + ' mil';
  return String(Math.round(v));
};
function toast(msg) {
  const t = document.createElement('div');
  t.className = 'toast'; t.textContent = msg;
  $('#toasts').appendChild(t);
  setTimeout(() => t.remove(), 4200);
}
/* Confirmación de seguridad propia (fondo con blur, foco en el diálogo) */
function askConfirm(title, msg, yesLabel) {
  return new Promise((resolve) => {
    $('#confirmTitle').textContent = title;
    $('#confirmMsg').textContent = msg;
    $('#confirmYes').textContent = yesLabel || 'Sí, eliminar';
    const ov = $('#confirmOverlay');
    const done = (val) => {
      ov.hidden = true;
      $('#confirmYes').onclick = $('#confirmNo').onclick = ov.onclick = null;
      document.removeEventListener('keydown', onKey);
      resolve(val);
    };
    const onKey = (e) => { if (e.key === 'Escape') done(false); };
    $('#confirmYes').onclick = () => done(true);
    $('#confirmNo').onclick = () => done(false);
    ov.onclick = (e) => { if (e.target === ov) done(false); };
    document.addEventListener('keydown', onKey);
    ov.hidden = false;
    $('#confirmNo').focus();
  });
}
const state = { escenario: 'base', horizonte: 30 };
const flujoState = { modo: 'diario', desde: '2026-01-19', mes: '2026-01', anio: '2026',
  expIng: false, expEgr: false, weeks: null, weekCache: {}, semLoading: false, semDone: false, dataEnd: null };

function addDaysISO(iso, days) {
  const d = new Date(iso + 'T12:00:00');
  return new Date(d.getTime() + days * 864e5).toISOString().slice(0, 10);
}
async function fetchWeek(desde) {
  if (!flujoState.weekCache[desde])
    flujoState.weekCache[desde] = await Api.flujo('diario', { desde });
  return flujoState.weekCache[desde];
}

/* ===== ROUTER (una sola pantalla, sin recargar) ===== */
const VIEWS = ['dashboard', 'flujo', 'movimientos', 'entidades', 'config'];
function route() {
  const v = (location.hash.replace('#/', '') || 'dashboard').split('?')[0];
  const view = VIEWS.includes(v) ? v : 'dashboard';
  document.querySelectorAll('.view').forEach((el) => el.classList.remove('active'));
  $('#view-' + view).classList.add('active');
  document.querySelectorAll('.nav-item').forEach((a) =>
    a.classList.toggle('active', a.dataset.view === view));
  document.body.classList.remove('nav-open');
  if (view === 'dashboard') renderDashboard().catch((e) => { console.error(e); toast('Error al cargar el dashboard'); });
  if (view === 'flujo') renderFlujo().catch((e) => { console.error(e); toast('Error al cargar la matriz'); });
  if (view === 'movimientos') renderMovimientos().catch((e) => { console.error(e); toast('Error al cargar movimientos'); });
  if (view === 'entidades') renderEntidades().catch((e) => { console.error(e); toast('Error al cargar entidades'); });
  if (view === 'config') renderConfig().catch((e) => { console.error(e); toast('Error al cargar configuración'); });
}
window.addEventListener('hashchange', route);

/* ===== DASHBOARD ===== */
function aplicarEscenario(cols, key) {
  const f = Api.ESCENARIOS[key];
  let acum = cols[0].saldo_inicial;
  return cols.map((c) => {
    const ing = c.ing * f.ing, egr = c.egr * f.egr, neto = ing - egr;
    acum = acum + neto;
    return { ...c, ing, egr, neto, acumulado: acum };
  });
}

async function renderDashboard() {
  const saldos = await Api.saldos();
  if (!saldos.length) {
    // BD vacía recién iniciada: sin datos que graficar (el modal RF-14 guía la carga).
    $('#dashRange').textContent = 'Sin datos todavía · importa tu Excel o crea movimientos';
    $('#dashAlert').innerHTML = '';
    $('#kpis').innerHTML = '';
    $('#chartFoot').textContent = 'Sin datos';
    const cv = $('#chart');
    if (cv) cv.getContext('2d').clearRect(0, 0, cv.width, cv.height);
    $('#upcoming').innerHTML = '<div class="empty"><h2>Sin movimientos</h2>' +
      '<p>Cuando importes tu libro o guardes movimientos, aquí verás el resumen.</p></div>';
    return;
  }
  const n = Math.min(state.horizonte, saldos.length);
  const base = saldos.slice(-n);
  // Ventana con etiquetas día + fecha para el gráfico y KPIs
  const cols = base.map((s) => {
    const d = new Date(s.fecha + 'T12:00:00');
    return { clave: s.fecha, ing: s.ing, egr: s.egr,
      titulo: ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'][d.getDay()],
      subtitulo: s.fecha.slice(8, 10) + '/' + s.fecha.slice(5, 7),
      saldo_inicial: 0 };
  });
  cols[0].saldo_inicial = base[0].acumulado_usd - base[0].neto;
  const sim = aplicarEscenario(cols, state.escenario);

  const totIng = sim.reduce((s, c) => s + c.ing, 0);
  const totEgr = sim.reduce((s, c) => s + c.egr, 0);
  const neto = totIng - totEgr;
  const actual = sim[sim.length - 1].acumulado;
  const inicial = sim[0].saldo_inicial;

  $('#dashRange').textContent =
    'Del ' + fmtFecha(sim[0].clave) + ' al ' + fmtFecha(sim[sim.length - 1].clave) +
    ' · escenario ' + Api.ESCENARIOS[state.escenario].nombre + ' · USD';

  // Alerta de déficit: primer día con acumulado < 0
  const mal = sim.find((c) => c.acumulado < 0);
  const box = $('#dashAlert');
  if (mal) {
    const dias = sim.indexOf(mal);
    box.innerHTML =
      '<div class="banner error enter" role="alert">' +
      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>' +
      '<div><b>Déficit proyectado el ' + fmtFecha(mal.clave) + ': ' + fmtUSD.format(mal.acumulado) + '.</b> ' +
      'Faltan ' + dias + ' días al escenario ' + Api.ESCENARIOS[state.escenario].nombre.toLowerCase() + '.</div>' +
      '<span class="act"><a class="btn" href="#/flujo">Ver en Flujo</a></span></div>';
  } else {
    box.innerHTML =
      '<div class="banner info enter">' +
      '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>' +
      '<div><b>Sin déficit en el horizonte de ' + n + ' días</b> al escenario ' +
      Api.ESCENARIOS[state.escenario].nombre.toLowerCase() + '.</div></div>';
  }

  const kpi = (label, val, sub, hero) =>
    '<div class="kpi' + (hero ? ' hero' : '') + '"><div class="kpi-top"><span class="kpi-label">' + label + '</span></div>' +
    '<div class="kpi-val">' + val + '</div><div class="kpi-sub">' + sub + '</div></div>';
  const cls = (v) => v < 0 ? 'neg' : 'pos';
  $('#kpis').innerHTML =
    kpi('Saldo actual', fmtUSD.format(actual),
      'Inicio periodo ' + fmtUSD.format(inicial), true) +
    kpi('Ingresos periodo', fmtUSD.format(totIng),
      '<b class="' + cls(totIng) + '">' + sim.filter((c) => c.ing > 0).length + '</b> días con cobro') +
    kpi('Egresos periodo', fmtUSD.format(totEgr),
      '<b class="' + cls(-totEgr) + '">' + sim.filter((c) => c.egr > 0).length + '</b> días con pago') +
    kpi('Flujo neto', '<span class="' + cls(neto) + '">' + fmtUSD.format(neto) + '</span>',
      neto < 0 ? 'Periodo en rojo' : 'Periodo en verde');

  drawChart(sim);
  $('#chartFoot').textContent = n + ' días · ' + fmtFecha(sim[0].clave) + ' → ' + fmtFecha(sim[sim.length - 1].clave);

  // Vencidos y próximos: pendientes/aplazados ordenados por fecha
  const { rows } = await Api.movimientos({ status: '', page: 1, limit: 200 });
  const pend = rows.filter((m) => m.status !== 'realizado')
    .sort((a, b) => a.fecha_pago < b.fecha_pago ? -1 : 1).slice(0, 5);
  $('#upcoming').innerHTML = pend.length ? '<table class="tbl"><thead><tr>' +
    '<th>Movimiento</th><th>Fecha pago</th><th>Estado</th><th class="amount">Valor</th></tr></thead><tbody>' +
    pend.map((m) =>
      '<tr><td><div class="ent"><span class="ent-ico ' + (m.tipo === 'ingreso' ? 'in' : 'out') + '">' +
      (m.tipo === 'ingreso'
        ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 7 7 17"/><path d="M16 17H7V8"/></svg>'
        : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7"/><path d="M8 7h9v9"/></svg>') +
      '</span><span>' + esc(m.entidad || '(sin entidad)') + '<small>' + esc(m.observacion || m.concepto_pago) + '</small></span></div></td>' +
      '<td class="num">' + fmtFecha(m.fecha_pago) + '</td>' +
      '<td><span class="badge ' + (m.status === 'pendiente' ? 'warn' : 'info') + '">' + m.status + '</span></td>' +
      '<td class="amount ' + (m.tipo === 'ingreso' ? 'pos' : 'neg') + '">' +
      (m.tipo === 'ingreso' ? '+' : '−') + fmtUSD.format(m.valor_usd).replace('−', '') + '</td></tr>').join('') +
    '</tbody></table>'
    : '<div class="empty"><h2>Sin vencidos ni próximos</h2><p>No hay movimientos pendientes o aplazados.</p></div>';
}

function esc(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ===== VISTA DE FLUJO (matriz 5 filas + subfilas, sin paginación) ===== */
const cell = (v) => '<td class="' + (v < 0 ? 'neg' : '') + '">' + fmtUSD.format(v) + '</td>';
const cell0 = (v) => '<td class="' + (v < 0 ? 'neg' : '') + '">' + (v === 0 ? '—' : fmtUSD.format(v)) + '</td>';

function subRows(movs, cols, signo) {
  const idx = {};
  cols.forEach((c, i) => { idx[c.clave] = i; });
  const orden = movs.slice().sort((a, b) =>
    a.fecha_pago < b.fecha_pago ? -1 : a.fecha_pago > b.fecha_pago ? 1 : a.id - b.id);
  return orden.map((m) => {
    const tds = cols.map((c) => {
      const hit = esMesCol(c.clave) ? m.fecha_pago.startsWith(c.clave) : m.fecha_pago === c.clave;
      return hit ? '<td class="hit" data-mid="' + m.id + '">' + (signo < 0 ? '−' : '+') + fmtUSD.format(m.valor_usd) + '</td>' : '<td></td>';
    }).join('');
    const etiqueta = esc(m.entidad || '(sin entidad)') + ' · ' + esc(m.banco);
    return '<tr class="sub"><th class="concept" scope="row">' + etiqueta + '</th>' + tds + '</tr>';
  }).join('');
}
function esMesCol(clave) { return /^\d{4}-\d{2}$/.test(clave); }

/* ===== selección tipo Excel (celda / columna / fila) ===== */
function clearSel() {
  document.querySelectorAll('#matrix .sel, #matrix .col-sel, #matrix .row-sel')
    .forEach((el) => el.classList.remove('sel', 'col-sel', 'row-sel'));
  document.querySelectorAll('#matrix .cell-detail').forEach((el) => el.remove());
  const s = $('#matrixSel');
  if (s) s.textContent = '';
}
function headLabel(c) {
  const col = (flujoState.lastCols || [])[c];
  return col ? (col.titulo + (col.subtitulo ? ' ' + col.subtitulo : '')).trim() : 'columna';
}
function rowLabel(r) {
  const tbl = $('#matrix');
  if (!tbl.tBodies.length) return 'fila';
  const th = tbl.tBodies[0].rows[r] && tbl.tBodies[0].rows[r].cells[0];
  return th ? th.textContent.replace(/^[▸▾]/, '').replace(/\d+$/, '').trim() : 'fila';
}
function paintSel(r, c) {
  const tbl = $('#matrix');
  if (!tbl.tHead || !tbl.tBodies.length) return;
  clearSel();
  const headCells = [...tbl.tHead.rows[0].cells];
  const bodyRows = [...tbl.tBodies[0].rows];
  if (r != null && c != null && bodyRows[r] && bodyRows[r].cells[c + 1]) {
    const td = bodyRows[r].cells[c + 1];
    td.classList.add('sel');
    headCells[c + 1].classList.add('col-sel');
    bodyRows[r].cells[0].classList.add('row-sel');
    // El ⋯ solo aparece sobre el monto seleccionado de una subfila
    if (td.dataset.mid) {
      const b = document.createElement('button');
      b.className = 'mini-btn cell-detail';
      b.dataset.detail = td.dataset.mid;
      b.setAttribute('aria-label', 'Ver movimiento completo');
      b.innerHTML = '<svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">' +
        '<circle cx="5" cy="12" r="1.6"/><circle cx="12" cy="12" r="1.6"/><circle cx="19" cy="12" r="1.6"/></svg>';
      td.appendChild(b);
    }
    $('#matrixSel').textContent = headLabel(c) + ' · ' + rowLabel(r) + ' = ' +
      td.textContent.trim();
  } else if (c != null && headCells[c + 1]) {
    headCells[c + 1].classList.add('col-sel');
    bodyRows.forEach((row) => {
      const td = row.cells[c + 1];
      if (td && td.tagName === 'TD') td.classList.add('sel');
    });
    $('#matrixSel').textContent = 'Columna ' + headLabel(c);
  } else if (r != null && bodyRows[r]) {
    bodyRows[r].cells[0].classList.add('row-sel');
    [...bodyRows[r].cells].forEach((td) => { if (td.tagName === 'TD') td.classList.add('sel'); });
    $('#matrixSel').textContent = 'Fila ' + rowLabel(r);
  }
}

async function renderFlujo() {
  const { modo, desde, mes, anio, expIng, expEgr } = flujoState;
  const wrap = $('#matrixWrap');
  const sl = wrap.scrollLeft; // anexar a la derecha no debe saltar el scroll
  let data;
  if (modo === 'diario') {
    // Scroll infinito: la fecha elegida es el punto de partida, se anexan días de 7 en 7.
    if (!flujoState.weeks) {
      flujoState.weeks = [desde];
      flujoState.semDone = false;
      flujoState.semLoading = false;
    }
    if (!flujoState.dataEnd) {
      const s = await Api.saldos();
      flujoState.dataEnd = s.length ? s[s.length - 1].fecha : desde;
    }
    const cols = [], detI = {}, detE = {};
    for (const w of flujoState.weeks) {
      const dw = await fetchWeek(w);
      cols.push(...dw.columnas);
      Object.assign(detI, dw.detalle_ingresos);
      Object.assign(detE, dw.detalle_egresos);
    }
    data = { columnas: cols, detalle_ingresos: detI, detalle_egresos: detE };
  } else {
    data = await Api.flujo(modo, { desde, mes, anio });
  }
  const cols = data.columnas;
  const tbl = $('#matrix');
  if (!cols.length) {
    tbl.innerHTML = '';
    $('#matrixFoot').textContent = 'Sin datos en este periodo';
    return;
  }
  const nIng = Object.values(data.detalle_ingresos).flat().length;
  const nEgr = Object.values(data.detalle_egresos).flat().length;

  const head = '<thead><tr><th class="corner" scope="col">Concepto</th>' +
    cols.map((c) => '<th scope="col">' + esc(c.titulo) +
      (c.subtitulo ? '<span class="d">' + esc(c.subtitulo) + '</span>' : '') + '</th>').join('') + '</tr></thead>';

  const fila = (cls, label, vals, fmt) =>
    '<tr class="' + cls + '"><th class="concept" scope="row">' + label + '</th>' +
    vals.map((v) => fmt(v)).join('') + '</tr>';

  const btnIng = '<button class="exp-btn" data-exp="ing" aria-expanded="' + expIng + '" aria-label="Desglosar ingresos">' + (expIng ? '▾' : '▸') + '</button>';
  const btnEgr = '<button class="exp-btn" data-exp="egr" aria-expanded="' + expEgr + '" aria-label="Desglosar egresos">' + (expEgr ? '▾' : '▸') + '</button>';

  let html = head + '<tbody>';
  html += fila('', 'Saldo inicial', cols.map((c) => c.saldo_inicial), cell);
  html += fila('tot', btnIng + 'Total Ingresos<span class="cnt">' + nIng + '</span>',
    cols.map((c) => c.ing), cell0);
  if (expIng) html += subRows(Object.values(data.detalle_ingresos).flat(), cols, +1);
  html += fila('tot', btnEgr + 'Total Egresos<span class="cnt">' + nEgr + '</span>',
    cols.map((c) => c.egr), cell0);
  if (expEgr) html += subRows(Object.values(data.detalle_egresos).flat(), cols, -1);
  html += fila('neto', 'Flujo neto diario', cols.map((c) => c.neto), cell);
  html += fila('acum', 'Flujo acumulado diario', cols.map((c) => c.acumulado), cell);
  html += '</tbody>';
  tbl.innerHTML = html;
  flujoState.lastCols = cols;
  clearSel();

  const rango = modo === 'diario'
    ? 'Desde el ' + fmtFecha(cols[0].clave) + ' · scroll infinito hacia la derecha'
    : modo === 'trimestre'
      ? 'Trimestre ' + cols.map((c) => c.clave).join(' · ')
      : 'Mensual ' + anio + ' (12 meses)';
  $('#flujoRange').textContent = rango + ' · montos en USD · clic en ▸ para desglosar';
  $('#matrixFoot').textContent = modo === 'diario'
    ? cols.length + ' días cargados · ' + (flujoState.semDone ? 'fin de los datos' : 'sigue a la derecha para más')
    : cols.length + ' columnas · ' + (nIng + nEgr) + ' movimientos · scroll horizontal, sin paginación';
  wrap.scrollLeft = sl;
  // Si todo cabe en pantalla no hay scroll: anexar hasta desbordar o agotar datos.
  if (modo === 'diario' && !flujoState.semDone)
    requestAnimationFrame(() => {
      if (wrap.scrollWidth <= wrap.clientWidth + 10) loadNextWeek();
    });
}

/* Anexa los siguientes 7 días al acercarse al borde derecho (solo modo diario) */
async function loadNextWeek() {
  if (flujoState.semLoading || flujoState.semDone || flujoState.weeks.length >= 60) return;
  flujoState.semLoading = true;
  try {
    const next = addDaysISO(flujoState.weeks[flujoState.weeks.length - 1], 7);
    const dw = await fetchWeek(next);
    const conMov = dw.columnas.some((c) => c.ing > 0 || c.egr > 0);
    if (!conMov && next > flujoState.dataEnd) {
      flujoState.semDone = true;
    } else {
      flujoState.weeks.push(next);
    }
    await renderFlujo();
  } finally {
    flujoState.semLoading = false;
  }
}

/* ===== GRÁFICO (canvas vanilla, HiDPI) ===== */
function drawChart(cols) {
  const cv = $('#chart'), tip = $('#chartTip');
  const box = cv.parentElement.getBoundingClientRect();
  const W = Math.max(box.width, 280), H = 270, dpr = window.devicePixelRatio || 1;
  cv.width = W * dpr; cv.height = H * dpr;
  const ctx = cv.getContext('2d');
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, W, H);
  const css = (v) => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
  const padL = 52, padR = 10, padT = 12, padB = 26;
  const iw = W - padL - padR, ih = H - padT - padB;
  const acum = cols.map((c) => c.acumulado), neto = cols.map((c) => c.neto);
  const lo = Math.min(...acum, ...neto, 0), hi = Math.max(...acum, ...neto, 0);
  const span = (hi - lo) || 1;
  const X = (i) => padL + (cols.length === 1 ? iw / 2 : (i / (cols.length - 1)) * iw);
  const Y = (v) => padT + ih - ((v - lo) / span) * ih;

  // grid + etiquetas Y abreviadas
  ctx.strokeStyle = css('--grid'); ctx.fillStyle = css('--ticks');
  ctx.font = '12px Arial'; ctx.textAlign = 'right'; ctx.lineWidth = 1;
  ctx.setLineDash([3, 4]);
  for (let g = 0; g <= 4; g++) {
    const v = lo + (span * g) / 4, y = Y(v);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(W - padR, y); ctx.stroke();
    ctx.fillText(fmtK(v), padL - 8, y + 4);
  }
  ctx.setLineDash([]);
  // cero
  if (lo < 0 && hi > 0) {
    ctx.strokeStyle = '#c2313c'; ctx.beginPath(); ctx.moveTo(padL, Y(0)); ctx.lineTo(W - padR, Y(0)); ctx.stroke();
  }
  // barras neto
  const bw = Math.max(2, Math.min(10, iw / cols.length - 3));
  cols.forEach((c, i) => {
    ctx.fillStyle = c.neto < 0 ? '#e8a3a8' : '#9ec3ee';
    const y0 = Y(0), y1 = Y(c.neto);
    ctx.fillRect(X(i) - bw / 2, Math.min(y0, y1), bw, Math.max(2, Math.abs(y1 - y0)));
  });
  // etiquetas X (cada N)
  ctx.fillStyle = css('--ticks'); ctx.textAlign = 'center';
  const step = Math.ceil(cols.length / 8);
  cols.forEach((c, i) => { if (i % step === 0) ctx.fillText(c.subtitulo, X(i), H - 8); });
  // línea acumulado + relleno
  const grad = ctx.createLinearGradient(0, padT, 0, padT + ih);
  grad.addColorStop(0, 'rgba(0,112,242,.18)'); grad.addColorStop(1, 'rgba(0,112,242,.01)');
  ctx.beginPath();
  cols.forEach((c, i) => { const x = X(i), y = Y(c.acumulado); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.strokeStyle = css('--chart'); ctx.lineWidth = 2.5; ctx.lineJoin = 'round'; ctx.stroke();
  ctx.lineTo(X(cols.length - 1), Y(lo)); ctx.lineTo(X(0), Y(lo)); ctx.closePath();
  ctx.fillStyle = grad; ctx.fill();

  // tooltip
  cv.onmousemove = (ev) => {
    const r = cv.getBoundingClientRect();
    const mx = ev.clientX - r.left;
    let best = 0, bd = 1e9;
    cols.forEach((c, i) => { const d = Math.abs(X(i) - mx); if (d < bd) { bd = d; best = i; } });
    const c = cols[best];
    tip.style.display = 'block';
    tip.innerHTML = '<b>' + c.titulo + ' ' + c.subtitulo + '</b><br><span class="num">Acumulado ' +
      fmtUSD.format(Math.round(c.acumulado)) + '</span><br><span class="num">Neto ' +
      (c.neto < 0 ? '−' : '+') + fmtUSD.format(Math.abs(Math.round(c.neto))).replace('$', '$') + '</span>';
    const tx = Math.min(Math.max(X(best) + 12, 4), W - 170);
    tip.style.left = tx + 'px'; tip.style.top = '8px';
  };
  cv.onmouseleave = () => { tip.style.display = 'none'; };
}

/* ===== MOVIMIENTOS (tabla + filtros + paginación + modal CRUD) ===== */
const movState = { tipo: '', status: '', q: '', page: 1, limit: 20 };
const badgeStatus = (s) => s === 'realizado' ? 'ok' : s === 'pendiente' ? 'warn' : 'info';

async function renderMovimientos() {
  const { total, page, limit, rows } = await Api.movimientos(movState);
  const pages = Math.max(1, Math.ceil(total / limit));
  movState.page = Math.min(movState.page, pages);
  $('#movCount').textContent = total + ' movimientos · página ' + movState.page + ' de ' + pages;
  $('#movPage').textContent = total + ' movimientos';
  $('#movPrev').disabled = movState.page <= 1;
  $('#movNext').disabled = movState.page >= pages;
  const tbl = $('#movTable');
  tbl.innerHTML = '<thead><tr><th>Movimiento</th><th>Fecha pago</th><th>Tipo pago</th>' +
    '<th>Banco</th><th>Status</th><th class="amount">Valor USD</th><th><span class="sr-only">Acciones</span></th></tr></thead><tbody>' +
    (rows.length ? rows.map((m) =>
      '<tr><td><div class="ent"><span class="ent-ico ' + (m.tipo === 'ingreso' ? 'in' : 'out') + '">' +
      (m.tipo === 'ingreso'
        ? '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17 7 7 17"/><path d="M16 17H7V8"/></svg>'
        : '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M7 17 17 7"/><path d="M8 7h9v9"/></svg>') +
      '</span><span>' + esc(m.entidad || '(sin entidad)') +
      '<small>' + esc(m.concepto_pago) + (m.centro_costo ? ' · ' + esc(m.centro_costo) : '') +
      (m.observacion ? ' · ' + esc(m.observacion) : '') + '</small></span></div></td>' +
      '<td class="num">' + fmtFecha(m.fecha_pago) + '</td>' +
      '<td>' + esc(m.tipo_pago) + '</td><td>' + esc(m.banco) + '</td>' +
      '<td><span class="badge ' + badgeStatus(m.status) + '">' + m.status + '</span></td>' +
      '<td class="amount ' + (m.tipo === 'ingreso' ? 'pos' : 'neg') + '">' +
      (m.tipo === 'ingreso' ? '+' : '−') + fmtUSD.format(m.valor_usd) + '</td>' +
      '<td><div class="row-actions">' +
      '<button class="icon-btn" data-edit="' + m.id + '" aria-label="Editar movimiento ' + m.id + '">Editar</button>' +
      (m.status !== 'realizado'
        ? '<button class="icon-btn" data-done="' + m.id + '" aria-label="Marcar como realizado el movimiento ' + m.id + '">Realizado</button>'
        : '') +
      '<button class="icon-btn danger" data-del="' + m.id + '" aria-label="Eliminar movimiento ' + m.id + '">Borrar</button>' +
      '</div></td></tr>').join('')
      : '<tr><td colspan="7"><div class="empty"><h2>Sin resultados</h2><p>Ningún movimiento coincide con los filtros.</p></div></td></tr>') +
    '</tbody>';
}

/* --- modal: crear (9 campos, status pendiente|realizado) o editar (solo fecha+obs → aplazado) --- */
let editingId = null, reviewed = false;
const BLOQUEADOS_EDICION = ['f_tipo', 'f_banco', 'f_tipopago', 'f_entidad', 'f_concepto', 'f_cc', 'f_valor', 'f_status'];
async function openModal(id = null) {
  editingId = id; reviewed = false;
  const cuentas = await Api.cuentas();
  $('#f_banco').innerHTML = cuentas.map((c) => '<option>' + esc(c.banco) + '</option>').join('');
  const cli = await Api.entidades('cliente'), prv = await Api.entidades('proveedor');
  $('#dlEntidades').innerHTML = cli.concat(prv).map((e) => '<option value="' + esc(e.nombre) + '">').join('');
  // status según modo: al crear solo pendiente/realizado (RN-12)
  $('#f_status').innerHTML = id
    ? '<option value="aplazado">Aplazado (automático al editar)</option>'
    : '<option value="pendiente">Pendiente</option><option value="realizado">Realizado</option>';
  BLOQUEADOS_EDICION.forEach((fid) => { $('#' + fid).disabled = !!id; });
  $('#movAutoNote').hidden = !id;
  $('#movTitle').textContent = id ? 'Editar movimiento' : 'Nuevo movimiento';
  $('#movSub').textContent = id
    ? 'Solo puedes mover la fecha y la observación.'
    : 'Elige si es ingreso o egreso y completa los campos. Al guardar se recalculan los saldos.';
  if (id) {
    const { rows } = await Api.movimientos({ page: 1, limit: 500 });
    const m = rows.find((x) => x.id === +id);
    if (!m) { toast('Movimiento no encontrado'); return; }
    $('#f_tipo').value = m.tipo; $('#f_banco').value = m.banco; $('#f_fecha').value = m.fecha_pago;
    $('#f_tipopago').value = m.tipo_pago; $('#f_entidad').value = m.entidad;
    $('#f_concepto').value = m.concepto_pago; $('#f_cc').value = m.centro_costo || '';
    $('#f_valor').value = m.valor_usd; $('#f_status').value = 'aplazado';
    $('#f_obs').value = m.observacion || '';
  } else {
    $('#movForm').reset();
    $('#f_fecha').value = new Date().toISOString().slice(0, 10);
  }
  $('#movReview').hidden = true; $('#movLock').hidden = true;
  $('#movErr').hidden = true; $('#movSave').textContent = 'Revisar';
  $('#movOverlay').hidden = false;
  $('#f_fecha').focus();
}
function closeModal() { $('#movOverlay').hidden = true; editingId = null; }
function leerForm() {
  return { tipo: $('#f_tipo').value, banco: $('#f_banco').value, fecha_pago: $('#f_fecha').value,
    tipo_pago: $('#f_tipopago').value, entidad: $('#f_entidad').value.trim(),
    concepto_pago: $('#f_concepto').value, centro_costo: $('#f_cc').value.trim(),
    valor_usd: parseFloat($('#f_valor').value), status: $('#f_status').value,
    observacion: $('#f_obs').value.trim() };
}
async function submitModal(ev) {
  ev.preventDefault();
  const d = leerForm();
  $('#movErr').hidden = true;
  if (!reviewed) {
    // validación local espejo de RN-09 antes de mostrar el review
    const faltan = [];
    if (!d.fecha_pago) faltan.push('fecha de pago');
    if (!(d.valor_usd > 0)) faltan.push('valor mayor a 0');
    if (!d.banco) faltan.push('banco');
    if (faltan.length) {
      const e = $('#movErr');
      e.textContent = 'Falta: ' + faltan.join(', ') + '.';
      e.hidden = false;
      return;
    }
    $('#movReview').innerHTML = '<table>' +
      [['Tipo', d.tipo], ['Banco', d.banco], ['Fecha de pago', d.fecha_pago],
       ['Tipo de pago', d.tipo_pago], ['Entidad', d.entidad || '—'],
       ['Concepto', d.concepto_pago], ['Centro de costo', d.centro_costo || '—'],
       ['Valor', fmtUSD2.format(d.valor_usd)], ['Status', d.status],
       ['Observación', d.observacion || '—']]
        .map(([k, v]) => '<tr><td>' + k + '</td><td>' + esc(v) + '</td></tr>').join('') + '</table>';
    $('#movReview').hidden = false; $('#movLock').hidden = false;
    $('#movSave').textContent = editingId ? 'Confirmar cambios' : 'Confirmar guardado';
    reviewed = true;
    return;
  }
  try {
    if (editingId) {
      const ok = await askConfirm('¿Mover este movimiento al ' + fmtFecha(d.fecha_pago) + '?',
        'El status pasará a aplazado automáticamente y se recalcularán los saldos.', 'Sí, mover');
      if (!ok) return;
      await Api.actualizar(editingId, { fecha_pago: d.fecha_pago, observacion: d.observacion });
      closeModal();
      toast('Fecha movida · status actualizado a aplazado');
    } else {
      const ok = await askConfirm('¿Guardar este ' + (d.tipo === 'ingreso' ? 'ingreso' : 'egreso') +
        ' de ' + fmtUSD.format(d.valor_usd) + '?',
        'Entrará al flujo desde el ' + fmtFecha(d.fecha_pago) + ' y se recalcularán los saldos.', 'Sí, guardar');
      if (!ok) return;
      await Api.crear(d);
      closeModal();
      toast('Movimiento guardado · saldos recalculados');
    }
    movState.page = 1;
    await renderMovimientos();
  } catch (err) {
    const e = $('#movErr');
    e.textContent = 'No se pudo guardar: ' + err.message;
    e.hidden = false;
    reviewed = false;
    $('#movReview').hidden = true; $('#movLock').hidden = true;
    $('#movSave').textContent = 'Revisar';
  }
}

/* ===== DETALLE DE MOVIMIENTO (botón ⋯ de las subfilas) ===== */
let detailId = null;
async function openDetail(id) {
  const { rows } = await Api.movimientos({ page: 1, limit: 500 });
  const m = rows.find((x) => x.id === +id);
  if (!m) { toast('Movimiento no encontrado'); return; }
  detailId = m.id;
  $('#detailSub').textContent = (m.tipo === 'ingreso' ? 'Ingreso' : 'Egreso') + ' · ' + fmtFecha(m.fecha_pago);
  $('#detailBody').innerHTML = '<table>' +
    [['Tipo', m.tipo], ['Banco', m.banco], ['Fecha de pago', fmtFecha(m.fecha_pago)],
     ['Tipo de pago', m.tipo_pago], ['Entidad', m.entidad || '—'],
     ['Concepto de pago', m.concepto_pago], ['Centro de costo', m.centro_costo || '—'],
     ['Valor', fmtUSD2.format(m.valor_usd)], ['Status', m.status],
     ['Observación', m.observacion || '—']]
      .map(([k, v]) => '<tr><td>' + k + '</td><td>' + esc(v) + '</td></tr>').join('') + '</table>';
  $('#detailOverlay').hidden = false;
  $('#detailClose').focus();
}
function closeDetail() { $('#detailOverlay').hidden = true; detailId = null; }

/* ===== ENTIDADES (lectura: clientes, proveedores, bancos) ===== */
let entTab = 'cliente';
const ICO_BUILDING = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 22V4a2 2 0 0 1 2-2h8a2 2 0 0 1 2 2v18Z"/><path d="M10 6h4"/><path d="M10 10h4"/><path d="M10 14h4"/><path d="M10 18h4"/></svg>';
const ICO_BANK = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="3" x2="21" y1="22" y2="22"/><line x1="6" x2="6" y1="18" y2="11"/><line x1="10" x2="10" y1="18" y2="11"/><line x1="14" x2="14" y1="18" y2="11"/><line x1="18" x2="18" y1="18" y2="11"/><polygon points="12 2 20 7 4 7"/></svg>';

/* Resumen por entidad (nombre, total, nº movs, último): el mock ya lo trae
   calculado; con API real se agrega aquí desde los movimientos. */
async function resumenEntidades(rows, tipo) {
  if (rows.length && typeof rows[0].movimientos === 'number') return rows;
  const { rows: movs } = await Api.movimientos({ page: 1, limit: 500 });
  return rows.map((r) => {
    const ms = movs.filter((m) => m.entidad === r.nombre && m.status === 'realizado');
    const total = ms.reduce((s, m) => s + (m.tipo === 'ingreso' ? m.valor_usd : -m.valor_usd), 0);
    return { nombre: r.nombre, tipo, total_usd: total, movimientos: ms.length,
      ultimo: ms.length ? ms.map((m) => m.fecha_pago).sort().pop() : '—' };
  }).sort((a, b) => a.nombre < b.nombre ? -1 : 1);
}

async function renderEntidades() {
  document.querySelectorAll('.tab').forEach((t) => {
    const on = t.dataset.tab === entTab;
    t.classList.toggle('active', on);
    t.setAttribute('aria-selected', on);
  });
  const body = $('#entBody');
  if (entTab === 'banco') {
    const cuentas = await Api.cuentas();
    const { rows } = await Api.movimientos({ page: 1, limit: 500 });
    const info = {};
    for (const m of rows) {
      const b = info[m.banco] || (info[m.banco] = { ing: 0, egr: 0, n: 0, ultimo: '', ultimos: [], pend: 0 });
      if (m.status === 'realizado') {
        b[m.tipo === 'ingreso' ? 'ing' : 'egr'] += m.valor_usd;
        b.n++;
        if (!b.ultimo || m.fecha_pago > b.ultimo) b.ultimo = m.fecha_pago;
        b.ultimos.push(m);
      } else {
        b.pend++;
      }
    }
    Object.values(info).forEach((b) => {
      b.ultimos.sort((a, c) => a.fecha_pago < c.fecha_pago ? 1 : -1);
      b.ultimos = b.ultimos.slice(0, 5);
    });
    const saldoIni = (c) => +((c.saldo_inicial_usd ?? c.saldo_usd) || 0);
    const saldoCta = (c) => {
      const v = info[c.banco] || { ing: 0, egr: 0 };
      return saldoIni(c) + v.ing - v.egr;
    };
    const totalSaldo = cuentas.reduce((s, c) => s + saldoCta(c), 0);
    const max = Math.max(1, ...cuentas.map((c) => {
      const v = info[c.banco] || { ing: 0, egr: 0 };
      return v.ing + v.egr;
    }));
    const cards = '<div class="bank-cards"><div class="kpi hero"><div class="kpi-top">' +
      '<span class="kpi-label">Saldo total en bancos</span></div>' +
      '<div class="kpi-val">' + fmtUSD.format(totalSaldo) + '</div>' +
      '<div class="kpi-sub">' + cuentas.length + ' cuentas · solo realizado + saldo inicial</div></div>' +
      '<div class="kpi"><div class="kpi-top"><span class="kpi-label">Cuentas</span></div>' +
      '<div class="kpi-val">' + cuentas.length + '</div>' +
      '<div class="kpi-sub">Próximamente: estados de cuenta importados</div></div></div>';
    body.innerHTML = cards + '<div style="overflow-x:auto"><table class="tbl"><thead><tr>' +
      '<th>Banco</th><th class="amount">Saldo inicial</th><th>Movimientos</th><th class="amount">Ingresado</th>' +
      '<th class="amount">Pagado</th><th class="amount">Saldo</th><th>Volumen</th><th></th></tr></thead><tbody>' +
      cuentas.map((c) => {
        const v = info[c.banco] || { ing: 0, egr: 0, n: 0, ultimo: '', ultimos: [], pend: 0 };
        const pct = Math.round(((v.ing + v.egr) / max) * 100);
        const saldo = saldoCta(c);
        const ultimos = v.ultimos.map((m) =>
          '<tr><td class="num">' + fmtFecha(m.fecha_pago) + '</td><td>' + esc(m.entidad || '(sin entidad)') +
          '<small> · ' + esc(m.concepto_pago || '') + '</small></td>' +
          '<td class="amount ' + (m.tipo === 'ingreso' ? 'pos' : 'neg') + '">' +
          (m.tipo === 'ingreso' ? '+' : '−') + fmtUSD.format(m.valor_usd) + '</td></tr>').join('');
        return '<tr><td><div class="ent"><span class="ent-ico" style="background:#f0f5fa;color:#477291">' +
          ICO_BANK + '</span><span>' + esc(c.banco) +
          '<small>' + esc(c.numero || 'Sin número') + '</small></span></div></td>' +
          '<td class="amount">' + fmtUSD.format(saldoIni(c)) + '</td>' +
          '<td class="num">' + v.n + '</td>' +
          '<td class="amount pos">+' + fmtUSD.format(v.ing) + '</td>' +
          '<td class="amount neg">−' + fmtUSD.format(v.egr) + '</td>' +
          '<td class="amount' + (saldo < 0 ? ' neg' : '') + '">' + fmtUSD.format(saldo) + '</td>' +
          '<td><div class="vol" role="img" aria-label="Volumen ' + pct + '%"><i style="width:' + pct + '%"></i></div></td>' +
          '<td><div class="row-actions"><button class="icon-btn" data-q="' + esc(c.banco) + '">Ver movimientos</button></div></td></tr>' +
          '<tr class="stmt-row"><td colspan="8"><details class="stmt" data-estado="placeholder">' +
          '<summary>Ver saldo y estado resumido' + (v.ultimo ? ' · último ' + fmtFecha(v.ultimo) : '') +
          (v.pend ? ' · ' + v.pend + ' pendiente(s)' : '') + '</summary>' +
          '<div class="stmt-body">' +
          (v.n
            ? '<div style="overflow-x:auto"><table class="tbl"><tbody>' + ultimos + '</tbody></table></div>' +
              (v.pend ? '<p class="desc">' + v.pend + ' movimiento(s) pendiente(s)/aplazado(s) no suman al saldo.</p>' : '')
            : '<p class="desc">Sin estados de cuenta cargados para ' + esc(c.banco) +
              ' — aquí aparecerá el resumen cuando importes tus estados de cuenta.</p>' +
              '<!-- TODO: futura carga de estados de cuenta (CSV/Excel) por banco -->') +
          '</div></details></td></tr>';
      }).join('') + '</tbody></table></div>';
    return;
  }
  const rows = await resumenEntidades(await Api.entidades(entTab), entTab);
  const esCli = entTab === 'cliente';
  body.innerHTML = rows.length ? '<div style="overflow-x:auto"><table class="tbl"><thead><tr>' +
    '<th>' + (esCli ? 'Cliente' : 'Proveedor') + '</th><th>Movimientos</th>' +
    '<th class="amount">' + (esCli ? 'Cobrado' : 'Pagado') + '</th><th>Último</th><th></th></tr></thead><tbody>' +
    rows.map((e) =>
      '<tr><td><div class="ent"><span class="ent-ico ' + (esCli ? 'in' : 'out') + '">' + ICO_BUILDING + '</span>' +
      '<span>' + esc(e.nombre) + '</span></div></td>' +
      '<td class="num">' + e.movimientos + '</td>' +
      '<td class="amount ' + (e.total_usd < 0 ? 'neg' : '') + '">' + fmtUSD.format(Math.abs(e.total_usd)) + '</td>' +
      '<td class="num">' + (e.ultimo === '—' ? '—' : fmtFecha(e.ultimo)) + '</td>' +
      '<td><div class="row-actions"><button class="icon-btn" data-q="' + esc(e.nombre) + '">Ver movimientos</button></div></td></tr>'
    ).join('') + '</tbody></table></div>'
    : '<div class="empty"><h2>Sin ' + (esCli ? 'clientes' : 'proveedores') + '</h2>' +
      '<p>Aparecerán solos al guardar movimientos con entidad.</p></div>';
}

/* ===== CONFIGURACIÓN (zona de peligro RN-13) ===== */
async function renderConfig() {
  let n = '?';
  try { n = (await Api.estado()).movimientos; } catch (e) { /* sin backend */ }
  $('#cfgInfo').textContent = 'Hay ' + n + ' movimientos cargados en este momento.';
  $('#cfgErr').hidden = true;
}

/* ===== BIENVENIDA / PRIMER ARRANQUE (RF-14) ===== */
async function checkBienvenida() {
  let est = null;
  try { est = await Api.estado(); } catch (e) { return; }
  if (!est || !est.necesita_import) return;
  $('#welcomeOverlay').hidden = false;
  if (est.saldo_inicial_usd) $('#wSaldo').value = est.saldo_inicial_usd;
}
function wError(msg) {
  const e = $('#wErr');
  e.textContent = msg; e.hidden = false;
}

/* ===== EVENTOS ===== */
function init() {
  route();
  $('#fEscenario').addEventListener('change', (e) => { state.escenario = e.target.value; renderDashboard(); });
  $('#fHorizonte').addEventListener('change', (e) => { state.horizonte = +e.target.value; renderDashboard(); });
  $('#btnMovimiento').addEventListener('click', () => openModal());
  $('#btnNewMov').addEventListener('click', () => openModal());
  // Filtros + paginación Movimientos
  const refetch = () => { movState.page = 1; renderMovimientos(); };
  $('#mTipo').addEventListener('change', (e) => { movState.tipo = e.target.value; refetch(); });
  $('#mStatus').addEventListener('change', (e) => { movState.status = e.target.value; refetch(); });
  let qT; $('#mQ').addEventListener('input', (e) => {
    clearTimeout(qT); qT = setTimeout(() => { movState.q = e.target.value.trim(); refetch(); }, 250);
  });
  $('#movPrev').addEventListener('click', () => { if (movState.page > 1) { movState.page--; renderMovimientos(); } });
  $('#movNext').addEventListener('click', () => { movState.page++; renderMovimientos(); });
  $('#movTable').addEventListener('click', async (e) => {
    const eb = e.target.closest('[data-edit]');
    const done = e.target.closest('[data-done]');
    const db = e.target.closest('[data-del]');
    if (eb) openModal(eb.dataset.edit);
    if (done) {
      const ok = await askConfirm('¿Marcar como realizado?',
        'Se estampará hoy como fecha de pago y el movimiento entrará al flujo.', 'Sí, realizar');
      if (!ok) return;
      const r = await Api.marcarRealizado(done.dataset.done);
      toast('Marcado como realizado el ' + (r.fecha_pago || 'hoy') + ' · saldos recalculados');
      renderMovimientos();
    }
    if (db) {
      const ok = await askConfirm('¿Eliminar este movimiento?',
        'Se recalcularán neto y acumulado desde su fecha de pago.', 'Sí, eliminar');
      if (ok) {
        await Api.eliminar(db.dataset.del);
        toast('Movimiento eliminado · saldos recalculados');
        renderMovimientos();
      }
    }
  });
  // Modal
  $('#movCancel').addEventListener('click', closeModal);
  $('#movOverlay').addEventListener('click', (e) => { if (e.target.id === 'movOverlay') closeModal(); });
  // Detalle de movimiento (subfilas de Flujo)
  $('#detailClose').addEventListener('click', closeDetail);
  $('#detailOverlay').addEventListener('click', (e) => { if (e.target.id === 'detailOverlay') closeDetail(); });
  $('#detailGo').addEventListener('click', async () => {
    if (!detailId) return;
    const { rows } = await Api.movimientos({ page: 1, limit: 500 });
    const m = rows.find((x) => x.id === +detailId);
    closeDetail();
    movState.q = m && m.entidad ? m.entidad : '';
    movState.page = 1;
    $('#mQ').value = movState.q;
    location.hash = '#/movimientos';
    renderMovimientos();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && !$('#movOverlay').hidden) closeModal();
    if (e.key === 'Escape' && !$('#detailOverlay').hidden) closeDetail();
    if (e.key === 'Escape' && $('#movOverlay').hidden && $('#view-flujo').classList.contains('active')) clearSel();
  });
  $('#movForm').addEventListener('submit', submitModal);
  // Entidades: tabs + salto a movimientos filtrados
  document.querySelectorAll('.tab').forEach((t) =>
    t.addEventListener('click', () => { entTab = t.dataset.tab; renderEntidades(); }));
  $('#entBody').addEventListener('click', (e) => {
    const b = e.target.closest('[data-q]');
    if (!b) return;
    movState.q = b.dataset.q; movState.page = 1;
    $('#mQ').value = movState.q;
    location.hash = '#/movimientos';
    renderMovimientos();
  });
  // Bienvenida RF-14
  $('#wEmpty').addEventListener('click', async () => {
    try {
      await Api.initVacio({ saldo_inicial_usd: parseFloat($('#wSaldo').value) || 0,
        fecha_inicio: $('#wFecha').value });
      $('#welcomeOverlay').hidden = true;
      toast('Base lista · arrancamos en vacío con ' + fmtUSD.format(parseFloat($('#wSaldo').value) || 0));
      route();
    } catch (err) { wError('No se pudo iniciar: ' + err.message); }
  });
  $('#wImport').addEventListener('click', async () => {
    const f = $('#wFile').files[0];
    if (!f) { wError('Selecciona primero tu archivo .xlsx.'); return; }
    if (typeof Api.importar !== 'function') {
      wError('La importación Excel vive en el backend (ver backend/README.md). Por ahora usa Iniciar vacío.');
      return;
    }
    try {
      const r = await Api.importar(f);
      $('#welcomeOverlay').hidden = true;
      toast('Importadas ' + r.filas_ok + ' filas · bienvenido al Dashboard');
      route();
    } catch (err) { wError('No se pudo importar: ' + err.message); }
  });
  $('#wTemplate').addEventListener('click', async () => {
    if (await Api.modo() === 'real') {
      const a = document.createElement('a');
      a.href = '/api/plantilla'; a.download = 'plantilla_flujo.xlsx'; a.click();
      return;
    }
    wError('La plantilla se descarga del backend (GET /api/plantilla). Por ahora usa Iniciar vacío.');
  });
  // Configuración: borrado total con clave de administrador (RN-13)
  $('#btnBorrar').addEventListener('click', async () => {
    const err = $('#cfgErr');
    err.hidden = true;
    const clave = $('#cfgClave').value;
    if (!clave) { err.textContent = 'Escribe la clave de administrador.'; err.hidden = false; return; }
    const ok = await askConfirm('¿Borrar TODOS los datos?',
      'Se eliminan movimientos, saldos, entidades y cuentas. Volverás al primer arranque. No se puede deshacer.',
      'Sí, borrar todo');
    if (!ok) return;
    try {
      await Api.borrarDatos(clave);
      $('#cfgClave').value = '';
      toast('Datos borrados · de vuelta al inicio');
      renderConfig();
      checkBienvenida();
    } catch (e) { err.textContent = e.message; err.hidden = false; }
  });
  checkBienvenida();
  $('#menuBtn').addEventListener('click', () => document.body.classList.toggle('nav-open'));
  $('#scrim').addEventListener('click', () => document.body.classList.remove('nav-open'));
  const ICO_COLLAPSE = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m16 15-3-3 3-3"/></svg>';
  const ICO_EXPAND = '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/><path d="m14 9 3 3-3 3"/></svg>';
  $('#sideMinBtn').addEventListener('click', () => {
    const min = document.body.classList.toggle('side-min');
    const b = $('#sideMinBtn');
    b.innerHTML = min ? ICO_EXPAND : ICO_COLLAPSE;
    b.setAttribute('aria-label', min ? 'Expandir barra lateral' : 'Colapsar barra lateral');
    b.setAttribute('title', min ? 'Expandir barra lateral' : 'Colapsar barra lateral');
    b.setAttribute('aria-expanded', String(!min));
  });
  // Filtros Vista de Flujo
  const syncFlujoInputs = () => {
    $('#wDesde').hidden = flujoState.modo !== 'diario';
    $('#wMes').hidden = flujoState.modo !== 'trimestre';
    $('#wAnio').hidden = flujoState.modo !== 'mensual';
  };
  $('#fModo').addEventListener('change', (e) => {
    flujoState.modo = e.target.value; syncFlujoInputs(); renderFlujo();
  });
  $('#fDesde').addEventListener('change', (e) => {
    flujoState.desde = e.target.value; flujoState.weeks = null; renderFlujo();
  });
  $('#fMes').addEventListener('change', (e) => { flujoState.mes = e.target.value; renderFlujo(); });
  $('#fAnio').addEventListener('change', (e) => { flujoState.anio = e.target.value; renderFlujo(); });
  $('#matrix').addEventListener('click', (e) => {
    const b = e.target.closest('[data-exp]');
    if (b) {
      if (b.dataset.exp === 'ing') flujoState.expIng = !flujoState.expIng;
      else flujoState.expEgr = !flujoState.expEgr;
      renderFlujo();
      return;
    }
    const det = e.target.closest('[data-detail]');
    if (det) { openDetail(det.dataset.detail); return; }
    // Selección tipo Excel: celda, columna (encabezado) o fila (concepto)
    const tbl = $('#matrix');
    if (!tbl.tHead) return;
    const headCells = [...tbl.tHead.rows[0].cells];
    const bodyRows = [...tbl.tBodies[0].rows];
    const th = e.target.closest('th');
    const td = e.target.closest('td');
    if (th && tbl.tHead.contains(th)) {
      if (th.classList.contains('corner')) { clearSel(); return; }
      paintSel(null, headCells.indexOf(th) - 1);
      return;
    }
    if (th) { paintSel(bodyRows.indexOf(th.parentElement), null); return; }
    if (td) {
      const tr = td.parentElement;
      paintSel(bodyRows.indexOf(tr), [...tr.cells].indexOf(td) - 1);
    }
  });
  // Scroll infinito diario: anexar al acercarse al borde derecho
  $('#matrixWrap').addEventListener('scroll', (e) => {
    if (!$('#view-flujo').classList.contains('active') || flujoState.modo !== 'diario') return;
    const w = e.target;
    if (w.scrollLeft + w.clientWidth > w.scrollWidth - 500) loadNextWeek();
  });
  syncFlujoInputs();
  let rt; window.addEventListener('resize', () => { clearTimeout(rt); rt = setTimeout(renderDashboard, 150); });
}
document.addEventListener('DOMContentLoaded', init);
