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
           para pago de comisiones). Base para el modulo de Revendedores.
v0.16.1 -> Usuario: + CUIT y + clave temporal reenviable por WhatsApp.
v0.17.0 -> Cliente: base de clientes (cimiento del CRM de revendedoras).
v0.18.3 -> Suscriptor (C2): alta voluntaria desde la tienda publica.
v0.19.1 -> Factura / FacturaItem (Food Cost): facturas PDF de Torres.
v0.20.0 -> Importacion / ImportacionItem: historial de precios del mayorista.

v0.23.0 -> E2 · CIMIENTO DEL FRENTE E (VENTA DE LA REVENDEDORA).
           NO se crea una tabla de ventas nueva: se AMPLIA 'Pedido'.
           ¿Por que? Porque la venta de la revendedora ES un pedido. Si armaramos
           una tabla paralela, Juliana terminaria con DOS bandejas de pedidos (la
           web y la de las revendedoras), dos PDFs, dos CRMs y dos verdades. Con
           esto, entra todo por la misma pantalla.

           Lo que se agrega:
             · Pedido: revendedora_id, cliente_id, el circuito de aprobacion y el
               SNAPSHOT DE COMISION congelado.
             · ItemPedido: costo_unitario (hacia falta: sin el costo no se puede
               calcular el margen real de la venta, y sin margen no hay comision).
             · EstadoPedido: BORRADOR y RECHAZADO (el circuito de Juliana).

           EL CIRCUITO (tal como lo definio Ivan):
             1. La revendedora arma el pedido            -> BORRADOR
             2. Toca "Enviar a aprobacion"               -> PENDIENTE
             3. Juliana llama a Torres y chequea stock real
             4. Aprueba / edita / rechaza                -> CONFIRMADO o RECHAZADO
             5. Al APROBAR se congela la comision y le aparece a la revendedora
                en su dashboard como venta confirmada.
             6. Se entrega y se cobra                    -> ENTREGADO
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
    REVENDEDORA = 'REVENDEDORA'   # Vendedores del CRM (comisiones / niveles)

    TODOS = (SUPER_ADMIN, ADMIN, REVENDEDORA)
    # Roles que el super admin PUEDE asignar desde el panel (SUPER_ADMIN no se toca).
    ASIGNABLES = (ADMIN, REVENDEDORA)
    ETIQUETAS = {
        SUPER_ADMIN: 'Super Administrador',
        ADMIN: 'Administradora',
        REVENDEDORA: 'Revendedora',
    }


