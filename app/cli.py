"""
app/cli.py — Comandos de linea de comando.
  flask init-db     -> crea las tablas
  flask seed-data   -> crea los usuarios iniciales (Ivan super admin + Juliana admin)
"""
import click
from flask.cli import with_appcontext

from .extensions import db
from .models import Usuario, Rol


@click.command('init-db')
@with_appcontext
def init_db():
    """Crea todas las tablas de la base de datos."""
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


def registrar_comandos(app):
    app.cli.add_command(init_db)
    app.cli.add_command(seed_data)
