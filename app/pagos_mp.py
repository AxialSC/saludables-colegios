"""
app/pagos_mp.py — Integracion con Mercado Pago (Checkout Pro).
AXIAL SECURITY · Ivan Abrigo · v0.37.0

QUE HACE ESTE ARCHIVO
---------------------
Es la UNICA puerta de entrada a Mercado Pago. Ninguna pantalla habla con MP
por su cuenta: todo pasa por aca (misma filosofia que comisiones.py).

LAS CREDENCIALES NO VIVEN EN EL REPO
------------------------------------
Se leen de variables de entorno (MP_ACCESS_TOKEN / MP_PUBLIC_KEY) que se
definen en el archivo WSGI DENTRO de PythonAnywhere, que NO se sincroniza con
GitHub. Si el token estuviera en el repo, cualquiera que vea el codigo podria
cobrar en nombre de Ivan.

EL COSTO DE PLATAFORMA — LA CUENTA QUE IMPORTA
----------------------------------------------
Regla de negocio de Ivan: el precio de lista es el mismo para todos. El que
elige pagar con Mercado Pago (y financiarse con su tarjeta) paga ADEMAS el
costo que cobra la pasarela. Ivan cobra siempre sus $100 + IVA limpios.

Y aca esta la trampa: NO alcanza con sumar el porcentaje, porque Mercado Pago
tambien cobra comision SOBRE el recargo que agregaste. Hay que DIVIDIR:

        total_a_cobrar = total / (1 - comision)

Ejemplo con 1,89% (el 1,56% de 35 dias + IVA) sobre $121:
    MAL:  121 + (121 * 0.0189) = 123.29  ->  MP se lleva 2.33  ->  entran 120.96  ✗
    BIEN: 121 / (1 - 0.0189)   = 123.33  ->  MP se lleva 2.33  ->  entran 121.00  ✓
"""
import os

from flask import current_app, url_for

# El SDK puede no estar instalado (o PythonAnywhere free puede tener bloqueada
# la salida a la API). NUNCA se cae la tienda por eso: si algo falla, Mercado
# Pago simplemente no se ofrece y el resto del sistema sigue funcionando.
try:
    import mercadopago
    SDK_DISPONIBLE = True
except ImportError:
    mercadopago = None
    SDK_DISPONIBLE = False


# ----------------------------------------------------------------------
#  Credenciales
# ----------------------------------------------------------------------
def access_token():
    return (os.environ.get('MP_ACCESS_TOKEN') or '').strip()


def public_key():
    return (os.environ.get('MP_PUBLIC_KEY') or '').strip()


def es_sandbox():
    """
    Modo de prueba. Por defecto SI (mas seguro: nunca arrancamos cobrando
    plata real por accidente). Para pasar a produccion, en el archivo WSGI:
        os.environ['MP_SANDBOX'] = '0'
    """
    return (os.environ.get('MP_SANDBOX', '1') or '1').strip() != '0'


def sdk():
    """Devuelve el SDK listo para usar, o None si no se puede."""
    if not SDK_DISPONIBLE:
        return None
    tok = access_token()
    if not tok:
        return None
    try:
        return mercadopago.SDK(tok)
    except Exception:
        return None


def configurado():
    """True si Mercado Pago esta listo para operar (SDK + token)."""
    return sdk() is not None


def motivo_no_configurado():
    """Texto para el panel: por que MP no esta operativo."""
    if not SDK_DISPONIBLE:
        return ('La librería de Mercado Pago no está instalada en el servidor. '
                'Correr: pip3.13 install --user mercadopago')
    if not access_token():
        return ('Falta el Access Token. Va como variable de entorno '
                'MP_ACCESS_TOKEN en el archivo WSGI de PythonAnywhere '
                '(nunca en el repositorio).')
    return ''


# ----------------------------------------------------------------------
#  Costo de plataforma
# ----------------------------------------------------------------------
def comision_efectiva(ajustes):
    """
    Devuelve la comision como FRACCION (0.0189 = 1,89%).
    Sale del panel (Medios de pago), no esta hardcodeada: el dia que Mercado
    Pago cambie sus tarifas, o que la contadora defina si lleva IVA, se ajusta
    ahi sin tocar una linea de codigo.
    """
    try:
        pct = float(ajustes.mp_costo_pct or 0)
    except (TypeError, ValueError):
        pct = 0.0
    if pct <= 0:
        return 0.0
    if getattr(ajustes, 'mp_costo_iva', False):
        pct *= 1.21          # la comision de MP lleva IVA arriba
    return pct / 100.0


