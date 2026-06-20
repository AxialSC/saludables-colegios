"""
app/cli.py — Comandos de linea de comando.
  flask --app run init-db                  -> crea las tablas
  flask --app run seed-data                -> crea usuarios iniciales
  flask --app run import-planilla <ruta>   -> importa una planilla (respaldo / pruebas)
  flask --app run normalizar-rubros        -> limpia rubros duplicados (PREVISUALIZACION)
  flask --app run normalizar-rubros --aplicar  -> aplica la limpieza de rubros
"""
import click
from flask.cli import with_appcontext

from .extensions import db
from .models import Usuario, Rol
from .services import aplicar_importacion
from .utils.import_planilla import leer_planilla


@click.command('init-db')
@with_appcontext
def init_db():
    """Crea todas las tablas de la base de datos (no borra las existentes)."""
    db.create_all()
    click.echo('OK -> Tablas creadas.')


@click.command('seed-data')
@with_appcontext
def seed_data():
    """Crea los usuarios iniciales si no existen."""
    creados = []

    if not Usuario.query.filter_by(usuario='ivan').first():
        ivan = Usuario(usuario='ivan', nombre='Ivan Abrigo (AXIAL)',
                       rol=Rol.SUPER_ADMIN, debe_cambiar_password=True)
        ivan.set_password('Axial2026')
        db.session.add(ivan)
        creados.append('ivan / Axial2026 (SUPER_ADMIN)')

    if not Usuario.query.filter_by(usuario='juliana').first():
        juliana = Usuario(usuario='juliana', nombre='Juliana Maciel',
                          rol=Rol.ADMIN, debe_cambiar_password=True)
        juliana.set_password('Saludables2026')
        db.session.add(juliana)
        creados.append('juliana / Saludables2026 (ADMIN)')

    db.session.commit()

    if creados:
        click.echo('OK -> Usuarios creados:')
        for c in creados:
            click.echo('   - ' + c)
        click.echo('IMPORTANTE: ambos deben cambiar la contrasena en el primer ingreso.')
    else:
        click.echo('Los usuarios ya existian, no se creo nada.')


@click.command('import-planilla')
@click.argument('ruta')
@with_appcontext
def import_planilla_cmd(ruta):
    """Importa una planilla del mayorista desde la consola (respaldo)."""
    productos, resumen = leer_planilla(ruta)
    res = aplicar_importacion(productos)
    click.echo(f'Leidos: {resumen["productos_leidos"]} | descartados: {resumen["descartadas"]}')
    click.echo(f'OK -> nuevos: {res["nuevos"]} | actualizados: {res["actualizados"]} '
               f'| total: {res["total"]} | fuera de lista: {res["fuera_de_lista"]}')


@click.command('migrar-v06')
@with_appcontext
def migrar_v06():
    """
    Migracion v0.6: agrega columnas nuevas a 'pedidos' (sin perder datos) y
    crea la tabla 'cobros'. Es idempotente: se puede correr varias veces sin riesgo.
    """
    from sqlalchemy import text

    nuevas = {
        'ip_origen': 'VARCHAR(45)',
        'dispositivo': 'VARCHAR(20)',
        'facturado_en': 'DATETIME',
        'anulado_por': 'VARCHAR(80)',
        'anulado_en': 'DATETIME',
        'anulado_motivo': 'VARCHAR(200)',
    }
    existentes = [fila[1] for fila in db.session.execute(text("PRAGMA table_info(pedidos)"))]
    agregadas = 0
    for col, tipo in nuevas.items():
        if col not in existentes:
            db.session.execute(text(f'ALTER TABLE pedidos ADD COLUMN {col} {tipo}'))
            click.echo(f'   + columna pedidos.{col}')
            agregadas += 1
    db.session.commit()

    # Crea las tablas que falten (ej: cobros). No toca las existentes.
    db.create_all()

    click.echo(f'OK -> migración v0.6 aplicada ({agregadas} columnas nuevas + tabla cobros).')


