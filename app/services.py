"""
app/services.py — Logica de negocio reutilizable (web + CLI).

v0.20.0 -> La importacion ahora GUARDA HISTORIAL: compara el costo viejo contra
           el nuevo de cada producto, cuenta cuantos subieron / bajaron, y deja
           el detalle en Importacion / ImportacionItem. Asi Ivan puede controlar
           que le cambio el mayorista sin tener acceso a su base.
"""
from .extensions import db
from .models import Producto, Importacion, ImportacionItem
from .utils.timezone import ahora_argentina


# Diferencia de costo (en $) a partir de la cual se considera que "cambio" el
# precio. Evita contar como suba una diferencia de redondeo de milesimas.
TOLERANCIA = 0.001


def aplicar_importacion(productos, archivo=None, usuario=None):
    """
    Aplica la lista de productos leida de la planilla (upsert por codigo):
      - Si el codigo ya existe -> actualiza rubro, nombre y costo.
      - Si es nuevo -> lo crea.
      - Marca como 'en_ultima_lista' SOLO los que vinieron en este archivo.
        (Los que no vinieron quedan en la base pero marcados como fuera de lista,
         por si el mayorista los discontinuo. No se borra nada, por seguridad.)

    v0.20.0: ademas registra una Importacion con el resumen, y un ImportacionItem
    por cada producto que CAMBIO de precio o es NUEVO (los que quedaron igual no
    se guardan, para no llenar la base con 1600 filas identicas).

    Es atomico: si algo falla, se hace rollback y no queda a medias.
    Devuelve un dict con el resumen (compatible con lo que ya usaba admin.py) +
    las claves nuevas: subieron, bajaron, sin_cambio, variacion_promedio, importacion_id.

    'archivo' y 'usuario' son opcionales para que la CLI existente siga andando
    sin cambios.
    """
    ahora = ahora_argentina().replace(tzinfo=None)
    nuevos = 0
    actualizados = 0
    subieron = 0
    bajaron = 0
    sin_cambio = 0
    variaciones = []          # % de variacion de los que cambiaron (para el promedio)
    detalle = []              # filas que van a ImportacionItem

    try:
        # 1) Todos pasan a "fuera de lista"; los que vengan se reactivan abajo
        Producto.query.update({Producto.en_ultima_lista: False})

        # 2) Indice de los existentes para no consultar 1x1
        existentes = {p.codigo: p for p in Producto.query.all()}

        for item in productos:
            cod = item['codigo']
            costo_nuevo = float(item['costo_neto'])
            p = existentes.get(cod)

            if p is None:
                # --- Producto NUEVO ---
                p = Producto(codigo=cod, creado=ahora)
                db.session.add(p)
                existentes[cod] = p
                nuevos += 1
                detalle.append({
                    'codigo': cod, 'nombre': item['nombre'],
                    'costo_anterior': None, 'costo_nuevo': costo_nuevo,
                    'variacion_pct': None, 'es_nuevo': True,
                })
            else:
                # --- Producto EXISTENTE: comparamos el costo ---
                actualizados += 1
                costo_viejo = float(p.costo_neto) if p.costo_neto is not None else None

                if costo_viejo is None or abs(costo_nuevo - costo_viejo) < TOLERANCIA:
                    sin_cambio += 1
                else:
                    if costo_viejo > 0:
                        var = round((costo_nuevo - costo_viejo) / costo_viejo * 100, 2)
                    else:
                        var = None

                    if costo_nuevo > costo_viejo:
                        subieron += 1
                    else:
                        bajaron += 1

                    if var is not None:
                        variaciones.append(var)

                    detalle.append({
                        'codigo': cod, 'nombre': item['nombre'],
                        'costo_anterior': costo_viejo, 'costo_nuevo': costo_nuevo,
                        'variacion_pct': var, 'es_nuevo': False,
                    })

            p.rubro = item['rubro']
            p.nombre = item['nombre']
            p.costo_neto = item['costo_neto']
            p.en_ultima_lista = True
            p.activo = True
            p.actualizado = ahora

        db.session.flush()

        total = Producto.query.count()
        fuera_de_lista = Producto.query.filter_by(en_ultima_lista=False).count()
        var_prom = round(sum(variaciones) / len(variaciones), 2) if variaciones else None

        # 3) Guardar el registro de la importacion + su detalle
        imp = Importacion(
            archivo=archivo, creado=ahora, creado_por=usuario,
            nuevos=nuevos, actualizados=actualizados,
            subieron=subieron, bajaron=bajaron, sin_cambio=sin_cambio,
            fuera_de_lista=fuera_de_lista, total_catalogo=total,
            variacion_promedio=var_prom,
        )
        db.session.add(imp)
        db.session.flush()

        for d in detalle:
            db.session.add(ImportacionItem(importacion_id=imp.id, **d))

        db.session.commit()
        imp_id = imp.id

    except Exception:
        db.session.rollback()
        raise

    return {
        'nuevos': nuevos,
        'actualizados': actualizados,
        'total': total,
        'fuera_de_lista': fuera_de_lista,
        # --- v0.20.0 ---
        'subieron': subieron,
        'bajaron': bajaron,
        'sin_cambio': sin_cambio,
        'variacion_promedio': var_prom,
        'importacion_id': imp_id,
    }
