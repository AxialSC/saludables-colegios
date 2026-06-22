"""
app/revendedora.py — Portal propio de cada REVENDEDORA (v0.18.0).
AXIAL SECURITY · Ivan Abrigo

Cuando una revendedora loguea, el login la trae acá (no al panel admin).
Por ahora tiene:
  - Dashboard con su resumen (sus clientes, su nivel/comision).
  - Gestion de SUS clientes (los de revendedora_id == ella). Defensa en
    profundidad: cada accion valida que el cliente sea suyo.

Sobre esta base se montan despues: Ventas, comisiones, metricas, niveles,
estrellas y la pestaña de Redes Sociales.
"""
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, abort)
from flask_login import login_required, current_user

from .extensions import db
from .models import Cliente
from .utils.decorators import revendedora_requerido

revendedora_bp = Blueprint('revendedora', __name__, url_prefix='/portal')


# Niveles de comision (Etapa 2). Por ahora todas arrancan en el nivel inicial;
# cuando exista el modulo de Ventas, el nivel sube segun lo vendido.
NIVELES = [
    {'nombre': 'Inicial', 'comision': 2, 'desde': 0},
    {'nombre': 'Plata',   'comision': 3, 'desde': 5_000_000},
    {'nombre': 'Oro',     'comision': 4, 'desde': 10_000_000},
]


def _nivel_actual(vendido_total=0):
    nivel = NIVELES[0]
    for n in NIVELES:
        if vendido_total >= n['desde']:
            nivel = n
    return nivel


@revendedora_bp.before_request
@login_required
def _forzar_cambio_password():
    # Igual que el panel admin: si tiene clave temporal, primero la cambia.
    if current_user.is_authenticated and current_user.debe_cambiar_password:
        return redirect(url_for('auth.cambiar_password'))


def _mi_cliente_o_404(cid):
    """Trae el cliente solo si es de la revendedora logueada (sino 404/403)."""
    c = Cliente.query.get_or_404(cid)
    if c.revendedora_id != current_user.id:
        abort(403)
    return c


def _datos_cliente_del_form():
    g = request.form.get
    return dict(
        nombre=(g('nombre') or '').strip(),
        apellido=(g('apellido') or '').strip() or None,
        dni_cuit=(g('dni_cuit') or '').strip() or None,
        telefono=(g('telefono') or '').strip() or None,
        email=(g('email') or '').strip() or None,
        direccion=(g('direccion') or '').strip() or None,
        localidad=(g('localidad') or '').strip() or None,
        notas=(g('notas') or '').strip() or None,
    )


@revendedora_bp.route('/')
@revendedora_requerido
def dashboard():
    mis = Cliente.query.filter_by(revendedora_id=current_user.id)
    n_clientes = mis.count()
    n_activos = mis.filter_by(activo=True).count()

    # Por ahora sin ventas: nivel inicial. Cuando exista Ventas, se calcula real.
    vendido_total = 0
    nivel = _nivel_actual(vendido_total)

    return render_template('revendedora/dashboard.html',
                           n_clientes=n_clientes, n_activos=n_activos,
                           nivel=nivel, niveles=NIVELES, vendido_total=vendido_total)


@revendedora_bp.route('/clientes')
@revendedora_requerido
def clientes():
    q = (request.args.get('q') or '').strip()
    stmt = Cliente.query.filter_by(revendedora_id=current_user.id)
    if q:
        like = f'%{q}%'
        from sqlalchemy import or_
        stmt = stmt.filter(or_(Cliente.nombre.ilike(like), Cliente.apellido.ilike(like),
                               Cliente.dni_cuit.ilike(like), Cliente.telefono.ilike(like)))
    lista = stmt.order_by(Cliente.activo.desc(), Cliente.nombre).all()
    total = Cliente.query.filter_by(revendedora_id=current_user.id).count()
    return render_template('revendedora/clientes.html', lista=lista, q=q, total=total)


@revendedora_bp.route('/clientes/nuevo', methods=['GET', 'POST'])
@revendedora_requerido
def cliente_nuevo():
    if request.method == 'POST':
        datos = _datos_cliente_del_form()
        if not datos['nombre']:
            flash('El nombre del cliente es obligatorio.', 'error')
            return redirect(url_for('revendedora.cliente_nuevo'))
        c = Cliente(activo=True, revendedora_id=current_user.id,
                    creado_por=current_user.nombre, **datos)
        db.session.add(c)
        db.session.commit()
        flash(f'Cliente "{c.nombre_completo}" agregado ✓', 'success')
        return redirect(url_for('revendedora.clientes'))
    return render_template('revendedora/cliente_form.html', c=None)


@revendedora_bp.route('/clientes/<int:cid>/editar', methods=['GET', 'POST'])
@revendedora_requerido
def cliente_editar(cid):
    c = _mi_cliente_o_404(cid)
    if request.method == 'POST':
        datos = _datos_cliente_del_form()
        if not datos['nombre']:
            flash('El nombre del cliente es obligatorio.', 'error')
            return redirect(url_for('revendedora.cliente_editar', cid=cid))
        for k, v in datos.items():
            setattr(c, k, v)
        db.session.commit()
        flash(f'Cliente "{c.nombre_completo}" actualizado ✓', 'success')
        return redirect(url_for('revendedora.clientes'))
    return render_template('revendedora/cliente_form.html', c=c)


@revendedora_bp.route('/clientes/<int:cid>/activo', methods=['POST'])
@revendedora_requerido
def cliente_activo(cid):
    c = _mi_cliente_o_404(cid)
    c.activo = not c.activo
    db.session.commit()
    flash(f'Cliente "{c.nombre_completo}" ' + ('activado' if c.activo else 'desactivado') + '.',
          'success')
    return redirect(url_for('revendedora.clientes'))
