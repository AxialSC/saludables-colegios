"""
app/models.py — Modelos SQLAlchemy.

v0.1.0 -> Usuario + Rol (login)
v0.2.0 -> Producto (catalogo importado desde la planilla del mayorista)
"""
from flask_login import UserMixin

from .extensions import db, bcrypt
from .utils.timezone import ahora_argentina


def _ahora():
    return ahora_argentina().replace(tzinfo=None)


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
    debe_cambiar_password = db.Column(db.Boolean, nullable=False, default=True)
    creado = db.Column(db.DateTime, default=_ahora)
    ultimo_acceso = db.Column(db.DateTime, nullable=True)

    def set_password(self, raw):
        self.password_hash = bcrypt.generate_password_hash(raw).decode('utf-8')

    def check_password(self, raw):
        return bcrypt.check_password_hash(self.password_hash, raw)

    @property
    def es_super_admin(self):
        return self.rol == Rol.SUPER_ADMIN

    @property
    def es_admin(self):
        return self.rol in (Rol.SUPER_ADMIN, Rol.ADMIN)

    @property
    def rol_etiqueta(self):
        return Rol.ETIQUETAS.get(self.rol, self.rol)

    def __repr__(self):
        return f'<Usuario {self.usuario} ({self.rol})>'


# IVA general de Argentina (se usa para mostrar precios con IVA)
IVA = 0.21


class Producto(db.Model):
    """
    Producto del catalogo. Se carga/actualiza desde la planilla del mayorista.
    El 'costo_neto' es el precio SIN IVA tal como viene en la columna 'Pcio'.
    """
    __tablename__ = 'productos'

    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(40), unique=True, nullable=False, index=True)
    nombre = db.Column(db.String(255), nullable=False)
    rubro = db.Column(db.String(80), nullable=False, index=True)
    # Costo del mayorista SIN IVA (3 decimales como viene en la planilla)
    costo_neto = db.Column(db.Numeric(12, 3), nullable=False)

    # Campos para las proximas versiones (se crean ahora para no migrar despues)
    marca = db.Column(db.String(80), nullable=True, index=True)         # v0.3 (buscador)
    imagen = db.Column(db.String(255), nullable=True)                   # v0.5 (fotos)
    margen_individual = db.Column(db.Numeric(5, 2), nullable=True)      # v0.3 (markup x producto)
    destacado = db.Column(db.Boolean, nullable=False, default=False)    # v0.x (ofertas)

    activo = db.Column(db.Boolean, nullable=False, default=True)
    # Marca si el producto vino en la ultima planilla importada
    en_ultima_lista = db.Column(db.Boolean, nullable=False, default=True)

    creado = db.Column(db.DateTime, default=_ahora)
    actualizado = db.Column(db.DateTime, default=_ahora)

    @property
    def costo_con_iva(self):
        return float(self.costo_neto) * (1 + IVA)

    def __repr__(self):
        return f'<Producto {self.codigo} {self.nombre[:25]}>'


class Ajustes(db.Model):
    """
    Configuracion del negocio (una sola fila). Centraliza markup, descuentos,
    minimo de compra y WhatsApp. Se usa para calcular los precios de venta.
    """
    __tablename__ = 'ajustes'

    id = db.Column(db.Integer, primary_key=True)
    # Markup general de la web (margen sobre venta, Opcion 1). Editable por Juliana.
    markup_general = db.Column(db.Numeric(5, 2), nullable=False, default=30)
    # Piso de seguridad: nunca se vende por debajo de este margen
    markup_minimo = db.Column(db.Numeric(5, 2), nullable=False, default=20)
    # Descuentos por volumen (sobre el precio)
    desc_x5 = db.Column(db.Numeric(5, 2), nullable=False, default=3)
    desc_x10 = db.Column(db.Numeric(5, 2), nullable=False, default=5)
    # Compra minima del carrito (con IVA) -> v0.4
    minimo_compra = db.Column(db.Numeric(12, 2), nullable=False, default=30000)
    # WhatsApp de Juliana (formato internacional sin +, ej 5491171352560)
    whatsapp = db.Column(db.String(30), nullable=False, default='5491171352560')
    nombre_negocio = db.Column(db.String(120), nullable=False, default='Saludables')

    actualizado = db.Column(db.DateTime, default=_ahora)


def get_ajustes():
    """Devuelve la fila de ajustes; la crea con valores por defecto si no existe."""
    a = Ajustes.query.first()
    if a is None:
        a = Ajustes()
        db.session.add(a)
        db.session.commit()
    return a
