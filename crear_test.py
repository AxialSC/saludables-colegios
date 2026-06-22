"""
crear_test.py — Crea un usuario de PRUEBA para ver el portal de revendedora.
AXIAL SECURITY · Ivan Abrigo

Crea (o reusa) el usuario:
    usuario: test
    clave:   123456
    rol:     REVENDEDORA
    entra directo (sin pedir cambio de clave), para que puedas probar el portal.

COMO CORRERLO (en PythonAnywhere):
    cd ~/saludables-colegios
    python crear_test.py

Para sacarlo despues: python borrar_test.py
"""
from app import create_app
from app.extensions import db
from app.models import Usuario, Rol

app = create_app()

with app.app_context():
    u = Usuario.query.filter_by(usuario='test').first()
    if u:
        # Ya existe: lo reseteo a un estado de prueba conocido
        u.rol = Rol.REVENDEDORA
        u.activo = True
        u.debe_cambiar_password = False
        u.set_password('123456')
        db.session.commit()
        print('El usuario "test" ya existia -> lo deje listo (revendedora, clave 123456).')
    else:
        u = Usuario(usuario='test', nombre='Test', apellido='Revendedora',
                    rol=Rol.REVENDEDORA, activo=True, debe_cambiar_password=False)
        u.set_password('123456')
        db.session.add(u)
        db.session.commit()
        print('Usuario de prueba creado:')
    print('   usuario: test')
    print('   clave:   123456')
    print('   entra en: /login  ->  te lleva al portal de revendedora')
