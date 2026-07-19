"""
app/pdf_pedido.py — Comprobante de pedido en PDF (ReportLab).
NO es factura: es un comprobante de pedido sujeto a confirmacion de stock.

v0.38.0 · REDISEÑO CON LA IDENTIDAD DE LA TIENDA.
Antes usaba la paleta "El Arquitecto" (carbon + bronce + Times), que es la del
PANEL de Juliana. Este papel lo recibe el CLIENTE: tiene que verse como la
tienda (verde de marca), no como una herramienta interna. Los colores, el logo
y la marca de agua salen de pdf_marca.py, compartido con el presupuesto.

Cambios de esta version:
  · Franja verde con el logo real arriba.
  · Marca de agua con el isotipo, muy tenue.
  · Tabla de productos con encabezado verde y filas alternadas.
  · Se saco la IP y el dispositivo (dato interno; Ivan lo sigue viendo en el
    panel, pero no tiene por que estar en el papel del cliente).
  · Se muestra el COSTO DE PLATAFORMA cuando el pedido se pago con Mercado
    Pago. Antes el PDF decia un total y el cliente habia pagado otro.
"""
from io import BytesIO

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle)

from .utils.timezone import a_argentina
from .utils.validaciones import formatear_cuit
from . import pdf_marca as M


def _pesos(v):
    return M.pesos(v)


def generar_pdf_pedido(pedido, ajustes):
    """Devuelve los bytes del PDF para el pedido dado."""
    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=15 * mm, bottomMargin=16 * mm,
                            title=f'Pedido {pedido.numero}')
    st = M.estilos()
    elems = []

    # ---------- Franja de marca ----------
    elems.append(M.cabecera(ajustes))
    elems.append(Spacer(1, 6 * mm))

    # ---------- Numero y fecha ----------
    fecha = a_argentina(pedido.creado).strftime('%d/%m/%Y %H:%M') if pedido.creado else '—'
    extra = ''
    if pedido.modificado_en:
        extra = (f'<br/><font size="7" color="#2F6F4E">Modificado el '
                 f'{a_argentina(pedido.modificado_en).strftime("%d/%m/%Y %H:%M")} hs</font>')
    cab = [[Paragraph('<b>COMPROBANTE DE PEDIDO</b>', st['titulo']),
            Paragraph(f'<b>N° {pedido.numero}</b><br/>{fecha} hs{extra}', st['normal'])]]
    t_cab = Table(cab, colWidths=[100 * mm, 70 * mm])
    t_cab.setStyle(TableStyle([
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('LINEBELOW', (0, 0), (-1, -1), 1.2, M.VERDE),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    elems.append(t_cab)
    elems.append(Spacer(1, 5 * mm))

    # ---------- Datos del cliente ----------
    datos = (f'<b>Cliente:</b> {pedido.cliente_completo}<br/>'
             f'<b>CUIT:</b> {formatear_cuit(pedido.cuit)}<br/>'
             f'<b>WhatsApp:</b> {pedido.whatsapp}')
    if pedido.email:
        datos += f'<br/><b>Email:</b> {pedido.email}'
    entrega = (f'<b>Dirección:</b> {pedido.direccion}<br/>'
               f'<b>Zona / Colegio:</b> {pedido.zona}')
    if pedido.observaciones:
        entrega += f'<br/><b>Observaciones:</b> {pedido.observaciones}'
    elems.append(M.caja_datos(
        [Paragraph(datos, st['normal']), Paragraph(entrega, st['normal'])],
        [85 * mm, 85 * mm]))
    elems.append(Spacer(1, 6 * mm))

    # ---------- Productos ----------
    data = [['Código', 'Producto', 'Cant.', 'P. Unit.', 'Subtotal']]
    for it in pedido.items:
        data.append([it.codigo, Paragraph(it.nombre, st['chico']), str(it.cantidad),
                     _pesos(it.precio_unitario), _pesos(it.subtotal)])
    t_items = Table(data, colWidths=[20 * mm, 86 * mm, 14 * mm, 25 * mm, 25 * mm],
                    repeatRows=1)
    t_items.setStyle(M.estilo_tabla_items(col_center=2, col_right=3))
    elems.append(t_items)
    elems.append(Spacer(1, 5 * mm))

    # ---------- Totales ----------
    # v0.37.0 · Si el cliente pago con Mercado Pago, se le sumo el costo de la
    # pasarela. El comprobante TIENE que mostrarlo desglosado: si no, el papel
    # dice un numero y en el resumen de la tarjeta le figura otro.
    extra_pago = float(getattr(pedido, 'costo_plataforma', 0) or 0)
    if extra_pago > 0:
        filas = [
            ['Subtotal productos', _pesos(pedido.total)],
            ['Costo de plataforma de pago', _pesos(extra_pago)],
            ['TOTAL PAGADO', _pesos(pedido.total_a_pagar)],
        ]
        t_tot = Table(filas, colWidths=[120 * mm, 50 * mm])
        t_tot.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('FONTSIZE', (0, 0), (-1, -2), 9),
            ('TEXTCOLOR', (0, 0), (-1, -2), M.GRIS),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, -1), (-1, -1), 12),
            ('TEXTCOLOR', (0, -1), (-1, -1), M.VERDE),
            ('LINEABOVE', (0, -1), (-1, -1), 1, M.VERDE),
            ('TOPPADDING', (0, -1), (-1, -1), 8),
        ]))
        elems.append(t_tot)
    else:
        t_tot = Table([['TOTAL DEL PEDIDO', _pesos(pedido.total)]],
                      colWidths=[110 * mm, 60 * mm])
        t_tot.setStyle(TableStyle([
            ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ('BACKGROUND', (0, 0), (-1, -1), M.VERDE_SOFT),
            ('BOX', (0, 0), (-1, -1), 1, M.VERDE),
            ('FONTNAME', (0, 0), (-1, -1), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (0, 0), 11),
            ('FONTSIZE', (1, 0), (1, 0), 15),
            ('TEXTCOLOR', (0, 0), (-1, -1), M.VERDE),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 12),
        ]))
        elems.append(t_tot)

    # ---------- Cierre ----------
    # OJO: aca NO va el dispositivo ni la IP. Son datos internos de seguridad;
    # Ivan los sigue viendo en el panel, pero al cliente no le suman nada y en
    # un comprobante comercial quedan fuera de lugar.
    leyenda = ('Todos los pedidos se verifican según nuestro stock para mantener un nivel '
               'de calidad y buenas prácticas de venta. Este comprobante es un pedido sujeto '
               'a confirmación; <b>no es una factura</b>. Juliana se va a contactar para '
               'coordinar la entrega y el pago.')
    M.pie(elems, leyenda)

    doc.build(elems, onFirstPage=M.marca_agua, onLaterPages=M.marca_agua)
    buf.seek(0)
    return buf.getvalue()
