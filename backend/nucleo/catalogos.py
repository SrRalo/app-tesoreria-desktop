"""catalogos.py — catálogos cerrados RN-09/RN-12 en un solo lugar.

Centraliza los valores que antes estaban repetidos como tuplas inline en app.py
y etl/importar.py. Los servicios validan contra estas constantes.
"""
from __future__ import annotations

TIPOS = ("ingreso", "egreso")
TIPOS_PAGO = ("efectivo", "transferencia", "cheque")
STATUS = ("pendiente", "aplazado", "realizado", "vencido")
# RN-12: al crear solo se permite pendiente|realizado (sin aplazado ni vencido).
STATUS_CREACION = ("pendiente", "realizado")
TIPOS_ENTIDAD = ("cliente", "proveedor")


def en_catalogo(valor: str, catalogo: tuple[str, ...]) -> bool:
    """True si el valor pertenece al catálogo cerrado."""
    return valor in catalogo
