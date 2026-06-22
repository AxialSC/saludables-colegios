"""
borrar_test.py — Borra el usuario de prueba 'test' (y los clientes que haya
cargado mientras probabas). AXIAL SECURITY · Ivan Abrigo

COMO CORRERLO (en PythonAnywhere):
    cd ~/saludables-colegios
    python borrar_test.py
"""
from app import create_app
from app.extensions import db
from app.models import Usuario, Cliente

app = create_app()

with app.app_context():
    u = Usuario.query.filter_by(usuario='test').first()
    if not u:
        print('No existe ningun usuario "test". Nada que borrar.')
    else:
        # Borrar primero los clientes de prueba que haya cargado ese usuario
        n = Cliente.query.filter_by(revendedora_id=u.id).delete()
        db.session.delete(u)
        db.session.commit()
        print(f'Usuario "test" borrado. Tambien se borraron {n} cliente(s) de prueba suyos.')