# Forma en que se le paga la comision a una revendedora.
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
    cuit = db.Column(db.String(13), nullable=True)            # v0.16.1
    fecha_nacimiento = db.Column(db.Date, nullable=True)
    telefono = db.Column(db.String(30), nullable=True)        # movil / celular
    email = db.Column(db.String(120), nullable=True)
    direccion = db.Column(db.String(200), nullable=True)
    localidad = db.Column(db.String(120), nullable=True)      # barrio / zona
    # Datos para pagarle las comisiones
    cbu_cvu = db.Column(db.String(30), nullable=True)         # CBU o CVU (22 digitos)
    alias_cbu = db.Column(db.String(60), nullable=True)       # alias bancario
    banco_fintech = db.Column(db.String(80), nullable=True)   # nombre del banco / fintech
    forma_pago_comision = db.Column(db.String(20), nullable=True)  # ver FormaPagoComision
    notas = db.Column(db.Text, nullable=True)

    # v0.16.1: clave temporal en claro, SOLO para poder reenviarla por WhatsApp
    # mientras la persona todavia no entro. Se ignora cuando ya cambio la clave.
    password_temporal = db.Column(db.String(40), nullable=True)

    # v0.18.1: redes de la revendedora (las carga ella en su portal)
    instagram = db.Column(db.String(120), nullable=True)
    facebook = db.Column(db.String(120), nullable=True)
    tiktok = db.Column(db.String(120), nullable=True)
    whatsapp_grupo = db.Column(db.String(200), nullable=True)   # link de grupo/difusion

    # v0.26.0 · Motor de niveles (E5). 'nivel_actual' es el escalon ACTIVO
    # (INICIAL/PLATA/ORO); 'nivel_desde' es la fecha en que lo alcanzo por ultima
    # vez, y de ahi se cuenta la gracia de 6 meses. Los llena comisiones.py.
    nivel_actual = db.Column(db.String(20), nullable=True)
    nivel_desde = db.Column(db.Date, nullable=True)

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

    @property
    def wa_numero(self):
        """Telefono normalizado para armar un link wa.me (solo digitos, con 54)."""
        if not self.telefono:
            return None
        d = ''.join(c for c in self.telefono if c.isdigit())
        if not d:
            return None
        if not d.startswith('54'):
            d = '54' + d
        return d

    @property
    def clave_temporal_visible(self):
        """La clave temporal SOLO si la persona todavia no la cambio."""
        return self.password_temporal if self.debe_cambiar_password else None

    # --- v0.18.1: links de redes listos para usar (o None si no cargo) ---
    @staticmethod
    def _red_url(valor, base):
        v = (valor or '').strip()
        if not v:
            return None
        if v.startswith('http://') or v.startswith('https://'):
            return v
        return base + v.lstrip('@/')

    @property
    def instagram_url(self):
        return self._red_url(self.instagram, 'https://instagram.com/')

    @property
    def facebook_url(self):
        return self._red_url(self.facebook, 'https://facebook.com/')

    @property
    def tiktok_url(self):
        v = (self.tiktok or '').strip()
        if not v:
            return None
        if v.startswith('http'):
            return v
        return 'https://tiktok.com/@' + v.lstrip('@/')

    @property
    def whatsapp_grupo_url(self):
        v = (self.whatsapp_grupo or '').strip()
        return v if v.startswith('http') else None

    @property
    def tiene_redes(self):
        return any([self.instagram, self.facebook, self.tiktok, self.whatsapp_grupo])

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

    marca = db.Column(db.String(80), nullable=True, index=True)
    imagen = db.Column(db.String(255), nullable=True)
    margen_individual = db.Column(db.Numeric(5, 2), nullable=True)
    destacado = db.Column(db.Boolean, nullable=False, default=False)

    # v0.10 -> solapas de la tienda (legacy: quedan pero ya no se usan en la logica)
    es_saludable = db.Column(db.Boolean, nullable=False, default=False)
    es_alcoholica = db.Column(db.Boolean, nullable=False, default=False)

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
    markup_general = db.Column(db.Numeric(5, 2), nullable=False, default=30)
    markup_minimo = db.Column(db.Numeric(5, 2), nullable=False, default=20)
    desc_x5 = db.Column(db.Numeric(5, 2), nullable=False, default=3)
    desc_x10 = db.Column(db.Numeric(5, 2), nullable=False, default=5)
    # Compra minima del carrito de la TIENDA PUBLICA (con IVA).
    # OJO: el minimo de la REVENDEDORA es otro y es NETO
    # (config.py -> MINIMO_REVENDEDORA_NETO). No confundirlos.
    minimo_compra = db.Column(db.Numeric(12, 2), nullable=False, default=30000)
    whatsapp = db.Column(db.String(30), nullable=False, default='5491171352560')
    nombre_negocio = db.Column(db.String(120), nullable=False, default='Saludables')

    # ------------------------------------------------------------------
    # v0.35.0 · MEDIOS DE PAGO (lo que ve el cliente en el checkout)
    # ------------------------------------------------------------------
    # OJO con la diferencia, que son dos cosas distintas:
    #   · Cobro.forma_pago  -> COMO ENTRO la plata. Lo registra Juliana DESPUES,
    #     cuando el pago ya se hizo. Eso ya existia.
    #   · Estos campos      -> COMO PUEDE PAGARTE el cliente. Es la configuracion
    #     que se le muestra en la tienda ANTES de pagar.
    # Son interruptores: lo que este apagado NO se le muestra al cliente.
    pago_efectivo = db.Column(db.Boolean, nullable=False, default=True)
    pago_transferencia = db.Column(db.Boolean, nullable=False, default=True)
    pago_qr = db.Column(db.Boolean, nullable=False, default=False)
    # Mercado Pago queda APAGADO: el casillero esta listo, pero el cobro real
    # todavia no se programo (va en la proxima etapa). No prender hasta entonces.
    pago_mercadopago = db.Column(db.Boolean, nullable=False, default=False)

    # Datos de la cuenta para transferencia (una sola cuenta, decision de Ivan).
    transf_titular = db.Column(db.String(120), nullable=True)
    transf_banco = db.Column(db.String(120), nullable=True)
    transf_cbu = db.Column(db.String(30), nullable=True)      # CBU o CVU (22 digitos)
    transf_alias = db.Column(db.String(60), nullable=True)
    transf_cuit = db.Column(db.String(13), nullable=True)

    # Nombre del archivo del QR dentro de app/static/img/pagos/
    qr_imagen = db.Column(db.String(120), nullable=True)

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


# ============================================================================
#  PEDIDOS  (tienda web + v0.23.0: tambien las ventas de las revendedoras)
# ============================================================================

