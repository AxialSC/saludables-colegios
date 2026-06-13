"""
app/cliente.py — Blueprint PUBLICO (la tienda que ve el cliente).
Sin login. Muestra el catalogo con PRECIOS FINALES (markup + IVA).
El carrito y el minimo de compra llegan en la v0.4.
"""
from flask import Blueprint, render_template, request
from sqlalchemy import select, or_

from .extensions import db
from .models import Producto, get_ajustes
from . import pricing

cliente_bp = Blueprint('cliente', __name__)

POR_PAGINA = 24


def _rubro_display(rubro):
    """Limpia el nombre del rubro para mostrarlo lindo al cliente."""
    if not rubro:
        return 'Varios'
    r = rubro.replace('TEOLOGISTICA', '').strip()
    r = r.replace('Y HOGAR', 'y Hogar')
    return r.title()


@cliente_bp.route('/')
def catalogo():
    page = request.args.get('page', 1, type=int)
    q = (request.args.get('q') or '').strip()
    rubro = (request.args.get('rubro') or '').strip()

    ajustes = get_ajustes()

    stmt = select(Producto).where(Producto.activo.is_(True))
    if rubro:
        stmt = stmt.where(Producto.rubro == rubro)
    if q:
        like = f'%{q}%'
        stmt = stmt.where(or_(Producto.nombre.ilike(like),
                              Producto.codigo.ilike(like),
                              Producto.rubro.ilike(like)))
    stmt = stmt.order_by(Producto.rubro, Producto.nombre)

    paginacion = db.paginate(stmt, page=page, per_page=POR_PAGINA, error_out=False)

    # Precalculamos los precios de cada producto de la pagina
    items = []
    for p in paginacion.items:
        items.append({'p': p, 'precios': pricing.precios(p, ajustes)})

    # Rubros para los filtros (solo de productos activos)
    rubros_raw = db.session.execute(
        select(Producto.rubro).where(Producto.activo.is_(True))
        .distinct().order_by(Producto.rubro)
    ).scalars().all()
    rubros = [(r, _rubro_display(r)) for r in rubros_raw]

    return render_template('cliente/catalogo.html',
                           items=items, paginacion=paginacion,
                           rubros=rubros, q=q, rubro_sel=rubro,
                           ajustes=ajustes, rubro_display=_rubro_display)
