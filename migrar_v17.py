"""
migrar_v17.py — Migracion v0.17.0 (Base de Clientes)
AXIAL SECURITY · Ivan Abrigo

Crea la tabla 'clientes' (cimiento del CRM de revendedoras). No toca ninguna
otra tabla.
  - BACKUP AUTOMATICO antes de tocar nada.
  - SQL directo sqlite3 (regla AXIAL). IDEMPOTENTE (CREATE TABLE IF NOT EXISTS).

COMO CORRERLO (en PythonAnywhere, UNA sola vez):
    cd ~/saludables-colegios
    python migrar_v17.py
    # despues: Reload desde la pestaña Web
"""
import os
import sqlite3
import shutil
from datetime import datetime

DB = os.path.join('instance', 'saludables.db')

SQL_TABLA = """
CREATE TABLE IF NOT EXISTS clientes (
    id              INTEGER PRIMARY KEY,
    revendedora_id  INTEGER REFERENCES usuarios(id),
    nombre          VARCHAR(120) NOT NULL,
    apellido        VARCHAR(120),
    dni_cuit        VARCHAR(15),
    telefono        VARCHAR(30),
    email           VARCHAR(120),
    direccion       VARCHAR(200),
    localidad       VARCHAR(120),
    notas           TEXT,
    activo          BOOLEAN NOT NULL DEFAULT 1,
    creado          DATETIME,
    creado_por      VARCHAR(80)
);
"""
SQL_INDICE = "CREATE INDEX IF NOT EXISTS ix_clientes_revendedora_id ON clientes(revendedora_id);"


def main():
    if not os.path.exists(DB):
        print(f"ERROR: no encontre la base en '{DB}'.")
        print("Corre el script parado en la carpeta del proyecto:")
        print("   cd ~/saludables-colegios && python migrar_v17.py")
        return

    sello = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = os.path.join('instance', f'saludables_backup_v17_{sello}.db')
    shutil.copy2(DB, bak)
    print(f"Backup creado -> {bak}")

    con = sqlite3.connect(DB)
    cur = con.cursor()
    ya_existia = cur.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='clientes'").fetchone()
    cur.executescript(SQL_TABLA + SQL_INDICE)
    con.commit()
    con.close()

    if ya_existia:
        print("\nLa tabla 'clientes' ya existia. No se hizo nada (idempotente).")
    else:
        print("\nOK -> tabla 'clientes' creada. Base de Clientes lista.")
    print("Ahora hace el Reload desde la pestaña Web.")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print("ERROR inesperado:", e)
        print("No se aplico la migracion. Pegame el mensaje. Tu backup quedo a salvo.")