class OrigenPedido:
    """
    De donde salio el pedido. v0.23.0 suma REVENDEDORA.
    Los valores viejos (WEB / CUMPLE / COLEGIO) NO se tocan: los pedidos que ya
    existen en la base siguen siendo validos tal cual estan.
    """
    WEB = 'WEB'                    # el cliente compro solo desde la tienda publica
    CUMPLE = 'CUMPLE'              # nacio de una cotizacion de cumpleaños
    COLEGIO = 'COLEGIO'            # nacio de una cotizacion de colegio/comercio
    REVENDEDORA = 'REVENDEDORA'    # v0.23.0 · lo armo una revendedora en su portal

    TODOS = (WEB, CUMPLE, COLEGIO, REVENDEDORA)
    ETIQUETAS = {
        WEB: '🛒 Tienda web',
        CUMPLE: '🎉 Cumpleaños',
        COLEGIO: '🏫 Comercio',
        REVENDEDORA: '👩‍💼 Revendedora',
    }
    # Prefijo del numero correlativo de cada origen
    PREFIJOS = {WEB: 'WEB', CUMPLE: 'CUMPLE', COLEGIO: 'COLEGIO', REVENDEDORA: 'RV'}


class EstadoPedido:
    """
    v0.23.0 suma BORRADOR y RECHAZADO: son los dos estados que le faltaban al
    circuito de aprobacion de Juliana.

    Circuito de una venta de revendedora:
        BORRADOR -> PENDIENTE -> CONFIRMADO -> ENTREGADO
                         |
                         +-----> RECHAZADO   (Torres no tenia stock, etc.)

    Los pedidos de la tienda web arrancan directo en PENDIENTE (no pasan por
    BORRADOR): el cliente ya confirmo la compra al hacer el checkout.
    """
    BORRADOR = 'BORRADOR'      # v0.23 · la revendedora lo esta armando (Juliana NO lo ve)
    PENDIENTE = 'PENDIENTE'    # esperando que Juliana lo revise
    CONFIRMADO = 'CONFIRMADO'  # Juliana chequeo stock con Torres y lo aprobo
    ENTREGADO = 'ENTREGADO'    # entregado y cobrado
    RECHAZADO = 'RECHAZADO'    # v0.23 · Juliana no lo pudo aprobar (sin stock, etc.)
    ANULADO = 'ANULADO'

    TODOS = (BORRADOR, PENDIENTE, CONFIRMADO, ENTREGADO, RECHAZADO, ANULADO)
    ETIQUETAS = {
        BORRADOR: 'Borrador',
        PENDIENTE: 'Pendiente de aprobación',
        CONFIRMADO: 'Aprobado',
        ENTREGADO: 'Entregado',
        RECHAZADO: 'Rechazado',
        ANULADO: 'Anulado',
    }
    # Estados en los que la venta YA CUENTA para la comision de la revendedora.
    # Un pedido rechazado o anulado NO paga comision. Un borrador tampoco: todavia
    # no es una venta.
    CUENTAN_COMISION = (CONFIRMADO, ENTREGADO)


