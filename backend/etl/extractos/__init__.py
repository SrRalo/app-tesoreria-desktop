"""extractos — parsers de estados de cuenta bancarios (dato real) a filas normalizadas.

Cada parser devuelve un dict:
  {
    "banco": "Pichincha" | "Internacional" | "Produbanco",
    "numero": "2100319432",
    "periodo_inicio": "2026-08-01", "periodo_fin": "2026-08-31",
    "saldo_anterior": 321371.16,   # apertura 31-jul (explícita o inferida)
    "saldo_actual": 236014.39,     # cierre que reporta el banco
    "depositos": 553542.08, "retiros": 638898.85,
    "lineas": [{"fecha", "descripcion", "referencia",
                "debito", "credito", "saldo_banco"}],
  }

Los formatos son heterogéneos por banco (HTML, BIFF, xlsx-reporte), así que
hay un parser por banco. En runtime la app NUNCA lee estos archivos: se
importan una vez a extracto_lineas + cortes_bancarios vía importar_extracto.
"""
