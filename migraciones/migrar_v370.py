"""
migrar_v370.py — Migracion de la base para la v0.37.0 (MERCADO PAGO).
AXIAL SECURITY · Ivan Abrigo

QUE HACE
--------
Agrega columnas nuevas. NO borra ni modifica ningun dato existente.

  A `ajustes` (configuracion del costo de plataforma):
      mp_costo_activo   BOOLEAN  -> 1 (se le cobra al cliente)
      mp_costo_pct      NUMERIC  -> 1.56 (tarifa de 35 dias)
      mp_costo_iva      BOOLEAN  -> 1 (MP publica tarifas SIN IVA)

  A `pedidos` (seguimiento del pago):
      costo_plataforma  NUMERIC  -> 0 en todos los pedidos viejos
      mp_preference_id  TEXT
      mp_payment_id     TEXT
      mp_estado         TEXT

COMO SE USA (consola Bash de PythonAnywhere)
    cd ~/saludables-colegios
    python3.13 migrar_v370.py

ES IDEMPOTENTE: correrlo dos veces no rompe nada.
Hace BACKUP con fecha y hora antes de tocar la base.

ORDEN DE DEPLOY (no invertir):
    1) git pull        2) python3.13 migrar_v370.py        3) Reload
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'saludables.db')

COLUMNAS = [
    ('ajustes', 'mp_costo_activo',  'BOOLEAN',       '1'),
    ('ajustes', 'mp_costo_pct',     'NUMERIC(5,2)',  '1.56'),
    ('ajustes', 'mp_costo_iva',     'BOOLEAN',       '1'),
    ('pedidos', 'costo_plataforma', 'NUMERIC(12,2)', '0'),
    ('pedidos', 'mp_preference_id', 'VARCHAR(80)',   None),
    ('pedidos', 'mp_payment_id',    'VARCHAR(40)',   None),
    ('pedidos', 'mp_estado',        'VARCHAR(30)',   None),
]


def columnas_de(cur, tabla):
    cur.execute(f"PRAGMA table_info({tabla})")
    return {f[1] for f in cur.fetchall()}


def tabla_existe(cur, tabla):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabla,))
    return cur.fetchone() is not None


def main():
    print('=' * 62)
    print('  MIGRACION v0.37.0 — MERCADO PAGO')
    print('  AXIAL SECURITY · Sistema Saludables')
    print('=' * 62)

    if not os.path.exists(DB_PATH):
        print(f'\n[ERROR] No encuentro la base en:\n        {DB_PATH}')
        sys.exit(1)

    sello = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = os.path.join(BASE_DIR, 'instance', f'saludables_ANTES_v370_{sello}.db')
    shutil.copy2(DB_PATH, backup)
    print(f'\n[1/3] Backup hecho:\n      {os.path.basename(backup)}')

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    try:
        print('\n[2/3] Revisando que hay que agregar...')
        for tabla in ('ajustes', 'pedidos'):
            if not tabla_existe(cur, tabla):
                print(f'      [ERROR] No existe la tabla "{tabla}". Cancelado.')
                con.close()
                sys.exit(1)

        # Chequeo de orden: la v0.35 tiene que estar corrida antes que esta.
        if 'medio_pago' not in columnas_de(cur, 'pedidos'):
            print('\n      [ERROR] Falta la migracion v0.35 (medio_pago en pedidos).')
            print('              Corre primero:  python3.13 migrar_v350.py')
            con.close()
            sys.exit(1)

        pendientes = []
        for tabla, col, tipo, defecto in COLUMNAS:
            if col in columnas_de(cur, tabla):
                print(f'      · {tabla}.{col:18} ya existe → se saltea')
            else:
                pendientes.append((tabla, col, tipo, defecto))
                print(f'      · {tabla}.{col:18} FALTA    → se agrega')

        if not pendientes:
            print('\n[3/3] Nada que hacer: la base ya estaba migrada. ✓')
            con.close()
            print('\nPodes hacer el Reload tranquilo.\n')
            return

        print(f'\n[3/3] Agregando {len(pendientes)} columna(s)...')
        for tabla, col, tipo, defecto in pendientes:
            sql = f'ALTER TABLE {tabla} ADD COLUMN {col} {tipo}'
            if defecto is not None:
                sql += f' NOT NULL DEFAULT {defecto}'
            cur.execute(sql)
            print(f'      ✓ {tabla}.{col}')

        con.commit()

        print('\nVerificando...')
        faltan = [f'{t}.{c}' for t, c, _, _ in COLUMNAS if c not in columnas_de(cur, t)]
        if faltan:
            print('      [ERROR] No quedaron:', ', '.join(faltan))
            print(f'      Restaura el backup: {os.path.basename(backup)}')
            con.close()
            sys.exit(1)
        print('      ✓ Todas las columnas estan en su lugar.')

        cur.execute('SELECT mp_costo_activo, mp_costo_pct, mp_costo_iva FROM ajustes LIMIT 1')
        fila = cur.fetchone()
        if fila:
            activo, pct, iva = fila
            efectivo = float(pct) * (1.21 if iva else 1)
            print('\n      Costo de plataforma (valores iniciales):')
            print(f'        · Se le cobra al cliente: {"SI" if activo else "NO"}')
            print(f'        · Comision configurada:   {float(pct):.2f}%'
                  f'{" + IVA" if iva else ""}  ->  {efectivo:.2f}% efectivo')
            print('        (ajustable desde el panel: Sistema -> Medios de pago)')

    except Exception as e:
        con.rollback()
        con.close()
        print(f'\n[ERROR] {e}')
        print(f'        No se guardo nada. Backup intacto: {os.path.basename(backup)}')
        sys.exit(1)

    con.close()
    print('\n' + '=' * 62)
    print('  MIGRACION TERMINADA ✓')
    print('  Ahora si: hace el Reload en PythonAnywhere.')
    print('=' * 62 + '\n')


if __name__ == '__main__':
    main()
