"""
app/comisiones.py — Motor de comisiones del Frente E (v0.24.0).
AXIAL SECURITY · Ivan Abrigo

ESTE ARCHIVO ES LA UNICA FUENTE DE VERDAD DE LA PLATA DE LAS REVENDEDORAS.
Ninguna pantalla calcula comisiones por su cuenta: todas pasan por aca.

=============================================================================
  LA REGLA DE ORO (la que protege a Ivan)
=============================================================================
La comision sale DE ADENTRO del margen. NO se suma encima del precio.
Si se sumara encima, el precio final subiria y dejariamos de ser competitivos
-- y si el precio es malo no vende nadie, ni Ivan ni las revendedoras.

Entonces, de cada venta:

    margen de la venta  -  comision de la revendedora  =  lo que le queda a la casa

Y eso ULTIMO nunca puede bajar de MARGEN_CASA_MINIMO (6%, en config.py).
Despejando, el margen minimo que se le exige a cada revendedora es:

    margen_minimo = MARGEN_CASA_MINIMO + su_comision

    Inicial (2%) -> margen minimo  8%  ->  8 - 2 = 6% para la casa  ✓
    Plata   (3%) -> margen minimo  9%  ->  9 - 3 = 6% para la casa  ✓
    Oro     (4%) -> margen minimo 10%  -> 10 - 4 = 6% para la casa  ✓

Traducido a castellano: CUANTO MAS GANA ELLA, MENOS PUEDE REGALAR.
Y por ningun camino -- ni bajando el precio a mano, ni con un producto de margen
raro, ni con un descuento por volumen -- la casa termina ganando menos del 6%.
El backend lo hace cumplir SIEMPRE (defensa en profundidad): aunque el navegador
mande otro precio, aca se recalcula y se clampea.

=============================================================================
  TODO SOBRE NETO
=============================================================================
La comision se calcula sobre el NETO (sin IVA). Nunca sobre el precio final.
El IVA no es plata de Ivan: es plata que se le junta a AFIP. Nadie comisiona
sobre los impuestos.
"""
from flask import current_app
from sqlalchemy import func

from .extensions import db
from .models import IVA, Pedido, EstadoPedido
from . import pricing


# ============================================================================
#  Lectura de la configuracion (todo sale de config.py, nada hardcodeado)
# ============================================================================

def niveles():
    """Los escalones, tal como estan definidos en config.py."""
    return current_app.config.get('COMISION_NIVELES', [
        {'clave': 'INICIAL', 'nombre': 'Inicial', 'comision': 2.0, 'desde': 0},
    ])


def margen_casa_minimo():
    """Lo MINIMO que le tiene que quedar a la casa despues de pagar la comision."""
    return float(current_app.config.get('MARGEN_CASA_MINIMO', 6.0))


def minimo_neto():
    """Carrito minimo de un pedido de revendedora, en NETO (sin IVA)."""
    return float(current_app.config.get('MINIMO_REVENDEDORA_NETO', 50000.0))


# ============================================================================
#  NIVEL / ESCALON DE UNA REVENDEDORA
# ============================================================================

def vendido_neto(revendedora_id):
    """
    Ventas NETAS acumuladas y APROBADAS de esta revendedora.

    Solo cuentan los pedidos en estado CONFIRMADO o ENTREGADO. Un pedido que
    Juliana todavia no aprobo, o que rechazo porque Torres no tenia stock, NO
    es una venta: no suma para subir de escalon ni paga comision.
    """
    total = db.session.query(
        func.coalesce(func.sum(Pedido.neto_total), 0)
    ).filter(
        Pedido.revendedora_id == revendedora_id,
        Pedido.estado.in_(EstadoPedido.CUENTAN_COMISION),
    ).scalar()
    return float(total or 0)


def nivel_por_vendido(vendido):
    """El escalon que corresponde a X pesos netos vendidos."""
    actual = niveles()[0]
    for n in niveles():
        if vendido >= n['desde']:
            actual = n
    return actual


def nivel_de(revendedora_id):
    """El escalon en el que esta HOY una revendedora."""
    return nivel_por_vendido(vendido_neto(revendedora_id))


def falta_para_subir(vendido):
    """
    Cuanto le falta para el proximo escalon. Devuelve (siguiente, falta) o
    (None, 0) si ya esta en el tope. Sirve para motivarla en el dashboard:
    'te faltan $X para pasar a Plata y cobrar 3%'.
    """
    for n in niveles():
        if vendido < n['desde']:
            return n, round(n['desde'] - vendido, 2)
    return None, 0


