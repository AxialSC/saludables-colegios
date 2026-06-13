"""
app/cli.py — Comandos de linea de comando.
  flask --app run init-db                  -> crea las tablas
  flask --app run seed-data                -> crea usuarios iniciales
  flask --app run import-planilla <ruta>   -> importa una planilla (respaldo / pruebas)
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


def registrar_comandos(app):
    app.cli.add_command(init_db)
    app.cli.add_command(seed_data)
    app.cli.add_command(import_planilla_cmd)
