"""
app/admin.py — Blueprint del panel administrativo (El Arquitecto).
v0.1 Dashboard · v0.2 Catalogo + Importar · v0.3 Ajustes
v0.6 -> Panel de PEDIDOS (CRM de ventas de Juliana)
v0.9 -> Historial de modificaciones con código (prolijo)
v0.12 -> OFERTAS: publicar productos en oferta por 7 dias (piso 10% blindado)
v0.14 -> BANNERS: pestaña (solo super admin) para cargar el carrusel central
         y los banners laterales de la tienda.
v0.14.1 -> FOOD COST (placeholder): pestaña (solo super admin) que deja lista la
           seccion del lector de facturas PDF de Torres. NO toca la base de datos.
v0.16.0 -> USUARIOS: ABM completo (solo super admin) con perfil de la persona
           (DNI, nacimiento, contacto, datos bancarios para comisiones). Crear /
           editar / activar-desactivar / resetear contrasena. Tope de 5 admins.
"""
import os
import secrets
import tempfile
from datetime import timedelta, datetime as _dt
from urllib.parse import quote

from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, abort, Response, current_app, jsonify)
from flask_login import login_required, current_user
from sqlalchemy import select, or_, func
from werkzeug.utils import secure_filename

from .extensions import db
from .models import (Producto, Pedido, Cobro, ModificacionPedido, ItemPedido,
                     get_ajustes, EstadoPedido, FormaPago, CategoriaProducto,
                     Oferta, Cotizacion, CotizacionItem, TipoCotizacion,
                     EstadoCotizacion, generar_numero_cotizacion,
                     Banner, ZonaBanner, DestinoBanner,
                     Usuario, Rol, FormaPagoComision, Cliente)
from .services import aplicar_importacion
from .utils.decorators import admin_requerido, super_admin_requerido
from .utils.import_planilla import leer_planilla
from .utils.timezone import ahora_argentina
from .pdf_pedido import generar_pdf_pedido
from .pdf_cotizacion import generar_pdf_cotizacion
from . import pricing

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

EXTENSIONES_OK = ('.xlsx', '.xlsm', '.csv')

# Dias que dura una oferta publicada (v0.12)
DIAS_OFERTA = 7

# Minimo sugerido de bolsas para Cumpleaños (v0.12 C1). Aviso, no bloqueo.
MIN_BOLSAS_CUMPLE = 20

# Banners (v0.14): topes por zona y solapas disponibles como destino
MAX_BANNER_CENTRAL = 6
MAX_BANNER_LATERAL = 2
EXTENSIONES_IMG_BANNER = ('.jpg', '.jpeg', '.png', '.webp')
SOLAPAS_BANNER = [
    ('ofertas', '🏷️ Ofertas'),
    ('comida', '🥗 Saludables'),
    ('sin', '💧 Sin alcohol'),
    ('con', '🍷 Con alcohol'),
]

# Usuarios (v0.16): tope de administradoras (Juliana + hasta 4 mas). El super admin no cuenta.
MAX_ADMINS = 5


def _ahora():
    return ahora_argentina().replace(tzinfo=None)


def _pesos(v):
    s = f'{float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return '$' + s


@admin_bp.before_request
@login_required
def _forzar_cambio_password():
    if current_user.is_authenticated and current_user.debe_cambiar_password:
        return redirect(url_for('auth.cambiar_password'))


@admin_bp.route('/')
@admin_requerido
def dashboard():
    inicio_mes = ahora_argentina().replace(day=1, hour=0, minute=0, second=0,
                                           microsecond=0, tzinfo=None)
    ventas_mes = db.session.execute(
        select(func.coalesce(func.sum(Pedido.total), 0))
        .where(Pedido.creado >= inicio_mes)
        .where(Pedido.estado != EstadoPedido.ANULADO)
    ).scalar() or 0

    clientes = db.session.execute(
        select(func.count(func.distinct(Pedido.cuit)))
    ).scalar() or 0

    stats = {
        'productos': Producto.query.filter_by(activo=True).count(),
        'clientes': clientes,
        'pedidos_pendientes': Pedido.query.filter_by(estado=EstadoPedido.PENDIENTE).count(),
        'ventas_mes': float(ventas_mes),
    }
    return render_template('admin/dashboard.html', stats=stats)


# ======================= PEDIDOS (CRM) =======================

@admin_bp.route('/pedidos')
@admin_requerido
def pedidos():
    page = request.args.get('page', 1, type=int)
    q = (request.args.get('q') or '').strip()
    estado = (request.args.get('estado') or '').strip()

    stmt = select(Pedido)
    if estado:
        stmt = stmt.where(Pedido.estado == estado)
    if q:
        like = f'%{q}%'
        stmt = stmt.where(or_(Pedido.numero.ilike(like),
                              Pedido.nombre.ilike(like),
                              Pedido.apellido.ilike(like),
                              Pedido.cuit.ilike(like)))
    stmt = stmt.order_by(Pedido.creado.desc())

    paginacion = db.paginate(stmt, page=page, per_page=25, error_out=False)
    total = Pedido.query.count()

    return render_template('admin/pedidos.html', paginacion=paginacion,
                           q=q, estado_sel=estado, total=total,
                           estados=EstadoPedido.ETIQUETAS)


@admin_bp.route('/pedidos/<int:pid>')
@admin_requerido
def pedido_detalle(pid):
    pedido = Pedido.query.get_or_404(pid)
    return render_template('admin/pedido_detalle.html', pedido=pedido,
                           estados=EstadoPedido.ETIQUETAS,
                           formas=FormaPago.ETIQUETAS)


@admin_bp.route('/pedidos/<int:pid>/estado', methods=['POST'])
@admin_requerido
def pedido_estado(pid):
    pedido = Pedido.query.get_or_404(pid)
    if pedido.esta_anulado:
        flash('El pedido está anulado, no se puede cambiar de estado.', 'error')
        return redirect(url_for('admin.pedido_detalle', pid=pid))

    nuevo = (request.form.get('estado') or '').strip()
    if nuevo not in (EstadoPedido.PENDIENTE, EstadoPedido.CONFIRMADO, EstadoPedido.ENTREGADO):
        flash('Estado inválido.', 'error')
        return redirect(url_for('admin.pedido_detalle', pid=pid))

    pedido.estado = nuevo
    db.session.commit()
    flash(f'Pedido marcado como {EstadoPedido.ETIQUETAS[nuevo]}.', 'success')
    return redirect(url_for('admin.pedido_detalle', pid=pid))


@admin_bp.route('/pedidos/<int:pid>/facturado', methods=['POST'])
@admin_requerido
def pedido_facturado(pid):
    pedido = Pedido.query.get_or_404(pid)
    valor = request.form.get('facturado')
    pedido.facturado = (valor == 'si')
    pedido.facturado_en = _ahora()
    db.session.commit()
    flash('Estado de facturación actualizado.', 'success')
    return redirect(url_for('admin.pedido_detalle', pid=pid))


