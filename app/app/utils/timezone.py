"""
app/utils/timezone.py — Manejo de hora Argentina (regla AXIAL).
- Para GUARDAR datos nuevos: ahora_argentina().replace(tzinfo=None)
- Para MOSTRAR: filtro Jinja |ar_datetime  o  formatear_argentina()
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ARGENTINA_TZ = ZoneInfo('America/Argentina/Buenos_Aires')


def ahora_argentina():
    """Devuelve el datetime actual en hora Argentina (con tzinfo)."""
    return datetime.now(ARGENTINA_TZ)


def a_argentina(dt):
    """Convierte un datetime (naive=asume UTC, o aware) a hora Argentina."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ARGENTINA_TZ)


def formatear_argentina(dt, formato='%d/%m/%Y %H:%M'):
    if dt is None:
        return '—'
    return a_argentina(dt).strftime(formato)


def registrar_filtros_jinja(app):
    @app.template_filter('ar_datetime')
    def _ar_datetime(dt, formato='%d/%m/%Y %H:%M'):
        return formatear_argentina(dt, formato)

    @app.template_filter('ar_fecha')
    def _ar_fecha(dt, formato='%d/%m/%Y'):
        return formatear_argentina(dt, formato)
