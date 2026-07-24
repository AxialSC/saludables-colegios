"""
app/aprobaciones.py — Bandeja de aprobacion de ventas de revendedora (v0.25.0).
AXIAL SECURITY · Ivan Abrigo

E4 · EL OTRO LADO DEL MOSTRADOR.

Nadia arma un pedido en su portal y lo manda. Cae ACA. Juliana:
  · lo revisa,
  · llama a Torres y chequea el stock real,
  · y entonces APRUEBA, EDITA (si Torres tiene stock parcial) o RECHAZA.

Al APROBAR, la comision se CONGELA (Pattern 1 de AXIAL): se recalcula una ultima
vez con el escalon que rige HOY, se guarda, y no se toca nunca mas. Si Nadia sube
de nivel el mes que viene, esta venta sigue pagando lo que se pacto hoy.

POR QUE UN BLUEPRINT NUEVO Y NO METERLO EN admin.py:
  admin.py ya tiene ~900 lineas y esta EN PRODUCCION funcionando. Meterle mano a
  un archivo asi para agregar una seccion nueva es pedir un bug. Este modulo vive
  aparte, se registra solo, y no toca una linea del admin que ya anda.

SEGURIDAD (lo que pidio Ivan):
  · Editar/aprobar/rechazar: admin_requerido -> Juliana Y el super admin (Ivan
    ve y toca todo siempre, control total).
  · Al EDITAR, se recalcula la plata y se vuelve a verificar el piso del 6%.
    Si la edicion dejara a la casa por debajo, NO se guarda. El candado es el
    mismo que en el portal de Nadia: no hay forma de saltearlo.
  · Rechazar SIEMPRE pide motivo (queda claro para Nadia por que).
"""
import json

from flask import (Blueprint, render_template, redirect, url_for,
                   request, flash, abort, jsonify)
from flask_login import login_required, current_user
from sqlalchemy import or_

from .extensions import db
from .models import (Producto, Pedido, ItemPedido, ModificacionPedido,
                     EstadoPedido, OrigenPedido, Usuario, get_ajustes)
from .utils.decorators import admin_requerido
from .utils.timezone import ahora_argentina
from . import comisiones

aprobaciones_bp = Blueprint('aprobaciones', __name__, url_prefix='/admin/aprobaciones')


def _ahora():
    return ahora_argentina().replace(tzinfo=None)


def _pesos(v):
    s = f'{float(v):,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return '$' + s


@aprobaciones_bp.before_request
@login_required
def _guard():
    # admin_requerido lo aplica cada vista, pero forzamos login temprano igual.
    if current_user.is_authenticated and current_user.debe_cambiar_password:
        return redirect(url_for('auth.cambiar_password'))


def _venta_rev_o_404(pid):
    """Trae un pedido SOLO si es una venta de revendedora. Si no, 404."""
    p = Pedido.query.get_or_404(pid)
    if not p.es_de_revendedora:
        abort(404)
    return p


# ============================================================================
#  LA BANDEJA
# ============================================================================

@aprobaciones_bp.route('/')
@admin_requerido
def bandeja():
    """
    Lista de ventas de revendedora. Por defecto muestra las que ESPERAN
    aprobacion (lo urgente arriba). Se puede filtrar por estado y por revendedora.
    """
    estado = (request.args.get('estado') or 'PENDIENTE').strip().upper()
    rev_id = request.args.get('rev', type=int)

    stmt = Pedido.query.filter(Pedido.origen == OrigenPedido.REVENDEDORA)
    if estado in EstadoPedido.TODOS:
        stmt = stmt.filter(Pedido.estado == estado)
    elif estado == 'TODAS':
        pass
    else:
        estado = 'PENDIENTE'
        stmt = stmt.filter(Pedido.estado == estado)
    if rev_id:
        stmt = stmt.filter(Pedido.revendedora_id == rev_id)

    lista = stmt.order_by(Pedido.enviado_en.desc().nullslast(),
                          Pedido.creado.desc()).all()

    # Conteos para los tabs (lo importante: cuantas esperan)
    base = Pedido.query.filter(Pedido.origen == OrigenPedido.REVENDEDORA)
    n_pendientes = base.filter(Pedido.estado == EstadoPedido.PENDIENTE).count()

    # Revendedoras que alguna vez mandaron algo (para el filtro)
    revendedoras = (Usuario.query
                    .join(Pedido, Pedido.revendedora_id == Usuario.id)
                    .filter(Pedido.origen == OrigenPedido.REVENDEDORA)
                    .distinct().order_by(Usuario.nombre).all())

    return render_template('admin/aprobaciones.html',
                           lista=lista, estado_sel=estado, rev_sel=rev_id,
                           n_pendientes=n_pendientes, revendedoras=revendedoras,
                           estados=EstadoPedido.ETIQUETAS)


