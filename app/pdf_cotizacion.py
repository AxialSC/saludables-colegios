"""
app/pdf_cotizacion.py — Presupuesto de Cumpleaños / Comercio en PDF (ReportLab).
Es una PROPUESTA comercial (no es factura). Pensada para invitar a comprar:
calida, prolija, con un total bien claro y un cierre con el WhatsApp.

v0.38.0 · REDISEÑO CON LA IDENTIDAD DE LA TIENDA (misma tanda que el
comprobante de pedido). Los colores, el logo y la marca de agua salen de
pdf_marca.py: los dos documentos son la misma marca y se mantienen en un solo
lugar. Antes usaba la paleta del panel (carbon + bronce + Times).
"""
from io import BytesIO
from datetime import timedelta

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle)

from .utils.timezone import a_argentina
from .models import TipoCotizacion
from . import pdf_marca as M


def _pesos(v):
    return M.pesos(v)


def generar_pdf_cotizacion(coti, ajustes):
    """Devuelve los bytes del PDF de la cotización (Cumpleaños o Comercio)."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=15 * mm, bottomMargin=16 * mm,
                            title=f'Presupuesto {coti.numero}')
    st = M.estilos()
    es_cumple = (coti.tipo == TipoCotizacion.CUMPLE)
    elems = []

    # ---------- Franja de marca ----------
    # v0.27.0 · Si el presupuesto lo armo una revendedora, la firma es de ELLA:
    # el cliente le compra a Nadia, no al negocio.
    rev = getattr(coti, 'revendedora', None)
    extra = f'Tu vendedora: <b>{rev.nombre_completo}</b>' if rev is not None else None
    elems.append(M.cabecera(ajustes, extra=extra))
    elems.append(Spacer(1, 6 * mm))

    # ---------- Numero, fecha y validez ----------
    fecha = a_argentina(coti.creada_en).strftime('%d/%m/%Y') if coti.creada_en else '—'
    validez = ''
    if coti.creada_en:
        vto = a_argentina(coti.creada_en) + timedelta(days=7)
        validez = (f'<br/><font size="7" color="#7A7A72">Válido hasta el '
                   f'{vto.strftime("%d/%m/%Y")} (7 días)</font>')
    tit_txt = 'PRESUPUESTO · BOLSAS DE CUMPLEAÑOS' if es_cumple else 'PRESUPUESTO · COMERCIO'
    cab = [[Paragraph(f'<b>{tit_txt}</b>', st['titulo']),
            Paragraph(f'<b>N° {coti.numero}</b><br/>{fecha}{validez}', st['normal'])]]
    t_cab = Table(cab, colWidths=[100 * mm, 70 * mm])
    t_cab.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), 1.2, M.VERDE),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    elems.append(t_cab)
    elems.append(Spacer(1, 5 * mm))

    # ---------- Cliente ----------
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
        elems.append(M.caja_datos(
            [Paragraph('<br/>'.join(partes), st['normal'])], [170 * mm]))
        elems.append(Spacer(1, 5 * mm))

    # ---------- Intro calida ----------
    if es_cumple:
        elems.append(Paragraph(
            '¡Gracias por pensar en nosotros para tu festejo! Te preparamos esta '
            'propuesta de bolsas para que tu cumpleaños sea un éxito.', st['intro']))
    else:
        elems.append(Paragraph(
            'Le acercamos nuestra propuesta de productos. Quedamos a disposición '
            'para coordinar la entrega y el pago.', st['intro']))
    elems.append(Spacer(1, 4 * mm))

    # ---------- Items ----------
    elems.append(Paragraph('<b>Cada bolsa incluye:</b>' if es_cumple else '<b>Detalle:</b>',
                           st['titulo']))
    data = [['Cant.', 'Producto', 'P. Unit.', 'Subtotal']]
    for it in coti.items:
        data.append([str(it.cantidad), Paragraph(it.nombre, st['chico']),
                     _pesos(it.precio_unitario), _pesos(it.subtotal)])
    t_items = Table(data, colWidths=[16 * mm, 100 * mm, 27 * mm, 27 * mm], repeatRows=1)
    t_items.setStyle(M.estilo_tabla_items(col_center=0, col_right=2))
    elems.append(t_items)
    elems.append(Spacer(1, 5 * mm))

    # ---------- Resumen / total ----------
    resumen = []
    if es_cumple:
        resumen.append(['Productos por bolsa', _pesos(coti.subtotal_productos)])
        if coti.incluye_bolsa and float(coti.costo_bolsa) > 0:
            resumen.append(['Bolsa (por unidad)', _pesos(coti.costo_bolsa)])
        resumen.append(['Cantidad de bolsas', f'x {coti.unidades}'])
    resumen.append(['TOTAL', _pesos(coti.total)])
    t_res = Table(resumen, colWidths=[120 * mm, 50 * mm])
    t_res.setStyle(TableStyle([
        ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TEXTCOLOR', (0, 0), (-1, -1), M.GRIS),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE', (0, -1), (-1, -1), 14),
        ('TEXTCOLOR', (0, -1), (-1, -1), M.VERDE),
        ('LINEABOVE', (0, -1), (-1, -1), 1.2, M.VERDE),
        ('TOPPADDING', (0, -1), (-1, -1), 9),
    ]))
    elems.append(t_res)
    elems.append(Spacer(1, 7 * mm))

    # ---------- Cierre con CTA ----------
    # v0.27.0 · Si es de una revendedora, el contacto es EL DE ELLA.
    if rev is not None and (rev.telefono or '').strip():
        cierre = (f'Para confirmar tu pedido, escribile a <b>{rev.nombre_completo}</b> '
                  f'por WhatsApp al <b>{rev.telefono}</b>. ¡Te esperamos!')
    else:
        cierre = (f'Para confirmar tu pedido, escribinos por WhatsApp al '
                  f'<b>{ajustes.whatsapp}</b>. ¡Te esperamos!')
    t_cta = Table([[Paragraph(cierre, st['normal'])]], colWidths=[170 * mm])
    t_cta.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), M.VERDE_SOFT),
        ('BOX', (0, 0), (-1, -1), 0.8, M.VERDE),
        ('LINEBEFORE', (0, 0), (0, -1), 4, M.AMARILLO),   # acento de marca
        ('LEFTPADDING', (0, 0), (-1, -1), 12),
        ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ('TOPPADDING', (0, 0), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
    ]))
    elems.append(t_cta)

    # ---------- Pie ----------
    leyenda = ('Este presupuesto es una propuesta sujeta a confirmación de stock; '
               'no es una factura. Los precios pueden ajustarse pasada la fecha de validez.')
    M.pie(elems, leyenda)

    doc.build(elems, onFirstPage=M.marca_agua, onLaterPages=M.marca_agua)
    buf.seek(0)
    return buf.getvalue()
