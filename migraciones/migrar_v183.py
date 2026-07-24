"""
migrar_v183.py — Migracion v0.18.3: tabla 'suscriptores' (C2 - Alta de suscriptores).

Que hace:
  1. Hace un backup de la base ANTES de tocar nada.
  2. Crea la tabla 'suscriptores' si no existe (idempotente: se puede correr
     mas de una vez sin romper nada, y no toca ninguna tabla existente).

Como correrlo (Bash de PythonAnywhere), DESPUES del git pull y ANTES del Reload:

    cd ~/saludables-colegios
    python migrar_v183.py

Cuando termine sin errores, recien ahi hace el Reload desde la pestana Web.
"""
import os
import shutil
import sqlite3
from datetime import datetime

BASEDIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASEDIR, 'instance', 'saludables.db')


def backup():
    if not os.path.exists(DB_PATH):
        print(f'No encontre la base en {DB_PATH}. ¿Estas parado en la carpeta correcta del proyecto?')
        raise SystemExit(1)
    marca = datetime.now().strftime('%Y%m%d_%H%M%S')
    destino = os.path.join(BASEDIR, 'instance', f'saludables_backup_{marca}.db')
    shutil.copy2(DB_PATH, destino)
    print(f'Backup creado: {destino}')
    return destino


def migrar():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS suscriptores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre VARCHAR(120) NOT NULL,
            apellido VARCHAR(120),
            dni_cuit VARCHAR(15),
            email VARCHAR(120),
            whatsapp VARCHAR(30),
            dia_nacimiento INTEGER,
            mes_nacimiento INTEGER,
            acepta_notificaciones BOOLEAN NOT NULL DEFAULT 1,
            activo BOOLEAN NOT NULL DEFAULT 1,
            creado DATETIME,
            ip_origen VARCHAR(45)
        )
    """)
    con.commit()
    con.close()
    print('Tabla "suscriptores" lista (creada si no existia).')


if __name__ == '__main__':
    print('=== Migracion v0.18.3 - Suscriptores (C2) ===')
    backup()
    migrar()
    print('Listo. Ahora podes hacer Reload en la pestana Web de PythonAnywhere.')
