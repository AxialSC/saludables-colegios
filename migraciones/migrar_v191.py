"""
migrar_v191.py — Migracion v0.19.1: tablas 'facturas' y 'factura_items' (Food Cost).

Que hace:
  1. Hace un backup de la base ANTES de tocar nada.
  2. Crea las tablas 'facturas' y 'factura_items' si no existen (idempotente:
     se puede correr mas de una vez sin romper nada, y no toca ninguna tabla
     existente como 'productos' o 'usuarios').

Como correrlo (Bash de PythonAnywhere), DESPUES del git pull y ANTES del Reload:

    cd ~/saludables-colegios
    python migrar_v191.py

Cuando termine sin errores, recien ahi hace el Reload desde la pestana Web.

IMPORTANTE: este modulo tambien necesita la libreria 'pdfplumber' para leer los
PDF de las facturas. Si todavia no la tenes instalada, corre ANTES de todo esto:

    pip3.10 install --user pdfplumber

(Si tu PythonAnywhere usa otra version de Python, cambiá el "pip3.10" por la que
corresponda — se puede ver con "python3 --version").
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
        CREATE TABLE IF NOT EXISTS facturas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero VARCHAR(30) NOT NULL UNIQUE,
            proveedor VARCHAR(120) NOT NULL DEFAULT 'S.TORRES Y CIA S.A.',
            fecha DATE,
            subtotal NUMERIC(12, 2),
            iva NUMERIC(12, 2),
            reg_especiales NUMERIC(12, 2),
            total NUMERIC(12, 2),
            no_reconocidas TEXT,
            subida_en DATETIME,
            subida_por VARCHAR(80)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS factura_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            factura_id INTEGER NOT NULL REFERENCES facturas(id),
            codigo VARCHAR(40) NOT NULL,
            descripcion VARCHAR(255) NOT NULL,
            unidades NUMERIC(10, 2) NOT NULL DEFAULT 0,
            sugerido NUMERIC(12, 2),
            costo_unitario NUMERIC(12, 3) NOT NULL,
            importe NUMERIC(12, 2),
            producto_id INTEGER REFERENCES productos(id),
            costo_neto_anterior NUMERIC(12, 3),
            actualizado BOOLEAN NOT NULL DEFAULT 0
        )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_factura_items_codigo ON factura_items (codigo)")

    con.commit()
    con.close()
    print('Tablas "facturas" y "factura_items" listas (creadas si no existian).')


if __name__ == '__main__':
    print('=== Migracion v0.19.1 - Food Cost (facturas de Torres) ===')
    backup()
    migrar()
    print('Listo. Ahora podes hacer Reload en la pestana Web de PythonAnywhere.')