def costo_plataforma(total, ajustes):
    """
    Cuanto hay que SUMARLE al pedido para que, despues de que Mercado Pago se
    quede con lo suyo, entren exactamente los $total.

    Devuelve 0.0 si el cobro del costo esta apagado en el panel.
    """
    if not getattr(ajustes, 'mp_costo_activo', False):
        return 0.0
    c = comision_efectiva(ajustes)
    if c <= 0 or c >= 1:
        return 0.0
    try:
        total = float(total)
    except (TypeError, ValueError):
        return 0.0
    bruto = total / (1.0 - c)          # <- DIVIDIR, no sumar (ver nota de arriba)
    return round(bruto - total, 2)


# ----------------------------------------------------------------------
#  Crear la preferencia (el "carrito" del lado de Mercado Pago)
# ----------------------------------------------------------------------
def crear_preferencia(pedido, items, ajustes):
    """
    Arma la preferencia de pago y devuelve la URL a la que hay que mandar al
    cliente, o None si algo fallo (ahi la tienda sigue andando sin MP).

    'items' son los del pedido ya recalculados en el servidor. El costo de
    plataforma va como UNA LINEA APARTE, para que el comprador vea exactamente
    que esta pagando y por que.
    """
    s = sdk()
    if s is None:
        return None

    lineas = []
    for it in items:
        lineas.append({
            'title': (it['producto'].nombre or 'Producto')[:250],
            'quantity': int(it['cantidad']),
            'unit_price': float(it['precio_unitario']),
            'currency_id': 'ARS',
        })

    extra = float(pedido.costo_plataforma or 0)
    if extra > 0:
        lineas.append({
            'title': 'Costo de plataforma de pago',
            'quantity': 1,
            'unit_price': extra,
            'currency_id': 'ARS',
        })

    if not lineas:
        return None

    datos = {
        'items': lineas,
        # Con esto atamos el pago a NUESTRO pedido: cuando MP avise, sabemos
        # exactamente cual es sin depender de nada mas.
        'external_reference': pedido.token,
        'payer': {
            'name': (pedido.nombre or '')[:100],
            'surname': (pedido.apellido or '')[:100],
            'email': (pedido.email or '')[:100] or None,
        },
        'back_urls': {
            'success': url_for('cliente.mp_retorno', token=pedido.token, _external=True),
            'pending': url_for('cliente.mp_retorno', token=pedido.token, _external=True),
            'failure': url_for('cliente.mp_retorno', token=pedido.token, _external=True),
        },
        # Si el pago sale aprobado, MP devuelve al cliente solo a nuestra pagina.
        'auto_return': 'approved',
        # A donde avisa MP cuando cambia el estado de un pago (server a server).
        'notification_url': url_for('cliente.mp_webhook', _external=True),
        'statement_descriptor': (ajustes.nombre_negocio or 'SALUDABLES')[:22],
    }
    # Limpiar el email si vino vacio (MP rechaza None adentro de payer)
    if not datos['payer'].get('email'):
        datos['payer'].pop('email', None)

    try:
        resp = s.preference().create(datos)
    except Exception as e:
        current_app.logger.error('MP crear_preferencia fallo: %s', e)
        return None

    cuerpo = (resp or {}).get('response') or {}
    if not cuerpo.get('id'):
        current_app.logger.error('MP respondio sin preferencia: %s', resp)
        return None

    pedido.mp_preference_id = str(cuerpo.get('id'))[:80]

    # En sandbox hay una URL distinta para probar sin plata real.
    if es_sandbox() and cuerpo.get('sandbox_init_point'):
        return cuerpo['sandbox_init_point']
    return cuerpo.get('init_point')


# ----------------------------------------------------------------------
#  Consultar un pago (lo usa el webhook y la vuelta del cliente)
# ----------------------------------------------------------------------
def consultar_pago(payment_id):
    """
    Le pregunta a Mercado Pago como quedo un pago.
    Devuelve un dict simple o None. NUNCA confiamos en lo que llega por la URL
    del navegador: siempre se re-pregunta al servidor de MP (defensa en
    profundidad, igual que se recalcula el carrito en el backend).
    """
    s = sdk()
    if s is None or not payment_id:
        return None
    try:
        resp = s.payment().get(str(payment_id))
    except Exception as e:
        current_app.logger.error('MP consultar_pago fallo: %s', e)
        return None

    p = (resp or {}).get('response') or {}
    if not p.get('id'):
        return None
    return {
        'id': str(p.get('id')),
        'estado': p.get('status'),                    # approved / pending / rejected...
        'detalle': p.get('status_detail'),
        'monto': float(p.get('transaction_amount') or 0),
        'token_pedido': p.get('external_reference'),
        'medio': (p.get('payment_method_id') or ''),
    }


ESTADOS_OK = ('approved',)
ESTADOS_EN_PROCESO = ('pending', 'in_process', 'authorized')