# ============================================================================
#  PRECIOS: el piso de cada revendedora
# ============================================================================

def margen_minimo(comision_pct):
    """El margen minimo que se le exige a una revendedora de este escalon."""
    return margen_casa_minimo() + float(comision_pct)


def precio_minimo(producto, comision_pct):
    """
    El precio FINAL (con IVA) mas bajo al que esta revendedora puede vender este
    producto sin dejar a la casa por debajo del 6%.

    Reusa la matematica del motor de precios (venta = costo / (1 - margen)).
    No se reinventa nada.
    """
    return pricing.precio_oferta_minimo(producto, margen_minimo(comision_pct))


def precios_para(producto, ajustes, comision_pct):
    """
    Los 3 precios que ve la revendedora de un producto:
      · lista  -> el precio normal de la tienda (el techo razonable)
      · medio  -> el punto medio (para negociar sin regalar todo de una)
      · minimo -> SU piso, segun SU escalon. Por debajo de esto NO se puede.
    """
    lista = pricing.precio_final(producto, ajustes, 'x1')
    minimo = precio_minimo(producto, comision_pct)
    if minimo > lista:
        # Caso raro: un producto con margen individual bajisimo, donde el piso de
        # la revendedora queda POR ENCIMA del precio de lista. Manda el piso: no
        # se vende a perdida ni para vender.
        lista = minimo
    medio = round((lista + minimo) / 2, 2)
    return {
        'lista': lista,
        'medio': medio,
        'minimo': minimo,
        'costo': round(float(producto.costo_neto), 2),
    }


# ============================================================================
#  SNAPSHOT: la foto de la plata, congelada
# ============================================================================

def calcular(items, comision_pct):
    """
    Calcula toda la plata de una venta.

    'items' es una lista de dicts con:
        cantidad, precio_unitario (FINAL con IVA), costo_unitario (NETO)

    Devuelve el snapshot completo. Estos numeros son los que se congelan en el
    Pedido al aprobarlo, y NO se recalculan nunca mas (Pattern 1 de AXIAL:
    inmutabilidad historica). Si manana la revendedora sube de escalon, sus
    ventas viejas siguen pagando lo que se pacto el dia que se hicieron. Es la
    unica forma de que una liquidacion de comisiones sea auditable.
    """
    comision_pct = float(comision_pct)

    total = 0.0        # final, con IVA
    costo_total = 0.0  # neto, lo que se le paga a Torres
    for it in items:
        total += float(it['precio_unitario']) * int(it['cantidad'])
        costo_total += float(it['costo_unitario']) * int(it['cantidad'])

    total = round(total, 2)
    costo_total = round(costo_total, 2)

    # El neto: la base de TODA la cuenta. Sin IVA.
    neto = round(total / (1 + IVA), 2)

    # Margen sobre venta: de cada $100 netos que entran, cuantos son ganancia.
    margen_pct = round((neto - costo_total) / neto * 100, 2) if neto > 0 else 0.0

    comision_monto = round(neto * comision_pct / 100.0, 2)

    # Lo que le queda a la casa, en % y en pesos
    margen_casa_pct = round(margen_pct - comision_pct, 2)
    ganancia_casa = round((neto - costo_total) - comision_monto, 2)

    return {
        'total': total,                      # lo que paga el cliente (c/IVA)
        'neto_total': neto,                  # base de la comision
        'costo_total': costo_total,          # lo que se le paga a Torres
        'margen_pct': margen_pct,            # margen real de la venta
        'comision_pct': comision_pct,        # el escalon de ella
        'comision_monto': comision_monto,    # su plata
        'margen_casa_pct': margen_casa_pct,  # >= 6% SIEMPRE
        'ganancia_casa': ganancia_casa,      # la plata de la casa, en pesos
        'iva': round(total - neto, 2),       # lo que se junta para AFIP
    }


def cumple_piso_casa(snap):
    """
    El candado final. Se llama SIEMPRE antes de guardar o aprobar una venta.

    Se usa una tolerancia de 0.01 para que un redondeo de centavos no tire abajo
    una venta que en realidad esta bien (un 5.999999% no es una estafa, es un
    float).
    """
    return float(snap['margen_casa_pct']) >= margen_casa_minimo() - 0.01
