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
"""
import os

basedir = os.path.abspath(os.path.dirname(__file__))


class Config:
    # IMPORTANTE: en produccion poner una SECRET_KEY real via variable de entorno
    SECRET_KEY = os.environ.get('SECRET_KEY', 'axial-dev-cambiar-en-produccion')
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # --- Identidad / version ---
    APP_VERSION = '0.20.1'
    APP_NOMBRE = 'Saludables'
    APP_SUBTITULO = 'Catalogo Mayorista · Pilar'

    # URL publica del sistema (se usa en el mensaje de bienvenida por WhatsApp).
    # Si tu dominio es otro, cambialo aca.
    APP_URL = 'https://saludablespilar.pythonanywhere.com/'

    # --- v0.20.1: SESION (auto-logout por inactividad) ---
    # Minutos de inactividad antes de cerrar la sesion sola. CUALQUIER movimiento
    # del mouse o tecla reinicia el contador al maximo.
    # >>> Si 2 minutos te resulta molesto (ej: leer una lista larga sin tocar nada),
    #     cambia este numero y listo. No hay que tocar codigo ni migrar nada.
    SESION_TIMEOUT_MIN = 2
    # Segundos finales en los que la barra se pone roja y late (aviso visual).
    SESION_AVISO_SEG = 30

    # --- v0.18.2: Redes del NEGOCIO (para el "Seguinos en" de la tienda) ---
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
