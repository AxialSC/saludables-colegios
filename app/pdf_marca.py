"""
app/pdf_marca.py — Identidad visual COMPARTIDA de los PDF que ve el cliente.
AXIAL SECURITY · Ivan Abrigo · v0.38.0

POR QUE EXISTE ESTE ARCHIVO
---------------------------
El comprobante de pedido y el presupuesto son dos documentos distintos, pero
son LA MISMA MARCA. Antes cada uno definia sus colores por su cuenta y se
usaba la paleta "El Arquitecto" (carbon + bronce), que es la del PANEL DE
JULIANA. Perfecta ahi adentro, fuera de lugar en un papel que recibe el
cliente: Saludables vende alimentos, no es un estudio de arquitectura.

Ahora los dos toman de aca los colores, el logo y la marca de agua. Si manana
cambia un color de la marca, se toca UNA linea y cambian los dos documentos.

LOS ASSETS SALEN DEL REPO
-------------------------
Se leen de app/static/img/marca/. Si por lo que sea un archivo no esta, el PDF
NO se rompe: cae con elegancia al nombre del negocio en texto. Un comprobante
tiene que salir SIEMPRE, aunque falte una imagen.
"""
import os
from io import BytesIO

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import Image

# ----------------------------------------------------------------------
#  PALETA DE LA TIENDA (la misma de tienda.css)
# ----------------------------------------------------------------------
VERDE = colors.HexColor('#235339')        # verde del logo
VERDE_INT = colors.HexColor('#2F6F4E')    # verde de interfaz
VERDE_SOFT = colors.HexColor('#EDF4EF')   # fondo suave para cajas
VERDE_LINEA = colors.HexColor('#CFE0D6')
AMARILLO = colors.HexColor('#FDDA48')     # SOLO acento
TEXTO = colors.HexColor('#1F1F1D')
GRIS = colors.HexColor('#7A7A72')
LINEA = colors.HexColor('#E3E3DD')
BLANCO = colors.white

# Opacidad de la marca de agua. Muy baja A PROPOSITO: tiene que insinuarse,
# no competir con los precios. Si se sube de 0.10 empieza a molestar para leer
# y en impresion come tinta al pedo.
MARCA_AGUA_ALPHA = 0.07

_cache_agua = {}


def _ruta_asset(nombre):
    """Ruta a un archivo de app/static/img/marca/, o None si no existe."""
    try:
        p = os.path.join(current_app.static_folder, 'img', 'marca', nombre)
        return p if os.path.exists(p) else None
    except Exception:
        return None


def logo(alto_mm=13, blanco=False):
    """
    El logo de la marca como elemento para el PDF.
    'blanco=True' devuelve la version para fondo oscuro (la franja verde).
    Devuelve None si el archivo no esta (el que llama pone texto).
    """
    nombre = 'logo-blanco.png' if blanco else 'logo.png'
    ruta = _ruta_asset(nombre)
    if not ruta:
        return None
    try:
        lector = ImageReader(ruta)
        ancho_px, alto_px = lector.getSize()
        alto = alto_mm * mm
        ancho = alto * (ancho_px / float(alto_px))
        return Image(ruta, width=ancho, height=alto)
    except Exception:
        return None


def _isotipo_tenue():
    """
    El isotipo con la opacidad bajada, listo para usar de marca de agua.

    Se hace con Pillow porque ReportLab no sabe atenuar una imagen: se le baja
    el canal alpha y se le pasa el PNG resultante. Se cachea en memoria: es la
    misma imagen para todos los PDF, no tiene sentido recalcularla cada vez.
    """
    if 'img' in _cache_agua:
        return _cache_agua['img']
    _cache_agua['img'] = None
    ruta = _ruta_asset('isotipo.png')
    if not ruta:
        return None
    try:
        from PIL import Image as PILImage
        img = PILImage.open(ruta).convert('RGBA')
        alpha = img.split()[3].point(lambda p: int(p * MARCA_AGUA_ALPHA))
        img.putalpha(alpha)
        buf = BytesIO()
        img.save(buf, 'PNG')
        buf.seek(0)
        _cache_agua['img'] = ImageReader(buf)
    except Exception:
        _cache_agua['img'] = None
    return _cache_agua['img']


