"""
migrar_v200.py — Migracion v0.20.0: tablas 'importaciones' e 'importacion_items'
                 (Historial de precios del mayorista).

Que hace:
  1. Hace un backup de la base ANTES de tocar nada.
  2. Crea las tablas 'importaciones' e 'importacion_items' si no existen
     (idempotente: se puede correr mas de una vez sin romper nada, y NO toca
     ninguna tabla existente como 'productos', 'usuarios' o 'facturas').

Como correrlo (Bash de PythonAnywhere), DESPUES del git pull y ANTES del Reload:

    cd ~/saludables-colegios
    python migrar_v200.py

Cuando termine sin errores, recien ahi hace el Reload desde la pestana Web.

NOTA: el historial arranca vacio. La proxima planilla que importes va a ser la
primera registrada, y a partir de ahi el sistema empieza a compararte los precios.
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
        CREATE TABLE IF NOT EXISTS importaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            archivo VARCHAR(255),
            creado DATETIME,
            creado_por VARCHAR(80),
            nuevos INTEGER NOT NULL DEFAULT 0,
            actualizados INTEGER NOT NULL DEFAULT 0,
            subieron INTEGER NOT NULL DEFAULT 0,
            bajaron INTEGER NOT NULL DEFAULT 0,
            sin_cambio INTEGER NOT NULL DEFAULT 0,
            fuera_de_lista INTEGER NOT NULL DEFAULT 0,
            total_catalogo INTEGER NOT NULL DEFAULT 0,
            variacion_promedio NUMERIC(6, 2)
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_importaciones_creado ON importaciones (creado)")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS importacion_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            importacion_id INTEGER NOT NULL REFERENCES importaciones(id),
            codigo VARCHAR(40) NOT NULL,
            nombre VARCHAR(255) NOT NULL,
            costo_anterior NUMERIC(12, 3),
            costo_nuevo NUMERIC(12, 3) NOT NULL,
            variacion_pct NUMERIC(7, 2),
            es_nuevo BOOLEAN NOT NULL DEFAULT 0
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_importacion_items_imp "
                "ON importacion_items (importacion_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_importacion_items_codigo "
                "ON importacion_items (codigo)")

    con.commit()
    con.close()
    print('Tablas "importaciones" e "importacion_items" listas (creadas si no existian).')


if __name__ == '__main__':
    print('=== Migracion v0.20.0 - Historial de precios ===')
    backup()
    migrar()
    print('Listo. Ahora podes hacer Reload en la pestana Web de PythonAnywhere.')
