"""
app/pdf_pedido.py — Comprobante de pedido en PDF (ReportLab).
NO es factura: es un comprobante de pedido sujeto a confirmacion de stock.
"""
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle)

from .utils.timezone import a_argentina
from .utils.validaciones import formatear_cuit

CARBON = colors.HexColor('#1A1A1A')
BRONCE = colors.HexColor('#8B6F47')
CREMA = colors.HexColor('#F4F1EC')
GRIS = colors.HexColor('#888888')
LINEA = colors.HexColor('#E0DAD0')


def _pesos(v):
    s = f'{float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return '$' + s


def generar_pdf_pedido(pedido, ajustes):
    """Devuelve los bytes del PDF para el pedido dado."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f'Pedido {pedido.numero}')
    styles = getSampleStyleSheet()
    h_marca = ParagraphStyle('marca', parent=styles['Normal'], fontName='Times-Bold',
                             fontSize=20, textColor=BRONCE, spaceAfter=2, leading=22)
    h_sub = ParagraphStyle('sub', parent=styles['Normal'], fontSize=8, textColor=GRIS,
                           spaceAfter=2)
    normal = ParagraphStyle('n', parent=styles['Normal'], fontSize=9, leading=13)
    chico = ParagraphStyle('c', parent=styles['Normal'], fontSize=7.5, textColor=GRIS,
                           leading=11)
    titulo = ParagraphStyle('t', parent=styles['Normal'], fontName='Helvetica-Bold',
                            fontSize=11, textColor=CARBON, spaceBefore=6, spaceAfter=6)

    elems = []

    # Encabezado
    elems.append(Paragraph(ajustes.nombre_negocio, h_marca))
    elems.append(Paragraph('Catálogo Mayorista · Pilar, Zona Norte', h_sub))
    elems.append(Spacer(1, 6 * mm))

    # Datos del pedido
    fecha = a_argentina(pedido.creado).strftime('%d/%m/%Y %H:%M') if pedido.creado else '—'
    cab = [
        [Paragraph('<b>COMPROBANTE DE PEDIDO</b>', titulo),
         Paragraph(f'<b>N° {pedido.numero}</b><br/>{fecha} hs', normal)],
    ]
    t_cab = Table(cab, colWidths=[100 * mm, 70 * mm])
    t_cab.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), 1, BRONCE),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elems.append(t_cab)
    elems.append(Spacer(1, 5 * mm))

    # Cliente
    datos = (f'<b>Cliente:</b> {pedido.cliente_completo}<br/>'
             f'<b>CUIT:</b> {formatear_cuit(pedido.cuit)}<br/>'
             f'<b>WhatsApp:</b> {pedido.whatsapp}')
    if pedido.email:
        datos += f'<br/><b>Email:</b> {pedido.email}'
    entrega = (f'<b>Dirección:</b> {pedido.direccion}<br/>'
               f'<b>Zona / Colegio:</b> {pedido.zona}')
    if pedido.observaciones:
        entrega += f'<br/><b>Observaciones:</b> {pedido.observaciones}'

    t_datos = Table([[Paragraph(datos, normal), Paragraph(entrega, normal)]],
                    colWidths=[85 * mm, 85 * mm])
    t_datos.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BACKGROUND', (0, 0), (-1, -1), CREMA),
        ('BOX', (0, 0), (-1, -1), 0.5, LINEA),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elems.append(t_datos)
    elems.append(Spacer(1, 6 * mm))

    # Tabla de items
    data = [['Código', 'Producto', 'Cant.', 'P. Unit.', 'Subtotal']]
    for it in pedido.items:
        data.append([
            it.codigo,
            Paragraph(it.nombre, chico),
            str(it.cantidad),
            _pesos(it.precio_unitario),
            _pesos(it.subtotal),
        ])
    t_items = Table(data, colWidths=[20 * mm, 86 * mm, 14 * mm, 25 * mm, 25 * mm], repeatRows=1)
    t_items.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), CARBON),
        ('TEXTCOLOR', (0, 0), (-1, 0), CREMA),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (2, 0), (2, -1), 'CENTER'),
        ('ALIGN', (3, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FAF8F4')]),
        ('LINEBELOW', (0, 1), (-1, -1), 0.4, LINEA),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elems.append(t_items)
    elems.append(Spacer(1, 4 * mm))

    # Total
    t_total = Table([['TOTAL DEL PEDIDO', _pesos(pedido.total)]],
                    colWidths=[120 * mm, 50 * mm])
    t_total.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'RIGHT'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 12),
        ('TEXTCOLOR', (1, 0), (1, 0), BRONCE),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
    ]))
    elems.append(t_total)
    elems.append(Spacer(1, 8 * mm))

    # Leyenda (pedido de Ivan)
    leyenda = ('Todos los pedidos se verifican según nuestro stock para mantener un nivel '
               'de calidad y buenas prácticas de venta. Este comprobante es un pedido sujeto '
               'a confirmación; <b>no es una factura</b>. Juliana se va a contactar para '
               'coordinar la entrega y el pago.')
    elems.append(Paragraph(leyenda, chico))
    elems.append(Spacer(1, 6 * mm))
    elems.append(Paragraph('AXIAL SECURITY · Desarrollo a medida', chico))

    doc.build(elems)
    buf.seek(0)
    return buf.getvalue()
