-- schema.sql v4 — BD relacional portable (SQLite, monousuario, USD)
-- La DB vive junto al .exe (tesoreria.db). El Excel solo alimenta estas tablas vía ETL.
-- Formularios unificados ingreso/egreso (RF-10, RN-09):
--   banco | fecha_pago | tipo | tipo_pago | entidad | concepto_pago | centro_costo | valor_usd | status | observacion
-- v3: concilia estados de cuenta bancarios (dato real) contra movimientos (RF-19/RF-20):
--   extracto_lineas + cortes_bancarios + conciliacion + saldos_diarios_cuenta.
--   La apertura por cuenta es 31-jul-2026; el cierre agosto 2026 debe cuadrar
--   con la suma de los 3 cortes bancarios.

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS entidades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo TEXT NOT NULL CHECK (tipo IN ('cliente','proveedor')),
  nombre TEXT NOT NULL UNIQUE,
  activo INTEGER NOT NULL DEFAULT 1
);

-- v4: diferenciación sin campos extra (madre + extensiones 1-a-1).
-- movimientos.entidad_id sigue apuntando a entidades(id); clientes/proveedores
-- solo marcan a qué subtipo pertenece cada fila madre.
CREATE TABLE IF NOT EXISTS clientes (
  entidad_id INTEGER PRIMARY KEY REFERENCES entidades(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS proveedores (
  entidad_id INTEGER PRIMARY KEY REFERENCES entidades(id) ON DELETE CASCADE
);

-- v4: maestra de bancos; cuentas cuelga de bancos vía banco_id.
-- cuentas.banco (TEXT) se conserva como deprecated para DBs v3 en migración.
CREATE TABLE IF NOT EXISTS bancos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE,   -- Pichincha, Internacional, Produbanco, Guayaquil, Caja, PorDefinir
  logo TEXT NOT NULL DEFAULT '', -- ruta en frontend/assets/bancos/ (RF-25)
  activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS cuentas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  banco TEXT NOT NULL,               -- deprecated v4: usar bancos vía banco_id
  banco_id INTEGER REFERENCES bancos(id),
  numero TEXT DEFAULT '',
  saldo_inicial_usd REAL NOT NULL DEFAULT 0,
  activo INTEGER NOT NULL DEFAULT 1,
  -- v3: apertura bancaria real (corte 31-jul-2026) para cuadrar por cuenta.
  saldo_apertura_usd REAL NOT NULL DEFAULT 0,
  fecha_apertura TEXT DEFAULT '2026-07-31',
  tiene_extracto INTEGER NOT NULL DEFAULT 0,  -- 1 si ya se importó su estado de cuenta
  UNIQUE (banco, numero)
);

-- v4: vistas de compatibilidad (lectura). El front/API puede leer bancos o
-- clientes/proveedores sin romper queries contra entidades/cuentas.
CREATE VIEW IF NOT EXISTS v_clientes AS
  SELECT e.id, e.nombre, e.activo FROM entidades e
  JOIN clientes c ON c.entidad_id = e.id WHERE e.tipo = 'cliente';
CREATE VIEW IF NOT EXISTS v_proveedores AS
  SELECT e.id, e.nombre, e.activo FROM entidades e
  JOIN proveedores p ON p.entidad_id = e.id WHERE e.tipo = 'proveedor';
CREATE VIEW IF NOT EXISTS v_cuentas AS
  SELECT c.id, c.numero, c.saldo_inicial_usd, c.activo,
    c.saldo_apertura_usd, c.fecha_apertura, c.tiene_extracto,
    c.banco_id, COALESCE(b.nombre, c.banco) AS banco
  FROM cuentas c LEFT JOIN bancos b ON b.id = c.banco_id;

-- Catálogo cerrado de conceptos de pago (RN-09). Extensible solo por migración.
CREATE TABLE IF NOT EXISTS conceptos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  nombre TEXT NOT NULL UNIQUE          -- nomina, prestamo, ...
);

