"""
config.py — Configuracion del Sistema Saludables (Catalogo Mayorista)
AXIAL SECURITY · Ivan Abrigo

La version se cambia A MANO aca (regla AXIAL). El footer la toma automaticamente
desde el context_processor en app/__init__.py.

v0.18.3 -> C2: alta de suscriptores (form publico + panel admin + export CSV).
v0.19.0 -> Login rediseñado, estilo "El Arquitecto" (referencia: portal Lofty).
v0.19.1 -> Food Cost real: lector de facturas PDF de Torres.
v0.19.3 -> Fixes visuales: login sin scroll, sidebar auto-ajustable.
v0.20.0 -> HISTORIAL DE PRECIOS + Dashboard con alertas.
v0.20.1 -> Auto-logout por inactividad (con barra de sesion en el sidebar).
v0.21.0 -> E0: Fix CSRF + auto-logout REAL + timer en el portal + MARGEN_CASA_MINIMO.
v0.22.0 -> E1: Rediseño de la tienda (header 3 zonas + navbar), banners en grilla
               (3 bugs corregidos), assets de marca, placeholder de producto y
               sidebar del panel agrupado por secciones.
"""
import os
from datetime import timedelta

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # IMPORTANTE: en produccion poner una SECRET_KEY real via variable de entorno
    SECRET_KEY = os.environ.get('SECRET_KEY', 'axial-dev-cambiar-en-produccion')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Identidad / version ---
    APP_VERSION = '0.22.0'
    APP_NOMBRE = 'Saludables'
    APP_SUBTITULO = 'Catalogo Mayorista · Pilar'

    # URL publica del sistema (se usa en el mensaje de bienvenida por WhatsApp).
    # Si tu dominio es otro, cambialo aca.
    APP_URL = 'https://saludablespilar.pythonanywhere.com/'

    # ------------------------------------------------------------------
    # v0.21.0 · CSRF — fix del "Bad Request: The CSRF token has expired"
    # ------------------------------------------------------------------
    # Por defecto Flask-WTF le pone al token CSRF un vencimiento de 1 HORA,
    # INDEPENDIENTE de la sesion. Resultado: dejas el login (o cualquier
    # formulario) abierto una hora, apretas Guardar, y te salta un "Bad Request"
    # crudo y feo. Le paso None: el token deja de tener reloj propio y pasa a
    # durar LO MISMO QUE LA SESION.
    #
    # ¿Se pierde seguridad? NO. El token sigue siendo unico y firmado con la
    # SECRET_KEY: la proteccion contra CSRF sigue intacta. Lo unico que se quita
    # es el vencimiento por tiempo, que es justo lo que molestaba. Y como abajo
    # la sesion muere sola por inactividad, el token muere con ella.
    WTF_CSRF_TIME_LIMIT = None

    # ------------------------------------------------------------------
    # v0.20.1 / v0.21.0 · SESION (auto-logout por inactividad)
    # ------------------------------------------------------------------
    # Minutos de inactividad antes de cerrar la sesion sola. CUALQUIER movimiento
    # del mouse o tecla reinicia el contador al maximo.
    # >>> Si 2 minutos te resulta molesto (ej: leer una lista larga sin tocar
    #     nada), cambia este numero y listo. No hay que tocar codigo ni migrar.
    SESION_TIMEOUT_MIN = 2

    # Segundos finales en los que la barra se pone roja y late (aviso visual).
    SESION_AVISO_SEG = 30

    # --- v0.21.0: el candado DE VERDAD (server-side) ---
    # Hasta v0.20.1 el auto-logout era SOLO JavaScript: si alguien cerraba el
    # navegador (o desactivaba el JS), la cookie de sesion seguia viva y podia
    # volver a entrar sin loguearse. Esto lo arregla: la cookie se VENCE SOLA en
    # el servidor, pase lo que pase en el navegador.
    #
    # Le doy 1 minuto de colchon sobre el contador visual, para que el JS llegue
    # a redirigir con su mensaje lindo ANTES de que el servidor corte en seco.
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=SESION_TIMEOUT_MIN + 1)

    # Renovar la cookie en cada request. Junto con el "heartbeat" del navegador
    # (ver base_admin.html / base_revendedora.html), mantiene sincronizado lo que
    # muestra la barrita con lo que realmente piensa el servidor.
    SESSION_REFRESH_EACH_REQUEST = True

    # Endurecer la cookie de sesion (no cuesta nada y suma).
    SESSION_COOKIE_HTTPONLY = True     # el JS no puede leer la cookie (anti-XSS)
    SESSION_COOKIE_SAMESITE = 'Lax'    # no viaja desde sitios de terceros

    # ------------------------------------------------------------------
    # v0.21.0 · PISO DE GANANCIA DE LA CASA (base del modulo de comisiones, E2)
    # ------------------------------------------------------------------
    # La comision de la revendedora sale DE ADENTRO del margen, no se suma
    # encima. Entonces, con el piso blindado del 10% y una revendedora en el
    # escalon del 4%:
    #
    #       margen de la venta (10%)  -  comision (4%)  =  6% para la casa
    #
    # Este numero es LO MINIMO que le tiene que quedar a la casa (Ivan + Juliana)
    # DESPUES de pagar la comision. El backend NUNCA va a dejar confirmar una
    # venta que deje a la casa por debajo de este piso.
    #
    # Regla que se hace cumplir en el servidor:
    #       margen_de_la_venta  -  comision_del_escalon  >=  MARGEN_CASA_MINIMO
    #
    # (Todavia no lo usa nadie: queda definido aca para que E2 lo tome de una.)
    MARGEN_CASA_MINIMO = 6.0

    # ------------------------------------------------------------------
    # v0.18.2 · Redes del NEGOCIO (para el "Seguinos en" de la tienda)
    # ------------------------------------------------------------------
    # Completa solo las que tengas; las vacias no se muestran.
    # Pega el link completo (https://...).
    REDES = {
        'instagram': '',
        'facebook': '',
        'youtube': '',
        'tiktok': '',
        'linkedin': '',
        'whatsapp_canal': '',   # link del canal de WhatsApp (boton "Sumate al canal")
    }

    # Base de datos (SQLite en instance/)
    SQLALCHEMY_DATABASE_URI = 'sqlite:///' + os.path.join(basedir, 'instance', 'saludables.db')


class DevConfig(Config):
    DEBUG = True


class ProdConfig(Config):
    DEBUG = False


config = {
    'dev': DevConfig,
    'prod': ProdConfig,
    'default': DevConfig,
}