def marca_agua(canvas, doc):
    """
    Dibuja el isotipo tenue, centrado, DETRAS del contenido.

    Se pasa como onFirstPage/onLaterPages al construir el documento, asi que
    sale en todas las hojas. Envuelto en try: si falla, el PDF sale igual sin
    marca de agua (nunca se pierde un comprobante por un tema decorativo).
    """
    try:
        iso = _isotipo_tenue()
        if iso is None:
            return
        ancho_px, alto_px = iso.getSize()
        ancho = 110 * mm
        alto = ancho * (alto_px / float(ancho_px))
        x = (doc.pagesize[0] - ancho) / 2.0
        y = (doc.pagesize[1] - alto) / 2.0
        canvas.saveState()
        canvas.drawImage(iso, x, y, width=ancho, height=alto, mask='auto')
        canvas.restoreState()
    except Exception:
        pass


def pesos(v):
    """Formato argentino: $1.234,56"""
    s = f'{float(v or 0):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return '$' + s


def estilos():
    """Los estilos de texto que comparten los dos documentos."""
    base = getSampleStyleSheet()
    return {
        'marca': ParagraphStyle('marca', parent=base['Normal'],
                                fontName='Helvetica-Bold', fontSize=19,
                                textColor=BLANCO, leading=22),
        'marca_sub': ParagraphStyle('marca_sub', parent=base['Normal'],
                                    fontSize=8, textColor=colors.HexColor('#C9DED2'),
                                    leading=11),
        'normal': ParagraphStyle('n', parent=base['Normal'], fontSize=9,
                                 leading=13, textColor=TEXTO),
        'chico': ParagraphStyle('c', parent=base['Normal'], fontSize=7.5,
                                textColor=GRIS, leading=11),
        'titulo': ParagraphStyle('t', parent=base['Normal'],
                                 fontName='Helvetica-Bold', fontSize=12,
                                 textColor=VERDE, spaceBefore=4, spaceAfter=6),
        'intro': ParagraphStyle('i', parent=base['Normal'], fontSize=9.5,
                                leading=14, textColor=TEXTO),
    }


def cabecera(ajustes, bajada='Catálogo Mayorista · Pilar, Zona Norte', extra=None):
    """
    La franja verde de arriba con el logo. Es lo primero que ve el cliente y lo
    que hace que el papel se reconozca como de Saludables de un vistazo.
    'extra' es una linea opcional (ej: "Tu vendedora: Nadia").
    """
    from reportlab.platypus import Table, TableStyle, Paragraph
    st = estilos()

    izq = logo(alto_mm=13, blanco=True)
    if izq is None:
        izq = Paragraph(ajustes.nombre_negocio, st['marca'])

    texto = bajada if not extra else f'{bajada}<br/>{extra}'
    t = Table([[izq, Paragraph(texto, st['marca_sub'])]],
              colWidths=[75 * mm, 95 * mm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), VERDE),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 11),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 11),
    ]))
    return t


def estilo_tabla_items(col_center=None, col_right=None):
    """
    El estilo de la tabla de productos, igual en los dos documentos:
    encabezado VERDE con letra blanca y filas alternadas en verde clarito
    (con 15 renglones, el ojo se pierde si son todas iguales).
    """
    from reportlab.platypus import TableStyle
    reglas = [
        ('BACKGROUND', (0, 0), (-1, 0), VERDE),
        ('TEXTCOLOR', (0, 0), (-1, 0), BLANCO),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('TEXTCOLOR', (0, 1), (-1, -1), TEXTO),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [BLANCO, VERDE_SOFT]),
        ('LINEBELOW', (0, 1), (-1, -1), 0.4, VERDE_LINEA),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]
    if col_center is not None:
        reglas.append(('ALIGN', (col_center, 0), (col_center, -1), 'CENTER'))
    if col_right is not None:
        reglas.append(('ALIGN', (col_right, 0), (-1, -1), 'RIGHT'))
    return TableStyle(reglas)


def caja_datos(contenido_cols, anchos):
    """Caja verde suave para los datos del cliente."""
    from reportlab.platypus import Table, TableStyle
    t = Table([contenido_cols], colWidths=anchos)
    t.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), VERDE_SOFT),
        ('BOX', (0, 0), (-1, -1), 0.6, VERDE_LINEA),
        ('LEFTPADDING', (0, 0), (-1, -1), 9),
        ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
    ]))
    return t


def pie(elems, leyenda_texto):
    """El cierre igual para los dos documentos (sin datos internos)."""
    from reportlab.platypus import Paragraph, Spacer
    st = estilos()
    elems.append(Spacer(1, 7 * mm))
    elems.append(Paragraph(leyenda_texto, st['chico']))
    elems.append(Spacer(1, 3 * mm))
    elems.append(Paragraph('AXIAL SECURITY · Desarrollo a medida', st['chico']))
    return elems
