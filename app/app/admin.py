"""
app/admin.py — Blueprint del panel administrativo (El Arquitecto).
v0.1.0 -> Dashboard
v0.2.0 -> Catalogo (ver productos) + Importar planilla (solo super admin)
"""
import os
import tempfile

from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, current_app)
from flask_login import login_required, current_user
from sqlalchemy import select, or_
from werkzeug.utils import secure_filename

from .extensions import db
from .models import Producto
from .services import aplicar_importacion
from .utils.decorators import admin_requerido, super_admin_requerido
from .utils.import_planilla import leer_planilla

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

    rubros = db.session.execute(
        select(Producto.rubro).distinct().order_by(Producto.rubro)
    ).scalars().all()

    total = Producto.query.count()

    return render_template('admin/catalogo.html',
                           paginacion=paginacion, rubros=rubros,
                           q=q, rubro_sel=rubro, total=total)


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

        # Guardamos el archivo en una ubicacion temporal para leerlo
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
