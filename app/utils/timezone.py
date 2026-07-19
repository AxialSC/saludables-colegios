"""
app/utils/timezone.py — Manejo de hora Argentina (regla AXIAL).
- Para GUARDAR datos nuevos: ahora_argentina().replace(tzinfo=None)
- Para MOSTRAR: filtro Jinja |ar_datetime  o  formatear_argentina()

=============================================================================
 v0.38.1 · FIX DE LA DOBLE CONVERSION (todo se veia 3 horas atrasado)
=============================================================================
EL BUG
------
a_argentina() asumia que un datetime SIN zona venia en UTC y le restaba 3 horas.
Pero en este sistema NADA se guarda en UTC: los 14 campos de fecha del modelo
usan _ahora(), que es justamente ahora_argentina().replace(tzinfo=None), o sea
HORA ARGENTINA sin la etiqueta de zona.

Resultado: se guardaba hora argentina y al mostrarla se le volvia a restar 3
horas. Un pedido hecho a las 02:34 del 19/07 aparecia como 23:34 del 18/07.
Y no era solo cosmetico: un pedido de la madrugada figuraba con fecha del dia
anterior, lo que ensucia cualquier corte por dia.

EL FIX
------
Un datetime naive se interpreta como lo que REALMENTE es en esta base: hora
Argentina. Se le pone la etiqueta de zona y listo, no se lo mueve.

SOBRE LOS DATOS VIEJOS
----------------------
No hay que migrar nada. Lo guardado SIEMPRE estuvo bien; lo que estaba mal era
la lectura. Con este cambio, todas las fechas historicas pasan a mostrarse
correctas solas.

SI ALGUN DIA SE GUARDA ALGO EN UTC
----------------------------------
Guardalo como datetime CON zona (aware). Esta funcion lo convierte bien, porque
solo asume Argentina cuando el dato viene sin zona. Pero la regla del proyecto
sigue siendo la de arriba: guardar con _ahora().
"""
from datetime import datetime
from zoneinfo import ZoneInfo

ARGENTINA_TZ = ZoneInfo('America/Argentina/Buenos_Aires')


def ahora_argentina():
    """Devuelve el datetime actual en hora Argentina (con tzinfo)."""
    return datetime.now(ARGENTINA_TZ)


def a_argentina(dt):
    """
    Devuelve el datetime en hora Argentina.

    · Si viene SIN zona (naive): se asume que YA es hora Argentina, porque es
      asi como guarda todo este sistema. Se le pone la etiqueta y NO se mueve
      la hora. (Antes se asumia UTC y de ahi salia el atraso de 3 horas.)
    · Si viene CON zona (aware): se convierte de verdad a hora Argentina.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ARGENTINA_TZ)
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
