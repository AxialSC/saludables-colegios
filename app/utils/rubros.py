"""
app/utils/rubros.py — Limpieza y unificacion de rubros (FUENTE UNICA).

Lo usan dos lugares:
  - app/utils/import_planilla.py  -> para que TODO Excel que importes entre limpio.
  - app/cli.py (comando normalizar-rubros) -> para limpiar lo que ya esta cargado.

Si el mes que viene aparece otra palabra basura en la planilla del mayorista,
se agrega ACA (un solo lugar) y queda arreglado en la importacion Y en el
comando de mantenimiento al mismo tiempo. No hay logica duplicada.
"""
import re

# Palabras que NO son un rubro real (proveedor / lista del mayorista que se
# colo en la planilla). Se sacan del texto del rubro. Agregar mas si aparecen.
PALABRAS_BASURA_RUBRO = ['TEOLOGISTICA']

# Rubro por defecto cuando el producto viene sin rubro (o el rubro era todo basura).
RUBRO_VACIO = 'Sin Rubro'

# Conectores que van en minuscula en el medio de un rubro (look prolijo).
_CONECTORES = {'y', 'e', 'o', 'u', 'de', 'del', 'la', 'el', 'los', 'las',
               'con', 'sin', 'para', 'a', 'en'}


def _titulo_rubro(s):
    """'LIMPIEZA Y HOGAR' -> 'Limpieza y Hogar' (conectores en minuscula)."""
    palabras = s.split()
    salida = []
    for i, p in enumerate(palabras):
        bajo = p.lower()
        if i > 0 and bajo in _CONECTORES:
            salida.append(bajo)
        else:
            salida.append(p.capitalize())
    return ' '.join(salida)


def limpiar_rubro(s):
    """
    Limpia un rubro:
      1. Saca palabras basura (ej: 'TEOLOGISTICA').
      2. Recorta espacios y colapsa espacios dobles.
      3. Lo deja en formato Titulo prolijo ('BEBIDAS' -> 'Bebidas',
         'LIMPIEZA Y HOGAR' -> 'Limpieza y Hogar').
    Acepta texto, numero o None.
    Devuelve '' si despues de limpiar no queda nada (el que llama decide si en
    ese caso usa RUBRO_VACIO; para eso esta limpiar_rubro_o_default()).
    """
    texto = '' if s is None else str(s)
    for w in PALABRAS_BASURA_RUBRO:
        texto = re.sub(r'\b' + re.escape(w) + r'\b', ' ', texto, flags=re.IGNORECASE)
    texto = re.sub(r'\s+', ' ', texto).strip()
    if texto == '':
        return ''
    return _titulo_rubro(texto)


def limpiar_rubro_o_default(s):
    """Igual que limpiar_rubro pero NUNCA vacio: cae a RUBRO_VACIO ('Sin Rubro')."""
    return limpiar_rubro(s) or RUBRO_VACIO
