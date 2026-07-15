"""
app/revendedora.py — Portal propio de cada REVENDEDORA.
AXIAL SECURITY · Ivan Abrigo

v0.18.0 -> dashboard + gestion de SUS clientes + sus redes.
v0.24.0 -> E3 · EL PORTAL DE VENTAS (Frente E).

    EL CIRCUITO, tal como lo definio Ivan:

      1. La revendedora entra a "Vender", elige a UNO de SUS clientes.
      2. Busca productos (mismo motor de precios de siempre) y arma el carrito.
      3. Le pone precio a cada uno. El sistema le muestra 3 opciones:
             Lista  ·  Medio  ·  MAX (su piso)
         Por debajo de SU piso NO puede bajar. El piso depende de SU escalon:
         cuanto mas gana ella, menos puede regalar (ver app/comisiones.py).
      4. El carrito tiene que llegar a $50.000 NETOS (sin IVA).
      5. Toca "Enviar a aprobacion" -> el pedido cae en la bandeja de Juliana.
      6. Juliana llama a Torres, chequea stock real, y aprueba o rechaza.
      7. Al aprobar, la venta le aparece a ella como CONFIRMADA con su comision.

    DEFENSA EN PROFUNDIDAD (regla AXIAL): el navegador NO decide nada. Todos los
    precios se RECALCULAN en el servidor. Aunque alguien edite el JavaScript y
    mande un precio de $1, el backend lo clampea al piso.
"""
import json

from flask import (Blueprint, render_template, request, redirect,
                   url_for, flash, abort, jsonify, Response)
from flask_login import login_required, current_user
from sqlalchemy import or_, select

from .extensions import db
from .models import (Cliente, Producto, Pedido, ItemPedido, EstadoPedido,
                     OrigenPedido, generar_numero_pedido, get_ajustes,
                     IVA, Cotizacion, CotizacionItem, TipoCotizacion,
                     EstadoCotizacion, generar_numero_cotizacion)
from .utils.decorators import revendedora_requerido
from .utils.timezone import ahora_argentina
from . import comisiones
from .pdf_cotizacion import generar_pdf_cotizacion

revendedora_bp = Blueprint('revendedora', __name__, url_prefix='/portal')


def _ahora():
    return ahora_argentina().replace(tzinfo=None)


def _pesos(v):
    s = f'{float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return '$' + s


@revendedora_bp.before_request
@login_required
def _forzar_cambio_password():
    # Igual que el panel admin: si tiene clave temporal, primero la cambia.
    if current_user.is_authenticated and current_user.debe_cambiar_password:
        return redirect(url_for('auth.cambiar_password'))


def _mi_cliente_o_404(cid):
    """Trae el cliente SOLO si es de la revendedora logueada. Si no, 403."""
    c = Cliente.query.get_or_404(cid)
    if c.revendedora_id != current_user.id:
        abort(403)
    return c


def _mi_venta_o_404(pid):
    """Trae el pedido SOLO si es de la revendedora logueada. Si no, 403."""
    p = Pedido.query.get_or_404(pid)
    if p.revendedora_id != current_user.id:
        abort(403)
    return p


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


# ============================================================================
#  DASHBOARD
# ============================================================================

@revendedora_bp.route('/')
@revendedora_requerido
def dashboard():
    mis = Cliente.query.filter_by(revendedora_id=current_user.id)
    n_clientes = mis.count()
    n_activos = mis.filter_by(activo=True).count()

    # v0.24.0 · Numeros REALES (antes era un placeholder)
    # v0.26.0 · Ademas, al entrar se REVISA y actualiza el nivel (regla de
    # permanencia). Sin cron: el nivel se pone al dia justo cuando ella entra.
    vendido = comisiones.vendido_neto(current_user.id)
    estado_nivel = comisiones.revisar_y_actualizar_nivel(current_user.id)
    nivel = estado_nivel['nivel'] if estado_nivel else comisiones.nivel_por_vendido(vendido)
    siguiente, falta = comisiones.falta_para_subir(vendido)

    ventas = Pedido.query.filter_by(revendedora_id=current_user.id)
    n_pendientes = ventas.filter_by(estado=EstadoPedido.PENDIENTE).count()
    aprobadas = ventas.filter(Pedido.estado.in_(EstadoPedido.CUENTAN_COMISION)).all()
    n_aprobadas = len(aprobadas)

    comision_total = sum(float(p.comision_monto or 0) for p in aprobadas)
    comision_a_cobrar = sum(float(p.comision_monto or 0)
                            for p in aprobadas if not p.comision_pagada)

    ultimas = (ventas.order_by(Pedido.creado.desc()).limit(5).all())

    return render_template('revendedora/dashboard.html',
                           n_clientes=n_clientes, n_activos=n_activos,
                           nivel=nivel, niveles=comisiones.niveles(),
                           estado_nivel=estado_nivel,
                           vendido=vendido, siguiente=siguiente, falta=falta,
                           n_pendientes=n_pendientes, n_aprobadas=n_aprobadas,
                           comision_total=comision_total,
                           comision_a_cobrar=comision_a_cobrar,
                           ultimas=ultimas)