@admin_bp.route('/pedidos/<int:pid>/cobro', methods=['POST'])
@admin_requerido
def pedido_cobro(pid):
    pedido = Pedido.query.get_or_404(pid)
    if pedido.esta_anulado:
        flash('El pedido está anulado.', 'error')
        return redirect(url_for('admin.pedido_detalle', pid=pid))

    forma = (request.form.get('forma_pago') or '').strip()
    if forma not in FormaPago.TODAS:
        flash('Forma de pago inválida.', 'error')
        return redirect(url_for('admin.pedido_detalle', pid=pid))
    try:
        monto = float(request.form.get('monto') or 0)
    except ValueError:
        monto = 0
    if monto <= 0:
        flash('El monto del cobro debe ser mayor a cero.', 'error')
        return redirect(url_for('admin.pedido_detalle', pid=pid))

    cobro = Cobro(pedido_id=pedido.id, forma_pago=forma, monto=round(monto, 2),
                  nota=(request.form.get('nota') or '').strip() or None,
                  registrado_por=current_user.nombre)
    db.session.add(cobro)
    db.session.commit()
    flash('Cobro registrado.', 'success')
    return redirect(url_for('admin.pedido_detalle', pid=pid))


@admin_bp.route('/pedidos/<int:pid>/cobro/<int:cid>/borrar', methods=['POST'])
@admin_requerido
def pedido_cobro_borrar(pid, cid):
    cobro = Cobro.query.filter_by(id=cid, pedido_id=pid).first_or_404()
    db.session.delete(cobro)
    db.session.commit()
    flash('Cobro eliminado.', 'success')
    return redirect(url_for('admin.pedido_detalle', pid=pid))


@admin_bp.route('/pedidos/<int:pid>/anular', methods=['POST'])
@super_admin_requerido
def pedido_anular(pid):
    pedido = Pedido.query.get_or_404(pid)
    pedido.estado = EstadoPedido.ANULADO
    pedido.anulado_por = current_user.nombre
    pedido.anulado_en = _ahora()
    pedido.anulado_motivo = (request.form.get('motivo') or '').strip() or None
    db.session.commit()
    flash(f'Pedido {pedido.numero} anulado.', 'warning')
    return redirect(url_for('admin.pedido_detalle', pid=pid))


@admin_bp.route('/pedidos/<int:pid>/pdf')
@admin_requerido
def pedido_pdf_admin(pid):
    pedido = Pedido.query.get_or_404(pid)
    ajustes = get_ajustes()
    pdf = generar_pdf_pedido(pedido, ajustes)
    return Response(pdf, mimetype='application/pdf', headers={
        'Content-Disposition': f'inline; filename="Pedido_{pedido.numero}.pdf"'
    })


@admin_bp.route('/productos/buscar')
@admin_requerido
def productos_buscar():
    """Buscador JSON para agregar productos al editar un pedido."""
    q = (request.args.get('q') or '').strip()
    if len(q) < 2:
        return jsonify([])
    ajustes = get_ajustes()
    like = f'%{q}%'
    prods = Producto.query.filter(Producto.activo.is_(True)).filter(
        or_(Producto.nombre.ilike(like), Producto.codigo.ilike(like))
    ).order_by(Producto.nombre).limit(15).all()
    res = []
    for p in prods:
        pr = pricing.precios(p, ajustes)
        res.append({'codigo': p.codigo, 'nombre': p.nombre,
                    'p1': pr['x1'], 'p5': pr['x5'], 'p10': pr['x10']})
    return jsonify(res)


@admin_bp.route('/pedidos/<int:pid>/editar', methods=['GET', 'POST'])
@admin_requerido
def pedido_editar(pid):
    pedido = Pedido.query.get_or_404(pid)
    ajustes = get_ajustes()

    if pedido.esta_anulado:
        flash('Un pedido anulado no se puede editar.', 'error')
        return redirect(url_for('admin.pedido_detalle', pid=pid))

    if request.method == 'POST':
        import json
        try:
            nuevos = json.loads(request.form.get('carrito_json') or '{}')
        except (ValueError, TypeError):
            nuevos = {}

        # Precios congelados de los items actuales (por si algun codigo ya no esta en catalogo)
        originales = {it.codigo: it for it in pedido.items}

        items_calc = []
        total = 0.0
        for cod, qty in nuevos.items():
            try:
                qty = int(qty)
            except (TypeError, ValueError):
                continue
            if qty < 1:
                continue
            p = Producto.query.filter_by(codigo=str(cod), activo=True).first()
            if p is not None:
                pu = pricing.precio_por_cantidad(p, ajustes, qty)
                nombre = p.nombre
            elif str(cod) in originales:
                pu = float(originales[str(cod)].precio_unitario)
                nombre = originales[str(cod)].nombre
            else:
                continue
            sub = round(pu * qty, 2)
            items_calc.append({'codigo': str(cod), 'nombre': nombre,
                               'cantidad': qty, 'precio_unitario': pu, 'subtotal': sub})
            total += sub
        total = round(total, 2)

        # Validaciones
        if not items_calc:
            flash('El pedido no puede quedar vacío.', 'error')
            return redirect(url_for('admin.pedido_editar', pid=pid))
        if total < float(ajustes.minimo_compra):
            flash(f'El nuevo total ({_pesos(total)}) no llega al mínimo de '
                  f'{_pesos(ajustes.minimo_compra)}. No se guardó el cambio.', 'error')
            return redirect(url_for('admin.pedido_editar', pid=pid))
        if pedido.total_cobrado > total + 0.01:
            flash(f'El nuevo total ({_pesos(total)}) es menor a lo ya cobrado '
                  f'({_pesos(pedido.total_cobrado)}). Ajustá los cobros antes de bajar el monto.',
                  'error')
            return redirect(url_for('admin.pedido_editar', pid=pid))

        # Armar el historial (comparar viejo vs nuevo) — con código y orden estable
        viejos = {it.codigo: (it.cantidad, it.nombre) for it in pedido.items}
        nuevos_q = {it['codigo']: (it['cantidad'], it['nombre']) for it in items_calc}
        cambios = []
        for cod in sorted(set(viejos) | set(nuevos_q)):
            vq = viejos.get(cod, (0, None))[0]
            nq = nuevos_q.get(cod, (0, None))[0]
            nombre = (viejos.get(cod) or nuevos_q.get(cod))[1]
            if vq == 0 and nq > 0:
                cambios.append(f'agregó {nq}× [{cod}] {nombre}')
            elif nq == 0 and vq > 0:
                cambios.append(f'quitó {vq}× [{cod}] {nombre}')
            elif vq != nq:
                cambios.append(f'[{cod}] {nombre}: de {vq} a {nq} u.')

        if not cambios:
            flash('No hiciste ningún cambio.', 'warning')
            return redirect(url_for('admin.pedido_editar', pid=pid))

        try:
            total_anterior = float(pedido.total)
            # Reemplazar items
            for it in list(pedido.items):
                db.session.delete(it)
            db.session.flush()
            for it in items_calc:
                db.session.add(ItemPedido(pedido_id=pedido.id, codigo=it['codigo'],
                                          nombre=it['nombre'], cantidad=it['cantidad'],
                                          precio_unitario=it['precio_unitario'],
                                          subtotal=it['subtotal']))
            pedido.total = total
            pedido.modificado_en = _ahora()
            db.session.add(ModificacionPedido(
                pedido_id=pedido.id,
                descripcion='; '.join(cambios),
                total_anterior=total_anterior,
                total_nuevo=total,
                hecho_por=current_user.nombre,
            ))
            db.session.commit()
        except Exception:
            db.session.rollback()
            flash('Hubo un problema al guardar la edición. Probá de nuevo.', 'error')
            return redirect(url_for('admin.pedido_editar', pid=pid))

        flash('Pedido actualizado ✓', 'success')
        return redirect(url_for('admin.pedido_detalle', pid=pid))

    # GET -> armar los items actuales con sus precios para la pantalla de edicion
    items_data = []
    for it in pedido.items:
        p = Producto.query.filter_by(codigo=it.codigo, activo=True).first()
        if p is not None:
            pr = pricing.precios(p, ajustes)
            items_data.append({'codigo': it.codigo, 'nombre': it.nombre,
                               'p1': pr['x1'], 'p5': pr['x5'], 'p10': pr['x10'],
                               'qty': it.cantidad})
        else:
            pu = float(it.precio_unitario)
            items_data.append({'codigo': it.codigo, 'nombre': it.nombre,
                               'p1': pu, 'p5': pu, 'p10': pu, 'qty': it.cantidad})

    return render_template('admin/pedido_editar.html', pedido=pedido,
                           ajustes=ajustes, items_data=items_data)