# ============================================================================
#  EL DETALLE (donde se aprueba / edita / rechaza)
# ============================================================================

@aprobaciones_bp.route('/<int:pid>')
@admin_requerido
def detalle(pid):
    p = _venta_rev_o_404(pid)
    nivel = comisiones.nivel_de(p.revendedora_id)

    # Para el editor: cada item con SU piso recalculado hoy (por si Torres cambio
    # el costo desde que Nadia armo el pedido).
    items_data = []
    for it in p.items:
        prod = Producto.query.filter_by(codigo=it.codigo, activo=True).first()
        if prod is not None:
            minimo = comisiones.precio_minimo(prod, nivel['comision'])
            lista = comisiones.precios_para(prod, get_ajustes(), nivel['comision'])['lista']
            costo = float(prod.costo_neto)
            existe = True
        else:
            # El producto ya no esta en catalogo: se respeta lo congelado en el item
            minimo = float(it.precio_unitario)
            lista = float(it.precio_unitario)
            costo = float(it.costo_unitario or 0)
            existe = False
        items_data.append({
            'codigo': it.codigo, 'nombre': it.nombre, 'cantidad': it.cantidad,
            'precio': float(it.precio_unitario), 'minimo': minimo, 'lista': lista,
            'costo': costo, 'existe': existe,
        })

    return render_template('admin/aprobacion_detalle.html', p=p, nivel=nivel,
                           items_data=items_data,
                           margen_casa=comisiones.margen_casa_minimo(),
                           minimo_neto=comisiones.minimo_neto(),
                           ajustes=get_ajustes())


# ============================================================================
#  v0.40.0 · BUSCADOR PARA AGREGAR UN PRODUCTO A LA VENTA
# ============================================================================

@aprobaciones_bp.route('/<int:pid>/buscar')
@admin_requerido
def buscar_producto(pid):
    """
    Buscador JSON para AGREGAR un producto a una venta de revendedora que
    Juliana esta editando.

    EL CASO REAL QUE RESUELVE:
      Nadia vendio 10 Rumba. Juliana llama a Torres y no hay stock. Antes solo
      podia sacar el producto (cantidad 0) o rechazar el pedido entero y pedirle
      a Nadia que lo rearme. Ahora puede llamar al cliente, ofrecerle Mellizas,
      y hacer el cambio en el momento.

    OJO — POR QUE NO SE REUSA revendedora.vender_buscar NI admin.ofertas_buscar:
      · vender_buscar tiene @revendedora_requerido (Juliana recibiria un 403) y
        calcula el piso con la comision de QUIEN ESTA LOGUEADO. Aca hay que usar
        la comision de LA REVENDEDORA DEL PEDIDO, que es otra persona.
      · ofertas_buscar devuelve el piso del 10% del admin, que NO es el piso de
        ella (el suyo es 8/9/10% segun su escalon).
      Devolver el piso equivocado seria regalarle margen a la casa o pisarle la
      comision a Nadia. Por eso esta ruta es propia y ata el piso al pedido.
    """
    p = _venta_rev_o_404(pid)

    q = (request.args.get('q') or '').strip()
    rubro = (request.args.get('rubro') or '').strip()
    if not q and not rubro:
        return jsonify([])

    nivel = comisiones.nivel_de(p.revendedora_id)
    ajustes = get_ajustes()

    # Codigos que YA estan en el pedido: se marcan para no duplicar renglones.
    ya_estan = {it.codigo for it in p.items}

    stmt = Producto.query.filter(Producto.activo.is_(True))
    if rubro:
        stmt = stmt.filter(Producto.rubro == rubro)
    if q:
        like = f'%{q}%'
        stmt = stmt.filter(or_(Producto.nombre.ilike(like),
                               Producto.codigo.ilike(like),
                               Producto.marca.ilike(like)))
    prods = stmt.order_by(Producto.nombre).limit(40).all()

    res = []
    for prod in prods:
        pr = comisiones.precios_para(prod, ajustes, nivel['comision'])
        res.append({
            'codigo': prod.codigo,
            'nombre': prod.nombre,
            'marca': prod.marca or '',
            'rubro': prod.rubro or '',
            'lista': pr['lista'],       # precio sugerido al agregarlo
            'minimo': pr['minimo'],     # SU piso, segun SU escalon
            'costo': pr['costo'],
            'ya_esta': prod.codigo in ya_estan,
        })
    return jsonify(res)


# ============================================================================
#  APROBAR
# ============================================================================