# ============================================================================
#  MIS CLIENTES
# ============================================================================

@revendedora_bp.route('/clientes')
@revendedora_requerido
def clientes():
    q = (request.args.get('q') or '').strip()
    stmt = Cliente.query.filter_by(revendedora_id=current_user.id)
    if q:
        like = f'%{q}%'
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


# ============================================================================
#  v0.24.0 — VENDER (el armador de pedidos)
# ============================================================================

# Datos del cliente que SI o SI tienen que estar cargados para poder venderle.
# No es burocracia: el pedido guarda un snapshot de estos datos, y si manana hay
# un problema con la entrega o el cobro, hay que saber a quien y donde ir.
CAMPOS_OBLIGATORIOS = [
    ('dni_cuit', 'DNI o CUIT'),
    ('telefono', 'teléfono'),
    ('direccion', 'dirección'),
]


def _falta_del_cliente(c):
    """Devuelve la lista de datos que le faltan al cliente para poder venderle."""
    return [etiqueta for campo, etiqueta in CAMPOS_OBLIGATORIOS
            if not (getattr(c, campo) or '').strip()]


@revendedora_bp.route('/vender')
@revendedora_requerido
def vender():
    """Pantalla para armar una venta nueva."""
    ajustes = get_ajustes()
    nivel = comisiones.nivel_de(current_user.id)

    # Solo sus clientes ACTIVOS, y marcamos a cuales les falta algun dato
    mis = (Cliente.query
           .filter_by(revendedora_id=current_user.id, activo=True)
           .order_by(Cliente.nombre).all())
    lista_clientes = [{'c': c, 'falta': _falta_del_cliente(c)} for c in mis]

    # Rubros y marcas, para los filtros del buscador
    marcas = db.session.execute(
        select(Producto.marca).where(Producto.activo.is_(True))
        .where(Producto.marca.isnot(None)).where(Producto.marca != '')
        .distinct().order_by(Producto.marca)
    ).scalars().all()
    rubros = db.session.execute(
        select(Producto.rubro).where(Producto.activo.is_(True))
        .where(Producto.rubro.isnot(None)).where(Producto.rubro != '')
        .distinct().order_by(Producto.rubro)
    ).scalars().all()

    cliente_sel = request.args.get('cliente', type=int)

    return render_template('revendedora/vender.html',
                           clientes=lista_clientes, cliente_sel=cliente_sel,
                           marcas=marcas, rubros=rubros, ajustes=ajustes,
                           nivel=nivel,
                           margen_minimo=comisiones.margen_minimo(nivel['comision']),
                           margen_casa=comisiones.margen_casa_minimo(),
                           minimo_neto=comisiones.minimo_neto())


@revendedora_bp.route('/vender/buscar')
@revendedora_requerido
def vender_buscar():
    """
    Buscador JSON del armador. Devuelve, para cada producto, los 3 precios que
    ESTA revendedora puede usar (segun SU escalon).

    OJO: es una ruta propia del portal, NO se reusa la del panel admin
    (admin.ofertas_buscar tiene @admin_requerido: una revendedora recibiria un
    403). Ademas, los precios minimos son distintos: los de ella dependen de su
    comision.

    Si no hay ningun filtro no devuelve nada, para no dumpear los 1654 productos.
    """
    q = (request.args.get('q') or '').strip()
    marca = (request.args.get('marca') or '').strip()
    rubro = (request.args.get('rubro') or '').strip()

    if not q and not marca and not rubro:
        return jsonify([])

    ajustes = get_ajustes()
    nivel = comisiones.nivel_de(current_user.id)

    stmt = Producto.query.filter(Producto.activo.is_(True))
    if marca:
        stmt = stmt.filter(Producto.marca == marca)
    if rubro:
        stmt = stmt.filter(Producto.rubro == rubro)
    if q:
        like = f'%{q}%'
        stmt = stmt.filter(or_(Producto.nombre.ilike(like),
                               Producto.codigo.ilike(like),
                               Producto.marca.ilike(like)))
    prods = stmt.order_by(Producto.nombre).limit(60).all()

    res = []
    for p in prods:
        pr = comisiones.precios_para(p, ajustes, nivel['comision'])
        res.append({
            'id': p.id,
            'codigo': p.codigo,
            'nombre': p.nombre,
            'marca': p.marca or '',
            'lista': pr['lista'],
            'medio': pr['medio'],
            'minimo': pr['minimo'],
            'costo': pr['costo'],
        })
    return jsonify(res)