# ======================= CATALOGO =======================

@admin_bp.route('/catalogo')
@admin_requerido
def catalogo():
    page = request.args.get('page', 1, type=int)
    q = (request.args.get('q') or '').strip()
    rubro = (request.args.get('rubro') or '').strip()
    cat = (request.args.get('cat') or '').strip()   # filtro por categoria (v0.11)

    stmt = select(Producto)
    if rubro:
        stmt = stmt.where(Producto.rubro == rubro)
    if q:
        like = f'%{q}%'
        stmt = stmt.where(or_(Producto.nombre.ilike(like),
                              Producto.codigo.ilike(like)))
    if cat == 'sin_categoria':
        stmt = stmt.where(or_(Producto.categoria == '', Producto.categoria.is_(None)))
    elif cat in CategoriaProducto.TODAS:
        stmt = stmt.where(Producto.categoria == cat)
    stmt = stmt.order_by(Producto.rubro, Producto.nombre)

    paginacion = db.paginate(stmt, page=page, per_page=50, error_out=False)

    ajustes = get_ajustes()
    filas = []
    for p in paginacion.items:
        filas.append({'p': p, 'venta': pricing.precio_final(p, ajustes, 'x1'),
                      'margen': pricing.margen_efectivo(p, ajustes)})

    rubros = db.session.execute(
        select(Producto.rubro).distinct().order_by(Producto.rubro)
    ).scalars().all()

    total = Producto.query.count()

    return render_template('admin/catalogo.html',
                           filas=filas, paginacion=paginacion, rubros=rubros,
                           q=q, rubro_sel=rubro, cat_sel=cat, total=total,
                           ajustes=ajustes, categorias=CategoriaProducto.ETIQUETAS)


@admin_bp.route('/catalogo/<int:pid>/categoria', methods=['POST'])
@admin_requerido
def catalogo_categoria(pid):
    """
    Asigna la categoria unica de un producto (AJAX): comida saludable,
    bebida sin/con alcohol, o sin categoria. Lo usan Ivan y Juliana (v0.11).
    """
    producto = Producto.query.get_or_404(pid)
    cat = (request.form.get('categoria') or '').strip()
    if cat not in ('',) + CategoriaProducto.TODAS:
        return jsonify({'ok': False, 'error': 'categoría inválida'}), 400
    producto.categoria = cat
    db.session.commit()
    return jsonify({'ok': True, 'categoria': cat,
                    'etiqueta': producto.categoria_etiqueta})


# ======================= OFERTAS (v0.12) =======================

@admin_bp.route('/ofertas')
@admin_requerido
def ofertas():
    """Panel para armar y publicar ofertas (productos con precio especial, 7 dias)."""
    ajustes = get_ajustes()

    # Ofertas activas + no vencidas (las que el cliente ve hoy en la tienda)
    activas = (Oferta.query.filter(Oferta.activa.is_(True))
               .order_by(Oferta.vence_en.asc()).all())
    vigentes = [o for o in activas if o.vigente]

    # Marcas disponibles para el selector (si la planilla las trae)
    marcas = db.session.execute(
        select(Producto.marca)
        .where(Producto.activo.is_(True))
        .where(Producto.marca.isnot(None))
        .where(Producto.marca != '')
        .distinct().order_by(Producto.marca)
    ).scalars().all()

    # Rubros: se usan como filtro alternativo cuando no hay marcas cargadas
    rubros = db.session.execute(
        select(Producto.rubro)
        .where(Producto.activo.is_(True))
        .where(Producto.rubro.isnot(None))
        .where(Producto.rubro != '')
        .distinct().order_by(Producto.rubro)
    ).scalars().all()

    return render_template('admin/ofertas.html', vigentes=vigentes,
                           marcas=marcas, rubros=rubros,
                           dias=DIAS_OFERTA, ajustes=ajustes)


@admin_bp.route('/ofertas/buscar')
@admin_requerido
def ofertas_buscar():
    """
    JSON para el buscador del panel de ofertas. Devuelve productos con costo,
    precio de lista y precio MINIMO (piso 10% blindado). Filtra por texto, por
    marca y/o por rubro. No devuelve nada si no hay ningun filtro (para no
    dumpear los 1654 productos de una).
    """
    q = (request.args.get('q') or '').strip()
    marca = (request.args.get('marca') or '').strip()
    rubro = (request.args.get('rubro') or '').strip()
    ajustes = get_ajustes()

    if not q and not marca and not rubro:
        return jsonify([])

    stmt = Producto.query.filter(Producto.activo.is_(True))
    if marca:
        stmt = stmt.filter(Producto.marca == marca)
    if rubro:
        stmt = stmt.filter(Producto.rubro == rubro)
    if q:
        like = f'%{q}%'
        stmt = stmt.filter(or_(Producto.nombre.ilike(like),
                               Producto.codigo.ilike(like),
                               Producto.marca.ilike(like)))
    prods = stmt.order_by(Producto.nombre).limit(80).all()

    # IDs de productos que YA tienen oferta vigente (para marcarlos)
    en_oferta = {o.producto_id for o in Oferta.query.filter(Oferta.activa.is_(True)).all()
                 if o.vigente}

    res = []
    for p in prods:
        res.append({
            'id': p.id,
            'codigo': p.codigo,
            'nombre': p.nombre,
            'marca': p.marca or '',
            'costo': round(float(p.costo_neto), 2),
            'precio_lista': pricing.precio_final(p, ajustes, 'x1'),
            'precio_min': pricing.precio_oferta_minimo(p, 10),   # piso 10% blindado
            'precio_m20': pricing.precio_oferta_minimo(p, 20),   # oferta margen 20%
            'precio_m15': pricing.precio_oferta_minimo(p, 15),   # oferta margen 15%
            'en_oferta': p.id in en_oferta,
        })
    return jsonify(res)


