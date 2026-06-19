"""
app/cliente.py — Blueprint PUBLICO (la tienda que ve el cliente).
v0.3 -> catalogo con precios
v0.4 -> (carrito en el front)
v0.5 -> checkout: datos del cliente (CUIT validado), guarda el pedido,
        pagina de confirmacion con WhatsApp + PDF.
v0.9.1 -> orden del catalogo (recomendados / nombre / precio / mas vendidos)
v0.9.2 -> buscador EN VIVO (?ajax=1 devuelve solo el fragmento _grid.html)
v0.10.0 -> filtros Saludables y Con/Sin alcohol (segun marcado del panel)
v0.11.0 -> categoria unica (solapas comida / sin / con)
v0.12.0 -> solapa OFERTAS: muestra productos en oferta (precio tachado + precio
           nuevo). El precio de oferta se RECALCULA en backend (defensa en
           profundidad): aunque el front mande otro precio, manda el real.
"""
import json

from flask import (Blueprint, render_template, request, redirect, url_for,
                   abort, Response, flash)
from sqlalchemy import select, or_, func

from .extensions import db
from .models import (Producto, Pedido, ItemPedido, Oferta, get_ajustes,
                     generar_numero_pedido, EstadoPedido, CategoriaProducto)
from .utils.validaciones import validar_cuit, limpiar_cuit
from .utils.timezone import ahora_argentina
from . import pricing
from .pdf_pedido import generar_pdf_pedido

cliente_bp = Blueprint('cliente', __name__)

POR_PAGINA = 24

# Opciones de orden que ofrece la tienda (clave -> etiqueta visible)
ORDENES = {
    'relevancia':  'Recomendados',
    'nombre':      'Nombre A–Z',
    'precio_asc':  'Precio: menor a mayor',
    'precio_desc': 'Precio: mayor a menor',
    'vendidos':    'Más vendidos',
}


def _ahora_local():
    return ahora_argentina().replace(tzinfo=None)


def _ofertas_vigentes_dict():
    """
    Devuelve {producto_id: Oferta} solo con las ofertas ACTIVAS y NO vencidas.
    Si un producto tuviera varias, queda la publicada mas recientemente.
    """
    ahora = _ahora_local()
    d = {}
    for o in (Oferta.query
              .filter(Oferta.activa.is_(True), Oferta.vence_en > ahora)
              .order_by(Oferta.publicada_en.asc()).all()):
        d[o.producto_id] = o
    return d


def _rubro_display(rubro):
    if not rubro:
        return 'Varios'
    r = rubro.replace('TEOLOGISTICA', '').strip()
    r = r.replace('Y HOGAR', 'y Hogar')
    return r.title()