@revendedora_bp.route('/vender/guardar', methods=['POST'])
@revendedora_requerido
def vender_guardar():
    """
    Crea la venta y la manda a la bandeja de Juliana.

    ACA ESTA EL CANDADO. Todo se recalcula en el servidor:
      1. Se ignora el precio que mando el navegador si esta por debajo del piso.
      2. Se verifica el minimo de $50.000 NETOS.
      3. Se verifica que a la casa le quede >= 6%.
    Si algo no cierra, NO se guarda nada.
    """
    ajustes = get_ajustes()
    nivel = comisiones.nivel_de(current_user.id)
    comision_pct = nivel['comision']

    # ---------- 1) El cliente ----------
    cid = request.form.get('cliente_id', type=int)
    if not cid:
        flash('Elegí a qué cliente le estás vendiendo.', 'error')
        return redirect(url_for('revendedora.vender'))
    cliente = _mi_cliente_o_404(cid)

    faltan = _falta_del_cliente(cliente)
    if faltan:
        flash(f'A "{cliente.nombre_completo}" le faltan datos: {", ".join(faltan)}. '
              f'Completá su ficha antes de venderle.', 'error')
        return redirect(url_for('revendedora.cliente_editar', cid=cid))

    # ---------- 2) Los items ----------
    try:
        items_in = json.loads(request.form.get('items_json') or '[]')
    except (ValueError, TypeError):
        items_in = []

    if not items_in:
        flash('Agregá al menos un producto al pedido.', 'error')
        return redirect(url_for('revendedora.vender', cliente=cid))

    items_calc = []
    clampeados = 0
    for it in items_in:
        pid = it.get('id')
        if not str(pid).isdigit():
            continue
        p = Producto.query.filter_by(id=int(pid), activo=True).first()
        if p is None:
            continue

        try:
            cant = int(it.get('cantidad') or 1)
        except (TypeError, ValueError):
            cant = 1
        if cant < 1:
            cant = 1

        # EL PISO. Se recalcula aca, en el servidor. Punto.
        piso = comisiones.precio_minimo(p, comision_pct)
        try:
            precio = round(float(it.get('precio') or piso), 2)
        except (TypeError, ValueError):
            precio = piso
        if precio < piso:
            precio = piso
            clampeados += 1

        items_calc.append({
            'producto': p,
            'cantidad': cant,
            'precio_unitario': precio,
            'costo_unitario': float(p.costo_neto),
            'subtotal': round(precio * cant, 2),
        })

    if not items_calc:
        flash('No se pudo armar el pedido (los productos ya no están disponibles).', 'error')
        return redirect(url_for('revendedora.vender', cliente=cid))

    # ---------- 3) La plata ----------
    snap = comisiones.calcular(items_calc, comision_pct)

    # Minimo de $50.000 NETOS (sin IVA)
    minimo = comisiones.minimo_neto()
    if snap['neto_total'] < minimo:
        falta = minimo - snap['neto_total']
        flash(f'El pedido no llega al mínimo. Necesitás {_pesos(minimo)} netos '
              f'(sin IVA) y llevás {_pesos(snap["neto_total"])}. '
              f'Te faltan {_pesos(falta)}.', 'error')
        return redirect(url_for('revendedora.vender', cliente=cid))

    # El candado final: a la casa le tiene que quedar >= 6%
    if not comisiones.cumple_piso_casa(snap):
        flash(f'Este pedido dejaría a la casa con {snap["margen_casa_pct"]}% de ganancia, '
              f'por debajo del mínimo de {comisiones.margen_casa_minimo()}%. '
              f'Subí los precios. (Si te pasó esto, avisale a Iván.)', 'error')
        return redirect(url_for('revendedora.vender', cliente=cid))

    # ---------- 4) Guardar ----------
    try:
        pedido = Pedido(
            numero=generar_numero_pedido(OrigenPedido.REVENDEDORA),
            origen=OrigenPedido.REVENDEDORA,
            estado=EstadoPedido.PENDIENTE,          # va derecho a la bandeja de Juliana

            # Snapshot de los datos del cliente (si despues editan la ficha, el
            # pedido sigue diciendo a quien se le vendio ESE dia)
            nombre=cliente.nombre,
            apellido=(cliente.apellido or '—'),
            cuit=(cliente.dni_cuit or ''),
            whatsapp=(cliente.telefono or ''),
            email=cliente.email,
            direccion=(cliente.direccion or ''),
            zona=(cliente.localidad or 'Sin zona'),
            observaciones=(request.form.get('observaciones') or '').strip() or None,

            total=snap['total'],

            revendedora_id=current_user.id,
            cliente_id=cliente.id,
            enviado_en=_ahora(),

            # Snapshot de plata. OJO: estos numeros son una ESTIMACION hasta que
            # Juliana apruebe. Al aprobar se vuelven a calcular y ahi si quedan
            # congelados para siempre (por si ella sube de escalon entre medio).
            neto_total=snap['neto_total'],
            costo_total=snap['costo_total'],
            margen_pct=snap['margen_pct'],
            comision_pct=snap['comision_pct'],
            comision_monto=snap['comision_monto'],
            margen_casa_pct=snap['margen_casa_pct'],
        )
        db.session.add(pedido)
        db.session.flush()   # para tener pedido.id

        for it in items_calc:
            db.session.add(ItemPedido(
                pedido_id=pedido.id,
                codigo=it['producto'].codigo,
                nombre=it['producto'].nombre,
                cantidad=it['cantidad'],
                precio_unitario=it['precio_unitario'],
                subtotal=it['subtotal'],
                costo_unitario=it['costo_unitario'],
            ))
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Hubo un problema al guardar el pedido. Probá de nuevo.', 'error')
        return redirect(url_for('revendedora.vender', cliente=cid))

    if clampeados:
        flash(f'{clampeados} producto(s) se ajustaron al precio mínimo permitido '
              f'para tu nivel. El pedido se guardó con esos precios.', 'warning')

    flash(f'Pedido {pedido.numero} enviado a Juliana ✓ '
          f'Te avisamos acá cuando lo apruebe.', 'success')
    return redirect(url_for('revendedora.venta_detalle', pid=pedido.id))


