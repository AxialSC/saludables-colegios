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
                   url_for, flash, abort, jsonify)
from flask_login import login_required, current_user
from sqlalchemy import or_, select

from .extensions import db
from .models import (Cliente, Producto, Pedido, ItemPedido, EstadoPedido,
                     OrigenPedido, generar_numero_pedido, get_ajustes)
from .utils.decorators import revendedora_requerido
from .utils.timezone import ahora_argentina
from . import comisiones

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
    vendido = comisiones.vendido_neto(current_user.id)
    nivel = comisiones.nivel_por_vendido(vendido)
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
