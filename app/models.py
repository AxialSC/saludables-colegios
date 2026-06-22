"""
app/models.py — Modelos SQLAlchemy.

v0.1.0  -> Usuario + Rol (login)
v0.2.0  -> Producto (catalogo importado desde la planilla del mayorista)
v0.10.0 -> Producto: es_saludable + es_alcoholica (solapas Saludables / con-sin alcohol)
v0.11.0 -> Producto.categoria (categoria unica, fuente de verdad de las solapas)
v0.12.0 -> Oferta (ofertas publicas por 7 dias) + Cotizacion / CotizacionItem
           (Cumpleaños y Colegios: carritos que arma Juliana, con PDF + WhatsApp/mail).
v0.14.0 -> Banner (carrusel central + laterales izq/der de la tienda).
v0.16.0 -> Usuario: PERFIL COMPLETO (DNI, nacimiento, contacto, datos bancarios
           para pago de comisiones). Base para el modulo de Revendedores (Etapa 2).
"""
from flask_login import UserMixin

from .extensions import db, bcrypt
from .utils.timezone import ahora_argentina


def _ahora():
    return ahora_argentina().replace(tzinfo=None)


class Rol:
    """Roles del sistema (string simple, evita bugs de comparacion de Enum)."""
    SUPER_ADMIN = 'SUPER_ADMIN'   # Ivan (dueno del sistema, carga planillas)
    ADMIN = 'ADMIN'               # Juliana + hasta 4 mas (administran todo menos importar)
    REVENDEDORA = 'REVENDEDORA'   # Vendedores del CRM (Etapa 2: comisiones / niveles)

    TODOS = (SUPER_ADMIN, ADMIN, REVENDEDORA)
    # Roles que el super admin PUEDE asignar desde el panel (SUPER_ADMIN no se toca).
    ASIGNABLES = (ADMIN, REVENDEDORA)
    ETIQUETAS = {
        SUPER_ADMIN: 'Super Administrador',
        ADMIN: 'Administradora',
        REVENDEDORA: 'Revendedora',
    }