# ============================================================================
#  v0.24.0 — MIS VENTAS
# ============================================================================

@revendedora_bp.route('/ventas')
@revendedora_requerido
def ventas():
    estado = (request.args.get('estado') or '').strip().upper()
    stmt = Pedido.query.filter_by(revendedora_id=current_user.id)
    if estado in EstadoPedido.TODOS:
        stmt = stmt.filter_by(estado=estado)
    lista = stmt.order_by(Pedido.creado.desc()).all()

    total = Pedido.query.filter_by(revendedora_id=current_user.id).count()
    return render_template('revendedora/ventas.html', lista=lista,
                           estado_sel=estado, total=total,
                           estados=EstadoPedido.ETIQUETAS)


@revendedora_bp.route('/ventas/<int:pid>')
@revendedora_requerido
def venta_detalle(pid):
    p = _mi_venta_o_404(pid)
    return render_template('revendedora/venta_detalle.html', p=p,
                           ajustes=get_ajustes())


@revendedora_bp.route('/ventas/<int:pid>/whatsapp')
@revendedora_requerido
def venta_whatsapp(pid):
    """
    Arma el mensaje de WhatsApp para que la revendedora le pase el pedido
    APROBADO a su cliente. Solo tiene sentido si ya esta aprobado: mandarle un
    pedido que Juliana todavia no confirmo con Torres es prometer stock que
    puede no existir.
    """
    p = _mi_venta_o_404(pid)
    if not p.esta_aprobado:
        flash('Todavía no está aprobado. Esperá a que Juliana confirme el stock '
              'con la distribuidora antes de avisarle al cliente.', 'warning')
        return redirect(url_for('revendedora.venta_detalle', pid=pid))

    from urllib.parse import quote
    lineas = [f'Hola {p.nombre}! Te confirmo tu pedido {p.numero}:', '']
    for it in p.items:
        lineas.append(f'· {it.cantidad}x {it.nombre} — {_pesos(it.subtotal)}')
    lineas += ['', f'TOTAL: {_pesos(p.total)} (IVA incluido)', '',
               'Cualquier cosa me escribís. Gracias!']
    msg = '\n'.join(lineas)

    numero = ''.join(c for c in (p.whatsapp or '') if c.isdigit())
    if not numero:
        flash('El cliente no tiene un teléfono cargado.', 'error')
        return redirect(url_for('revendedora.venta_detalle', pid=pid))
    if not numero.startswith('54'):
        numero = '54' + numero

    return redirect(f'https://wa.me/{numero}?text={quote(msg)}')


# ============================================================================
#  MIS REDES
# ============================================================================

@revendedora_bp.route('/redes', methods=['GET', 'POST'])
@revendedora_requerido
def redes():
    if request.method == 'POST':
        g = request.form.get
        current_user.instagram = (g('instagram') or '').strip() or None
        current_user.facebook = (g('facebook') or '').strip() or None
        current_user.tiktok = (g('tiktok') or '').strip() or None
        current_user.whatsapp_grupo = (g('whatsapp_grupo') or '').strip() or None
        db.session.commit()
        flash('Tus redes se guardaron ✓', 'success')
        return redirect(url_for('revendedora.redes'))
    return render_template('revendedora/redes.html')


