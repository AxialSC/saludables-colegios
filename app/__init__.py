"""
app/__init__.py — Application Factory del Sistema Saludables.
AXIAL SECURITY · Ivan Abrigo
"""
import os
from flask import Flask, render_template, redirect, url_for

from config import config
from .extensions import db, bcrypt, login_manager, csrf
from .utils.timezone import ahora_argentina, registrar_filtros_jinja


def create_app(config_name=None):
    config_name = config_name or os.environ.get('FLASK_CONFIG', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    # Asegurar que exista la carpeta instance/ (donde vive la BD SQLite)
    instance_dir = os.path.join(os.path.dirname(app.root_path), 'instance')
    os.makedirs(instance_dir, exist_ok=True)

    # --- Inicializar extensiones ---
    db.init_app(app)
    bcrypt.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Por favor ingresá para continuar.'
    login_manager.login_message_category = 'error'

    # --- User loader ---
    from .models import Usuario

    @login_manager.user_loader
    def load_user(user_id):
        return Usuario.query.get(int(user_id))

    # --- Filtros Jinja (fechas Argentina) ---
    registrar_filtros_jinja(app)

    @app.template_filter('pesos')
    def _pesos(valor):
        try:
            v = float(valor)
        except (TypeError, ValueError):
            return valor
        s = f'{v:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
        return '$' + s

    # --- Variables disponibles en TODOS los templates (footer con version, etc) ---
    @app.context_processor
    def inject_app_data():
        return dict(
            app_version=app.config.get('APP_VERSION', ''),
            app_nombre=app.config.get('APP_NOMBRE', ''),
            app_subtitulo=app.config.get('APP_SUBTITULO', ''),
            now=ahora_argentina().replace(tzinfo=None),
        )

    # --- Blueprints ---
    from .auth import auth_bp
    from .admin import admin_bp
    from .cliente import cliente_bp
    app.register_blueprint(cliente_bp)   # tienda publica en la raiz '/'
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)

    # --- Manejo de errores ---
    @app.errorhandler(403)
    def err_403(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def err_404(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def err_500(e):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    # --- Comandos CLI ---
    from .cli import registrar_comandos
    registrar_comandos(app)

    return app
