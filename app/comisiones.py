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
from .models import IVA, Pedido, EstadoPedido, Usuario
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
    """
    El nivel que se GANA con X pesos netos acumulados (de por vida).
    Esto es el 'techo': lo mas alto que la revendedora llego a merecer.
    Que lo MANTENGA o no es otra cosa (ver nivel_de).
    """
    actual = niveles()[0]
    for n in niveles():
        if vendido >= n['desde']:
            actual = n
    return actual


def _idx(clave):
    """Posicion de un nivel en la escalera (0=Inicial, 1=Plata, 2=Oro)."""
    for i, n in enumerate(niveles()):
        if n['clave'] == clave:
            return i
    return 0


def _por_idx(i):
    ns = niveles()
    i = max(0, min(i, len(ns) - 1))
    return ns[i]


# ============================================================================
#  v0.26.0 · MOTOR DE PERMANENCIA (regla mixta, sin cron)
# ============================================================================
#
#  Como PythonAnywhere free no tiene tareas programadas, el nivel NO se
#  actualiza solo a medianoche: se CALCULA en el momento en que alguien lo
#  consulta (cuando Nadia entra o arma un pedido). Lo que importa es que sea
#  correcto en el instante en que se usa para una comision, y eso se garantiza
#  llamando a nivel_de() justo antes de cada calculo.
#
#  La regla (confirmada por Ivan):
#    1. Un nivel se GANA por ventas netas acumuladas de por vida.
#    2. Al alcanzarlo, se asegura COMISION_MESES_GRACIA meses: no baja pase lo
#       que pase.
#    3. Pasada la gracia, cada mes CERRADO se exige COMISION_PISO_MENSUAL de
#       venta neta. El primer mes que no llega -> baja UN escalon y arranca una
#       gracia nueva en el nivel de abajo.
#
#  IMPORTANTE: esto solo cambia el nivel para las ventas NUEVAS. Las comisiones
#  ya aprobadas quedaron congeladas (Pattern 1) y no se recalculan jamas.

from datetime import date

from sqlalchemy import extract


def _sumar_meses(d, meses):
    """
    Suma 'meses' a una fecha, sin depender de dateutil.

    ¿Por que no uso dateutil.relativedelta? Porque en PythonAnywhere con Python
    3.13 sin virtualenv una libreria puede no estar instalada (ya paso con
    pdfplumber). Sumar meses a mano es trivial y no arrastra ninguna dependencia.

    Maneja bien el corte de fin de mes: 31/01 + 1 mes = 28/02 (no explota).
    """
    m = d.month - 1 + meses
    anio = d.year + m // 12
    mes = m % 12 + 1
    # Ultimo dia valido de ese mes destino
    if mes == 12:
        dia_max = 31
    else:
        dia_max = (date(anio, mes + 1, 1) - date(anio, mes, 1)).days
    dia = min(d.day, dia_max)
    return date(anio, mes, dia)


def _meses_gracia():
    return int(current_app.config.get('COMISION_MESES_GRACIA', 6))


def _piso_mensual():
    return float(current_app.config.get('COMISION_PISO_MENSUAL', 2_000_000))


def _hoy():
    from .utils.timezone import ahora_argentina
    return ahora_argentina().date()


def _neto_del_mes(revendedora_id, anio, mes):
    """Venta neta aprobada de una revendedora en un mes calendario puntual."""
    total = db.session.query(
        func.coalesce(func.sum(Pedido.neto_total), 0)
    ).filter(
        Pedido.revendedora_id == revendedora_id,
        Pedido.estado.in_(EstadoPedido.CUENTAN_COMISION),
        extract('year', Pedido.aprobado_en) == anio,
        extract('month', Pedido.aprobado_en) == mes,
    ).scalar()
    return float(total or 0)


def _primer_dia(d):
    return d.replace(day=1)