# ============================================================================
#  v0.27.0 — E6 · PRESUPUESTOS (Cumpleaños / Comercios) EN EL PORTAL
# ============================================================================
#
#  El circuito, tal como lo definio Ivan (opcion 3):
#    1. La revendedora arma un PRESUPUESTO para UNO de SUS clientes.
#         · Cumpleaños -> 1 bolsa modelo (productos x cantidad) + N bolsas.
#         · Comercio   -> lista de items con cantidades.
#    2. Genera un PDF lindo CON SU CONTACTO y se lo manda por WhatsApp. Eso es un
#       TANTEO: no reserva stock ni paga comision.
#    3. Si el cliente acepta, toca "Convertir en pedido" -> cae en la MISMA
#       bandeja de aprobacion de Juliana que una venta normal (circuito E4).
#    4. Juliana chequea stock con Torres y aprueba: recien ahi se congela la
#       comision de la revendedora.
#
#  Reglas confirmadas por Ivan:
#    · El presupuesto usa el PISO DE ELLA (segun su escalon), no el 10% fijo del
#      panel admin. Un cumple de Nadia es una venta de Nadia.
#    · Comercio exige el minimo de $50.000 netos; Cumpleaños NO (una bolsita
#      puede ser chica y estaria mal bloquearla).
#    · Al convertir un cumple, las bolsas se MULTIPLICAN (3 alfajores x 20
#      bolsas = 60 alfajores): el pedido es lo que Juliana le pide a Torres de
#      verdad. El candado del 6% se REVALIDA sobre ese total final multiplicado,
#      con el costo de HOY (si Torres subio, no se convierte: se rearma).


def _mi_presupuesto_o_404(cid):
    """Trae la cotizacion SOLO si es de la revendedora logueada. Si no, 403."""
    c = Cotizacion.query.get_or_404(cid)
    if c.revendedora_id != current_user.id:
        abort(403)
    return c


@revendedora_bp.route('/presupuestos')
@revendedora_requerido
def presupuestos():
    """Lista de MIS presupuestos. Filtra por tipo si viene ?tipo=."""
    tipo = (request.args.get('tipo') or '').strip().upper()
    if tipo not in TipoCotizacion.TODAS:
        tipo = ''
    stmt = Cotizacion.query.filter_by(revendedora_id=current_user.id)
    if tipo:
        stmt = stmt.filter_by(tipo=tipo)
    cotis = stmt.order_by(Cotizacion.creada_en.desc()).limit(100).all()
    return render_template('revendedora/presupuestos.html', cotis=cotis,
                           tipo_sel=tipo, tipos=TipoCotizacion.ETIQUETAS)


@revendedora_bp.route('/presupuestos/nuevo/<tipo>')
@revendedora_requerido
def presupuesto_armar(tipo):
    """Pantalla para armar un presupuesto nuevo (CUMPLE o COMERCIO=COLEGIO)."""
    tipo = (tipo or '').strip().upper()
    if tipo not in TipoCotizacion.TODAS:
        abort(404)
    ajustes = get_ajustes()
    nivel = comisiones.nivel_de(current_user.id)

    # Solo SUS clientes ACTIVOS, marcando a cuales les falta algun dato (igual
    # que en Vender: sin datos completos no se puede convertir en pedido).
    mis = (Cliente.query
           .filter_by(revendedora_id=current_user.id, activo=True)
           .order_by(Cliente.nombre).all())
    lista_clientes = [{'c': c, 'falta': _falta_del_cliente(c)} for c in mis]

    marcas = db.session.execute(
        select(Producto.marca).where(Producto.activo.is_(True))
        .where(Producto.marca.isnot(None)).where(Producto.marca != '')
        .distinct().order_by(Producto.marca)
    ).scalars().all()
    rubros = db.session.execute(
        select(Producto.rubro).where(Producto.activo.is_(True))
        .where(Producto.rubro.isnot(None)).where(Producto.rubro != '')
        .distinct().order_by(Producto.rubro)
    ).scalars().all()

    cliente_sel = request.args.get('cliente', type=int)

    return render_template('revendedora/presupuesto_armar.html',
                           tipo=tipo, es_cumple=(tipo == TipoCotizacion.CUMPLE),
                           tipo_etiqueta=TipoCotizacion.ETIQUETAS[tipo],
                           clientes=lista_clientes, cliente_sel=cliente_sel,
                           marcas=marcas, rubros=rubros, ajustes=ajustes,
                           nivel=nivel,
                           margen_minimo=comisiones.margen_minimo(nivel['comision']),
                           minimo_neto=comisiones.minimo_neto())


