"""
migrar_v350.py — Migracion de la base para la v0.35.0 (MEDIOS DE PAGO).
AXIAL SECURITY · Ivan Abrigo

QUE HACE
--------
Agrega columnas nuevas. NO borra ni modifica ningun dato existente.

  A la tabla `ajustes` (la configuracion del negocio, una sola fila):
      pago_efectivo        BOOLEAN  -> arranca en 1 (prendido)
      pago_transferencia   BOOLEAN  -> arranca en 1 (prendido)
      pago_qr              BOOLEAN  -> arranca en 0 (apagado, no hay QR cargado)
      pago_mercadopago     BOOLEAN  -> arranca en 0 (APAGADO a proposito)
      transf_titular       TEXT
      transf_banco         TEXT
      transf_cbu           TEXT
      transf_alias         TEXT
      transf_cuit          TEXT
      qr_imagen            TEXT

  A la tabla `pedidos`:
      medio_pago           TEXT     -> queda NULL en los pedidos viejos

COMO SE USA (consola Bash de PythonAnywhere)
--------------------------------------------
    cd ~/saludables-colegios
    python3.13 migrar_v350.py

ES IDEMPOTENTE: si lo corres dos veces no rompe nada. La segunda vez detecta
que las columnas ya estan y no hace nada.

ANTES DE TOCAR NADA hace un BACKUP con fecha y hora al lado de la base.
Si algo sale mal, se restaura copiando ese backup encima de saludables.db.

ORDEN DE DEPLOY (no invertir):
    1) git pull        2) python3.13 migrar_v350.py        3) Reload
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'saludables.db')

# (tabla, columna, tipo SQL, valor por defecto)
COLUMNAS = [
    ('ajustes', 'pago_efectivo',      'BOOLEAN', '1'),
    ('ajustes', 'pago_transferencia', 'BOOLEAN', '1'),
    ('ajustes', 'pago_qr',            'BOOLEAN', '0'),
    ('ajustes', 'pago_mercadopago',   'BOOLEAN', '0'),
    ('ajustes', 'transf_titular',     'VARCHAR(120)', None),
    ('ajustes', 'transf_banco',       'VARCHAR(120)', None),
    ('ajustes', 'transf_cbu',         'VARCHAR(30)',  None),
    ('ajustes', 'transf_alias',       'VARCHAR(60)',  None),
    ('ajustes', 'transf_cuit',        'VARCHAR(13)',  None),
    ('ajustes', 'qr_imagen',          'VARCHAR(120)', None),
    ('pedidos', 'medio_pago',         'VARCHAR(20)',  None),
]


def columnas_de(cur, tabla):
    """Devuelve el set de nombres de columna que HOY tiene una tabla."""
    cur.execute(f"PRAGMA table_info({tabla})")
    return {fila[1] for fila in cur.fetchall()}


def tabla_existe(cur, tabla):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabla,))
    return cur.fetchone() is not None


def main():
    print('=' * 62)
    print('  MIGRACION v0.35.0 — MEDIOS DE PAGO')
    print('  AXIAL SECURITY · Sistema Saludables')
    print('=' * 62)

    if not os.path.exists(DB_PATH):
        print(f'\n[ERROR] No encuentro la base en:\n        {DB_PATH}')
        print('        Corre este script desde la carpeta del proyecto.')
        sys.exit(1)

    # ---------- 1) BACKUP (siempre, antes de tocar nada) ----------
    sello = datetime.now().strftime('%Y%m%d_%H%M%S')
    backup = os.path.join(BASE_DIR, 'instance', f'saludables_ANTES_v350_{sello}.db')
    shutil.copy2(DB_PATH, backup)
    print(f'\n[1/3] Backup hecho:\n      {os.path.basename(backup)}')

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    try:
        # ---------- 2) Chequeo previo ----------
        print('\n[2/3] Revisando que hay que agregar...')
        for tabla in ('ajustes', 'pedidos'):
            if not tabla_existe(cur, tabla):
                print(f'      [ERROR] No existe la tabla "{tabla}". Migracion cancelada.')
                con.close()
                sys.exit(1)

        pendientes = []
        for tabla, col, tipo, defecto in COLUMNAS:
            if col in columnas_de(cur, tabla):
                print(f'      · {tabla}.{col:20} ya existe → se saltea')
            else:
                pendientes.append((tabla, col, tipo, defecto))
                print(f'      · {tabla}.{col:20} FALTA    → se agrega')

        if not pendientes:
            print('\n[3/3] No hay nada que hacer: la base ya estaba migrada. ✓')
            con.close()
            print('\nPodes hacer el Reload tranquilo.\n')
            return

        # ---------- 3) Agregar columnas ----------
        print(f'\n[3/3] Agregando {len(pendientes)} columna(s)...')
        for tabla, col, tipo, defecto in pendientes:
            sql = f'ALTER TABLE {tabla} ADD COLUMN {col} {tipo}'
            if defecto is not None:
                sql += f' NOT NULL DEFAULT {defecto}'
            cur.execute(sql)
            print(f'      ✓ {tabla}.{col}')

        con.commit()

        # ---------- Verificacion final ----------
        print('\nVerificando...')
        faltan = [f'{t}.{c}' for t, c, _, _ in COLUMNAS if c not in columnas_de(cur, t)]
        if faltan:
            print('      [ERROR] Estas columnas no quedaron:', ', '.join(faltan))
            print(f'      Restaura el backup: {os.path.basename(backup)}')
            con.close()
            sys.exit(1)

        print('      ✓ Todas las columnas estan en su lugar.')

        # Mostrar como quedo la configuracion de pagos
        cur.execute('SELECT pago_efectivo, pago_transferencia, pago_qr, pago_mercadopago '
                    'FROM ajustes LIMIT 1')
        fila = cur.fetchone()
        if fila:
            print('\n      Medios de pago (estado inicial):')
            for nombre, valor in zip(('Efectivo', 'Transferencia', 'QR', 'Mercado Pago'), fila):
                print(f'        · {nombre:14} {"PRENDIDO" if valor else "apagado"}')

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
