"""
app/pricing.py — Motor de precios (Opcion 1: MARGEN SOBRE VENTA).
AXIAL · Decision confirmada por Ivan.

Formula base:
    venta_neta  = costo_neto / (1 - margen)
    precio_final = venta_neta * (1 + IVA)

Reglas:
  - El margen es 'sobre venta' (ej: 20% -> de cada $100 que paga el cliente,
    $20 son ganancia limpia).
  - Piso de seguridad: NUNCA se vende por debajo del 'markup_minimo' (20%).
  - Descuentos por volumen (x5 -3%, x10 -5%) se aplican sobre el precio, PERO
    con un tope: si el descuento haria caer el margen por debajo del minimo,
    el precio se 'clampea' al precio de margen minimo (no se regala).
"""
from .models import IVA


def margen_efectivo(producto, ajustes):
    """Margen a aplicar: el individual del producto si tiene, sino el general.
       Siempre respetando el piso (markup_minimo)."""
    base = producto.margen_individual
    if base is None:
        base = ajustes.markup_general
    return max(float(base), float(ajustes.markup_minimo))


def _venta_neta(costo, margen_pct):
    margen = float(margen_pct) / 100.0
    if margen >= 1:        # proteccion ante datos invalidos
        margen = 0.99
    return costo / (1.0 - margen)


def precio_final(producto, ajustes, escala='x1'):
    """Precio final CON IVA para una escala de cantidad ('x1', 'x5', 'x10')."""
    costo = float(producto.costo_neto)
    margen = margen_efectivo(producto, ajustes)

    neta = _venta_neta(costo, margen)

    descuentos = {'x1': 0.0, 'x5': float(ajustes.desc_x5), 'x10': float(ajustes.desc_x10)}
    desc = descuentos.get(escala, 0.0) / 100.0
    neta_con_desc = neta * (1.0 - desc)

    # Piso: no bajar del margen minimo aunque haya descuento por volumen
    neta_piso = _venta_neta(costo, ajustes.markup_minimo)
    if neta_con_desc < neta_piso:
        neta_con_desc = neta_piso

    return round(neta_con_desc * (1.0 + IVA), 2)


def precios(producto, ajustes):
    """Devuelve los 3 precios + el margen aplicado (para mostrar en el catalogo)."""
    return {
        'x1': precio_final(producto, ajustes, 'x1'),
        'x5': precio_final(producto, ajustes, 'x5'),
        'x10': precio_final(producto, ajustes, 'x10'),
        'margen': margen_efectivo(producto, ajustes),
    }


def escala_por_cantidad(cantidad):
    """1-4 -> x1 | 5-9 -> x5 | 10+ -> x10"""
    if cantidad >= 10:
        return 'x10'
    if cantidad >= 5:
        return 'x5'
    return 'x1'


def precio_por_cantidad(producto, ajustes, cantidad):
    """Precio unitario final segun la cantidad pedida de ese producto."""
    return precio_final(producto, ajustes, escala_por_cantidad(cantidad))
