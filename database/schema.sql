-- schema.sql v2 — BD relacional portable (SQLite, monousuario, USD)
-- La DB vive junto al .exe (tesoreria.db). El Excel solo alimenta estas tablas vía ETL.
-- Formularios unificados ingreso/egreso (RF-10, RN-09):
--   banco | fecha_pago | tipo | tipo_pago | entidad | concepto_pago | centro_costo | valor_usd | status | observacion

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS entidades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tipo TEXT NOT NULL CHECK (tipo IN ('cliente','proveedor')),
  nombre TEXT NOT NULL UNIQUE,
  activo INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS cuentas (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  banco TEXT NOT NULL,               -- Pichincha, Guayaquil, Internacional, Caja
  numero TEXT DEFAULT '',
  saldo_inicial_usd REAL NOT NULL DEFAULT 0,
  activo INTEGER NOT NULL DEFAULT 1,
  UNIQUE (banco, numero)
);

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
  cuenta_id INTEGER NOT NULL REFERENCES cuentas(id),
  centro_costo TEXT DEFAULT '',
  valor_usd REAL NOT NULL CHECK (valor_usd > 0),
  status TEXT NOT NULL DEFAULT 'pendiente'
    CHECK (status IN ('pendiente','aplazado','realizado','vencido')),
  observacion TEXT DEFAULT '',
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX IF NOT EXISTS idx_mov
  ON movimientos(fecha_pago, tipo, entidad_id, cuenta_id, status);

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

-- Catálogos base (RN-09)
INSERT OR IGNORE INTO conceptos (nombre) VALUES ('nomina'), ('prestamo'),
  ('cobranza_clientes'), ('pago_proveedores');

INSERT OR IGNORE INTO cuentas (banco, numero, saldo_inicial_usd) VALUES
  ('Pichincha','Cte 11111',0), ('Guayaquil','',0),
  ('Internacional','',0), ('Caja','chica',0), ('PorDefinir','',0);

INSERT OR IGNORE INTO config (clave, valor) VALUES
  ('saldo_inicial_usd','5000'), ('fecha_inicio','2026-01-05');