class Pedido(db.Model):
    """
    Pedido. Los precios quedan CONGELADOS en los items (snapshot), para que valgan
    lo que valian al momento de la compra.

    v0.23.0 · Si 'revendedora_id' NO es None, este pedido es una VENTA DE
    REVENDEDORA. Ahi entran a jugar todos los campos de comision.
    """
    __tablename__ = 'pedidos'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(20), unique=True, nullable=False, index=True)  # WEB-00001 / RV-00001
    # token publico no adivinable para la pagina de confirmacion / PDF
    token = db.Column(db.String(32), unique=True, nullable=False, index=True,
                      default=lambda: secrets.token_hex(8))
    origen = db.Column(db.String(15), nullable=False, default=OrigenPedido.WEB)
    estado = db.Column(db.String(15), nullable=False, default=EstadoPedido.PENDIENTE)

    # Datos del cliente (en las ventas de revendedora se copian del Cliente:
    # snapshot, para que el pedido no cambie si despues editan la ficha)
    nombre = db.Column(db.String(80), nullable=False)
    apellido = db.Column(db.String(80), nullable=False)
    cuit = db.Column(db.String(13), nullable=False)
    whatsapp = db.Column(db.String(30), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    direccion = db.Column(db.String(200), nullable=False)
    zona = db.Column(db.String(120), nullable=False)         # barrio/colegio (para metricas)
    observaciones = db.Column(db.Text, nullable=True)

    # v0.35.0 · Que medio de pago ELIGIO el cliente en el checkout.
    # Es una INTENCION, no un cobro: dice "pienso pagarte con esto". La plata
    # que realmente entra se sigue registrando aparte, en Cobro. Nullable
    # porque los pedidos viejos (y los de revendedora) no lo tienen.
    medio_pago = db.Column(db.String(20), nullable=True)

    total = db.Column(db.Numeric(12, 2), nullable=False)      # FINAL con IVA

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

    modificado_en = db.Column(db.DateTime, nullable=True)
    creado = db.Column(db.DateTime, default=_ahora, index=True)

    # ==================================================================
    #  v0.23.0 — FRENTE E: VENTA DE REVENDEDORA
    # ==================================================================
    # De quien es la venta. None = pedido normal de la tienda web.
    revendedora_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'),
                               nullable=True, index=True)
    # A que cliente del CRM le vendio (None si es un pedido web suelto)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'),
                           nullable=True, index=True)

    # --- Circuito de aprobacion ---
    enviado_en = db.Column(db.DateTime, nullable=True)       # cuando lo mando a Juliana
    aprobado_por = db.Column(db.String(80), nullable=True)   # quien lo aprobo/rechazo
    aprobado_en = db.Column(db.DateTime, nullable=True)
    rechazado_motivo = db.Column(db.String(200), nullable=True)

    # --- SNAPSHOT DE PLATA (Pattern 1 de AXIAL: inmutabilidad historica) ---
    # Estos numeros se CONGELAN al aprobar y NO se recalculan nunca mas.
    # Si Nadia sube de escalon el mes que viene, sus ventas viejas siguen pagando
    # lo que se pacto el dia que se hicieron. Esa es la unica forma de que una
    # liquidacion de comisiones sea auditable.
    neto_total = db.Column(db.Numeric(12, 2), nullable=True)
    #   ^ La venta SIN IVA. Es la BASE DE LA COMISION. Nadie comisiona sobre el
    #     IVA: esa plata no es de Ivan, es de AFIP.

    costo_total = db.Column(db.Numeric(12, 2), nullable=True)
    #   ^ Lo que le cuesta a Ivan comprarle esa mercaderia a Torres (neto).

    margen_pct = db.Column(db.Numeric(5, 2), nullable=True)
    #   ^ Margen REAL de la venta, sobre venta: (neto - costo) / neto * 100.

    comision_pct = db.Column(db.Numeric(5, 2), nullable=True)
    #   ^ El escalon que regia el dia que se aprobo. CONGELADO.

    comision_monto = db.Column(db.Numeric(12, 2), nullable=True)
    #   ^ neto_total * comision_pct / 100. CONGELADO.

    margen_casa_pct = db.Column(db.Numeric(5, 2), nullable=True)
    #   ^ Lo que le queda a la casa DESPUES de pagar la comision:
    #         margen_pct - comision_pct
    #     El backend NUNCA deja aprobar un pedido con esto por debajo de
    #     config.MARGEN_CASA_MINIMO (6%). Se guarda igual, para que quede
    #     auditado que en su momento se cumplio.

    # --- Pago de la comision ---
    comision_pagada = db.Column(db.Boolean, nullable=False, default=False)
    comision_pagada_en = db.Column(db.DateTime, nullable=True)
    comision_pagada_por = db.Column(db.String(80), nullable=True)

    items = db.relationship('ItemPedido', backref='pedido',
                            cascade='all, delete-orphan', lazy='selectin')
    cobros = db.relationship('Cobro', backref='pedido',
                             cascade='all, delete-orphan', lazy='selectin')
    modificaciones = db.relationship('ModificacionPedido', backref='pedido',
                                     cascade='all, delete-orphan', lazy='selectin',
                                     order_by='ModificacionPedido.creado.desc()')

    revendedora = db.relationship('Usuario', foreign_keys=[revendedora_id], lazy='joined')
    cliente = db.relationship('Cliente', foreign_keys=[cliente_id], lazy='joined')

    # ---------- Propiedades de siempre ----------
    @property
    def cliente_completo(self):
        return f'{self.nombre} {self.apellido}'.strip()

    @property
    def estado_etiqueta(self):
        return EstadoPedido.ETIQUETAS.get(self.estado, self.estado)

    @property
    def medio_pago_etiqueta(self):
        """
        v0.35.0 · Con que medio dijo el cliente que iba a pagar, en lindo.
        Devuelve None si el pedido no tiene ninguno (los pedidos viejos y los
        de revendedora no lo tienen: ahi la pantalla no muestra nada).
        """
        if not self.medio_pago:
            return None
        return FormaPago.ETIQUETAS.get(self.medio_pago, self.medio_pago)

    @property
    def origen_etiqueta(self):
        return OrigenPedido.ETIQUETAS.get(self.origen, self.origen)

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

    # ---------- v0.23.0 · Propiedades del Frente E ----------
    @property
    def es_de_revendedora(self):
        return self.revendedora_id is not None

    @property
    def es_borrador(self):
        """Todavia lo esta armando la revendedora: Juliana NO lo ve."""
        return self.estado == EstadoPedido.BORRADOR

    @property
    def espera_aprobacion(self):
        """Esta en la bandeja de Juliana, esperando que llame a Torres."""
        return self.estado == EstadoPedido.PENDIENTE and self.es_de_revendedora

    @property
    def esta_aprobado(self):
        return self.estado in EstadoPedido.CUENTAN_COMISION

    @property
    def paga_comision(self):
        """True si esta venta le tiene que pagar comision a la revendedora."""
        return (self.es_de_revendedora
                and self.estado in EstadoPedido.CUENTAN_COMISION
                and self.comision_monto is not None
                and float(self.comision_monto) > 0)

    @property
    def revendedora_nombre(self):
        return self.revendedora.nombre_completo if self.revendedora else '—'

    @property
    def ganancia_casa(self):
        """
        Plata que le queda a la casa (Ivan + Juliana) despues de pagarle la
        comision a la revendedora. En pesos, no en porcentaje.
            (neto - costo) - comision
        """
        if self.neto_total is None or self.costo_total is None:
            return None
        bruta = float(self.neto_total) - float(self.costo_total)
        return round(bruta - float(self.comision_monto or 0), 2)

    def __repr__(self):
        return f'<Pedido {self.numero} {self.estado}>'