CREATE TABLE IF NOT EXISTS movimientos (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha_pago TEXT NOT NULL,            -- YYYY-MM-DD
  tipo TEXT NOT NULL CHECK (tipo IN ('ingreso','egreso')),
  tipo_pago TEXT NOT NULL CHECK (tipo_pago IN ('efectivo','transferencia','cheque')),
  concepto_id INTEGER NOT NULL REFERENCES conceptos(id),
  entidad_id INTEGER REFERENCES entidades(id),
  centro_costo TEXT DEFAULT '',
  valor_usd REAL NOT NULL CHECK (valor_usd > 0),
  status TEXT NOT NULL DEFAULT 'pendiente'
    CHECK (status IN ('pendiente','aplazado','realizado','vencido')),
  observacion TEXT DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mov
  ON movimientos(fecha_pago, tipo, entidad_id, status);

-- v3: extracto bancario (dato real, inmutable). Una fila por línea del estado
-- de cuenta. La conciliación amarra cada línea a su movimiento; lo no
-- amarrado genera el movimiento realizado automáticamente al importar.
CREATE TABLE IF NOT EXISTS extracto_lineas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  cuenta_id INTEGER NOT NULL REFERENCES cuentas(id),
  fecha TEXT NOT NULL,               -- YYYY-MM-DD (fecha valor del banco)
  descripcion TEXT NOT NULL DEFAULT '',
  referencia TEXT DEFAULT '',
  debito_usd REAL NOT NULL DEFAULT 0 CHECK (debito_usd >= 0),
  credito_usd REAL NOT NULL DEFAULT 0 CHECK (credito_usd >= 0),
  saldo_banco_usd REAL,              -- saldo que reporta el banco tras la línea
  hash_unico TEXT NOT NULL UNIQUE,   -- cuenta|fecha|debito|credito|referencia (idempotencia)
  import_log_id INTEGER REFERENCES import_log(id),
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_ext
  ON extracto_lineas(cuenta_id, fecha);

-- v3: cortes de cada estado de cuenta (encabezado del banco = prueba de cuadre).
CREATE TABLE IF NOT EXISTS cortes_bancarios (
  cuenta_id INTEGER NOT NULL REFERENCES cuentas(id),
  fecha_corte TEXT NOT NULL,         -- YYYY-MM-DD (último día del periodo)
  saldo_anterior REAL NOT NULL DEFAULT 0,
  depositos REAL NOT NULL DEFAULT 0,
  retiros REAL NOT NULL DEFAULT 0,
  saldo_actual REAL NOT NULL DEFAULT 0,
  archivo TEXT NOT NULL DEFAULT '',
  PRIMARY KEY (cuenta_id, fecha_corte)
);

-- v3: amarre movimiento <-> línea de extracto (conciliación automática por fecha).
CREATE TABLE IF NOT EXISTS conciliacion (
  movimiento_id INTEGER REFERENCES movimientos(id) ON DELETE SET NULL,
  extracto_id INTEGER NOT NULL UNIQUE REFERENCES extracto_lineas(id) ON DELETE CASCADE,
  tipo_match TEXT NOT NULL DEFAULT 'auto'
    CHECK (tipo_match IN ('auto','manual','generado')),
  fecha TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

-- Saldos precalculados: Dashboard y Vista de Flujo leen aquí, no suman movimientos cada vez.
-- Solo movimientos con status='realizado' suman al flujo (pendiente/aplazado = proyección).
CREATE TABLE IF NOT EXISTS saldos_diarios (
  fecha TEXT PRIMARY KEY,            -- YYYY-MM-DD
  ing REAL NOT NULL DEFAULT 0,
  egr REAL NOT NULL DEFAULT 0,
  neto REAL NOT NULL DEFAULT 0,
  acumulado_usd REAL NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS config (
  clave TEXT PRIMARY KEY,
  valor TEXT NOT NULL
);

-- v3: saldos precalculados por cuenta (apertura 31-jul + realizados de esa
-- cuenta). El cuadre mensual compara 'calculado' contra el corte del banco.
CREATE TABLE IF NOT EXISTS saldos_diarios_cuenta (
  fecha TEXT NOT NULL,               -- YYYY-MM-DD
  cuenta_id INTEGER NOT NULL REFERENCES cuentas(id),
  ing REAL NOT NULL DEFAULT 0,
  egr REAL NOT NULL DEFAULT 0,
  neto REAL NOT NULL DEFAULT 0,
  acumulado_usd REAL NOT NULL DEFAULT 0,
  PRIMARY KEY (fecha, cuenta_id)
);

CREATE TABLE IF NOT EXISTS import_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  archivo TEXT NOT NULL,
  filas_ok INTEGER NOT NULL DEFAULT 0,
  filas_error INTEGER NOT NULL DEFAULT 0,
  fecha TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Bitácora de auditoría v3: registra toda acción CRUD + sistema (origen UI/IMPORT/SISTEMA).
-- dato_anterior/dato_nuevo guardan JSON con los valores antes/después para consultas post-fallo.
-- Se preserva ante el borrado total (RN-13): borrar_todo() no la vacía.
CREATE TABLE IF NOT EXISTS bitacora (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  fecha TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  accion TEXT NOT NULL CHECK (accion IN
    ('CREAR','EDITAR','REALIZADO','ELIMINAR','IMPORTAR','INIT_VACIO','BORRADO_TOTAL','EXPORTAR_LOGS')),
  tabla TEXT NOT NULL DEFAULT 'movimientos',
  registro_id INTEGER,
  detalle TEXT DEFAULT '',
  dato_anterior TEXT DEFAULT '',
  dato_nuevo TEXT DEFAULT '',
  origen TEXT NOT NULL DEFAULT 'UI' CHECK (origen IN ('UI','IMPORT','SISTEMA'))
);
CREATE INDEX IF NOT EXISTS idx_bitacora
  ON bitacora(fecha, accion, tabla);

-- Catálogos base (RN-09) + fallbacks antipérdida (RF-ETL-08)
INSERT OR IGNORE INTO conceptos (nombre) VALUES ('nomina'), ('prestamo'),
  ('cobranza_clientes'), ('pago_proveedores'), ('comision'), ('insumos'), ('por_definir');

-- v4: maestra de bancos primero; cuentas enlaza vía banco_id + texto deprecated.
-- NOTA: el seed de cuentas NO usa banco_id para que el executescript no rompa
-- en BDs v3 (sin esa columna); _migrar_v4() rellena bancos + banco_id después.
INSERT OR IGNORE INTO bancos (nombre, logo) VALUES
  ('Pichincha','assets/bancos/pichincha.png'),
  ('Guayaquil',''), ('Internacional','assets/bancos/internacional.png'),
  ('Caja',''), ('PorDefinir',''), ('Produbanco','assets/bancos/produbanco.webp');

INSERT OR IGNORE INTO cuentas (banco, numero, saldo_inicial_usd) VALUES
  ('Pichincha','2100319432',0), ('Guayaquil','',0),
  ('Internacional','7100614609',0), ('Caja','chica',0), ('PorDefinir','',0),
  ('Produbanco','02006198356',0);

-- v4: si la BD ya tenía entidades, clasifica cada fila madre en su hija.
INSERT OR IGNORE INTO clientes (entidad_id) SELECT id FROM entidades WHERE tipo='cliente';
INSERT OR IGNORE INTO proveedores (entidad_id) SELECT id FROM entidades WHERE tipo='proveedor';

INSERT OR IGNORE INTO config (clave, valor) VALUES
  ('saldo_inicial_usd','0'), ('fecha_inicio','2026-01-05');
