"""
app/admin.py — Blueprint del panel administrativo (El Arquitecto).
v0.1.0 -> Dashboard
v0.2.0 -> Catalogo + Importar planilla (solo super admin)
v0.3.0 -> Ajustes (markup/descuentos) + precio de venta visible en el catalogo
"""
import os
import tempfile

from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash)
from flask_login import login_required, current_user
from sqlalchemy import select, or_
from werkzeug.utils import secure_filename

from .extensions import db
from .models import Producto, get_ajustes
from .services import aplicar_importacion
from .utils.decorators import admin_requerido, super_admin_requerido
from .utils.import_planilla import leer_planilla
from . import pricing

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

EXTENSIONES_OK = ('.xlsx', '.xlsm', '.csv')


@admin_bp.before_request
@login_required
def _forzar_cambio_password():
    if current_user.is_authenticated and current_user.debe_cambiar_password:
        return redirect(url_for('auth.cambiar_password'))


@admin_bp.route('/')
@admin_requerido
def dashboard():
    stats = {
        'productos': Producto.query.filter_by(activo=True).count(),
        'clientes': 0,
        'pedidos_pendientes': 0,
        'ventas_mes': 0,
    }
    return render_template('admin/dashboard.html', stats=stats)


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
    # Calculamos el precio de venta (x1) de cada producto para que Juliana lo vea
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

        # Piso de seguridad: el minimo no puede ser menor a 20 (regla del negocio)
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
