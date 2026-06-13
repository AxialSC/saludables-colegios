"""
app/models.py — Modelos SQLAlchemy.

v0.1.0 -> Solo Usuario + Rol (lo necesario para login).
Los modelos Producto / Cliente / Pedido se agregan en las proximas versiones
(v0.2.0 importador, v0.6.0 CRM), para ir paso a paso.
"""
from flask_login import UserMixin

from .extensions import db, bcrypt
from .utils.timezone import ahora_argentina


class Rol:
    """Roles del sistema (string simple, evita bugs de comparacion de Enum)."""
    SUPER_ADMIN = 'SUPER_ADMIN'   # Ivan (dueno del sistema, carga planillas)
    ADMIN = 'ADMIN'               # Juliana (administra todo menos importar)
    REVENDEDORA = 'REVENDEDORA'   # Futuro (v0.8.0)

    TODOS = (SUPER_ADMIN, ADMIN, REVENDEDORA)
    ETIQUETAS = {
        SUPER_ADMIN: 'Super Administrador',
        ADMIN: 'Administradora',
        REVENDEDORA: 'Revendedora',
    }


class Usuario(UserMixin, db.Model):
    __tablename__ = 'usuarios'

    id = db.Column(db.Integer, primary_key=True)
    usuario = db.Column(db.String(50), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(120), nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False, default=Rol.ADMIN)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    # Obliga a cambiar la contrasena en el primer ingreso (regla de seguridad)
    debe_cambiar_password = db.Column(db.Boolean, nullable=False, default=True)
    creado = db.Column(db.DateTime, default=lambda: ahora_argentina().replace(tzinfo=None))
    ultimo_acceso = db.Column(db.DateTime, nullable=True)

    # --- Password ---
    def set_password(self, raw):
        self.password_hash = bcrypt.generate_password_hash(raw).decode('utf-8')

    def check_password(self, raw):
        return bcrypt.check_password_hash(self.password_hash, raw)

    # --- Helpers de rol ---
    @property
    def es_super_admin(self):
        return self.rol == Rol.SUPER_ADMIN

    @property
    def es_admin(self):
        # Super admin tambien tiene permisos de admin
        return self.rol in (Rol.SUPER_ADMIN, Rol.ADMIN)

    @property
    def rol_etiqueta(self):
        return Rol.ETIQUETAS.get(self.rol, self.rol)

    def __repr__(self):
        return f'<Usuario {self.usuario} ({self.rol})>'