@admin_bp.route('/ofertas/publicar', methods=['POST'])
@admin_requerido
def ofertas_publicar():
    """
    Publica ofertas a partir de un JSON {producto_id: precio_oferta}.
    BLINDAJE: el backend recalcula el piso 10% y NUNCA deja publicar por debajo
    (si viene mas bajo, lo clampea al piso). Tampoco deja una 'oferta' mas cara
    que el precio de lista. Si el producto ya tenia una oferta vigente, la
    reemplaza (despublica la anterior).
    """
    import json
    ajustes = get_ajustes()
    try:
        data = json.loads(request.form.get('ofertas_json') or '{}')
    except (ValueError, TypeError):
        data = {}

    if not data:
        flash('No seleccionaste ningún producto para publicar.', 'error')
        return redirect(url_for('admin.ofertas'))

    vence = _ahora() + timedelta(days=DIAS_OFERTA)
    creadas = 0
    clampeadas = 0

    for pid, precio in data.items():
        if not str(pid).isdigit():
            continue
        p = Producto.query.filter_by(id=int(pid), activo=True).first()
        if p is None:
            continue

        piso = pricing.precio_oferta_minimo(p)              # piso 10% blindado
        lista = pricing.precio_final(p, ajustes, 'x1')

        try:
            precio = round(float(precio), 2)
        except (TypeError, ValueError):
            precio = piso

        # BLINDAJE: nunca por debajo del piso del 10%
        if precio < piso:
            precio = piso
            clampeadas += 1
        # Una oferta no puede ser mas cara que el precio de lista
        if precio > lista:
            precio = lista

        # Reemplazo: si ya hay oferta vigente del mismo producto, se despublica
        for o in Oferta.query.filter_by(producto_id=p.id, activa=True).all():
            o.activa = False

        db.session.add(Oferta(
            producto_id=p.id,
            precio_oferta=precio,
            precio_lista_snapshot=lista,
            costo_neto_snapshot=p.costo_neto,
            publicada_en=_ahora(),
            vence_en=vence,
            activa=True,
            creada_por=current_user.nombre,
        ))
        creadas += 1

    db.session.commit()

    if creadas:
        msg = f'{creadas} oferta(s) publicada(s) por {DIAS_OFERTA} días.'
        if clampeadas:
            msg += (f' {clampeadas} se ajustó(aron) al precio mínimo para '
                    f'protegerte el 10% de ganancia.')
        flash(msg, 'success')
    else:
        flash('No se publicó ninguna oferta (revisá los productos).', 'warning')

    return redirect(url_for('admin.ofertas'))


@admin_bp.route('/ofertas/<int:oid>/despublicar', methods=['POST'])
@admin_requerido
def oferta_despublicar(oid):
    """Saca una oferta de la tienda (no se borra: queda inactiva en la base)."""
    o = Oferta.query.get_or_404(oid)
    o.activa = False
    db.session.commit()
    flash('Oferta despublicada. Ya no se muestra en la tienda.', 'warning')
    return redirect(url_for('admin.ofertas'))


# ======================= COTIZADOR (Cumpleaños / Colegios · v0.12 C1) =======================

@admin_bp.route('/cotizador')
@admin_requerido
def cotizador():
    """Lista de cotizaciones. Filtra por tipo (CUMPLE / COLEGIO) si viene ?tipo=."""
    tipo = (request.args.get('tipo') or '').strip().upper()
    if tipo not in TipoCotizacion.TODAS:
        tipo = ''

    stmt = Cotizacion.query
    if tipo:
        stmt = stmt.filter_by(tipo=tipo)
    cotis = stmt.order_by(Cotizacion.creada_en.desc()).limit(100).all()

    return render_template('admin/cotizador.html', cotis=cotis, tipo_sel=tipo,
                           tipos=TipoCotizacion.ETIQUETAS)


@admin_bp.route('/cotizador/nueva/<tipo>')
@admin_requerido
def cotizador_armar(tipo):
    """Pantalla para armar una cotización nueva (CUMPLE o COLEGIO)."""
    tipo = (tipo or '').strip().upper()
    if tipo not in TipoCotizacion.TODAS:
        abort(404)
    ajustes = get_ajustes()

    marcas = db.session.execute(
        select(Producto.marca).where(Producto.activo.is_(True))
        .where(Producto.marca.isnot(None)).where(Producto.marca != '')
        .distinct().order_by(Producto.marca)
    ).scalars().all()
    rubros = db.session.execute(
        select(Producto.rubro).where(Producto.activo.is_(True))
        .where(Producto.rubro.isnot(None)).where(Producto.rubro != '')
        .distinct().order_by(Producto.rubro)
    ).scalars().all()

    return render_template('admin/cotizador_armar.html', tipo=tipo,
                           tipo_etiqueta=TipoCotizacion.ETIQUETAS[tipo],
                           es_cumple=(tipo == TipoCotizacion.CUMPLE),
                           marcas=marcas, rubros=rubros, ajustes=ajustes,
                           min_bolsas=MIN_BOLSAS_CUMPLE)


@admin_bp.route('/cotizador/guardar', methods=['POST'])
@admin_requerido
def cotizador_guardar():
    """
    Guarda una cotización nueva a partir del JSON de items.
    BLINDAJE: cada precio se valida en backend contra el piso del 10%.
    """
    import json
    tipo = (request.form.get('tipo') or '').strip().upper()
    if tipo not in TipoCotizacion.TODAS:
        flash('Tipo de cotización inválido.', 'error')
        return redirect(url_for('admin.cotizador'))

    try:
        items_in = json.loads(request.form.get('items_json') or '[]')
    except (ValueError, TypeError):
        items_in = []

    if not items_in:
        flash('Agregá al menos un producto a la cotización.', 'error')
        return redirect(url_for('admin.cotizador_armar', tipo=tipo))

    # Datos del cliente (todos opcionales)
    nombre_cliente = (request.form.get('nombre_cliente') or '').strip() or None
    whatsapp = (request.form.get('whatsapp') or '').strip() or None
    email = (request.form.get('email') or '').strip() or None
    nota = (request.form.get('nota') or '').strip() or None

    es_cumple = (tipo == TipoCotizacion.CUMPLE)

    # Unidades (bolsas). Solo CUMPLE multiplica; COLEGIO siempre 1.
    try:
        unidades = int(request.form.get('unidades') or 1)
    except (TypeError, ValueError):
        unidades = 1
    if unidades < 1:
        unidades = 1
    if not es_cumple:
        unidades = 1

    # Bolsa fisica (solo CUMPLE)
    incluye_bolsa = (request.form.get('incluye_bolsa') == 'si') and es_cumple
    try:
        costo_bolsa = round(float(request.form.get('costo_bolsa') or 0), 2)
    except (TypeError, ValueError):
        costo_bolsa = 0.0
    if not incluye_bolsa or costo_bolsa < 0:
        costo_bolsa = 0.0

    # Armar items con blindaje del piso 10%
    items_calc = []
    subtotal_bolsa = 0.0
    costo_prod_bolsa = 0.0
    for it in items_in:
        pid = it.get('id')
        if not str(pid).isdigit():
            continue
        p = Producto.query.filter_by(id=int(pid), activo=True).first()
        if p is None:
            continue
        try:
            cant = int(it.get('cantidad') or 1)
        except (TypeError, ValueError):
            cant = 1
        if cant < 1:
            cant = 1
        piso = pricing.precio_oferta_minimo(p, 10)
        try:
            precio = round(float(it.get('precio') or piso), 2)
        except (TypeError, ValueError):
            precio = piso
        if precio < piso:        # BLINDAJE 10%
            precio = piso
        sub = round(precio * cant, 2)
        items_calc.append({
            'codigo': p.codigo, 'nombre': p.nombre, 'cantidad': cant,
            'costo_unitario': float(p.costo_neto),
            'precio_unitario': precio, 'subtotal': sub,
        })
        subtotal_bolsa += sub
        costo_prod_bolsa += float(p.costo_neto) * cant

    if not items_calc:
        flash('No se pudo armar la cotización (productos no encontrados).', 'error')
        return redirect(url_for('admin.cotizador_armar', tipo=tipo))

    subtotal_bolsa = round(subtotal_bolsa, 2)
    total = round((subtotal_bolsa + costo_bolsa) * unidades, 2)
    costo_total = round(costo_prod_bolsa * unidades, 2)

    try:
        coti = Cotizacion(
            tipo=tipo,
            numero=generar_numero_cotizacion(tipo),
            nombre_cliente=nombre_cliente, whatsapp=whatsapp, email=email, nota=nota,
            unidades=unidades, incluye_bolsa=incluye_bolsa, costo_bolsa=costo_bolsa,
            costo_total=costo_total, total=total,
            estado=EstadoCotizacion.BORRADOR, creada_por=current_user.nombre,
        )
        db.session.add(coti)
        db.session.flush()
        for it in items_calc:
            db.session.add(CotizacionItem(cotizacion_id=coti.id, **it))
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Hubo un problema al guardar la cotización. Probá de nuevo.', 'error')
        return redirect(url_for('admin.cotizador_armar', tipo=tipo))

    if es_cumple and unidades < MIN_BOLSAS_CUMPLE:
        flash(f'Ojo: {unidades} bolsas está por debajo del mínimo sugerido '
              f'({MIN_BOLSAS_CUMPLE}). Si el cliente no llega, contactá al super '
              f'administrador para cerrar la venta.', 'warning')
    flash(f'Cotización {coti.numero} creada ✓', 'success')
    return redirect(url_for('admin.cotizador_detalle', cid=coti.id))