# Forma en que se le paga la comision a una revendedora (Etapa 2 lo usa).
class FormaPagoComision:
    EFECTIVO = 'EFECTIVO'
    TRANSFERENCIA = 'TRANSFERENCIA'
    MERCADOPAGO = 'MERCADOPAGO'

    TODAS = (EFECTIVO, TRANSFERENCIA, MERCADOPAGO)
    ETIQUETAS = {
        EFECTIVO: 'Efectivo',
        TRANSFERENCIA: 'Transferencia bancaria',
        MERCADOPAGO: 'MercadoPago / billetera',
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

    # ----- v0.16: PERFIL DE LA PERSONA (sobre todo para revendedoras) -----
    apellido = db.Column(db.String(120), nullable=True)
    dni = db.Column(db.String(15), nullable=True)
    fecha_nacimiento = db.Column(db.Date, nullable=True)
    telefono = db.Column(db.String(30), nullable=True)        # movil / celular
    email = db.Column(db.String(120), nullable=True)
    direccion = db.Column(db.String(200), nullable=True)
    localidad = db.Column(db.String(120), nullable=True)      # barrio / zona
    # Datos para pagarle las comisiones (Etapa 2)
    cbu_cvu = db.Column(db.String(30), nullable=True)         # CBU o CVU (22 digitos)
    alias_cbu = db.Column(db.String(60), nullable=True)       # alias bancario
    banco_fintech = db.Column(db.String(80), nullable=True)   # nombre del banco / fintech
    forma_pago_comision = db.Column(db.String(20), nullable=True)  # ver FormaPagoComision
    notas = db.Column(db.Text, nullable=True)

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
    def es_revendedora(self):
        return self.rol == Rol.REVENDEDORA

    @property
    def rol_etiqueta(self):
        return Rol.ETIQUETAS.get(self.rol, self.rol)

    @property
    def nombre_completo(self):
        return f'{self.nombre} {self.apellido}'.strip() if self.apellido else self.nombre

    @property
    def edad(self):
        """Edad en anios a partir de la fecha de nacimiento (None si no cargada)."""
        if not self.fecha_nacimiento:
            return None
        hoy = ahora_argentina().date()
        return (hoy.year - self.fecha_nacimiento.year
                - ((hoy.month, hoy.day) < (self.fecha_nacimiento.month, self.fecha_nacimiento.day)))

    @property
    def forma_pago_comision_etiqueta(self):
        return FormaPagoComision.ETIQUETAS.get(self.forma_pago_comision, '—')

    def __repr__(self):
        return f'<Usuario {self.usuario} ({self.rol})>'


# IVA general de Argentina (se usa para mostrar precios con IVA)
IVA = 0.21


class CategoriaProducto:
    """
    Categoria unica del producto para las solapas de la tienda (v0.11).
    Reemplaza el uso de los flags es_saludable / es_alcoholica.
    """
    NINGUNA = ''
    COMIDA = 'COMIDA_SALUDABLE'
    BEBIDA_SIN = 'BEBIDA_SIN'
    BEBIDA_CON = 'BEBIDA_CON'

    TODAS = (COMIDA, BEBIDA_SIN, BEBIDA_CON)
    ETIQUETAS = {
        COMIDA: '🥗 Comida saludable',
        BEBIDA_SIN: '💧 Bebida sin alcohol',
        BEBIDA_CON: '🍷 Bebida con alcohol',
    }


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

    # v0.10 -> solapas de la tienda (legacy: quedan pero ya no se usan en la logica)
    es_saludable = db.Column(db.Boolean, nullable=False, default=False)   # solapa "Saludables"
    es_alcoholica = db.Column(db.Boolean, nullable=False, default=False)  # bebidas con/sin alcohol

    # v0.11 -> categoria unica (fuente de verdad para las solapas)
    categoria = db.Column(db.String(20), nullable=False, default='', index=True)

    activo = db.Column(db.Boolean, nullable=False, default=True)
    # Marca si el producto vino en la ultima planilla importada
    en_ultima_lista = db.Column(db.Boolean, nullable=False, default=True)

    creado = db.Column(db.DateTime, default=_ahora)
    actualizado = db.Column(db.DateTime, default=_ahora)

    @property
    def costo_con_iva(self):
        return float(self.costo_neto) * (1 + IVA)

    @property
    def categoria_etiqueta(self):
        return CategoriaProducto.ETIQUETAS.get(self.categoria, '—')

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


# ============================================================================
#  v0.12.0 — OFERTAS (publicas, por 7 dias)
# ============================================================================

class Oferta(db.Model):
    """
    Oferta publica de un producto (v0.12). Precio especial que Juliana publica por
    un plazo (por defecto 7 dias) y que aparece en la solapa 'Ofertas' de la tienda.

    Reglas:
      - 'precio_oferta' es el precio FINAL con IVA. SIEMPRE se valida en backend
        contra el piso del 10% de margen (blindado): jamas se publica por debajo.
      - 'precio_lista_snapshot' guarda el precio normal al momento de publicar,
        para poder mostrarlo tachado en la tienda.
      - 'costo_neto_snapshot' guarda el costo del momento (auditoria / food cost).
      - No hay tareas programadas en PythonAnywhere free: la oferta 'se vence sola'
        porque las consultas de la tienda filtran por vence_en > ahora. Ademas
        Juliana puede despublicarla a mano (activa = False).
    """
    __tablename__ = 'ofertas'

    id = db.Column(db.Integer, primary_key=True)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'),
                            nullable=False, index=True)

    precio_oferta = db.Column(db.Numeric(12, 2), nullable=False)            # final c/IVA
    precio_lista_snapshot = db.Column(db.Numeric(12, 2), nullable=True)     # tachado
    costo_neto_snapshot = db.Column(db.Numeric(12, 3), nullable=True)       # auditoria

    publicada_en = db.Column(db.DateTime, default=_ahora, index=True)
    vence_en = db.Column(db.DateTime, nullable=False, index=True)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    creada_por = db.Column(db.String(80), nullable=True)

    producto = db.relationship('Producto', lazy='joined')

    @property
    def vigente(self):
        """True si esta activa y todavia no vencio."""
        return bool(self.activa) and self.vence_en is not None and self.vence_en > _ahora()

    @property
    def dias_restantes(self):
        """Dias que faltan para que venza (0 si ya vencio)."""
        if self.vence_en is None:
            return 0
        delta = self.vence_en - _ahora()
        if delta.total_seconds() <= 0:
            return 0
        # Redondeo hacia arriba para mostrar 'vence en X dias' amigable
        dias = delta.days + (1 if delta.seconds > 0 else 0)
        return max(1, dias)

    @property
    def descuento_pct(self):
        """% de descuento respecto del precio de lista (para mostrar etiqueta)."""
        if not self.precio_lista_snapshot or float(self.precio_lista_snapshot) <= 0:
            return 0
        lista = float(self.precio_lista_snapshot)
        ofert = float(self.precio_oferta)
        return int(round((lista - ofert) / lista * 100))