@revendedora_bp.route('/presupuestos/guardar', methods=['POST'])
@revendedora_requerido
def presupuesto_guardar():
    """
    Guarda un presupuesto nuevo. BLINDAJE: cada precio se recalcula en el
    servidor contra el PISO de esta revendedora (su escalon). El navegador no
    decide nada.
    """
    tipo = (request.form.get('tipo') or '').strip().upper()
    if tipo not in TipoCotizacion.TODAS:
        flash('Tipo de presupuesto inválido.', 'error')
        return redirect(url_for('revendedora.presupuestos'))
    es_cumple = (tipo == TipoCotizacion.CUMPLE)

    # ---------- 1) El cliente (obligatorio) ----------
    cid = request.form.get('cliente_id', type=int)
    if not cid:
        flash('Elegí a qué cliente le estás armando el presupuesto.', 'error')
        return redirect(url_for('revendedora.presupuesto_armar', tipo=tipo))
    cliente = _mi_cliente_o_404(cid)
    faltan = _falta_del_cliente(cliente)
    if faltan:
        flash(f'A "{cliente.nombre_completo}" le faltan datos: {", ".join(faltan)}. '
              f'Completá su ficha antes de armar el presupuesto.', 'error')
        return redirect(url_for('revendedora.cliente_editar', cid=cid))

    # ---------- 2) Los items ----------
    try:
        items_in = json.loads(request.form.get('items_json') or '[]')
    except (ValueError, TypeError):
        items_in = []
    if not items_in:
        flash('Agregá al menos un producto al presupuesto.', 'error')
        return redirect(url_for('revendedora.presupuesto_armar', tipo=tipo, cliente=cid))

    nivel = comisiones.nivel_de(current_user.id)
    comision_pct = nivel['comision']

    # Unidades (bolsas). Solo CUMPLE multiplica; COMERCIO siempre 1.
    try:
        unidades = int(request.form.get('unidades') or 1)
    except (TypeError, ValueError):
        unidades = 1
    if not es_cumple:
        unidades = 1
    elif unidades < 1:
        unidades = 1

    nota = (request.form.get('nota') or '').strip() or None

    items_calc = []
    subtotal_bolsa = 0.0
    costo_prod_bolsa = 0.0
    clampeados = 0
    for it in items_in:
        pid = it.get('id')
        if not str(pid).isdigit():
            continue
        p = Producto.query.filter_by(id=int(pid), activo=True).first()
        if p is None:
            continue
        try:
            cant = int(it.get('cantidad') or 1)
        except (TypeError, ValueError):
            cant = 1
        if cant < 1:
            cant = 1
        piso = comisiones.precio_minimo(p, comision_pct)     # SU piso, por escalon
        try:
            precio = round(float(it.get('precio') or piso), 2)
        except (TypeError, ValueError):
            precio = piso
        if precio < piso:                                    # BLINDAJE
            precio = piso
            clampeados += 1
        sub = round(precio * cant, 2)
        items_calc.append({
            'codigo': p.codigo, 'nombre': p.nombre, 'cantidad': cant,
            'costo_unitario': float(p.costo_neto),
            'precio_unitario': precio, 'subtotal': sub,
        })
        subtotal_bolsa += sub
        costo_prod_bolsa += float(p.costo_neto) * cant

    if not items_calc:
        flash('No se pudo armar el presupuesto (productos no encontrados).', 'error')
        return redirect(url_for('revendedora.presupuesto_armar', tipo=tipo, cliente=cid))

    subtotal_bolsa = round(subtotal_bolsa, 2)
    total = round(subtotal_bolsa * unidades, 2)
    costo_total = round(costo_prod_bolsa * unidades, 2)

    # Comercio: minimo de $50.000 netos. Cumple: sin minimo.
    if not es_cumple:
        neto = round(total / (1 + IVA), 2)
        minimo = comisiones.minimo_neto()
        if neto < minimo:
            falta_min = round(minimo - neto, 2)
            flash(f'El presupuesto de comercio no llega al mínimo. Necesitás '
                  f'{_pesos(minimo)} netos (sin IVA) y llevás {_pesos(neto)}. '
                  f'Te faltan {_pesos(falta_min)}.', 'error')
            return redirect(url_for('revendedora.presupuesto_armar', tipo=tipo, cliente=cid))

    # ---------- 3) Guardar ----------
    try:
        coti = Cotizacion(
            tipo=tipo,
            numero=generar_numero_cotizacion(tipo),
            nombre_cliente=cliente.nombre_completo,
            whatsapp=(cliente.telefono or None),
            email=cliente.email,
            nota=nota,
            unidades=unidades,
            incluye_bolsa=False, costo_bolsa=0,
            costo_total=costo_total, total=total,
            estado=EstadoCotizacion.BORRADOR,
            creada_por=current_user.nombre,
            revendedora_id=current_user.id,
            cliente_id=cliente.id,
        )
        db.session.add(coti)
        db.session.flush()
        for it in items_calc:
            db.session.add(CotizacionItem(cotizacion_id=coti.id, **it))
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Hubo un problema al guardar el presupuesto. Probá de nuevo.', 'error')
        return redirect(url_for('revendedora.presupuesto_armar', tipo=tipo, cliente=cid))

    if clampeados:
        flash(f'{clampeados} producto(s) se ajustaron a tu precio mínimo permitido '
              f'para tu nivel.', 'warning')
    flash(f'Presupuesto {coti.numero} creado ✓ Descargá el PDF y mandáselo a tu '
          f'cliente.', 'success')
    return redirect(url_for('revendedora.presupuesto_detalle', cid=coti.id))