@cliente_bp.route('/')
def catalogo():
    page = request.args.get('page', 1, type=int)
    q = (request.args.get('q') or '').strip()
    rubro = (request.args.get('rubro') or '').strip()
    orden = (request.args.get('orden') or 'relevancia').strip()
    if orden not in ORDENES:
        orden = 'relevancia'
    # Filtro por categoria/solapa (v0.11): comida | sin | con · (v0.12): ofertas
    cat = (request.args.get('cat') or '').strip().lower()
    _mapa_cat = {
        'comida': CategoriaProducto.COMIDA,
        'sin': CategoriaProducto.BEBIDA_SIN,
        'con': CategoriaProducto.BEBIDA_CON,
    }
    es_ofertas = (cat == 'ofertas')
    cat_db = _mapa_cat.get(cat)
    if cat_db is None and not es_ofertas:
        cat = ''

    ajustes = get_ajustes()
    ofertas_dict = _ofertas_vigentes_dict()

    stmt = select(Producto).where(Producto.activo.is_(True))
    if rubro:
        stmt = stmt.where(Producto.rubro == rubro)
    if q:
        like = f'%{q}%'
        stmt = stmt.where(or_(Producto.nombre.ilike(like),
                              Producto.codigo.ilike(like),
                              Producto.rubro.ilike(like)))
    if cat_db:
        stmt = stmt.where(Producto.categoria == cat_db)
    if es_ofertas:
        ids = list(ofertas_dict.keys())
        stmt = stmt.where(Producto.id.in_(ids) if ids else Producto.id == -1)

    # --- Orden ---
    # Nota: para "precio" ordenamos por costo_neto. Con el markup general da el
    # mismo orden que el precio final (precio = costo / (1 - margen) * IVA).
    if orden == 'nombre':
        stmt = stmt.order_by(Producto.nombre)
    elif orden == 'precio_asc':
        stmt = stmt.order_by(Producto.costo_neto.asc(), Producto.nombre)
    elif orden == 'precio_desc':
        stmt = stmt.order_by(Producto.costo_neto.desc(), Producto.nombre)
    elif orden == 'vendidos':
        ventas_sub = (
            select(ItemPedido.codigo,
                   func.sum(ItemPedido.cantidad).label('vendidas'))
            .join(Pedido, Pedido.id == ItemPedido.pedido_id)
            .where(Pedido.estado != EstadoPedido.ANULADO)
            .group_by(ItemPedido.codigo)
            .subquery()
        )
        stmt = (stmt.outerjoin(ventas_sub, ventas_sub.c.codigo == Producto.codigo)
                    .order_by(func.coalesce(ventas_sub.c.vendidas, 0).desc(),
                              Producto.nombre))
    else:  # relevancia (default)
        orden = 'relevancia'
        stmt = stmt.order_by(Producto.rubro, Producto.nombre)

    paginacion = db.paginate(stmt, page=page, per_page=POR_PAGINA, error_out=False)

    items = []
    for p in paginacion.items:
        pr = pricing.precios(p, ajustes)
        of = ofertas_dict.get(p.id)
        oferta = None
        if of:
            lista = float(of.precio_lista_snapshot) if of.precio_lista_snapshot else pr['x1']
            oferta = {'precio': float(of.precio_oferta), 'lista': lista,
                      'pct': of.descuento_pct}
        items.append({'p': p, 'precios': pr, 'oferta': oferta})

    # Contexto que necesita el fragmento de la grilla
    ctx_grid = dict(items=items, paginacion=paginacion, q=q, rubro_sel=rubro,
                    orden=orden, cat=cat, rubro_display=_rubro_display)

    # Buscador EN VIVO: pedido AJAX -> devolvemos SOLO el fragmento de la grilla.
    if request.args.get('ajax'):
        return render_template('cliente/_grid.html', **ctx_grid)

    rubros_raw = db.session.execute(
        select(Producto.rubro).where(Producto.activo.is_(True))
        .distinct().order_by(Producto.rubro)
    ).scalars().all()
    rubros = [(r, _rubro_display(r)) for r in rubros_raw]

    return render_template('cliente/catalogo.html',
                           rubros=rubros, ordenes=ORDENES, ajustes=ajustes,
                           n_ofertas=len(ofertas_dict), **ctx_grid)


def _recalcular_carrito(carrito_dict, ajustes):
    """
    Recalcula el carrito en el SERVIDOR (defensa en profundidad, regla AXIAL).
    No confia en los precios que manda el navegador.
    Si un producto tiene oferta vigente, usa el PRECIO DE OFERTA (plano, sin
    escalon por cantidad). Si no, usa el precio normal con escalon.
    Devuelve (items, total, descartados).
    """
    ofertas_dict = _ofertas_vigentes_dict()
    items = []
    total = 0.0
    descartados = 0
    for cod, qty in carrito_dict.items():
        try:
            qty = int(qty)
        except (TypeError, ValueError):
            continue
        if qty < 1:
            continue
        p = Producto.query.filter_by(codigo=str(cod), activo=True).first()
        if p is None:
            descartados += 1
            continue
        of = ofertas_dict.get(p.id)
        if of:
            pu = float(of.precio_oferta)         # precio de oferta, blindado
        else:
            pu = pricing.precio_por_cantidad(p, ajustes, qty)
        sub = round(pu * qty, 2)
        items.append({'producto': p, 'cantidad': qty,
                      'precio_unitario': pu, 'subtotal': sub})
        total += sub
    return items, round(total, 2), descartados


