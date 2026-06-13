"""
app/services.py — Logica de negocio reutilizable (web + CLI).
"""
from .extensions import db
from .models import Producto
from .utils.timezone import ahora_argentina


def aplicar_importacion(productos):
    """
    Aplica la lista de productos leida de la planilla (upsert por codigo):
      - Si el codigo ya existe -> actualiza rubro, nombre y costo.
      - Si es nuevo -> lo crea.
      - Marca como 'en_ultima_lista' SOLO los que vinieron en este archivo.
        (Los que no vinieron quedan en la base pero marcados como fuera de lista,
         por si el mayorista los discontinuo. No se borra nada, por seguridad.)

    Es atomico: si algo falla, se hace rollback y no queda a medias.
    Devuelve un dict con el resumen: nuevos, actualizados, total, fuera_de_lista.
    """
    ahora = ahora_argentina().replace(tzinfo=None)
    nuevos = 0
    actualizados = 0

    try:
        # 1) Todos pasan a "fuera de lista"; los que vengan se reactivan abajo
        Producto.query.update({Producto.en_ultima_lista: False})

        # 2) Indice de los existentes para no consultar 1x1
        existentes = {p.codigo: p for p in Producto.query.all()}

        for item in productos:
            cod = item['codigo']
            p = existentes.get(cod)
            if p is None:
                p = Producto(codigo=cod, creado=ahora)
                db.session.add(p)
                existentes[cod] = p
                nuevos += 1
            else:
                actualizados += 1

            p.rubro = item['rubro']
            p.nombre = item['nombre']
            p.costo_neto = item['costo_neto']
            p.en_ultima_lista = True
            p.activo = True
            p.actualizado = ahora

        db.session.commit()
    except Exception:
        db.session.rollback()
        raise

    total = Producto.query.count()
    fuera_de_lista = Producto.query.filter_by(en_ultima_lista=False).count()

    return {
        'nuevos': nuevos,
        'actualizados': actualizados,
        'total': total,
        'fuera_de_lista': fuera_de_lista,
    }
