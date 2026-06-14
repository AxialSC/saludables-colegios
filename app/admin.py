"""
app/admin.py — Blueprint del panel administrativo (El Arquitecto).
v0.1 Dashboard · v0.2 Catalogo + Importar · v0.3 Ajustes
v0.6 -> Panel de PEDIDOS (CRM de ventas de Juliana)
"""
import os
import tempfile

from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, abort, Response)
from flask_login import login_required, current_user
from sqlalchemy import select, or_, func
from werkzeug.utils import secure_filename

from .extensions import db
from .models import (Producto, Pedido, Cobro, get_ajustes,
                     EstadoPedido, FormaPago)
from .services import aplicar_importacion
from .utils.decorators import admin_requerido, super_admin_requerido
from .utils.import_planilla import leer_planilla
from .utils.timezone import ahora_argentina
from .pdf_pedido import generar_pdf_pedido
from . import pricing

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

EXTENSIONES_OK = ('.xlsx', '.xlsm', '.csv')


def _ahora():
    return ahora_argentina().replace(tzinfo=None)


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


# ======================= CATALOGO =======================

@admin_bp.route('/catalogo')
@admin_requerido
def catalogo():
    page = request.args.get('page', 1, type=int)
    q = (request.args.get('q') or '').strip()
    rubro = (request.args.get('rubro') or '').strip()

    stmt = select(Producto)
    if rubro:
        stmt = stmt.where(Producto.rubro == rubro)
    if q:
        like = f'%{q}%'
        stmt = stmt.where(or_(Producto.nombre.ilike(like),
                              Producto.codigo.ilike(like)))
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
                           q=q, rubro_sel=rubro, total=total, ajustes=ajustes)


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