@admin_bp.route('/cotizador/<int:cid>')
@admin_requerido
def cotizador_detalle(cid):
    coti = Cotizacion.query.get_or_404(cid)
    return render_template('admin/cotizador_detalle.html', coti=coti,
                           ajustes=get_ajustes())


@admin_bp.route('/cotizador/<int:cid>/anular', methods=['POST'])
@admin_requerido
def cotizador_anular(cid):
    coti = Cotizacion.query.get_or_404(cid)
    coti.estado = EstadoCotizacion.ANULADA
    db.session.commit()
    flash(f'Cotización {coti.numero} anulada.', 'warning')
    return redirect(url_for('admin.cotizador'))


@admin_bp.route('/cotizador/<int:cid>/pdf')
@admin_requerido
def cotizador_pdf(cid):
    """PDF del presupuesto (Cumpleaños / Colegio) para mandarle al cliente."""
    coti = Cotizacion.query.get_or_404(cid)
    ajustes = get_ajustes()
    pdf = generar_pdf_cotizacion(coti, ajustes)
    return Response(pdf, mimetype='application/pdf', headers={
        'Content-Disposition': f'inline; filename="{coti.numero}.pdf"'
    })


@admin_bp.route('/cotizador/<int:cid>/estado', methods=['POST'])
@admin_requerido
def cotizador_estado(cid):
    """Cambia el estado de una cotización (Borrador / Enviada / Cerrada=vendida)."""
    coti = Cotizacion.query.get_or_404(cid)
    if coti.estado == EstadoCotizacion.ANULADA:
        flash('La cotización está anulada.', 'error')
        return redirect(url_for('admin.cotizador_detalle', cid=cid))

    nuevo = (request.form.get('estado') or '').strip().upper()
    validos = (EstadoCotizacion.BORRADOR, EstadoCotizacion.ENVIADA, EstadoCotizacion.CERRADA)
    if nuevo not in validos:
        flash('Estado inválido.', 'error')
        return redirect(url_for('admin.cotizador_detalle', cid=cid))

    coti.estado = nuevo
    coti.modificada_en = _ahora()
    db.session.commit()
    flash(f'Cotización marcada como {EstadoCotizacion.ETIQUETAS[nuevo]}.', 'success')
    return redirect(url_for('admin.cotizador_detalle', cid=cid))


# ======================= FOTOS =======================

EXTENSIONES_IMG = ('.jpg', '.jpeg', '.png', '.webp')


def _carpeta_fotos():
    carpeta = os.path.join(current_app.static_folder, 'img', 'productos')
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


@admin_bp.route('/fotos', methods=['GET', 'POST'])
@admin_requerido
def fotos():
    carpeta = _carpeta_fotos()

    if request.method == 'POST':
        from PIL import Image

        archivos = request.files.getlist('fotos')
        asignadas = 0
        sin_producto = []
        invalidas = 0

        for f in archivos:
            if not f or not f.filename:
                continue
            nombre = secure_filename(f.filename)
            base, ext = os.path.splitext(nombre)
            if ext.lower() not in EXTENSIONES_IMG:
                invalidas += 1
                continue
            codigo = base.strip()
            producto = Producto.query.filter_by(codigo=codigo).first()
            if producto is None:
                sin_producto.append(codigo)
                continue
            try:
                img = Image.open(f.stream).convert('RGB')
                img.thumbnail((600, 600))  # achicar para que pese poco
                destino = os.path.join(carpeta, f'{codigo}.jpg')
                img.save(destino, 'JPEG', quality=82)
                producto.imagen = f'{codigo}.jpg'
                asignadas += 1
            except Exception:
                invalidas += 1

        db.session.commit()

        partes = [f'{asignadas} foto(s) asignada(s)']
        if sin_producto:
            ej = ', '.join(sin_producto[:8])
            partes.append(f'{len(sin_producto)} sin producto (código no encontrado: {ej})')
        if invalidas:
            partes.append(f'{invalidas} inválida(s)')
        flash(' · '.join(partes), 'success' if asignadas else 'warning')
        return redirect(url_for('admin.fotos'))

    con_foto = Producto.query.filter(Producto.imagen.isnot(None)).count()
    total = Producto.query.count()
    return render_template('admin/fotos.html', con_foto=con_foto, total=total)


# ======================= BANNERS (v0.14 · solo super admin) =======================

def _carpeta_banners():
    carpeta = os.path.join(current_app.static_folder, 'img', 'banners')
    os.makedirs(carpeta, exist_ok=True)
    return carpeta


@admin_bp.route('/banners')
@super_admin_requerido
def banners():
    """Pantalla para cargar/gestionar los banners (central + laterales)."""
    data = {z: Banner.query.filter_by(zona=z).order_by(Banner.orden, Banner.id).all()
            for z in ZonaBanner.TODAS}
    topes = {ZonaBanner.CENTRAL: MAX_BANNER_CENTRAL,
             ZonaBanner.IZQ: MAX_BANNER_LATERAL,
             ZonaBanner.DER: MAX_BANNER_LATERAL}
    return render_template('admin/banners.html',
                           data=data, topes=topes,
                           zonas=ZonaBanner.ETIQUETAS,
                           destinos=DestinoBanner.ETIQUETAS,
                           solapas=SOLAPAS_BANNER,
                           ajustes=get_ajustes())