def estado_nivel(revendedora_id, alcanzado_en=None):
    """
    Devuelve el estado COMPLETO del nivel de una revendedora, aplicando la regla
    de permanencia. Es la funcion central de E5.

    'alcanzado_en' = fecha (date) en que la revendedora alcanzo por ultima vez
    un nivel (o su fecha de alta). Sale de Usuario.nivel_desde (lo agrega la
    migracion). Si es None, se usa la fecha de creacion del usuario.

    Devuelve un dict con:
        nivel        -> el nivel ACTIVO hoy (dict de niveles())
        ganado       -> el nivel que merece por acumulado (el techo)
        en_gracia    -> bool: si todavia esta en los 6 meses asegurados
        gracia_hasta -> date en que se le vence la gracia
        bajo         -> bool: si bajo de escalon por no cumplir el piso
        motivo       -> texto explicativo para mostrarle
    """
    vendido = vendido_neto(revendedora_id)
    ganado = nivel_por_vendido(vendido)

    if alcanzado_en is None:
        u = db.session.get(Usuario, revendedora_id)
        alcanzado_en = (u.creado.date() if u and u.creado else _hoy())

    hoy = _hoy()
    gracia_hasta = _sumar_meses(alcanzado_en, _meses_gracia())
    en_gracia = hoy < gracia_hasta

    # Si esta en gracia, tiene asegurado el nivel que GANO. Punto.
    if en_gracia:
        return {
            'nivel': ganado, 'ganado': ganado,
            'en_gracia': True, 'gracia_hasta': gracia_hasta,
            'bajo': False,
            'motivo': f'Nivel asegurado hasta el {gracia_hasta.strftime("%d/%m/%Y")}.',
        }

    # Pasada la gracia: se revisa el ULTIMO mes calendario cerrado.
    # (el mes en curso no cuenta: todavia lo puede levantar)
    primer_dia_mes_actual = _primer_dia(hoy)
    ultimo_cerrado = _sumar_meses(primer_dia_mes_actual, -1)
    neto_mes = _neto_del_mes(revendedora_id, ultimo_cerrado.year, ultimo_cerrado.month)

    piso = _piso_mensual()
    if neto_mes >= piso or ganado['clave'] == niveles()[0]['clave']:
        # Cumplio el piso (o ya esta en el nivel mas bajo, no puede caer mas)
        return {
            'nivel': ganado, 'ganado': ganado,
            'en_gracia': False, 'gracia_hasta': gracia_hasta,
            'bajo': False,
            'motivo': (f'Nivel mantenido: vendiste {_fmt(neto_mes)} el mes pasado '
                       f'(mínimo {_fmt(piso)}).') if ganado['clave'] != niveles()[0]['clave']
                      else 'Nivel base.',
        }

    # No llego al piso -> baja UN escalon
    bajo_nivel = _por_idx(_idx(ganado['clave']) - 1)
    return {
        'nivel': bajo_nivel, 'ganado': ganado,
        'en_gracia': False, 'gracia_hasta': gracia_hasta,
        'bajo': True,
        'motivo': (f'Bajaste a {bajo_nivel["nombre"]}: el mes pasado vendiste '
                   f'{_fmt(neto_mes)}, por debajo del mínimo de {_fmt(piso)}. '
                   f'Recuperá {ganado["nombre"]} vendiendo más este mes.'),
    }


def _fmt(v):
    s = f'{float(v):,.0f}'.replace(',', '.')
    return '$' + s


def nivel_de(revendedora_id):
    """
    El nivel ACTIVO hoy de una revendedora, YA con la regla de permanencia
    aplicada. Este es el que se usa para calcular comisiones de ventas nuevas.

    Ojo: usa Usuario.nivel_desde si existe (la columna que agrega la migracion
    v0.26.0). Si la columna todavia no esta (base sin migrar), cae con elegancia
    al comportamiento viejo (nivel por acumulado), sin romper nada.
    """
    u = db.session.get(Usuario, revendedora_id)
    alcanzado = getattr(u, 'nivel_desde', None) if u else None
    if alcanzado is None and u is not None:
        alcanzado = u.creado.date() if u.creado else None
    try:
        return estado_nivel(revendedora_id, alcanzado)['nivel']
    except Exception:
        # Cinturon y tiradores: si algo falla (ej: columna inexistente en una
        # base sin migrar), no se cae el sistema; se usa el nivel por acumulado.
        return nivel_por_vendido(vendido_neto(revendedora_id))


def revisar_y_actualizar_nivel(revendedora_id):
    """
    Consulta el estado y, si el nivel activo CAMBIO respecto de lo guardado,
    persiste el cambio y resetea el reloj de gracia.

    Se llama al entrar al portal (dashboard) y al armar un pedido. Asi el nivel
    'se actualiza solo' sin necesidad de cron: la proxima venta ya usa el nivel
    correcto.

    Devuelve el estado_nivel completo (para mostrarlo en el dashboard).
    """
    u = db.session.get(Usuario, revendedora_id)
    if u is None:
        return None

    alcanzado = getattr(u, 'nivel_desde', None)
    if alcanzado is None:
        alcanzado = u.creado.date() if u.creado else _hoy()

    est = estado_nivel(revendedora_id, alcanzado)

    # Guardar el nivel activo actual si cambio
    nivel_guardado = getattr(u, 'nivel_actual', None)
    nivel_nuevo = est['nivel']['clave']

    if nivel_guardado != nivel_nuevo and hasattr(u, 'nivel_actual'):
        u.nivel_actual = nivel_nuevo
        # Si SUBIO (gano un nivel nuevo), reseteamos el reloj de gracia a hoy.
        # Si BAJO, tambien: arranca gracia nueva en el nivel de abajo.
        if hasattr(u, 'nivel_desde'):
            u.nivel_desde = _hoy()
        try:
            db.session.commit()
        except Exception:
            db.session.rollback()

    return est


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