# ============================================================================
#  v0.12.0 — COTIZACIONES (Cumpleaños / Colegios) que arma Juliana en el panel
# ============================================================================

class TipoCotizacion:
    CUMPLE = 'CUMPLE'     # Bolsa de cumpleaños (minimo de unidades, ver Ajustes/constante)
    COLEGIO = 'COLEGIO'   # Pedido para un colegio (sin minimo de bolsas)

    TODAS = (CUMPLE, COLEGIO)
    ETIQUETAS = {
        CUMPLE: '🎉 Cumpleaños',
        COLEGIO: '🏫 Colegio',
    }
    PREFIJOS = {CUMPLE: 'CUMPLE', COLEGIO: 'COLEGIO'}


class EstadoCotizacion:
    BORRADOR = 'BORRADOR'   # Juliana la esta armando
    ENVIADA = 'ENVIADA'     # ya genero PDF / la mando por WhatsApp o mail
    CERRADA = 'CERRADA'     # el cliente acepto (se concreto la venta)
    ANULADA = 'ANULADA'     # descartada (no se borra, queda auditada)

    ETIQUETAS = {
        BORRADOR: 'Borrador',
        ENVIADA: 'Enviada',
        CERRADA: 'Cerrada',
        ANULADA: 'Anulada',
    }


class Cotizacion(db.Model):
    """
    Carrito personalizado que arma Juliana para un cliente (Cumpleaños o Colegio).
    Es una herramienta del panel (no se compra online): Juliana elige productos,
    el sistema suma el costo y aplica el piso del 10% blindado, y ella genera un
    PDF para mandar por WhatsApp o mail.

    'unidades':
      - CUMPLE  -> cantidad de bolsas iguales (minimo 20). El total = (suma de los
                   items de 1 bolsa) * unidades.
      - COLEGIO -> 1 (la cantidad va en cada item).

    Los items guardan snapshot (codigo, nombre, costo y precio) para que la
    cotizacion valga lo que valia el dia que se armo, aunque la lista cambie.
    """
    __tablename__ = 'cotizaciones'

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(15), nullable=False, default=TipoCotizacion.CUMPLE, index=True)
    numero = db.Column(db.String(20), unique=True, nullable=False, index=True)  # CUMPLE-00001
    token = db.Column(db.String(32), unique=True, nullable=False, index=True,
                      default=lambda: secrets.token_hex(8))

    # Datos del cliente (todos opcionales: Juliana puede armar un presupuesto rapido)
    nombre_cliente = db.Column(db.String(120), nullable=True)
    whatsapp = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    nota = db.Column(db.Text, nullable=True)

    unidades = db.Column(db.Integer, nullable=False, default=1)   # nº de bolsas (CUMPLE)

    # v0.12 C1 -> opcion de bolsa fisica (solo CUMPLE):
    #   incluye_bolsa = False -> el cliente trae la bolsa (sin costo)
    #   incluye_bolsa = True  -> nosotros ponemos la bolsa (costo_bolsa por unidad, lo carga Juliana)
    incluye_bolsa = db.Column(db.Boolean, nullable=False, default=False)
    costo_bolsa = db.Column(db.Numeric(12, 2), nullable=False, default=0)  # por bolsa

    costo_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)  # costo neto (food cost)
    total = db.Column(db.Numeric(12, 2), nullable=False, default=0)        # precio final c/IVA

    estado = db.Column(db.String(15), nullable=False, default=EstadoCotizacion.BORRADOR)

    creada_por = db.Column(db.String(80), nullable=True)
    creada_en = db.Column(db.DateTime, default=_ahora, index=True)
    modificada_en = db.Column(db.DateTime, nullable=True)

    items = db.relationship('CotizacionItem', backref='cotizacion',
                            cascade='all, delete-orphan', lazy='selectin')

    @property
    def tipo_etiqueta(self):
        return TipoCotizacion.ETIQUETAS.get(self.tipo, self.tipo)

    @property
    def estado_etiqueta(self):
        return EstadoCotizacion.ETIQUETAS.get(self.estado, self.estado)

    @property
    def cantidad_items(self):
        """Cantidad total de articulos en UNA bolsa / en el carrito."""
        return sum(i.cantidad for i in self.items)

    @property
    def subtotal_productos(self):
        """Subtotal de los productos de UNA bolsa (sin multiplicar por unidades)."""
        return round(sum(float(i.subtotal) for i in self.items), 2)

    @property
    def ganancia_estimada(self):
        """Ganancia bruta estimada (precio final sin IVA - costo). Solo informativa."""
        neto_venta = float(self.total) / (1 + IVA)
        return round(neto_venta - float(self.costo_total), 2)