@click.command('migrar-v08')
@with_appcontext
def migrar_v08():
    """
    Migracion v0.8: agrega columna 'modificado_en' a pedidos y crea la tabla
    'modificaciones_pedido'. Idempotente y sin perder datos.
    """
    from sqlalchemy import text

    existentes = [fila[1] for fila in db.session.execute(text("PRAGMA table_info(pedidos)"))]
    agregadas = 0
    if 'modificado_en' not in existentes:
        db.session.execute(text('ALTER TABLE pedidos ADD COLUMN modificado_en DATETIME'))
        click.echo('   + columna pedidos.modificado_en')
        agregadas += 1
    db.session.commit()

    db.create_all()  # crea modificaciones_pedido si falta
    click.echo(f'OK -> migración v0.8 aplicada ({agregadas} columna + tabla modificaciones).')


@click.command('migrar-v10')
@with_appcontext
def migrar_v10():
    """
    Migracion v0.10: agrega columnas 'es_saludable' y 'es_alcoholica' a 'productos'.
    Idempotente y sin perder datos. Las filas existentes quedan en 0 (no marcado).
    """
    from sqlalchemy import text

    nuevas = {
        'es_saludable': 'BOOLEAN NOT NULL DEFAULT 0',
        'es_alcoholica': 'BOOLEAN NOT NULL DEFAULT 0',
    }
    existentes = [fila[1] for fila in db.session.execute(text("PRAGMA table_info(productos)"))]
    agregadas = 0
    for col, tipo in nuevas.items():
        if col not in existentes:
            db.session.execute(text(f'ALTER TABLE productos ADD COLUMN {col} {tipo}'))
            click.echo(f'   + columna productos.{col}')
            agregadas += 1
    db.session.commit()

    click.echo(f'OK -> migración v0.10 aplicada ({agregadas} columnas nuevas en productos).')


@click.command('migrar-v11')
@with_appcontext
def migrar_v11():
    """
    Migracion v0.11: agrega 'categoria' a productos y la deriva de los tildes viejos.
      - es_alcoholica = 1            -> BEBIDA_CON  (prioridad)
      - es_saludable = 1 (no alcohol) -> COMIDA_SALUDABLE
      - el resto queda sin categoria.
    La conversion SOLO corre cuando se crea la columna (idempotente: correrla de
    nuevo no pisa lo que Ivan/Juliana hayan re-categorizado a mano).
    """
    from sqlalchemy import text

    existentes = [fila[1] for fila in db.session.execute(text("PRAGMA table_info(productos)"))]
    if 'categoria' in existentes:
        click.echo('La columna productos.categoria ya existe. No se hace nada (idempotente).')
        return

    db.session.execute(text(
        "ALTER TABLE productos ADD COLUMN categoria VARCHAR(20) NOT NULL DEFAULT ''"))
    click.echo('   + columna productos.categoria')

    # Derivar de los tildes viejos (solo en esta primera corrida)
    r1 = db.session.execute(text(
        "UPDATE productos SET categoria='BEBIDA_CON' WHERE es_alcoholica=1"))
    r2 = db.session.execute(text(
        "UPDATE productos SET categoria='COMIDA_SALUDABLE' "
        "WHERE es_saludable=1 AND (es_alcoholica=0 OR es_alcoholica IS NULL) AND categoria=''"))
    db.session.commit()

    click.echo(f'   ~ {r1.rowcount} producto(s) -> Bebida con alcohol')
    click.echo(f'   ~ {r2.rowcount} producto(s) -> Comida saludable')
    click.echo('OK -> migración v0.11 aplicada (categoria creada y derivada de los tildes).')