@aprobaciones_bp.route('/<int:pid>/aprobar', methods=['POST'])
@admin_requerido
def aprobar(pid):
    """
    Aprueba la venta. Recalcula la comision con el escalon de HOY y la CONGELA.

    Puede venir con ediciones (items_json): si Torres tenia stock parcial, Juliana
    ajusto cantidades o saco productos. En ese caso se rearman los items y se
    revalida TODO (minimo + piso del 6%) antes de aprobar.
    """
    p = _venta_rev_o_404(pid)

    if p.estado != EstadoPedido.PENDIENTE:
        flash(f'Este pedido ya está {p.estado_etiqueta.lower()}, no se puede aprobar de nuevo.',
              'warning')
        return redirect(url_for('aprobaciones.detalle', pid=pid))

    nivel = comisiones.nivel_de(p.revendedora_id)
    comision_pct = nivel['comision']

    # ¿Vino editado?
    hubo_edicion = False
    try:
        editado = json.loads(request.form.get('items_json') or 'null')
    except (ValueError, TypeError):
        editado = None

    if editado:
        # --- Rearmar items desde la edicion de Juliana ---
        items_calc = []
        cambios = []
        originales = {it.codigo: it for it in p.items}
        for e in editado:
            cod = str(e.get('codigo') or '')
            try:
                cant = int(e.get('cantidad') or 0)
            except (TypeError, ValueError):
                cant = 0
            if cant < 1:
                # cantidad 0 = Juliana saco este producto (no habia stock)
                if cod in originales:
                    o = originales[cod]
                    cambios.append(f'quitó [{cod}] {o.nombre} · eran {o.cantidad} u.')
                continue

            prod = Producto.query.filter_by(codigo=cod, activo=True).first()
            if prod is not None:
                piso = comisiones.precio_minimo(prod, comision_pct)
                costo = float(prod.costo_neto)
            elif cod in originales:
                piso = float(originales[cod].precio_unitario)
                costo = float(originales[cod].costo_unitario or 0)
                prod = None
            else:
                continue

            try:
                precio = round(float(e.get('precio') or piso), 2)
            except (TypeError, ValueError):
                precio = piso
            if precio < piso:        # el mismo candado de siempre
                precio = piso

            nombre = prod.nombre if prod else originales[cod].nombre
            items_calc.append({
                'codigo': cod, 'nombre': nombre, 'cantidad': cant,
                'precio_unitario': precio, 'costo_unitario': costo,
                'subtotal': round(precio * cant, 2),
            })

            # Detectar cambios para el historial.
            # v0.41.0 · El texto tiene que entenderse SOLO, sin ir a buscar el
            # codigo a la tabla: por eso va siempre el nombre del producto. Y se
            # usa "·" y "×" en vez de pegar la cantidad con una "x", que se
            # confundia con el nombre del producto ("Agua x2000cc x1000").
            if cod in originales:
                oc = originales[cod].cantidad
                op = float(originales[cod].precio_unitario)
                if oc != cant:
                    cambios.append(f'[{cod}] {nombre} · cantidad {oc} → {cant} u.')
                if abs(op - precio) > 0.01:
                    cambios.append(f'[{cod}] {nombre} · precio {_pesos(op)} → {_pesos(precio)}')
            else:
                # v0.40.0 · Producto AGREGADO por Juliana (no venia en el pedido
                # original). Tipico: no habia stock de uno y se cambio por otro.
                # Queda registrado igual que las quitas, para que Nadia entienda
                # que paso con su venta.
                cambios.append(f'agregó [{cod}] {nombre} · {cant} u. × {_pesos(precio)}')

        if not items_calc:
            flash('No podés aprobar un pedido sin productos. Si no hay stock de nada, '
                  'rechazalo.', 'error')
            return redirect(url_for('aprobaciones.detalle', pid=pid))

        snap = comisiones.calcular(items_calc, comision_pct)

        # Revalidar minimo
        if snap['neto_total'] < comisiones.minimo_neto():
            flash(f'Con esos cambios el pedido queda en {_pesos(snap["neto_total"])} netos, '
                  f'por debajo del mínimo de {_pesos(comisiones.minimo_neto())}. '
                  f'Ajustá o rechazá.', 'error')
            return redirect(url_for('aprobaciones.detalle', pid=pid))

        # Revalidar el piso del 6% (una edicion podria romperlo)
        if not comisiones.cumple_piso_casa(snap):
            flash(f'Con esos cambios a la casa le quedaría {snap["margen_casa_pct"]}%, '
                  f'por debajo del mínimo de {comisiones.margen_casa_minimo()}%. '
                  f'Subí algún precio.', 'error')
            return redirect(url_for('aprobaciones.detalle', pid=pid))

        # Reemplazar items
        total_anterior = float(p.total)
        for it in list(p.items):
            db.session.delete(it)
        db.session.flush()
        for it in items_calc:
            db.session.add(ItemPedido(pedido_id=p.id, **it))
        if cambios:
            db.session.add(ModificacionPedido(
                pedido_id=p.id,
                descripcion='Al aprobar: ' + '; '.join(cambios),
                total_anterior=total_anterior, total_nuevo=snap['total'],
                hecho_por=current_user.nombre,
            ))
            hubo_edicion = True
    else:
        # Sin edicion: recalcular sobre los items tal cual, con el nivel de hoy
        items_calc = [{
            'cantidad': it.cantidad,
            'precio_unitario': float(it.precio_unitario),
            'costo_unitario': float(it.costo_unitario or 0),
        } for it in p.items]
        snap = comisiones.calcular(items_calc, comision_pct)

        # Aunque no se edite, revalidamos el piso: el costo de Torres pudo cambiar
        # entre que Nadia armo el pedido y hoy que Juliana lo aprueba.
        if not comisiones.cumple_piso_casa(snap):
            flash(f'Ojo: con los costos de hoy, a la casa le quedaría '
                  f'{snap["margen_casa_pct"]}% (mínimo {comisiones.margen_casa_minimo()}%). '
                  f'Editá los precios antes de aprobar.', 'error')
            return redirect(url_for('aprobaciones.detalle', pid=pid))

    # --- CONGELAR el snapshot y aprobar ---
    p.total = snap['total']
    p.neto_total = snap['neto_total']
    p.costo_total = snap['costo_total']
    p.margen_pct = snap['margen_pct']
    p.comision_pct = snap['comision_pct']
    p.comision_monto = snap['comision_monto']
    p.margen_casa_pct = snap['margen_casa_pct']
    p.estado = EstadoPedido.CONFIRMADO
    p.aprobado_por = current_user.nombre
    p.aprobado_en = _ahora()
    if hubo_edicion:
        p.modificado_en = _ahora()

    db.session.commit()

    flash(f'Venta {p.numero} APROBADA ✓ · Comisión de {p.revendedora_nombre}: '
          f'{_pesos(p.comision_monto)} ({p.comision_pct}%). '
          f'{"Se ajustó según tu edición. " if hubo_edicion else ""}'
          f'Ya le aparece confirmada en su portal.', 'success')
    return redirect(url_for('aprobaciones.detalle', pid=pid))


