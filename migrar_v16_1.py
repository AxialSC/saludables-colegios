"""
migrar_v16_1.py — Migracion v0.16.1
AXIAL SECURITY · Ivan Abrigo

Agrega 2 columnas a la tabla 'usuarios':
  - cuit                -> el CUIT de la persona
  - password_temporal   -> clave temporal en claro (para reenviarla por WhatsApp
                           mientras la revendedora todavia no entro; se ignora
                           una vez que la cambia)

  - Hace BACKUP AUTOMATICO antes de tocar nada.
  - SQL directo sqlite3 (regla AXIAL). IDEMPOTENTE.

COMO CORRERLO (en PythonAnywhere, UNA sola vez):
    cd ~/saludables-colegios
    python migrar_v16_1.py
    # despues: Reload desde la pestaña Web
"""
import os
import sqlite3
import shutil
from datetime import datetime

DB = os.path.join('instance', 'saludables.db')

NUEVAS = {
    'cuit': 'VARCHAR(13)',
    'password_temporal': 'VARCHAR(40)',
}


def main():
    if not os.path.exists(DB):
        print(f"ERROR: no encontre la base en '{DB}'.")
        print("Corre el script parado en la carpeta del proyecto:")
        print("   cd ~/saludables-colegios && python migrar_v16_1.py")
        return

    sello = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = os.path.join('instance', f'saludables_backup_v161_{sello}.db')
    shutil.copy2(DB, bak)
    print(f"Backup creado -> {bak}")

    con = sqlite3.connect(DB)
    cur = con.cursor()
    existentes = [fila[1] for fila in cur.execute("PRAGMA table_info(usuarios)")]

    agregadas = 0
    for col, tipo in NUEVAS.items():
        if col not in existentes:
            cur.execute(f"ALTER TABLE usuarios ADD COLUMN {col} {tipo}")
            print(f"   + columna usuarios.{col}")
            agregadas += 1
    con.commit()
    con.close()

    if agregadas:
        print(f"\nOK -> migracion v0.16.1 aplicada ({agregadas} columna(s) nueva(s)).")
    else:
        print("\nLas columnas ya existian. No se hizo nada (idempotente).")
    print("Ahora hace el Reload desde la pestaña Web.")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print("ERROR inesperado:", e)
        print("No se aplico la migracion. Pegame el mensaje. Tu backup quedo a salvo.")