class CotizacionItem(db.Model):
    """Item (producto) dentro de una cotizacion. Snapshot de codigo/nombre/costo/precio."""
    __tablename__ = 'cotizacion_items'

    id = db.Column(db.Integer, primary_key=True)
    cotizacion_id = db.Column(db.Integer, db.ForeignKey('cotizaciones.id'), nullable=False)
    codigo = db.Column(db.String(40), nullable=False)
    nombre = db.Column(db.String(255), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    costo_unitario = db.Column(db.Numeric(12, 3), nullable=False)   # neto, para food cost
    precio_unitario = db.Column(db.Numeric(12, 2), nullable=False)  # final c/IVA (piso 10%)
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)         # precio_unitario * cantidad


def generar_numero_cotizacion(tipo=TipoCotizacion.CUMPLE):
    """Numero correlativo por tipo: CUMPLE-00001, COLEGIO-00001."""
    pref = TipoCotizacion.PREFIJOS.get(tipo, 'COT')
    n = Cotizacion.query.filter_by(tipo=tipo).count() + 1
    return f'{pref}-{n:05d}'


def generar_numero_pedido(origen='WEB'):
    """Numero correlativo por origen: WEB-00001, CUMPLE-00001, COLEGIO-00001."""
    prefijos = {'WEB': 'WEB', 'CUMPLE': 'CUMPLE', 'COLEGIO': 'COLEGIO'}
    pref = prefijos.get(origen, 'WEB')
    n = Pedido.query.filter_by(origen=origen).count() + 1
    return f'{pref}-{n:05d}'


# ============================================================================
#  v0.14.0 — BANNERS (carrusel central + laterales izquierdo/derecho)
# ============================================================================

class ZonaBanner:
    """Donde aparece el banner en la tienda."""
    CENTRAL = 'CENTRAL'   # carrusel arriba de todo (lo primero que se ve)
    IZQ = 'IZQ'           # lateral izquierdo (fijo, ocupa el scroll)
    DER = 'DER'           # lateral derecho (fijo, ocupa el scroll)

    TODAS = (CENTRAL, IZQ, DER)
    ETIQUETAS = {
        CENTRAL: 'Banner central (carrusel arriba)',
        IZQ: 'Banner lateral izquierdo',
        DER: 'Banner lateral derecho',
    }


class DestinoBanner:
    """A donde lleva el banner cuando el cliente lo toca."""
    NINGUNO = 'NINGUNO'     # solo imagen, no es clickeable
    BUSQUEDA = 'BUSQUEDA'   # lleva al catalogo con una busqueda (destino_valor = texto)
    SOLAPA = 'SOLAPA'       # lleva a una solapa (destino_valor = ofertas/comida/sin/con)
    WHATSAPP = 'WHATSAPP'   # abre WhatsApp de Juliana (destino_valor = mensaje opcional)

    TODOS = (NINGUNO, BUSQUEDA, SOLAPA, WHATSAPP)
    ETIQUETAS = {
        NINGUNO: 'Sin link (solo imagen)',
        BUSQUEDA: 'Búsqueda en la tienda',
        SOLAPA: 'Solapa / categoría',
        WHATSAPP: 'WhatsApp a Juliana',
    }


class Banner(db.Model):
    """
    Imagen de banner que muestra la tienda (v0.14).
      - zona CENTRAL  -> entra al carrusel de arriba (varias rotan).
      - zona IZQ/DER  -> banner lateral fijo (1 o 2 imagenes que rotan lento).
    El archivo de imagen vive en static/img/banners/ (lo sube Ivan desde el panel).
    El destino define a donde lleva al tocarlo (busqueda, solapa o WhatsApp).
    """
    __tablename__ = 'banners'

    id = db.Column(db.Integer, primary_key=True)
    zona = db.Column(db.String(10), nullable=False, index=True)
    imagen = db.Column(db.String(255), nullable=False)        # archivo en static/img/banners/
    orden = db.Column(db.Integer, nullable=False, default=0)  # orden dentro de la zona
    destino_tipo = db.Column(db.String(12), nullable=False, default=DestinoBanner.NINGUNO)
    destino_valor = db.Column(db.String(200), nullable=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado = db.Column(db.DateTime, default=_ahora)

    @property
    def zona_etiqueta(self):
        return ZonaBanner.ETIQUETAS.get(self.zona, self.zona)

    @property
    def destino_etiqueta(self):
        return DestinoBanner.ETIQUETAS.get(self.destino_tipo, self.destino_tipo)