@admin_bp.route('/banners/subir', methods=['POST'])
@super_admin_requerido
def banner_subir():
    """Sube una imagen de banner a una zona, con su destino (link)."""
    from PIL import Image, ImageOps

    zona = (request.form.get('zona') or '').strip().upper()
    if zona not in ZonaBanner.TODAS:
        flash('Zona inválida.', 'error')
        return redirect(url_for('admin.banners'))

    tope = MAX_BANNER_CENTRAL if zona == ZonaBanner.CENTRAL else MAX_BANNER_LATERAL
    if Banner.query.filter_by(zona=zona).count() >= tope:
        flash(f'Ya tenés el máximo de {tope} imágenes en {ZonaBanner.ETIQUETAS[zona]}. '
              f'Borrá una para subir otra.', 'warning')
        return redirect(url_for('admin.banners'))

    f = request.files.get('imagen')
    if not f or not f.filename:
        flash('No seleccionaste ninguna imagen.', 'error')
        return redirect(url_for('admin.banners'))
    ext = os.path.splitext(secure_filename(f.filename))[1].lower()
    if ext not in EXTENSIONES_IMG_BANNER:
        flash('Formato inválido. Subí una imagen JPG, PNG o WEBP.', 'error')
        return redirect(url_for('admin.banners'))

    destino_tipo = (request.form.get('destino_tipo') or DestinoBanner.NINGUNO).strip().upper()
    if destino_tipo not in DestinoBanner.TODOS:
        destino_tipo = DestinoBanner.NINGUNO
    destino_valor = (request.form.get('destino_valor') or '').strip() or None

    girar = (request.form.get('girar') == 'si')
    carpeta = _carpeta_banners()
    nombre_archivo = f'{zona.lower()}_{secrets.token_hex(4)}.jpg'
    try:
        img = Image.open(f.stream)
        img = ImageOps.exif_transpose(img)      # corrige fotos giradas (celular)
        img = img.convert('RGB')
        if girar:
            img = img.rotate(-90, expand=True)  # girar 90° horario, sin perder proporcion
        if zona == ZonaBanner.CENTRAL:
            img.thumbnail((1400, 700))          # ancho (carrusel)
        else:
            img.thumbnail((600, 1600))          # vertical (lateral)
        img.save(os.path.join(carpeta, nombre_archivo), 'JPEG', quality=85)
    except Exception:
        flash('No pude procesar esa imagen. Probá con otra.', 'error')
        return redirect(url_for('admin.banners'))

    orden = (db.session.query(func.coalesce(func.max(Banner.orden), 0))
             .filter(Banner.zona == zona).scalar() or 0) + 1
    db.session.add(Banner(zona=zona, imagen=nombre_archivo, orden=orden,
                          destino_tipo=destino_tipo, destino_valor=destino_valor,
                          activo=True))
    db.session.commit()
    flash('Banner agregado ✓', 'success')
    return redirect(url_for('admin.banners'))


@admin_bp.route('/banners/<int:bid>/borrar', methods=['POST'])
@super_admin_requerido
def banner_borrar(bid):
    """Elimina un banner (borra la fila y el archivo de imagen)."""
    b = Banner.query.get_or_404(bid)
    try:
        os.remove(os.path.join(_carpeta_banners(), b.imagen))
    except OSError:
        pass
    db.session.delete(b)
    db.session.commit()
    flash('Banner eliminado.', 'warning')
    return redirect(url_for('admin.banners'))


@admin_bp.route('/banners/<int:bid>/activo', methods=['POST'])
@super_admin_requerido
def banner_activo(bid):
    """Activa o pausa un banner sin borrarlo."""
    b = Banner.query.get_or_404(bid)
    b.activo = not b.activo
    db.session.commit()
    flash('Banner ' + ('activado' if b.activo else 'pausado') + '.', 'success')
    return redirect(url_for('admin.banners'))


# ======================= FOOD COST (v0.15 · en preparacion) =======================
# Placeholder de la futura seccion de Control de Compras / Food Cost.
# Deja la pestaña en el menu (solo super admin) lista para cuando tengamos la
# primera factura de muestra de Torres. NO toca la base de datos: es solo una
# pantalla informativa. El motor real (lectura de PDF + tablas) llega en v0.15.0.

@admin_bp.route('/food-cost')
@super_admin_requerido
def food_cost():
    """Placeholder de Food Cost. Esperando la primera factura de Torres."""
    return render_template('admin/food_cost.html')


# ======================= USUARIOS (v0.16 · solo super admin) =======================
# ABM de usuarios con perfil completo de la persona. Pensado tanto para las
# administradoras como para las revendedoras (Etapa 2: comisiones y niveles).
# Candados de seguridad:
#   - Solo el super admin entra (decorador).
#   - El rol SUPER_ADMIN NO se asigna desde el panel (solo existe Ivan via seed).
#   - No se borra a nadie: se desactiva (historial intacto).
#   - No te podes desactivar a vos mismo ni tocar al super admin.
#   - Tope de 5 administradoras.

def _password_temporal():
    """Genera una contrasena temporal corta y legible (ej: Salud-4827)."""
    return f'Salud-{secrets.randbelow(9000) + 1000}'


def _parse_fecha(s):
    """Convierte 'YYYY-MM-DD' (input date) a date, o None si viene vacio/mal."""
    s = (s or '').strip()
    if not s:
        return None
    try:
        return _dt.strptime(s, '%Y-%m-%d').date()
    except ValueError:
        return None


def _datos_perfil_del_form():
    """Lee del form los campos de perfil comunes (crear/editar)."""
    g = request.form.get
    forma = (g('forma_pago_comision') or '').strip().upper()
    return dict(
        nombre=(g('nombre') or '').strip(),
        apellido=(g('apellido') or '').strip() or None,
        dni=(g('dni') or '').strip() or None,
        cuit=(g('cuit') or '').strip() or None,
        fecha_nacimiento=_parse_fecha(g('fecha_nacimiento')),
        telefono=(g('telefono') or '').strip() or None,
        email=(g('email') or '').strip() or None,
        direccion=(g('direccion') or '').strip() or None,
        localidad=(g('localidad') or '').strip() or None,
        cbu_cvu=(g('cbu_cvu') or '').strip() or None,
        alias_cbu=(g('alias_cbu') or '').strip() or None,
        banco_fintech=(g('banco_fintech') or '').strip() or None,
        forma_pago_comision=(forma if forma in FormaPagoComision.TODAS else None),
        notas=(g('notas') or '').strip() or None,
    )


def _mensaje_bienvenida(u, clave, app_url, negocio):
    """
    Texto de bienvenida para mandarle a la revendedora por WhatsApp.
    Sin emojis a proposito: algunos telefonos los muestran como simbolos raros.
    """
    nombre = u.nombre or 'Hola'
    if clave:
        return (
            f'¡Hola {nombre}! Te damos la bienvenida como revendedora de {negocio}.\n\n'
            f'Estos son tus datos para ingresar:\n'
            f'Usuario: {u.usuario}\n'
            f'Contraseña temporal: {clave}\n'
            f'Ingresá acá: {app_url}\n\n'
            f'Cuando entres por primera vez, el sistema te va a pedir que cambies la '
            f'contraseña por una tuya. ¡Bienvenida!'
        )
    return (
        f'¡Hola {nombre}! Te dejamos tus datos de acceso a {negocio}.\n\n'
        f'Usuario: {u.usuario}\n'
        f'Ingresá acá: {app_url}\n\n'
        f'Si no recordás tu contraseña, avisanos y te la reseteamos.'
    )


@admin_bp.route('/usuarios')
@super_admin_requerido
def usuarios():
    """Lista de usuarios del sistema, filtrable por rol."""
    rol_sel = (request.args.get('rol') or '').strip().upper()
    stmt = Usuario.query
    if rol_sel in Rol.TODOS:
        stmt = stmt.filter_by(rol=rol_sel)
    lista = stmt.order_by(Usuario.rol, Usuario.nombre).all()

    # Conteos para los filtros
    n_admins = Usuario.query.filter_by(rol=Rol.ADMIN).count()
    n_super = Usuario.query.filter_by(rol=Rol.SUPER_ADMIN).count()

    # Codigo de ficha estable por orden de alta (id). Como no se borra (se
    # desactiva), el numero de cada uno queda fijo. Admins: ADMIN-001;
    # revendedoras: REV-001.
    admin_ids = [a.id for a in Usuario.query.filter_by(rol=Rol.ADMIN)
                 .order_by(Usuario.id).all()]
    num_adm = {uid: i + 1 for i, uid in enumerate(admin_ids)}
    revend_ids = [r.id for r in Usuario.query.filter_by(rol=Rol.REVENDEDORA)
                  .order_by(Usuario.id).all()]
    num_rev = {uid: i + 1 for i, uid in enumerate(revend_ids)}
    n_rev = len(revend_ids)
    for u in lista:
        if u.id in num_rev:
            u.codigo_rev = f'REV-{num_rev[u.id]:03d}'
        elif u.id in num_adm:
            u.codigo_rev = f'ADMIN-{num_adm[u.id]:03d}'
        else:
            u.codigo_rev = None

    return render_template('admin/usuarios.html', lista=lista, rol_sel=rol_sel,
                           roles=Rol.ETIQUETAS, n_admins=n_admins, max_admins=MAX_ADMINS,
                           n_rev=n_rev, n_super=n_super)