class ItemPedido(db.Model):
    """
    Renglon de un pedido. Snapshot: guardamos codigo y nombre por si el producto
    cambia despues.

    v0.23.0 -> + costo_unitario. Hacia falta y no estaba: SIN EL COSTO NO SE PUEDE
    CALCULAR EL MARGEN REAL DE LA VENTA, y sin margen no hay forma de saber si la
    comision deja a la casa por encima del 6%. Es nullable a proposito: los
    pedidos web que ya existen no lo tienen y no hay que inventarselo.
    """
    __tablename__ = 'items_pedido'

    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos.id'), nullable=False)
    codigo = db.Column(db.String(40), nullable=False)
    nombre = db.Column(db.String(255), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False)
    precio_unitario = db.Column(db.Numeric(12, 2), nullable=False)  # FINAL con IVA
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)

    # v0.23.0 · costo NETO del producto al momento de la venta (lo que paga Ivan
    # a Torres). Congelado: si Torres sube el precio manana, esta venta ya
    # quedo cerrada con el costo de hoy.
    costo_unitario = db.Column(db.Numeric(12, 3), nullable=True)

    @property
    def neto_unitario(self):
        """Precio unitario SIN IVA (base de la comision)."""
        return round(float(self.precio_unitario) / (1 + IVA), 2)

    @property
    def neto_subtotal(self):
        return round(float(self.subtotal) / (1 + IVA), 2)

    @property
    def costo_subtotal(self):
        if self.costo_unitario is None:
            return None
        return round(float(self.costo_unitario) * self.cantidad, 2)


