"""
app/food_cost_parser.py — Lector de facturas PDF de Distribuidora Torres (v0.19.1).

Formato esperado (factura estandar de Torres, "S.TORRES Y CIA S.A."):
  Encabezado con Numero / Fecha / Subtotal / IVA 21 / Reg. Especiales / TOTAL.
  Tabla de renglones: Codigo  Unidades  Descripcion  Sugerido  Unit.  Importe  Imp.Int.

Probado contra la factura real A00012-00553289 (12/13 renglones OK, la linea de
"Percepcion IIBB" queda aparte en 'no_reconocidas' porque no es un producto).

Si Torres cambia el formato de la factura en el futuro, este parser puede dejar
de funcionar correctamente -> avisar a Ivan para recalibrarlo con la factura
nueva real (nunca asumir que el formato viejo sigue sirviendo sin revisar).
"""
import re

# Renglon de producto: codigo, unidades, descripcion, y 4 montos con "$ "
ROW_RE = re.compile(
    r'^(\d+)\s+([\d.,]+)\s+(.+?)\s+\$\s*([\d.,]+)\s+\$\s*([\d.,]+)\s+\$\s*([\d.,]+)\s+\$\s*([\d.,]+)$'
)

# Palabras que marcan el FIN de la tabla de renglones (empieza el pie de la factura)
_FOOTER_KEYWORDS = ('UNIDADES:', 'IMPORTE:', 'Forma de Pago', 'Subtotal', 'Imp. Internos',
                     'Reg. Especiales', 'GuiaID', 'IVA 21', 'CAE', 'Powered by', 'TOTAL:')


def _parse_monto(s):
    """Convierte '74.215,62' (formato AR: punto de miles, coma decimal) a float 74215.62"""
    s = (s or '').strip().replace('.', '').replace(',', '.')
    try:
        return float(s)
    except ValueError:
        return 0.0


def _buscar(patron, texto, grupo=1, default=None):
    m = re.search(patron, texto)
    return m.group(grupo) if m else default


def parsear_factura_pdf(ruta_pdf):
    """
    Lee un PDF de factura de Torres y devuelve un dict:
      {
        'numero': str, 'fecha': str ('DD/MM/AAAA') o None,
        'subtotal': float, 'iva': float, 'reg_especiales': float, 'total': float,
        'items': [ {codigo, unidades, descripcion, sugerido, unitario, importe}, ... ],
        'no_reconocidas': [linea, linea, ...],   # renglones de la tabla no interpretados
      }
    Lanza ValueError si no encuentra el numero de factura (formato inesperado).
    """
    import pdfplumber

    texto_completo = ''
    with pdfplumber.open(ruta_pdf) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ''
            texto_completo += t + '\n'

    numero = _buscar(r'N[uú]mero:\s*([A-Za-z0-9\-]+)', texto_completo)
    if not numero:
        raise ValueError('No pude encontrar el número de factura en el PDF. '
                          '¿Es una factura de Torres con el formato habitual?')

    fecha = _buscar(r'Fecha:\s*(\d{2}/\d{2}/\d{4})', texto_completo)
    subtotal = _parse_monto(_buscar(r'Subtotal:\s*\$\s*([\d.,]+)', texto_completo, default='0'))
    iva = _parse_monto(_buscar(r'IVA\s*21:\s*\$\s*([\d.,]+)', texto_completo, default='0'))
    reg_esp = _parse_monto(_buscar(r'Reg\. Especiales:\s*\$\s*([\d.,]+)', texto_completo, default='0'))
    total = _parse_monto(_buscar(r'TOTAL:\s*\$\s*([\d.,]+)', texto_completo, default='0'))

    items = []
    no_reconocidas = []
    inicio = False
    for linea in texto_completo.split('\n'):
        linea = linea.strip()
        if not linea:
            continue
        if linea.startswith('Código') and 'Unidades' in linea:
            inicio = True
            continue
        if not inicio:
            continue
        if any(linea.startswith(k) for k in _FOOTER_KEYWORDS):
            break

        m = ROW_RE.match(linea)
        if m:
            items.append({
                'codigo': m.group(1),
                'unidades': _parse_monto(m.group(2)),
                'descripcion': m.group(3).strip(),
                'sugerido': _parse_monto(m.group(4)),
                'unitario': _parse_monto(m.group(5)),
                'importe': _parse_monto(m.group(6)),
            })
        elif items and not linea[0].isdigit():
            # Continuacion de la descripcion de la fila anterior (linea larga cortada
            # por el ancho del PDF, ej: "x50g" en su propia linea)
            items[-1]['descripcion'] += ' ' + linea
        else:
            # Renglon de la tabla que no pudimos interpretar (ej: percepciones/impuestos,
            # que no son productos). Se guarda para que Ivan lo revise, nunca se descarta
            # en silencio.
            no_reconocidas.append(linea)

    return {
        'numero': numero, 'fecha': fecha,
        'subtotal': subtotal, 'iva': iva, 'reg_especiales': reg_esp, 'total': total,
        'items': items, 'no_reconocidas': no_reconocidas,
    }
