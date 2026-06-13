"""
app/admin.py — Blueprint del panel administrativo (El Arquitecto).
v0.1.0 -> Dashboard placeholder. Catalogo/Importar/Clientes/Pedidos/Reportes
llegan en las proximas versiones.
"""
from flask import Blueprint, render_template, redirect, url_for
from flask_login import login_required, current_user

from .utils.decorators import admin_requerido

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')


@admin_bp.before_request
@login_required
def _forzar_cambio_password():
    """Si el usuario todavia tiene la contrasena temporal, lo manda a cambiarla."""
    if current_user.is_authenticated and current_user.debe_cambiar_password:
        return redirect(url_for('auth.cambiar_password'))


@admin_bp.route('/')
@admin_requerido
def dashboard():
    # Datos placeholder hasta tener catalogo/clientes/pedidos reales
    stats = {
        'productos': 0,
        'clientes': 0,
        'pedidos_pendientes': 0,
        'ventas_mes': 0,
    }
    return render_template('admin/dashboard.html', stats=stats)
