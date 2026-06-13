"""
app/auth.py — Blueprint de autenticacion.
Login / Logout / Cambio de contrasena obligatorio en primer ingreso.
"""
from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash)
from flask_login import login_user, logout_user, login_required, current_user

from .extensions import db
from .models import Usuario
from .utils.timezone import ahora_argentina

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # Si ya esta logueado, va directo al panel
    if current_user.is_authenticated:
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        usuario = (request.form.get('usuario') or '').strip()
        password = request.form.get('password') or ''

        u = Usuario.query.filter_by(usuario=usuario).first()
        if u and u.activo and u.check_password(password):
            login_user(u)
            u.ultimo_acceso = ahora_argentina().replace(tzinfo=None)
            db.session.commit()
            if u.debe_cambiar_password:
                return redirect(url_for('auth.cambiar_password'))
            return redirect(url_for('admin.dashboard'))

        flash('Usuario o contrasena incorrectos.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/cambiar-password', methods=['GET', 'POST'])
@login_required
def cambiar_password():
    if request.method == 'POST':
        actual = request.form.get('actual') or ''
        nueva = request.form.get('nueva') or ''
        repetir = request.form.get('repetir') or ''

        if not current_user.check_password(actual):
            flash('La contrasena actual no es correcta.', 'error')
        elif len(nueva) < 6:
            flash('La nueva contrasena debe tener al menos 6 caracteres.', 'error')
        elif nueva != repetir:
            flash('Las contrasenas nuevas no coinciden.', 'error')
        else:
            current_user.set_password(nueva)
            current_user.debe_cambiar_password = False
            db.session.commit()
            flash('Contrasena actualizada con exito.', 'success')
            return redirect(url_for('admin.dashboard'))

    return render_template('auth/cambiar_password.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Sesion cerrada.', 'success')
    return redirect(url_for('auth.login'))