@click.command('migrar-v12')
@with_appcontext
def migrar_v12():
    """
    Migracion v0.12: crea las tablas nuevas para Ofertas y Cotizaciones
    (Cumpleaños / Colegios). NO toca ninguna tabla existente: db.create_all()
    solo crea las tablas que faltan, nunca modifica ni borra las que ya estan.
    Tablas nuevas: ofertas, cotizaciones, cotizacion_items.
    Idempotente: correrla de nuevo no hace nada.
    """
    from sqlalchemy import inspect

    insp = inspect(db.engine)
    antes = set(insp.get_table_names())

    db.create_all()  # solo agrega tablas faltantes

    insp = inspect(db.engine)
    despues = set(insp.get_table_names())
    nuevas = sorted(despues - antes)

    if nuevas:
        for t in nuevas:
            click.echo(f'   + tabla {t}')
        click.echo(f'OK -> migración v0.12 aplicada ({len(nuevas)} tabla(s) nueva(s)).')
    else:
        click.echo('Las tablas de v0.12 ya existían. No se hizo nada (idempotente).')


@click.command('migrar-v12b')
@with_appcontext
def migrar_v12b():
    """
    Migracion v0.12b: agrega columnas de 'bolsa' a la tabla cotizaciones
    (incluye_bolsa, costo_bolsa). Idempotente y sin perder datos.
    Necesaria para el Cotizador de Cumpleaños/Colegios (Paso C1).
    """
    from sqlalchemy import text

    db.create_all()  # asegura que exista la tabla cotizaciones (creada en v0.12)

    nuevas = {
        'incluye_bolsa': 'BOOLEAN NOT NULL DEFAULT 0',
        'costo_bolsa': 'NUMERIC(12,2) NOT NULL DEFAULT 0',
    }
    existentes = [fila[1] for fila in db.session.execute(text("PRAGMA table_info(cotizaciones)"))]
    agregadas = 0
    for col, tipo in nuevas.items():
        if col not in existentes:
            db.session.execute(text(f'ALTER TABLE cotizaciones ADD COLUMN {col} {tipo}'))
            click.echo(f'   + columna cotizaciones.{col}')
            agregadas += 1
    db.session.commit()

    if agregadas:
        click.echo(f'OK -> migración v0.12b aplicada ({agregadas} columna(s) nueva(s)).')
    else:
        click.echo('Las columnas de bolsa ya existían. No se hizo nada (idempotente).')


@click.command('normalizar-rubros')
@click.option('--aplicar', is_flag=True, default=False,
              help='Aplica los cambios. SIN este flag corre en PREVISUALIZACION (no toca nada).')
