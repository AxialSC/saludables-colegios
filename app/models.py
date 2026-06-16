"""
app/models.py — Modelos SQLAlchemy.

v0.1.0 -> Usuario + Rol (login)
v0.2.0 -> Producto (catalogo importado desde la planilla del mayorista)
v0.10.0 -> Producto: es_saludable + es_alcoholica (solapas Saludables / con-sin alcohol)
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

    # v0.10 -> solapas de la tienda
    es_saludable = db.Column(db.Boolean, nullable=False, default=False)   # solapa "Saludables"
    es_alcoholica = db.Column(db.Boolean, nullable=False, default=False)  # bebidas con/sin alcohol

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


import secrets


class EstadoPedido:
    PENDIENTE = 'PENDIENTE'    # recien hecho, falta que Juliana lo confirme
    CONFIRMADO = 'CONFIRMADO'  # Juliana verifico stock y lo acordo
    ENTREGADO = 'ENTREGADO'    # entregado y cobrado
    ANULADO = 'ANULADO'

    ETIQUETAS = {
        PENDIENTE: 'Pendiente',
        CONFIRMADO: 'Confirmado',
        ENTREGADO: 'Entregado',
        ANULADO: 'Anulado',
    }


class Pedido(db.Model):
    """
    Pedido hecho por un cliente desde la web. Los precios quedan CONGELADOS
    en los items (snapshot), para que valgan lo que valian al momento de la compra.
    """
    __tablename__ = 'pedidos'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(20), unique=True, nullable=False, index=True)  # WEB-00001
    # token publico no adivinable para la pagina de confirmacion / PDF
    token = db.Column(db.String(32), unique=True, nullable=False, index=True,
                      default=lambda: secrets.token_hex(8))
    origen = db.Column(db.String(15), nullable=False, default='WEB')  # WEB / CUMPLE / COLEGIO
    estado = db.Column(db.String(15), nullable=False, default=EstadoPedido.PENDIENTE)

    # Datos del cliente
    nombre = db.Column(db.String(80), nullable=False)
    apellido = db.Column(db.String(80), nullable=False)
    cuit = db.Column(db.String(13), nullable=False)
    whatsapp = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    direccion = db.Column(db.String(200), nullable=False)
    zona = db.Column(db.String(120), nullable=False)         # barrio/colegio (para metricas)
    observaciones = db.Column(db.Text, nullable=True)

    total = db.Column(db.Numeric(12, 2), nullable=False)

    # Para la contabilidad de Juliana (se completa en el panel)
    facturado = db.Column(db.Boolean, nullable=True, default=None)
    facturado_en = db.Column(db.DateTime, nullable=True)

    # Datos de origen (seguridad / validacion)
    ip_origen = db.Column(db.String(45), nullable=True)
    dispositivo = db.Column(db.String(20), nullable=True)   # Celular / Computadora

    # Anulacion (no se borra nunca; queda auditado)
    anulado_por = db.Column(db.String(80), nullable=True)
    anulado_en = db.Column(db.DateTime, nullable=True)
    anulado_motivo = db.Column(db.String(200), nullable=True)

    # Ultima modificacion (cuando Juliana edita el pedido)
    modificado_en = db.Column(db.DateTime, nullable=True)

    creado = db.Column(db.DateTime, default=_ahora, index=True)

    items = db.relationship('ItemPedido', backref='pedido',
                            cascade='all, delete-orphan', lazy='selectin')
    cobros = db.relationship('Cobro', backref='pedido',
                             cascade='all, delete-orphan', lazy='selectin')
    modificaciones = db.relationship('ModificacionPedido', backref='pedido',
                                     cascade='all, delete-orphan', lazy='selectin',
                                     order_by='ModificacionPedido.creado.desc()')

    @property
    def cliente_completo(self):
        return f'{self.nombre} {self.apellido}'.strip()

    @property
    def estado_etiqueta(self):
        return EstadoPedido.ETIQUETAS.get(self.estado, self.estado)

    @property
    def cantidad_items(self):
        return sum(i.cantidad for i in self.items)

    @property
    def total_cobrado(self):
        return sum(float(c.monto) for c in self.cobros)

    @property
    def saldo(self):
        return round(float(self.total) - self.total_cobrado, 2)

    @property
    def esta_cobrado(self):
        return self.total_cobrado >= float(self.total) - 0.01

    @property
    def esta_anulado(self):
        return self.estado == EstadoPedido.ANULADO


class ItemPedido(db.Model):
    __tablename__ = 'items_pedido'

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos.id'), nullable=False)
    # Snapshot: guardamos codigo y nombre por si el producto cambia despues
    codigo = db.Column(db.String(40), nullable=False)
    nombre = db.Column(db.String(255), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Numeric(12, 2), nullable=False)  # ya con escalon aplicado
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)


class FormaPago:
    EFECTIVO = 'EFECTIVO'
    TRANSFERENCIA = 'TRANSFERENCIA'
    MERCADOPAGO = 'MERCADOPAGO'
    OTRO = 'OTRO'

    TODAS = (EFECTIVO, TRANSFERENCIA, MERCADOPAGO, OTRO)
    ETIQUETAS = {
        EFECTIVO: 'Efectivo',
        TRANSFERENCIA: 'Transferencia',
        MERCADOPAGO: 'MercadoPago',
        OTRO: 'Otro',
    }


class Cobro(db.Model):
    """Registro de un cobro de un pedido (puede haber varios: seña + saldo)."""
    __tablename__ = 'cobros'

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos.id'), nullable=False)
    forma_pago = db.Column(db.String(20), nullable=False, default=FormaPago.EFECTIVO)
    monto = db.Column(db.Numeric(12, 2), nullable=False)
    nota = db.Column(db.String(200), nullable=True)
    registrado_por = db.Column(db.String(80), nullable=False)
    creado = db.Column(db.DateTime, default=_ahora)

    @property
    def forma_etiqueta(self):
        return FormaPago.ETIQUETAS.get(self.forma_pago, self.forma_pago)


class ModificacionPedido(db.Model):
    """Historial de ediciones de un pedido (que se quitó/agregó/cambió y por quién)."""
    __tablename__ = 'modificaciones_pedido'

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos.id'), nullable=False)
    descripcion = db.Column(db.Text, nullable=False)
    total_anterior = db.Column(db.Numeric(12, 2), nullable=False)
    total_nuevo = db.Column(db.Numeric(12, 2), nullable=False)
    hecho_por = db.Column(db.String(80), nullable=False)
    creado = db.Column(db.DateTime, default=_ahora)


def generar_numero_pedido(origen='WEB'):
    """Numero correlativo por origen: WEB-00001, CUMPLE-00001, COLEGIO-00001."""
    prefijos = {'WEB': 'WEB', 'CUMPLE': 'CUMPLE', 'COLEGIO': 'COLEGIO'}
    pref = prefijos.get(origen, 'WEB')
    n = Pedido.query.filter_by(origen=origen).count() + 1
    return f'{pref}-{n:05d}'