@revendedora_bp.route('/presupuestos/<int:cid>')
@revendedora_requerido
def presupuesto_detalle(cid):
    coti = _mi_presupuesto_o_404(cid)
    pedido = Pedido.query.get(coti.pedido_id) if coti.pedido_id else None
    return render_template('revendedora/presupuesto_detalle.html', coti=coti,
                           pedido=pedido, ajustes=get_ajustes())


@revendedora_bp.route('/presupuestos/<int:cid>/pdf')
@revendedora_requerido
def presupuesto_pdf(cid):
    """PDF del presupuesto, con el contacto de la revendedora (no el del negocio)."""
    coti = _mi_presupuesto_o_404(cid)
    pdf = generar_pdf_cotizacion(coti, get_ajustes())
    return Response(pdf, mimetype='application/pdf', headers={
        'Content-Disposition': f'inline; filename="{coti.numero}.pdf"'
    })


@revendedora_bp.route('/presupuestos/<int:cid>/whatsapp')
@revendedora_requerido
def presupuesto_whatsapp(cid):
    """Abre un WhatsApp al cliente con un texto base. El PDF lo adjunta ella."""
    coti = _mi_presupuesto_o_404(cid)
    from urllib.parse import quote
    nombre = (coti.nombre_cliente or '').split(' ')[0]
    lineas = [f'Hola {nombre}! Te paso el presupuesto {coti.numero}.',
              'Te adjunto el PDF con el detalle. Cualquier cosa me escribís 😊']
    msg = '\n'.join(lineas)
    numero = ''.join(c for c in (coti.whatsapp or '') if c.isdigit())
    if not numero:
        flash('El cliente no tiene un teléfono cargado.', 'error')
        return redirect(url_for('revendedora.presupuesto_detalle', cid=cid))
    if not numero.startswith('54'):
        numero = '54' + numero
    return redirect(f'https://wa.me/{numero}?text={quote(msg)}')


@revendedora_bp.route('/presupuestos/<int:cid>/anular', methods=['POST'])
@revendedora_requerido
def presupuesto_anular(cid):
    coti = _mi_presupuesto_o_404(cid)
    if coti.pedido_id:
        flash('Ya se convirtió en pedido; no se puede anular el presupuesto.', 'error')
        return redirect(url_for('revendedora.presupuesto_detalle', cid=cid))
    coti.estado = EstadoCotizacion.ANULADA
    coti.modificada_en = _ahora()
    db.session.commit()
    flash(f'Presupuesto {coti.numero} anulado.', 'warning')
    return redirect(url_for('revendedora.presupuestos'))