@with_appcontext
def normalizar_rubros(aplicar):
    """
    Limpia rubros duplicados de 'productos' por diferencias invisibles:
    espacios al inicio/final, espacios dobles internos y mayusculas/minusculas.

    Por defecto corre en modo PREVISUALIZACION (dry-run): muestra que pasaria
    pero NO modifica nada. Con --aplicar hace los cambios de verdad.

    Criterio (sin inventar rubros nuevos):
      1. Limpieza SIEMPRE segura: trim + colapsar espacios internos.
         (ej:  "Bebidas "  ->  "Bebidas")
      2. Unificacion por mayus/minus: los rubros que SOLO se diferencian en
         espacios o mayusculas se agrupan y todos pasan a la forma 'ganadora'
         = la que tiene MAS productos (si hay empate, la primera alfabeticamente).
         (ej:  "BEBIDAS" (2 prod)  +  "Bebidas" (40 prod)  ->  "Bebidas")
      NO une rubros semanticamente distintos (ej: 'Gaseosas' y 'Bebidas' quedan
      separados: eso es decision tuya, no del comando).

    Seguridad:
      - Si un rubro queda VACIO al limpiarlo (era todo espacios), se AVISA y NO se
        toca (la columna es NOT NULL: lo revisas a mano).
      - Hace UPDATE matcheando el texto EXACTO original, fila por fila.
    """
    from sqlalchemy import text
    import re
    from collections import defaultdict

    # 1. Rubros actuales con su conteo de productos
    filas = db.session.execute(text(
        "SELECT rubro, COUNT(*) AS n FROM productos GROUP BY rubro ORDER BY rubro"
    )).all()

    if not filas:
        click.echo('No hay productos cargados. Nada que hacer.')
        return

    def limpiar(s):
        # trim + colapsar espacios internos (NO toca mayus/minus)
        return re.sub(r'\s+', ' ', (s or '').strip())

    # Agrupar por clave insensible a mayus/minus y espacios
    grupos = defaultdict(list)   # clave -> [(rubro_original, rubro_limpio, n), ...]
    vacios = []                  # rubros que quedan vacios tras limpiar
    for rubro_orig, n in filas:
        limpio = limpiar(rubro_orig)
        if limpio == '':
            vacios.append((rubro_orig, n))
            continue
        grupos[limpio.casefold()].append((rubro_orig, limpio, n))

    # Elegir la forma ganadora de cada grupo y armar los cambios
    cambios = []          # (rubro_origen, rubro_destino, n)
    grupos_afectados = 0
    for _clave, variantes in grupos.items():
        por_limpio = defaultdict(int)   # cuenta productos por forma LIMPIA
        for _orig, limpio, n in variantes:
            por_limpio[limpio] += n
        # ganadora: mas productos; empate -> alfabetica
        ganadora = sorted(por_limpio.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]

        hubo_cambio = False
        for orig, _limpio, n in variantes:
            if orig != ganadora:
                cambios.append((orig, ganadora, n))
                hubo_cambio = True
        if hubo_cambio:
            grupos_afectados += 1

    # 2. Reporte
    modo = '(PREVISUALIZACION - no se toca nada)' if not aplicar else '(APLICANDO)'
    click.echo('')
    click.echo('=== NORMALIZACION DE RUBROS ' + modo + ' ===')
    click.echo(f'Rubros distintos hoy: {len(filas)}')
    click.echo(f'Grupos con duplicados: {grupos_afectados}')
    click.echo('')

    if not cambios:
        click.echo('No hay rubros duplicados por espacios/mayusculas. Todo limpio.')
    else:
        click.echo('Cambios que se harian:')
        for orig, destino, n in sorted(cambios, key=lambda c: c[1].casefold()):
            click.echo(f'   "{orig}"  ->  "{destino}"   ({n} producto/s)')

    if vacios:
        click.echo('')
        click.echo('ATENCION - rubros que quedan VACIOS al limpiar (NO se tocan):')
        for orig, n in vacios:
            click.echo(f'   "{orig}"   ({n} producto/s)  <- revisalo a mano')

    # 3. Aplicar (solo con --aplicar)
    if not aplicar:
        click.echo('')
        click.echo('Esto fue solo una PREVISUALIZACION. No se modifico nada.')
        click.echo('Si estas de acuerdo, primero hace backup y despues corre:')
        click.echo('   flask --app run normalizar-rubros --aplicar')
        return

    if not cambios:
        return

    total_filas = 0
    for orig, destino, _n in cambios:
        r = db.session.execute(
            text("UPDATE productos SET rubro = :destino WHERE rubro = :orig"),
            {'destino': destino, 'orig': orig}
        )
        total_filas += r.rowcount
    db.session.commit()

    click.echo('')
    click.echo(f'OK -> rubros normalizados. {total_filas} producto(s) actualizado(s) '
               f'en {len(cambios)} cambio(s).')


def registrar_comandos(app):
    app.cli.add_command(init_db)
    app.cli.add_command(seed_data)
    app.cli.add_command(import_planilla_cmd)
    app.cli.add_command(migrar_v06)
    app.cli.add_command(migrar_v08)
    app.cli.add_command(migrar_v10)
    app.cli.add_command(migrar_v11)
    app.cli.add_command(migrar_v12)
    app.cli.add_command(migrar_v12b)
    app.cli.add_command(normalizar_rubros)