# ============================================================================
#  RECHAZAR (motivo obligatorio)
# ============================================================================

@aprobaciones_bp.route('/<int:pid>/rechazar', methods=['POST'])
@admin_requerido
def rechazar(pid):
    p = _venta_rev_o_404(pid)

    if p.estado != EstadoPedido.PENDIENTE:
        flash('Solo se puede rechazar un pedido que está pendiente.', 'warning')
        return redirect(url_for('aprobaciones.detalle', pid=pid))

    motivo = (request.form.get('motivo') or '').strip()
    if not motivo:
        flash('Escribí el motivo del rechazo. Nadia lo va a ver en su portal, '
              'así sabe qué pasó (ej: "Torres sin stock de estos productos").', 'error')
        return redirect(url_for('aprobaciones.detalle', pid=pid))

    p.estado = EstadoPedido.RECHAZADO
    p.rechazado_motivo = motivo
    p.aprobado_por = current_user.nombre     # reusamos el campo: quien lo resolvio
    p.aprobado_en = _ahora()
    # La comision NO se congela: un pedido rechazado no paga nada.
    p.comision_monto = None
    db.session.commit()

    flash(f'Venta {p.numero} rechazada. Nadia va a ver el motivo en su portal.', 'warning')
    return redirect(url_for('aprobaciones.detalle', pid=pid))


# ============================================================================
#  MARCAR ENTREGADO / PAGAR COMISION (acciones post-aprobacion)
# ============================================================================

@aprobaciones_bp.route('/<int:pid>/entregado', methods=['POST'])
@admin_requerido
def entregado(pid):
    p = _venta_rev_o_404(pid)
    if p.estado != EstadoPedido.CONFIRMADO:
        flash('Solo se marca como entregado un pedido aprobado.', 'warning')
        return redirect(url_for('aprobaciones.detalle', pid=pid))
    p.estado = EstadoPedido.ENTREGADO
    db.session.commit()
    flash(f'{p.numero} marcado como entregado.', 'success')
    return redirect(url_for('aprobaciones.detalle', pid=pid))


@aprobaciones_bp.route('/<int:pid>/pagar-comision', methods=['POST'])
@admin_requerido
def pagar_comision(pid):
    p = _venta_rev_o_404(pid)
    if not p.paga_comision:
        flash('Este pedido no tiene comisión a pagar.', 'warning')
        return redirect(url_for('aprobaciones.detalle', pid=pid))
    p.comision_pagada = True
    p.comision_pagada_en = _ahora()
    p.comision_pagada_por = current_user.nombre
    db.session.commit()
    flash(f'Comisión de {p.revendedora_nombre} marcada como PAGADA '
          f'({_pesos(p.comision_monto)}).', 'success')
    return redirect(url_for('aprobaciones.detalle', pid=pid))
