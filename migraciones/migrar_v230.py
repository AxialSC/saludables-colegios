"""
migrar_v230.py — MIGRACION v0.23.0 · E2: cimiento del Frente E.
AXIAL SECURITY · Ivan Abrigo

QUE HACE
--------
Le agrega a la base las columnas que necesita la VENTA DE LA REVENDEDORA:
  · pedidos       -> de quien es la venta, el circuito de aprobacion de Juliana
                     y el SNAPSHOT DE COMISION congelado.
  · items_pedido  -> costo_unitario (sin el costo no hay margen, y sin margen no
                     se puede saber si la comision deja a la casa arriba del 6%).
  · cotizaciones  -> de quien es el presupuesto y en que pedido termino.

QUE **NO** HACE
---------------
NO borra nada. NO modifica ningun dato existente. NO toca los pedidos que ya
estan cargados. Solo AGREGA columnas nuevas, todas en NULL.

COMO CORRERLO (regla AXIAL — el orden NO se cambia)
---------------------------------------------------
    1) git pull
    2) python migrar_v230.py      <-- ESTE PASO. Nunca despues del Reload.
    3) Reload (pestaña Web)

Si haces Reload ANTES de migrar, la web te tira un error 500 limpio: el codigo
nuevo va a buscar columnas que todavia no existen.

ES IDEMPOTENTE: podes correrlo dos veces sin romper nada. Antes de agregar cada
columna se fija si ya esta. Si esta, la saltea.

HACE BACKUP SOLO, ANTES DE TOCAR NADA.
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'saludables.db')

VERSION = 'v0.23.0'


# ============================================================================
#  LAS COLUMNAS NUEVAS
#  (tabla, columna, tipo SQL)  — el orden importa poco, pero se agrupan por tabla
# ============================================================================
COLUMNAS = [
    # ---------------- PEDIDOS: la venta de la revendedora ----------------
    # De quien es la venta. NULL = pedido normal de la tienda web (todos los
    # que ya existen quedan asi, que es lo correcto).
    ('pedidos', 'revendedora_id',      'INTEGER REFERENCES usuarios(id)'),
    ('pedidos', 'cliente_id',          'INTEGER REFERENCES clientes(id)'),

    # Circuito de aprobacion de Juliana
    ('pedidos', 'enviado_en',          'DATETIME'),
    ('pedidos', 'aprobado_por',        'VARCHAR(80)'),
    ('pedidos', 'aprobado_en',         'DATETIME'),
    ('pedidos', 'rechazado_motivo',    'VARCHAR(200)'),

    # SNAPSHOT DE PLATA (se congela al aprobar y no se recalcula NUNCA MAS)
    ('pedidos', 'neto_total',          'NUMERIC(12,2)'),   # venta SIN IVA = base de comision
    ('pedidos', 'costo_total',         'NUMERIC(12,2)'),   # lo que se le paga a Torres
    ('pedidos', 'margen_pct',          'NUMERIC(5,2)'),    # margen real de la venta
    ('pedidos', 'comision_pct',        'NUMERIC(5,2)'),    # el escalon que regia ese dia
    ('pedidos', 'comision_monto',      'NUMERIC(12,2)'),   # neto * comision_pct / 100
    ('pedidos', 'margen_casa_pct',     'NUMERIC(5,2)'),    # margen_pct - comision_pct  (>= 6%)

    # Pago de la comision
    ('pedidos', 'comision_pagada',     'BOOLEAN NOT NULL DEFAULT 0'),
    ('pedidos', 'comision_pagada_en',  'DATETIME'),
    ('pedidos', 'comision_pagada_por', 'VARCHAR(80)'),

    # ---------------- ITEMS: el costo, que faltaba ----------------
    # Es NULLABLE a proposito: los pedidos web que ya existen no lo tienen y NO
    # hay que inventarselo. El costo de Torres de hace tres meses no lo sabemos,
    # y ponerle el de hoy seria mentirle a la auditoria.
    ('items_pedido', 'costo_unitario', 'NUMERIC(12,3)'),

    # ---------------- COTIZACIONES: de quien es el presupuesto ----------------
    ('cotizaciones', 'revendedora_id', 'INTEGER REFERENCES usuarios(id)'),
    ('cotizaciones', 'cliente_id',     'INTEGER REFERENCES clientes(id)'),
    ('cotizaciones', 'pedido_id',      'INTEGER REFERENCES pedidos(id)'),
]

INDICES = [
    ('ix_pedidos_revendedora_id',      'pedidos',      'revendedora_id'),
    ('ix_pedidos_cliente_id',          'pedidos',      'cliente_id'),
    ('ix_cotizaciones_revendedora_id', 'cotizaciones', 'revendedora_id'),
    ('ix_cotizaciones_cliente_id',     'cotizaciones', 'cliente_id'),
    ('ix_cotizaciones_pedido_id',      'cotizaciones', 'pedido_id'),
]


def backup():
    """Copia de seguridad ANTES de tocar nada. Regla AXIAL: no se negocia."""
    marca = datetime.now().strftime('%Y%m%d_%H%M%S')
    destino = os.path.join(BASE_DIR, 'instance', f'saludables_backup_{marca}.db')
    shutil.copy2(DB_PATH, destino)
    kb = os.path.getsize(destino) / 1024
    print(f'  Backup: {os.path.basename(destino)}  ({kb:,.0f} KB)')
    return destino


def columnas_de(cur, tabla):
    cur.execute(f'PRAGMA table_info({tabla})')
    return {fila[1] for fila in cur.fetchall()}


def tabla_existe(cur, tabla):
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (tabla,))
    return cur.fetchone() is not None


def main():
    print()
    print('=' * 68)
    print(f'  MIGRACION {VERSION} — Frente E: venta de revendedora + comisiones')
    print('=' * 68)
    print()

    if not os.path.exists(DB_PATH):
        print(f'  ERROR: no encuentro la base en {DB_PATH}')
        print('  Corre este script desde la RAIZ del proyecto (donde esta config.py).')
        sys.exit(1)

    print(f'  Base: {DB_PATH}')
    backup()
    print()

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Chequeo previo: que existan las tablas que vamos a tocar
    for tabla in ('pedidos', 'items_pedido', 'cotizaciones', 'usuarios', 'clientes'):
        if not tabla_existe(cur, tabla):
            print(f'  ERROR: falta la tabla "{tabla}". La base no esta en v0.20+.')
            con.close()
            sys.exit(1)

    # ---------- COLUMNAS ----------
    print('  COLUMNAS')
    print('  ' + '-' * 64)
    agregadas = 0
    salteadas = 0
    cache = {}
    for tabla, col, tipo in COLUMNAS:
        if tabla not in cache:
            cache[tabla] = columnas_de(cur, tabla)
        if col in cache[tabla]:
            print(f'  ·  ya existe   {tabla}.{col}')
            salteadas += 1
            continue
        cur.execute(f'ALTER TABLE {tabla} ADD COLUMN {col} {tipo}')
        cache[tabla].add(col)
        print(f'  +  AGREGADA    {tabla}.{col}')
        agregadas += 1

    # ---------- INDICES ----------
    print()
    print('  INDICES')
    print('  ' + '-' * 64)
    for nombre, tabla, col in INDICES:
        cur.execute(f'CREATE INDEX IF NOT EXISTS {nombre} ON {tabla}({col})')
        print(f'  +  {nombre}')

    con.commit()

    # ---------- VERIFICACION ----------
    # No alcanza con que el script no explote: hay que MIRAR que las columnas
    # esten de verdad. Regla AXIAL: no se declara "validado" sin verificar.
    print()
    print('  VERIFICACION')
    print('  ' + '-' * 64)
    ok = True
    for tabla, col, _ in COLUMNAS:
        if col not in columnas_de(cur, tabla):
            print(f'  X  FALTA {tabla}.{col}')
            ok = False
    if ok:
        print('  OK · las 19 columnas estan en su lugar.')

    # Que no se haya tocado ni un dato
    cur.execute('SELECT COUNT(*) FROM pedidos')
    n_ped = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM items_pedido')
    n_it = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM cotizaciones')
    n_cot = cur.fetchone()[0]
    cur.execute('SELECT COUNT(*) FROM productos')
    n_prod = cur.fetchone()[0]

    con.close()

    print()
    print('  DATOS (tienen que ser los mismos que antes de migrar)')
    print('  ' + '-' * 64)
    print(f'  Productos      {n_prod:>6}')
    print(f'  Pedidos        {n_ped:>6}')
    print(f'  Items          {n_it:>6}')
    print(f'  Cotizaciones   {n_cot:>6}')
    print()
    print('  ' + '=' * 64)
    print(f'  LISTO · {agregadas} columna(s) agregada(s) · {salteadas} ya estaban')
    print()
    print('  >>> AHORA SI: hace el RELOAD desde la pestaña Web. <<<')
    print('  ' + '=' * 64)
    print()

    if not ok:
        sys.exit(1)


if __name__ == '__main__':
    main()