class FormaPago:
    EFECTIVO = 'EFECTIVO'
    TRANSFERENCIA = 'TRANSFERENCIA'
    MERCADOPAGO = 'MERCADOPAGO'
    QR = 'QR'
    OTRO = 'OTRO'

    TODAS = (EFECTIVO, TRANSFERENCIA, MERCADOPAGO, QR, OTRO)
    ETIQUETAS = {
        EFECTIVO: 'Efectivo',
        TRANSFERENCIA: 'Transferencia',
        MERCADOPAGO: 'MercadoPago',
        QR: 'QR / Billetera',
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
        porque las consultas de la tienda filtran por vence_en > ahora.
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
#  v0.12.0 — COTIZACIONES (Cumpleaños / Colegios)
# ============================================================================

class TipoCotizacion:
    CUMPLE = 'CUMPLE'     # Bolsa de cumpleaños (minimo de unidades)
    COLEGIO = 'COLEGIO'   # Pedido para un colegio / comercio
    #  ^ v0.23: en pantalla se muestra como "Comercios". El valor interno sigue
    #    siendo COLEGIO A PROPOSITO: renombrarlo obligaria a migrar las
    #    cotizaciones viejas y los numeros correlativos (COLEGIO-00001) por un
    #    cambio puramente cosmetico. Cero riesgo, mismo resultado visual.

    TODAS = (CUMPLE, COLEGIO)
    ETIQUETAS = {
        CUMPLE: '🎉 Cumpleaños',
        COLEGIO: '🏪 Comercios',
    }
    PREFIJOS = {CUMPLE: 'CUMPLE', COLEGIO: 'COLEGIO'}


class EstadoCotizacion:
    BORRADOR = 'BORRADOR'   # se esta armando
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
    Carrito personalizado que se arma para un cliente (Cumpleaños o Comercio).
    Es un PRESUPUESTO: se elige productos, el sistema suma el costo y aplica el
    piso blindado, y se genera un PDF para mandar por WhatsApp o mail.

    'unidades':
      - CUMPLE  -> cantidad de bolsas iguales. El total = (suma de los items de
                   1 bolsa) * unidades.
      - COLEGIO -> 1 (la cantidad va en cada item).
    """
    __tablename__ = 'cotizaciones'

    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(15), nullable=False, default=TipoCotizacion.CUMPLE, index=True)
    numero = db.Column(db.String(20), unique=True, nullable=False, index=True)
    token = db.Column(db.String(32), unique=True, nullable=False, index=True,
                      default=lambda: secrets.token_hex(8))

    nombre_cliente = db.Column(db.String(120), nullable=True)
    whatsapp = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    nota = db.Column(db.Text, nullable=True)

    unidades = db.Column(db.Integer, nullable=False, default=1)

    incluye_bolsa = db.Column(db.Boolean, nullable=False, default=False)
    costo_bolsa = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    costo_total = db.Column(db.Numeric(12, 2), nullable=False, default=0)
    total = db.Column(db.Numeric(12, 2), nullable=False, default=0)

    estado = db.Column(db.String(15), nullable=False, default=EstadoCotizacion.BORRADOR)

    creada_por = db.Column(db.String(80), nullable=True)
    creada_en = db.Column(db.DateTime, default=_ahora, index=True)
    modificada_en = db.Column(db.DateTime, nullable=True)

    # v0.23.0 · Si la armo una revendedora desde su portal, queda registrado.
    # None = la armo Juliana o un admin desde el panel (como hasta ahora).
    revendedora_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'),
                               nullable=True, index=True)
    cliente_id = db.Column(db.Integer, db.ForeignKey('clientes.id'),
                           nullable=True, index=True)
    # Si el presupuesto se convirtio en una venta, apunta al pedido que nacio de el.
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos.id'),
                          nullable=True, index=True)

    items = db.relationship('CotizacionItem', backref='cotizacion',
                            cascade='all, delete-orphan', lazy='selectin')
    revendedora = db.relationship('Usuario', foreign_keys=[revendedora_id], lazy='joined')

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
    precio_unitario = db.Column(db.Numeric(12, 2), nullable=False)  # final c/IVA
    subtotal = db.Column(db.Numeric(12, 2), nullable=False)


def generar_numero_cotizacion(tipo=TipoCotizacion.CUMPLE):
    """Numero correlativo por tipo: CUMPLE-00001, COLEGIO-00001."""
    pref = TipoCotizacion.PREFIJOS.get(tipo, 'COT')
    n = Cotizacion.query.filter_by(tipo=tipo).count() + 1
    return f'{pref}-{n:05d}'


def generar_numero_pedido(origen=OrigenPedido.WEB):
    """
    Numero correlativo por origen: WEB-00001, CUMPLE-00001, COLEGIO-00001,
    y v0.23.0: RV-00001 para las ventas de revendedoras.

    Se cuenta por origen (no global) para que cada serie sea independiente y se
    lea de un vistazo de donde salio cada venta.
    """
    pref = OrigenPedido.PREFIJOS.get(origen, 'WEB')
    n = Pedido.query.filter_by(origen=origen).count() + 1
    return f'{pref}-{n:05d}'


# ============================================================================
#  v0.14.0 — BANNERS
# ============================================================================

class ZonaBanner:
    """Donde aparece el banner en la tienda."""
    CENTRAL = 'CENTRAL'
    IZQ = 'IZQ'
    DER = 'DER'

    TODAS = (CENTRAL, IZQ, DER)
    ETIQUETAS = {
        CENTRAL: 'Banner central (carrusel arriba)',
        IZQ: 'Banner lateral izquierdo',
        DER: 'Banner lateral derecho',
    }


class DestinoBanner:
    """A donde lleva el banner cuando el cliente lo toca."""
    NINGUNO = 'NINGUNO'
    BUSQUEDA = 'BUSQUEDA'
    SOLAPA = 'SOLAPA'
    WHATSAPP = 'WHATSAPP'

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
    El archivo vive en static/img/banners/.
    """
    __tablename__ = 'banners'

    id = db.Column(db.Integer, primary_key=True)
    zona = db.Column(db.String(10), nullable=False, index=True)
    imagen = db.Column(db.String(255), nullable=False)
    orden = db.Column(db.Integer, nullable=False, default=0)
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


# ============================================================================
#  v0.17.0 — BASE DE CLIENTES (cimiento del CRM de revendedoras)
# ============================================================================

class Cliente(db.Model):
    """
    Cliente final del negocio. Lo da de alta una revendedora o un admin.
    Todos viven en la MISMA base: la revendedora ve y gestiona los suyos, y
    Juliana / cualquier admin ven y consultan TODOS.

    'revendedora_id' indica de quién es el cliente:
      - apunta a un Usuario con rol REVENDEDORA, o
      - queda NULL = cliente "de la casa".
    """
    __tablename__ = 'clientes'

    id = db.Column(db.Integer, primary_key=True)
    revendedora_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'),
                               nullable=True, index=True)

    nombre = db.Column(db.String(120), nullable=False)
    apellido = db.Column(db.String(120), nullable=True)
    dni_cuit = db.Column(db.String(15), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    direccion = db.Column(db.String(200), nullable=True)
    localidad = db.Column(db.String(120), nullable=True)
    notas = db.Column(db.Text, nullable=True)

    activo = db.Column(db.Boolean, nullable=False, default=True)
    creado = db.Column(db.DateTime, default=_ahora)
    creado_por = db.Column(db.String(80), nullable=True)

    revendedora = db.relationship('Usuario', foreign_keys=[revendedora_id], lazy='joined')

    @property
    def nombre_completo(self):
        return f'{self.nombre} {self.apellido}'.strip() if self.apellido else self.nombre

    @property
    def revendedora_nombre(self):
        return self.revendedora.nombre_completo if self.revendedora else 'De la casa'

    def __repr__(self):
        return f'<Cliente {self.nombre_completo}>'


# ============================================================================
#  v0.18.3 — SUSCRIPTORES
# ============================================================================

class Suscriptor(db.Model):
    """
    Persona que se anoto desde la tienda publica para recibir las ofertas antes
    que nadie. No requiere cuenta ni login.

    'dia_nacimiento' / 'mes_nacimiento' -> SOLO dia y mes (sin año, por privacidad
    en un formulario publico).

    Regla AXIAL: desactivar, nunca borrar.
    """
    __tablename__ = 'suscriptores'

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    apellido = db.Column(db.String(120), nullable=True)
    dni_cuit = db.Column(db.String(15), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    whatsapp = db.Column(db.String(30), nullable=True)

    dia_nacimiento = db.Column(db.Integer, nullable=True)    # 1-31
    mes_nacimiento = db.Column(db.Integer, nullable=True)    # 1-12

    acepta_notificaciones = db.Column(db.Boolean, nullable=False, default=True)
    activo = db.Column(db.Boolean, nullable=False, default=True)

    creado = db.Column(db.DateTime, default=_ahora, index=True)
    ip_origen = db.Column(db.String(45), nullable=True)

    @property
    def nombre_completo(self):
        return f'{self.nombre} {self.apellido}'.strip() if self.apellido else self.nombre

    @property
    def cumple_etiqueta(self):
        """Devuelve 'DD/MM' o '—' si no cargo cumpleaños."""
        if not self.dia_nacimiento or not self.mes_nacimiento:
            return '—'
        return f'{self.dia_nacimiento:02d}/{self.mes_nacimiento:02d}'

    def __repr__(self):
        return f'<Suscriptor {self.nombre_completo}>'


# ============================================================================
#  v0.19.1 — FOOD COST: facturas PDF de Torres + cruce contra catalogo
# ============================================================================

class Factura(db.Model):
    """
    Factura de compra (proveedor Torres) subida en PDF y leida automaticamente.
    No se borra nunca: queda como historial de auditoria de compras.
    """
    __tablename__ = 'facturas'

    id = db.Column(db.Integer, primary_key=True)
    numero = db.Column(db.String(30), nullable=False, unique=True, index=True)
    proveedor = db.Column(db.String(120), nullable=False, default='S.TORRES Y CIA S.A.')
    fecha = db.Column(db.Date, nullable=True)

    subtotal = db.Column(db.Numeric(12, 2), nullable=True)
    iva = db.Column(db.Numeric(12, 2), nullable=True)
    reg_especiales = db.Column(db.Numeric(12, 2), nullable=True)
    total = db.Column(db.Numeric(12, 2), nullable=True)

    # Renglones que el parser no pudo interpretar. Nunca se descartan en silencio.
    no_reconocidas = db.Column(db.Text, nullable=True)

    subida_en = db.Column(db.DateTime, default=_ahora, index=True)
    subida_por = db.Column(db.String(80), nullable=True)

    items = db.relationship('FacturaItem', backref='factura',
                            cascade='all, delete-orphan', lazy='selectin')

    @property
    def no_reconocidas_lista(self):
        return [l for l in (self.no_reconocidas or '').split('\n') if l.strip()]

    def __repr__(self):
        return f'<Factura {self.numero}>'


class FacturaItem(db.Model):
    """
    Renglon de una factura de Torres. Si 'codigo' matchea un Producto del catalogo,
    queda vinculado y se guarda el costo que tenia ANTES, para mostrar la variacion.
    """
    __tablename__ = 'factura_items'

    id = db.Column(db.Integer, primary_key=True)
    factura_id = db.Column(db.Integer, db.ForeignKey('facturas.id'), nullable=False)

    codigo = db.Column(db.String(40), nullable=False, index=True)
    descripcion = db.Column(db.String(255), nullable=False)
    unidades = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    sugerido = db.Column(db.Numeric(12, 2), nullable=True)
    costo_unitario = db.Column(db.Numeric(12, 3), nullable=False)
    importe = db.Column(db.Numeric(12, 2), nullable=True)

    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=True)
    costo_neto_anterior = db.Column(db.Numeric(12, 3), nullable=True)
    actualizado = db.Column(db.Boolean, nullable=False, default=False)

    producto = db.relationship('Producto', lazy='joined')

    @property
    def variacion_pct(self):
        """% de variacion del costo de la factura vs el costo_neto que tenia cargado."""
        if not self.costo_neto_anterior or float(self.costo_neto_anterior) <= 0:
            return None
        anterior = float(self.costo_neto_anterior)
        nuevo = float(self.costo_unitario)
        return round((nuevo - anterior) / anterior * 100, 1)

    def __repr__(self):
        return f'<FacturaItem {self.codigo} factura={self.factura_id}>'


# ============================================================================
#  v0.20.0 — HISTORIAL DE IMPORTACIONES (control de precios del mayorista)
# ============================================================================

class Importacion(db.Model):
    """
    Registro de cada planilla del mayorista importada.
    Sin acceso a la base de Torres, esta es la unica forma de saber QUE cambio
    y CUANDO. No se borra nunca.
    """
    __tablename__ = 'importaciones'

    id = db.Column(db.Integer, primary_key=True)
    archivo = db.Column(db.String(255), nullable=True)
    creado = db.Column(db.DateTime, default=_ahora, index=True)
    creado_por = db.Column(db.String(80), nullable=True)

    nuevos = db.Column(db.Integer, nullable=False, default=0)
    actualizados = db.Column(db.Integer, nullable=False, default=0)
    subieron = db.Column(db.Integer, nullable=False, default=0)
    bajaron = db.Column(db.Integer, nullable=False, default=0)
    sin_cambio = db.Column(db.Integer, nullable=False, default=0)
    fuera_de_lista = db.Column(db.Integer, nullable=False, default=0)
    total_catalogo = db.Column(db.Integer, nullable=False, default=0)

    variacion_promedio = db.Column(db.Numeric(6, 2), nullable=True)

    items = db.relationship('ImportacionItem', backref='importacion',
                            cascade='all, delete-orphan', lazy='select')

    @property
    def cambiaron(self):
        return (self.subieron or 0) + (self.bajaron or 0)

    def __repr__(self):
        return f'<Importacion {self.id} {self.creado}>'


class ImportacionItem(db.Model):
    """
    Detalle de UN producto dentro de una importacion. Solo se guardan los que
    CAMBIARON de precio o son NUEVOS (no tiene sentido guardar 1600 filas iguales).
    """
    __tablename__ = 'importacion_items'

    id = db.Column(db.Integer, primary_key=True)
    importacion_id = db.Column(db.Integer, db.ForeignKey('importaciones.id'),
                               nullable=False, index=True)

    codigo = db.Column(db.String(40), nullable=False, index=True)
    nombre = db.Column(db.String(255), nullable=False)
    costo_anterior = db.Column(db.Numeric(12, 3), nullable=True)
    costo_nuevo = db.Column(db.Numeric(12, 3), nullable=False)
    variacion_pct = db.Column(db.Numeric(7, 2), nullable=True)
    es_nuevo = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f'<ImportacionItem {self.codigo}>'
