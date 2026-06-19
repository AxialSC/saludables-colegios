"""
app/admin.py — Blueprint del panel administrativo (El Arquitecto).
v0.1 Dashboard · v0.2 Catalogo + Importar · v0.3 Ajustes
v0.6 -> Panel de PEDIDOS (CRM de ventas de Juliana)
v0.9 -> Historial de modificaciones con código (prolijo)
v0.12 -> OFERTAS: publicar productos en oferta por 7 dias (piso 10% blindado)
"""
import os
import tempfile
from datetime import timedelta

from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, abort, Response, current_app, jsonify)
from flask_login import login_required, current_user
from sqlalchemy import select, or_, func
from werkzeug.utils import secure_filename

from .extensions import db
from .models import (Producto, Pedido, Cobro, ModificacionPedido, ItemPedido,
                     get_ajustes, EstadoPedido, FormaPago, CategoriaProducto,
                     Oferta)
from .services import aplicar_importacion
from .utils.decorators import admin_requerido, super_admin_requerido
from .utils.import_planilla import leer_planilla
from .utils.timezone import ahora_argentina
from .pdf_pedido import generar_pdf_pedido
from . import pricing

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

EXTENSIONES_OK = ('.xlsx', '.xlsm', '.csv')

# Dias que dura una oferta publicada (v0.12)
DIAS_OFERTA = 7


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