@cliente_bp.route('/checkout', methods=['GET', 'POST'])
def checkout():
    ajustes = get_ajustes()

    if request.method == 'POST':
        # 1) Leer carrito que manda el front
        try:
            carrito = json.loads(request.form.get('carrito_json') or '{}')
        except (ValueError, TypeError):
            carrito = {}

        items, total, descartados = _recalcular_carrito(carrito, ajustes)

        # 2) Datos del cliente
        datos = {
            'nombre': (request.form.get('nombre') or '').strip(),
            'apellido': (request.form.get('apellido') or '').strip(),
            'cuit': limpiar_cuit(request.form.get('cuit')),
            'whatsapp': (request.form.get('whatsapp') or '').strip(),
            'email': (request.form.get('email') or '').strip() or None,
            'direccion': (request.form.get('direccion') or '').strip(),
            'zona': (request.form.get('zona') or '').strip(),
            'observaciones': (request.form.get('observaciones') or '').strip() or None,
        }

        # 3) Validaciones
        errores = []
        if not items:
            errores.append('Tu carrito está vacío o los productos ya no están disponibles.')
        if total < float(ajustes.minimo_compra):
            errores.append(f'El pedido no llega al mínimo de {pricing_pesos(ajustes.minimo_compra)}.')
        for campo, etiqueta in [('nombre', 'nombre'), ('apellido', 'apellido'),
                                ('whatsapp', 'WhatsApp'), ('direccion', 'dirección'),
                                ('zona', 'zona/colegio')]:
            if not datos[campo]:
                errores.append(f'Falta completar el {etiqueta}.')
        if not validar_cuit(datos['cuit']):
            errores.append('El CUIT no es válido. Revisá los 11 dígitos.')

        if errores:
            for e in errores:
                flash(e, 'error')
            return render_template('cliente/checkout.html', ajustes=ajustes,
                                   datos=datos)

        # 4) Crear el pedido (atomico)
        try:
            # Datos de origen (IP real detras del proxy de PythonAnywhere + dispositivo)
            xff = request.headers.get('X-Forwarded-For', '')
            ip = xff.split(',')[0].strip() if xff else (request.remote_addr or '')
            ua = (request.headers.get('User-Agent') or '').lower()
            disp = 'Celular' if any(k in ua for k in ('mobi', 'android', 'iphone', 'ipad')) else 'Computadora'

            pedido = Pedido(
                numero=generar_numero_pedido('WEB'),
                origen='WEB',
                total=total,
                ip_origen=ip,
                dispositivo=disp,
                **datos,
            )
            db.session.add(pedido)
            db.session.flush()  # para tener pedido.id
            for it in items:
                db.session.add(ItemPedido(
                    pedido_id=pedido.id,
                    codigo=it['producto'].codigo,
                    nombre=it['producto'].nombre,
                    cantidad=it['cantidad'],
                    precio_unitario=it['precio_unitario'],
                    subtotal=it['subtotal'],
                ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Hubo un problema al registrar el pedido. Probá de nuevo.', 'error')
            return render_template('cliente/checkout.html', ajustes=ajustes, datos=datos)

        return redirect(url_for('cliente.confirmacion', token=pedido.token))

    # GET -> muestra el formulario (el carrito lo lee el JS desde sessionStorage)
    return render_template('cliente/checkout.html', ajustes=ajustes, datos=None)


def pricing_pesos(v):
    s = f'{float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return '$' + s


@cliente_bp.route('/p/<token>')
def confirmacion(token):
    pedido = Pedido.query.filter_by(token=token).first()
    if pedido is None:
        abort(404)
    ajustes = get_ajustes()

    # Mensaje de WhatsApp para Juliana (lo manda el cliente desde su telefono)
    msg = (f'Hola Juliana! Soy {pedido.cliente_completo}. '
           f'Te acabo de hacer el pedido {pedido.numero} por {pricing_pesos(pedido.total)}. '
           f'Quedo a la espera para coordinar la entrega y el pago. ¡Gracias!')

    return render_template('cliente/confirmacion.html', pedido=pedido,
                           ajustes=ajustes, wa_msg=msg)


@cliente_bp.route('/p/<token>/pdf')
def pedido_pdf(token):
    pedido = Pedido.query.filter_by(token=token).first()
    if pedido is None:
        abort(404)
    ajustes = get_ajustes()
    pdf = generar_pdf_pedido(pedido, ajustes)
    return Response(pdf, mimetype='application/pdf', headers={
        'Content-Disposition': f'inline; filename="Pedido_{pedido.numero}.pdf"'
    })
