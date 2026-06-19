"""
app/pdf_cotizacion.py — Presupuesto de Cumpleaños / Colegio en PDF (ReportLab).
Es una PROPUESTA comercial (no es factura). Pensada para invitar a comprar:
calida, prolija, con un total bien claro y un cierre con el WhatsApp del negocio.
v0.12 C2.
"""
from io import BytesIO
from datetime import timedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle)

from .utils.timezone import a_argentina
from .models import TipoCotizacion

CARBON = colors.HexColor('#1A1A1A')
BRONCE = colors.HexColor('#8B6F47')
CREMA = colors.HexColor('#F4F1EC')
VERDE = colors.HexColor('#2F6F4E')
VERDE_SOFT = colors.HexColor('#E9F2EC')
GRIS = colors.HexColor('#888888')
LINEA = colors.HexColor('#E0DAD0')


def _pesos(v):
    s = f'{float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return '$' + s


def generar_pdf_cotizacion(coti, ajustes):
    """Devuelve los bytes del PDF de la cotización (Cumpleaños o Colegio)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=18 * mm, bottomMargin=18 * mm,
                            title=f'Presupuesto {coti.numero}')
    styles = getSampleStyleSheet()
    h_marca = ParagraphStyle('marca', parent=styles['Normal'], fontName='Times-Bold',
                             fontSize=20, textColor=BRONCE, spaceAfter=2, leading=22)
    h_sub = ParagraphStyle('sub', parent=styles['Normal'], fontSize=8, textColor=GRIS,
                           spaceAfter=2)
    normal = ParagraphStyle('n', parent=styles['Normal'], fontSize=9, leading=13)
    chico = ParagraphStyle('c', parent=styles['Normal'], fontSize=7.5, textColor=GRIS,
                           leading=11)
    titulo = ParagraphStyle('t', parent=styles['Normal'], fontName='Helvetica-Bold',
                            fontSize=12, textColor=CARBON, spaceBefore=6, spaceAfter=6)
    intro = ParagraphStyle('i', parent=styles['Normal'], fontSize=9.5, leading=14,
                           textColor=CARBON)

    es_cumple = (coti.tipo == TipoCotizacion.CUMPLE)
    elems = []

    # Encabezado
    elems.append(Paragraph(ajustes.nombre_negocio, h_marca))
    elems.append(Paragraph('Catálogo Mayorista · Pilar, Zona Norte', h_sub))
    elems.append(Spacer(1, 6 * mm))

    # Cabecera del presupuesto + validez
    fecha = a_argentina(coti.creada_en).strftime('%d/%m/%Y') if coti.creada_en else '—'
    validez = ''
    if coti.creada_en:
        vto = a_argentina(coti.creada_en) + timedelta(days=7)
        validez = (f'<br/><font size="7" color="#888888">Válido hasta el '
                   f'{vto.strftime("%d/%m/%Y")} (7 días)</font>')
    tit_txt = 'PRESUPUESTO · BOLSAS DE CUMPLEAÑOS' if es_cumple else 'PRESUPUESTO · COLEGIO'
    cab = [[Paragraph(f'<b>{tit_txt}</b>', titulo),
            Paragraph(f'<b>N° {coti.numero}</b><br/>{fecha}{validez}', normal)]]
    t_cab = Table(cab, colWidths=[100 * mm, 70 * mm])
    t_cab.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), 1, BRONCE),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elems.append(t_cab)
    elems.append(Spacer(1, 5 * mm))

    # Cliente (si hay datos)
    if coti.nombre_cliente or coti.whatsapp or coti.email or coti.nota:
        partes = []
        if coti.nombre_cliente:
            partes.append(f'<b>Cliente:</b> {coti.nombre_cliente}')
        if coti.whatsapp:
            partes.append(f'<b>WhatsApp:</b> {coti.whatsapp}')
        if coti.email:
            partes.append(f'<b>Email:</b> {coti.email}')
        if coti.nota:
            partes.append(f'<b>Nota:</b> {coti.nota}')
        t_cli = Table([[Paragraph('<br/>'.join(partes), normal)]], colWidths=[170 * mm])
        t_cli.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), CREMA),
            ('BOX', (0, 0), (-1, -1), 0.5, LINEA),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
            ('RIGHTPADDING', (0, 0), (-1, -1), 8),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ]))
        elems.append(t_cli)
        elems.append(Spacer(1, 5 * mm))

    # Intro calida
    if es_cumple:
        elems.append(Paragraph(
            '¡Gracias por pensar en nosotros para tu festejo! Te preparamos esta '
            'propuesta de bolsas para que tu cumpleaños sea un éxito.', intro))
    else:
        elems.append(Paragraph(
            'Le acercamos nuestra propuesta de productos. Quedamos a disposición '
            'para coordinar la entrega y el pago.', intro))
    elems.append(Spacer(1, 4 * mm))

    # Items
    elems.append(Paragraph('<b>Cada bolsa incluye:</b>' if es_cumple else '<b>Detalle:</b>',
                           titulo))
    data = [['Cant.', 'Producto', 'P. Unit.', 'Subtotal']]
    for it in coti.items:
        data.append([str(it.cantidad), Paragraph(it.nombre, chico),
                     _pesos(it.precio_unitario), _pesos(it.subtotal)])
    t_items = Table(data, colWidths=[16 * mm, 100 * mm, 27 * mm, 27 * mm], repeatRows=1)
    t_items.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), CARBON),
        ('TEXTCOLOR', (0, 0), (-1, 0), CREMA),
        ('FONTSIZE', (0, 0), (-1, 0), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 1), (-1, -1), 8),
        ('ALIGN', (0, 0), (0, -1), 'CENTER'),
        ('ALIGN', (2, 0), (-1, -1), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#FAF8F4')]),
        ('LINEBELOW', (0, 1), (-1, -1), 0.4, LINEA),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING', (0, 0), (-1, -1), 6),
    ]))
    elems.append(t_items)
    elems.append(Spacer(1, 4 * mm))

    # Resumen / total
    resumen = []
    if es_cumple:
        resumen.append(['Productos por bolsa', _pesos(coti.subtotal_productos)])
        if coti.incluye_bolsa and float(coti.costo_bolsa) > 0:
            resumen.append(['Bolsa (por unidad)', _pesos(coti.costo_bolsa)])
        resumen.append(['Cantidad de bolsas', f'x {coti.unidades}'])
    resumen.append(['TOTAL', _pesos(coti.total)])
    t_res = Table(resumen, colWidths=[120 * mm, 50 * mm])
    t_res.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, -1), 'RIGHT'),
        ('ALIGN', (1, 0), (1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 13),
        ('TEXTCOLOR', (1, -1), (1, -1), BRONCE),
        ('LINEABOVE', (0, -1), (-1, -1), 1, BRONCE),
        ('TOPPADDING', (0, -1), (-1, -1), 8),
    ]))
    elems.append(t_res)
    elems.append(Spacer(1, 8 * mm))

    # Cierre con CTA (WhatsApp)
    cierre = (f'Para confirmar tu pedido, escribinos por WhatsApp al '
              f'<b>{ajustes.whatsapp}</b>. ¡Te esperamos!')
    t_cta = Table([[Paragraph(cierre, normal)]], colWidths=[170 * mm])
    t_cta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), VERDE_SOFT),
        ('BOX', (0, 0), (-1, -1), 0.5, VERDE),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('RIGHTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 9),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 9),
    ]))
    elems.append(t_cta)
    elems.append(Spacer(1, 6 * mm))

    # Leyenda legal
    leyenda = ('Este presupuesto es una propuesta sujeta a confirmación de stock; '
               'no es una factura. Los precios pueden ajustarse pasada la fecha de validez.')
    elems.append(Paragraph(leyenda, chico))
    elems.append(Spacer(1, 2 * mm))
    elems.append(Paragraph('AXIAL SECURITY · Desarrollo a medida', chico))

    doc.build(elems)
    buf.seek(0)
    return buf.getvalue()
