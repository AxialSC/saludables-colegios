"""
migrar_v16.py — Migracion v0.16 (Usuarios con perfil completo)
AXIAL SECURITY · Ivan Abrigo

Agrega las columnas de PERFIL a la tabla 'usuarios' (apellido, DNI, nacimiento,
contacto, datos bancarios para comisiones). NO toca ninguna otra tabla.

  - Hace BACKUP AUTOMATICO de la base ANTES de tocar nada.
  - Usa SQL directo en sqlite3 (regla AXIAL), no SQLAlchemy automatico.
  - Es IDEMPOTENTE: si las columnas ya existen, no hace nada.

COMO CORRERLO (en PythonAnywhere, UNA sola vez):
    cd ~/saludables-colegios
    python migrar_v16.py
    # despues: Reload desde la pestaña Web
"""
import os
import sqlite3
import shutil
from datetime import datetime

DB = os.path.join('instance', 'saludables.db')

# Columnas nuevas (todas opcionales -> no rompen las filas que ya existen)
NUEVAS = {
    'apellido': 'VARCHAR(120)',
    'dni': 'VARCHAR(15)',
    'fecha_nacimiento': 'DATE',
    'telefono': 'VARCHAR(30)',
    'email': 'VARCHAR(120)',
    'direccion': 'VARCHAR(200)',
    'localidad': 'VARCHAR(120)',
    'cbu_cvu': 'VARCHAR(30)',
    'alias_cbu': 'VARCHAR(60)',
    'banco_fintech': 'VARCHAR(80)',
    'forma_pago_comision': 'VARCHAR(20)',
    'notas': 'TEXT',
}


def main():
    if not os.path.exists(DB):
        print(f"ERROR: no encontre la base en '{DB}'.")
        print("Corre este script PARADO en la carpeta del proyecto:")
        print("   cd ~/saludables-colegios")
        print("   python migrar_v16.py")
        return

    # 1) BACKUP automatico (siempre, antes de tocar nada)
    sello = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = os.path.join('instance', f'saludables_backup_v16_{sello}.db')
    shutil.copy2(DB, bak)
    print(f"Backup creado -> {bak}")

    # 2) Agregar solo las columnas que falten
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
        print(f"\nOK -> migracion v0.16 aplicada ({agregadas} columna(s) nueva(s) en 'usuarios').")
    else:
        print("\nLas columnas ya existian. No se hizo nada (idempotente).")
    print("Ahora hace el Reload desde la pestaña Web.")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print("ERROR inesperado:", e)
        print("No se aplico la migracion. Pegame este mensaje. Tu backup quedo a salvo.")