@admin_bp.route('/usuarios/<int:uid>/whatsapp', methods=['POST'])
@super_admin_requerido
def usuario_whatsapp(uid):
    """
    Manda el acceso por WhatsApp. Asegura SIEMPRE una clave temporal valida:
    si la persona todavia no entro y ya tiene una, la reusa; si no (o si ya habia
    cambiado la suya), genera una nueva temporal y la deja lista. Despues redirige
    a wa.me con el mensaje cargado. El target=_blank del form lo abre en otra pestaña.
    """
    u = Usuario.query.get_or_404(uid)
    if u.es_super_admin:
        abort(403)
    if not u.wa_numero:
        flash('Cargá el teléfono de la persona para poder enviarle el acceso.', 'error')
        return redirect(url_for('admin.usuarios'))

    if u.debe_cambiar_password and u.password_temporal:
        clave = u.password_temporal           # reusar la pendiente
    else:
        clave = _password_temporal()          # generar una nueva valida
        u.set_password(clave)
        u.debe_cambiar_password = True
        u.password_temporal = clave
        db.session.commit()

    app_url = current_app.config.get('APP_URL', '')
    negocio = get_ajustes().nombre_negocio
    mensaje = _mensaje_bienvenida(u, clave, app_url, negocio)
    return redirect(f'https://wa.me/{u.wa_numero}?text={quote(mensaje)}')


@admin_bp.route('/usuarios/nuevo', methods=['GET', 'POST'])
@super_admin_requerido
def usuario_nuevo():
    if request.method == 'POST':
        datos = _datos_perfil_del_form()
        login = (request.form.get('usuario') or '').strip().lower()
        rol = (request.form.get('rol') or '').strip().upper()
        pass_inicial = (request.form.get('password') or '').strip()

        if not login or not datos['nombre']:
            flash('El usuario (para ingresar) y el nombre son obligatorios.', 'error')
            return redirect(url_for('admin.usuario_nuevo'))
        if rol not in Rol.ASIGNABLES:
            flash('Rol inválido. Solo podés crear Administradoras o Revendedoras.', 'error')
            return redirect(url_for('admin.usuario_nuevo'))
        if Usuario.query.filter_by(usuario=login).first():
            flash(f'Ya existe un usuario "{login}". Elegí otro nombre de ingreso.', 'error')
            return redirect(url_for('admin.usuario_nuevo'))
        if rol == Rol.ADMIN and Usuario.query.filter_by(rol=Rol.ADMIN).count() >= MAX_ADMINS:
            flash(f'Ya tenés el máximo de {MAX_ADMINS} administradoras. '
                  f'Desactivá una antes de crear otra.', 'error')
            return redirect(url_for('admin.usuario_nuevo'))

        # Password: la que puso Ivan, o una temporal generada
        generada = None
        if not pass_inicial:
            pass_inicial = _password_temporal()
            generada = pass_inicial

        u = Usuario(usuario=login, rol=rol, activo=True,
                    debe_cambiar_password=True, password_temporal=pass_inicial, **datos)
        u.set_password(pass_inicial)
        db.session.add(u)
        db.session.commit()

        if generada:
            flash(f'Usuario "{login}" creado ✓ · Contraseña temporal: {generada} '
                  f'— pasásela por WhatsApp; al entrar el sistema la obliga a cambiarla.',
                  'success')
        else:
            flash(f'Usuario "{login}" creado ✓ — al entrar va a tener que cambiar la contraseña.',
                  'success')
        return redirect(url_for('admin.usuarios'))

    return render_template('admin/usuario_form.html', u=None,
                           roles_asignables=[(r, Rol.ETIQUETAS[r]) for r in Rol.ASIGNABLES],
                           formas_comision=FormaPagoComision.ETIQUETAS)


@admin_bp.route('/usuarios/<int:uid>/editar', methods=['GET', 'POST'])
@super_admin_requerido
def usuario_editar(uid):
    u = Usuario.query.get_or_404(uid)
    if u.es_super_admin:
        flash('El Super Administrador no se edita desde este panel.', 'warning')
        return redirect(url_for('admin.usuarios'))

    if request.method == 'POST':
        datos = _datos_perfil_del_form()
        rol = (request.form.get('rol') or '').strip().upper()
        if not datos['nombre']:
            flash('El nombre es obligatorio.', 'error')
            return redirect(url_for('admin.usuario_editar', uid=uid))
        if rol not in Rol.ASIGNABLES:
            flash('Rol inválido.', 'error')
            return redirect(url_for('admin.usuario_editar', uid=uid))
        # Si pasa a ADMIN (y no lo era), controlar el cupo
        if rol == Rol.ADMIN and u.rol != Rol.ADMIN:
            if Usuario.query.filter_by(rol=Rol.ADMIN).count() >= MAX_ADMINS:
                flash(f'Ya tenés el máximo de {MAX_ADMINS} administradoras.', 'error')
                return redirect(url_for('admin.usuario_editar', uid=uid))

        for k, v in datos.items():
            setattr(u, k, v)
        u.rol = rol
        db.session.commit()
        flash(f'Usuario "{u.usuario}" actualizado ✓', 'success')
        return redirect(url_for('admin.usuarios'))

    return render_template('admin/usuario_form.html', u=u,
                           roles_asignables=[(r, Rol.ETIQUETAS[r]) for r in Rol.ASIGNABLES],
                           formas_comision=FormaPagoComision.ETIQUETAS)


@admin_bp.route('/usuarios/<int:uid>/activo', methods=['POST'])
@super_admin_requerido
def usuario_activo(uid):
    u = Usuario.query.get_or_404(uid)
    if u.es_super_admin:
        flash('No podés desactivar al Super Administrador.', 'error')
        return redirect(url_for('admin.usuarios'))
    if u.id == current_user.id:
        flash('No podés desactivarte a vos mismo.', 'error')
        return redirect(url_for('admin.usuarios'))
    u.activo = not u.activo
    db.session.commit()
    flash(f'Usuario "{u.usuario}" ' + ('activado' if u.activo else 'desactivado') + '.',
          'success')
    return redirect(url_for('admin.usuarios'))


@admin_bp.route('/usuarios/<int:uid>/reset-password', methods=['POST'])
@super_admin_requerido
def usuario_reset(uid):
    u = Usuario.query.get_or_404(uid)
    if u.es_super_admin:
        flash('La contraseña del Super Administrador no se resetea desde acá.', 'error')
        return redirect(url_for('admin.usuarios'))
    nueva = _password_temporal()
    u.set_password(nueva)
    u.debe_cambiar_password = True
    u.password_temporal = nueva
    db.session.commit()
    flash(f'Contraseña de "{u.usuario}" reseteada · Nueva temporal: {nueva} '
          f'— pasásela por WhatsApp; al entrar la tiene que cambiar.', 'success')
    return redirect(url_for('admin.usuarios'))


