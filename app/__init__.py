"""
app/__init__.py — Application Factory del Sistema Saludables.
AXIAL SECURITY · Ivan Abrigo

v0.21.0 -> E0:
  1) Manejador de CSRFError: se acabo el "Bad Request / The CSRF token has
     expired" crudo. Ahora avisa lindo y manda a donde corresponde.
  2) Sesion PERMANENTE + auto-logout REAL en el servidor (no solo JavaScript).
  3) Ruta /sesion/ping: el "heartbeat" que manda el navegador cuando hay
     actividad real, para mantener sincronizado el reloj del servidor con la
     barrita que ve el usuario.
"""
import os
from flask import (Flask, render_template, redirect, url_for, session,
                   flash, request)
from flask_wtf.csrf import CSRFError

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
            redes=app.config.get('REDES', {}),
            now=ahora_argentina().replace(tzinfo=None),
        )

    # ======================================================================
    #  v0.21.0 · SESION CON VENCIMIENTO REAL (server-side)
    # ======================================================================
    # Flask, por defecto, usa cookies de sesion "de navegador": duran hasta que
    # se cierra el navegador y NO tienen vencimiento por inactividad. Marcando
    # la sesion como 'permanent', pasa a regir PERMANENT_SESSION_LIFETIME
    # (config.py) y la cookie SE VENCE SOLA por inactividad.
    #
    # ¿Por que importa? Porque el auto-logout de v0.20.1 era SOLO JavaScript.
    # Cualquiera que cerrara la solapa (o tocara la consola del navegador) se
    # quedaba con la sesion viva. Ahora el que decide es el SERVIDOR.
    #
    # Con SESSION_REFRESH_EACH_REQUEST=True, cada request valida renueva el
    # plazo. El "heartbeat" de abajo es lo que hace que mover el mouse tambien
    # cuente como actividad para el servidor, no solo para la barrita.
    @app.before_request
    def _sesion_permanente():
        session.permanent = True

    @app.route('/sesion/ping')
    def sesion_ping():
        """
        Heartbeat de sesion. El navegador lo llama cada tanto MIENTRAS HAYA
        ACTIVIDAD REAL del usuario (mouse, teclado, scroll, touch).

        No devuelve nada (204 = "todo bien, sin contenido"). Su unico efecto es
        ser un request valido, y por lo tanto renovar la cookie de sesion.

        Si el usuario se fue a tomar un cafe, el navegador NO llama a esta ruta,
        la cookie no se renueva, y la sesion se muere sola. Que es justo lo que
        queremos.

        Es GET a proposito: los GET no llevan token CSRF, asi que este ping nunca
        puede fallar por un token vencido (seria ironico, justamente).
        """
        return ('', 204)

    # ======================================================================
    #  v0.21.0 · CSRF VENCIDO -> mensaje humano, no "Bad Request"
    # ======================================================================
    @app.errorhandler(CSRFError)
    def err_csrf(e):
        """
        Atrapa el token CSRF vencido/invalido y, en vez de la pantalla cruda de
        'Bad Request' en Times New Roman, devuelve al usuario a donde tiene que
        estar, con un mensaje que se entiende.

        Ojo con el detalle: si el que falla es un formulario de la TIENDA PUBLICA
        (ej: el form de suscriptores), mandarlo al login seria un desproposito
        -- esa persona no tiene cuenta ni la necesita. A esos los devolvemos al
        catalogo.
        """
        if request.blueprint == 'cliente':
            flash('El formulario venció por seguridad. Completalo de nuevo, por favor.',
                  'error')
            return redirect(url_for('cliente.catalogo')), 302

        flash('Tu sesión venció por seguridad. Ingresá de nuevo para continuar.',
              'warning')
        return redirect(url_for('auth.login')), 302

    # --- Blueprints ---
    from .auth import auth_bp
    from .admin import admin_bp
    from .cliente import cliente_bp
    from .revendedora import revendedora_bp
    app.register_blueprint(cliente_bp)   # tienda publica en la raiz '/'
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(revendedora_bp)   # portal de revendedoras en '/portal'

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