@revendedora_bp.route('/presupuestos/<int:cid>/convertir', methods=['POST'])
@revendedora_requerido
def presupuesto_convertir(cid):
    """
    Convierte el presupuesto en un PEDIDO que cae en la bandeja de Juliana.
    Mismo circuito que una venta normal (E4). El candado del 6% se revalida
    sobre el total FINAL (cumple: bolsas multiplicadas) con el costo de HOY.
    """
    coti = _mi_presupuesto_o_404(cid)

    if coti.estado == EstadoCotizacion.ANULADA:
        flash('Este presupuesto está anulado.', 'error')
        return redirect(url_for('revendedora.presupuesto_detalle', cid=cid))
    if coti.pedido_id:
        flash('Este presupuesto ya se convirtió en un pedido.', 'warning')
        return redirect(url_for('revendedora.venta_detalle', pid=coti.pedido_id))
    if not coti.cliente_id:
        flash('El presupuesto no tiene un cliente asociado; no se puede convertir.', 'error')
        return redirect(url_for('revendedora.presupuesto_detalle', cid=cid))

    cliente = Cliente.query.get(coti.cliente_id)
    if cliente is None or cliente.revendedora_id != current_user.id:
        abort(403)
    faltan = _falta_del_cliente(cliente)
    if faltan:
        flash(f'A "{cliente.nombre_completo}" le faltan datos: {", ".join(faltan)}. '
              f'Completá su ficha antes de convertir.', 'error')
        return redirect(url_for('revendedora.cliente_editar', cid=cliente.id))

    es_cumple = (coti.tipo == TipoCotizacion.CUMPLE)
    unidades = coti.unidades if es_cumple else 1

    nivel = comisiones.nivel_de(current_user.id)
    comision_pct = nivel['comision']

    # Rearmar los items: cantidad FINAL (cumple x bolsas), precio que acepto el
    # cliente (snapshot del presupuesto) y COSTO DE HOY (lo que cobra Torres ahora).
    items_calc = []
    faltantes = []
    for it in coti.items:
        p = Producto.query.filter_by(codigo=it.codigo, activo=True).first()
        if p is None:
            faltantes.append(it.nombre)
            continue
        cant_final = it.cantidad * unidades
        items_calc.append({
            'producto': p,
            'cantidad': cant_final,
            'precio_unitario': float(it.precio_unitario),
            'costo_unitario': float(p.costo_neto),
            'subtotal': round(float(it.precio_unitario) * cant_final, 2),
        })

    if faltantes:
        flash('No se puede convertir: estos productos ya no están disponibles: '
              + ', '.join(faltantes) + '. Rearmá el presupuesto.', 'error')
        return redirect(url_for('revendedora.presupuesto_detalle', cid=cid))
    if not items_calc:
        flash('No se pudo convertir (sin productos válidos).', 'error')
        return redirect(url_for('revendedora.presupuesto_detalle', cid=cid))

    snap = comisiones.calcular(items_calc, comision_pct)

    # Comercio: revalidar el minimo sobre el total final. Cumple: sin minimo.
    if not es_cumple:
        minimo = comisiones.minimo_neto()
        if snap['neto_total'] < minimo:
            flash(f'El pedido no llega al mínimo de comercio ({_pesos(minimo)} '
                  f'netos). Ajustá el presupuesto.', 'error')
            return redirect(url_for('revendedora.presupuesto_detalle', cid=cid))

    # EL CANDADO: a la casa le tiene que quedar >= 6% sobre el total MULTIPLICADO.
    if not comisiones.cumple_piso_casa(snap):
        flash(f'No se puede convertir: con los costos de hoy, a la casa le quedaría '
              f'{snap["margen_casa_pct"]}% (mínimo {comisiones.margen_casa_minimo()}%). '
              f'Los costos de Torres cambiaron desde el presupuesto: rearmalo con '
              f'precios actualizados.', 'error')
        return redirect(url_for('revendedora.presupuesto_detalle', cid=cid))

    # Observaciones del pedido: la nota + el equivalente en bolsas (para Juliana)
    obs_partes = []
    if coti.nota:
        obs_partes.append(coti.nota)
    if es_cumple:
        obs_partes.append(f'🎉 Cumpleaños · equivale a {unidades} bolsa(s) iguales '
                          f'(presupuesto {coti.numero}).')
    else:
        obs_partes.append(f'🏪 Comercio · presupuesto {coti.numero}.')
    observaciones = ' · '.join(obs_partes) or None

    try:
        pedido = Pedido(
            numero=generar_numero_pedido(OrigenPedido.REVENDEDORA),
            origen=OrigenPedido.REVENDEDORA,
            estado=EstadoPedido.PENDIENTE,          # va derecho a la bandeja de Juliana
            nombre=cliente.nombre,
            apellido=(cliente.apellido or '—'),
            cuit=(cliente.dni_cuit or ''),
            whatsapp=(cliente.telefono or ''),
            email=cliente.email,
            direccion=(cliente.direccion or ''),
            zona=(cliente.localidad or 'Sin zona'),
            observaciones=observaciones,
            total=snap['total'],
            revendedora_id=current_user.id,
            cliente_id=cliente.id,
            enviado_en=_ahora(),
            # Snapshot de plata (ESTIMACION hasta que Juliana apruebe; ahi se
            # vuelve a calcular y queda congelado)
            neto_total=snap['neto_total'],
            costo_total=snap['costo_total'],
            margen_pct=snap['margen_pct'],
            comision_pct=snap['comision_pct'],
            comision_monto=snap['comision_monto'],
            margen_casa_pct=snap['margen_casa_pct'],
        )
        db.session.add(pedido)
        db.session.flush()
        for it in items_calc:
            db.session.add(ItemPedido(
                pedido_id=pedido.id,
                codigo=it['producto'].codigo,
                nombre=it['producto'].nombre,
                cantidad=it['cantidad'],
                precio_unitario=it['precio_unitario'],
                subtotal=it['subtotal'],
                costo_unitario=it['costo_unitario'],
            ))
        # Vincular presupuesto <-> pedido y cerrar el presupuesto
        coti.pedido_id = pedido.id
        coti.estado = EstadoCotizacion.CERRADA
        coti.modificada_en = _ahora()
        db.session.commit()
    except Exception:
        db.session.rollback()
        flash('Hubo un problema al convertir el presupuesto. Probá de nuevo.', 'error')
        return redirect(url_for('revendedora.presupuesto_detalle', cid=cid))

    flash(f'Presupuesto convertido en el pedido {pedido.numero} ✓ '
          f'Ya está en la bandeja de Juliana para aprobación.', 'success')
    return redirect(url_for('revendedora.venta_detalle', pid=pedido.id))