# ======================= CLIENTES (v0.17 · CRM base) =======================
# Base de clientes compartida. La gestionan los admins (Juliana, etc.) y mas
# adelante tambien las revendedoras desde su portal. 'revendedora_id' marca de
# quien es cada cliente (o "de la casa" si queda sin asignar).

def _datos_cliente_del_form():
    g = request.form.get
    rev_id = g('revendedora_id')
    try:
        rev_id = int(rev_id) if rev_id else None
    except (TypeError, ValueError):
        rev_id = None
    return dict(
        nombre=(g('nombre') or '').strip(),
        apellido=(g('apellido') or '').strip() or None,
        dni_cuit=(g('dni_cuit') or '').strip() or None,
        telefono=(g('telefono') or '').strip() or None,
        email=(g('email') or '').strip() or None,
        direccion=(g('direccion') or '').strip() or None,
        localidad=(g('localidad') or '').strip() or None,
        notas=(g('notas') or '').strip() or None,
        revendedora_id=rev_id,
    )


@admin_bp.route('/clientes')
@admin_requerido
def clientes():
    """Lista de clientes, con búsqueda y filtro por revendedora."""
    q = (request.args.get('q') or '').strip()
    rev_sel = request.args.get('rev', type=int)

    stmt = Cliente.query
    if rev_sel:
        stmt = stmt.filter_by(revendedora_id=rev_sel)
    if q:
        like = f'%{q}%'
        stmt = stmt.filter(or_(Cliente.nombre.ilike(like), Cliente.apellido.ilike(like),
                               Cliente.dni_cuit.ilike(like), Cliente.telefono.ilike(like)))
    lista = stmt.order_by(Cliente.activo.desc(), Cliente.nombre).all()

    revendedoras = (Usuario.query.filter_by(rol=Rol.REVENDEDORA)
                    .order_by(Usuario.nombre).all())
    total = Cliente.query.count()
    return render_template('admin/clientes.html', lista=lista, revendedoras=revendedoras,
                           rev_sel=rev_sel, q=q, total=total)


@admin_bp.route('/clientes/nuevo', methods=['GET', 'POST'])
@admin_requerido
def cliente_nuevo():
    if request.method == 'POST':
        datos = _datos_cliente_del_form()
        if not datos['nombre']:
            flash('El nombre del cliente es obligatorio.', 'error')
            return redirect(url_for('admin.cliente_nuevo'))
        c = Cliente(activo=True, creado_por=current_user.nombre, **datos)
        db.session.add(c)
        db.session.commit()
        flash(f'Cliente "{c.nombre_completo}" creado ✓', 'success')
        return redirect(url_for('admin.clientes'))

    revendedoras = (Usuario.query.filter_by(rol=Rol.REVENDEDORA)
                    .order_by(Usuario.nombre).all())
    return render_template('admin/cliente_form.html', c=None, revendedoras=revendedoras)


@admin_bp.route('/clientes/<int:cid>/editar', methods=['GET', 'POST'])
@admin_requerido
def cliente_editar(cid):
    c = Cliente.query.get_or_404(cid)
    if request.method == 'POST':
        datos = _datos_cliente_del_form()
        if not datos['nombre']:
            flash('El nombre del cliente es obligatorio.', 'error')
            return redirect(url_for('admin.cliente_editar', cid=cid))
        for k, v in datos.items():
            setattr(c, k, v)
        db.session.commit()
        flash(f'Cliente "{c.nombre_completo}" actualizado ✓', 'success')
        return redirect(url_for('admin.clientes'))

    revendedoras = (Usuario.query.filter_by(rol=Rol.REVENDEDORA)
                    .order_by(Usuario.nombre).all())
    return render_template('admin/cliente_form.html', c=c, revendedoras=revendedoras)


@admin_bp.route('/clientes/<int:cid>/activo', methods=['POST'])
@admin_requerido
def cliente_activo(cid):
    c = Cliente.query.get_or_404(cid)
    c.activo = not c.activo
    db.session.commit()
    flash(f'Cliente "{c.nombre_completo}" ' + ('activado' if c.activo else 'desactivado') + '.',
          'success')
    return redirect(url_for('admin.clientes'))


# ======================= AJUSTES =======================
@admin_bp.route('/ajustes', methods=['GET', 'POST'])
@admin_requerido
def ajustes():
    aj = get_ajustes()

    if request.method == 'POST':
        try:
            markup = float(request.form.get('markup_general', aj.markup_general))
            minimo = float(request.form.get('markup_minimo', aj.markup_minimo))
            dx5 = float(request.form.get('desc_x5', aj.desc_x5))
            dx10 = float(request.form.get('desc_x10', aj.desc_x10))
            min_compra = float(request.form.get('minimo_compra', aj.minimo_compra))
            whatsapp = (request.form.get('whatsapp') or aj.whatsapp).strip()
            negocio = (request.form.get('nombre_negocio') or aj.nombre_negocio).strip()
        except ValueError:
            flash('Revisá los valores: tienen que ser números.', 'error')
            return redirect(url_for('admin.ajustes'))

        if minimo < 20:
            minimo = 20
            flash('El margen mínimo no puede bajar de 20%. Lo dejé en 20%.', 'warning')
        if markup < minimo:
            flash(f'El markup general no puede ser menor al mínimo ({minimo:.0f}%). '
                  'Ajustalo y guardá de nuevo.', 'error')
            return redirect(url_for('admin.ajustes'))

        aj.markup_general = markup
        aj.markup_minimo = minimo
        aj.desc_x5 = dx5
        aj.desc_x10 = dx10
        aj.minimo_compra = min_compra
        aj.whatsapp = whatsapp
        aj.nombre_negocio = negocio
        db.session.commit()
        flash('Ajustes guardados ✓ Los precios del catálogo ya reflejan los cambios.', 'success')
        return redirect(url_for('admin.ajustes'))

    return render_template('admin/ajustes.html', aj=aj)


# ======================= IMPORTAR =======================

@admin_bp.route('/importar', methods=['GET', 'POST'])
@super_admin_requerido
def importar():
    if request.method == 'POST':
        archivo = request.files.get('planilla')
        if not archivo or archivo.filename == '':
            flash('No seleccionaste ningún archivo.', 'error')
            return redirect(url_for('admin.importar'))

        nombre = secure_filename(archivo.filename)
        ext = os.path.splitext(nombre)[1].lower()
        if ext not in EXTENSIONES_OK:
            flash('Formato no válido. Subí un archivo .xlsx o .csv', 'error')
            return redirect(url_for('admin.importar'))

        tmp_dir = tempfile.gettempdir()
        ruta = os.path.join(tmp_dir, nombre)
        archivo.save(ruta)

        try:
            productos, resumen = leer_planilla(ruta)
            res = aplicar_importacion(productos)
        except ValueError as e:
            flash(f'No se pudo importar: {e}', 'error')
            return redirect(url_for('admin.importar'))
        except Exception as e:
            flash(f'Error inesperado al importar: {e}', 'error')
            return redirect(url_for('admin.importar'))
        finally:
            try:
                os.remove(ruta)
            except OSError:
                pass

        flash(
            f'Planilla importada ✓  '
            f'{res["nuevos"]} nuevos · {res["actualizados"]} actualizados · '
            f'{res["total"]} productos en total'
            + (f' · {res["fuera_de_lista"]} fuera de la última lista'
               if res['fuera_de_lista'] else ''),
            'success')
        return redirect(url_for('admin.catalogo'))

    return render_template('admin/importar.html')
