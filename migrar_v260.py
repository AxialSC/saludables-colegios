"""
migrar_v260.py — MIGRACION v0.26.0 · E5: motor de niveles.
AXIAL SECURITY · Ivan Abrigo

QUE HACE
--------
Le agrega a la tabla 'usuarios' dos columnas para el motor de permanencia:
  · nivel_actual (VARCHAR) -> el escalon activo hoy (INICIAL / PLATA / ORO)
  · nivel_desde  (DATE)    -> desde cuando tiene ese nivel (reloj de la gracia)

Y ademas INICIALIZA esas columnas para las revendedoras que ya existen:
  · nivel_actual = el nivel que les corresponde por lo que ya vendieron
  · nivel_desde  = su fecha de alta (para que la gracia arranque desde que se
                   sumaron, no desde hoy)

QUE **NO** HACE
---------------
NO toca comisiones ya calculadas. NO cambia ninguna venta. Solo agrega las dos
columnas y las completa para las revendedoras existentes.

COMO CORRERLO (regla AXIAL — el orden no se cambia)
---------------------------------------------------
    1) git pull
    2) python3.13 migrar_v260.py
    3) Reload (pestaña Web)

Es IDEMPOTENTE: si lo corres dos veces, la segunda no hace nada (ve que las
columnas ya estan y no reinicializa a las que ya tienen nivel).

HACE BACKUP SOLO, antes de tocar nada.
"""
import os
import shutil
import sqlite3
import sys
from datetime import datetime

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'instance', 'saludables.db')
VERSION = 'v0.26.0'

# Los escalones, EN EL MISMO ORDEN que config.py. Se dejan aca para que el script
# sea autonomo (no importa config para algo tan simple).
NIVELES = [
    ('INICIAL', 0),
    ('PLATA', 5_000_000),
    ('ORO', 10_000_000),
]

COLUMNAS = [
    ('usuarios', 'nivel_actual', 'VARCHAR(20)'),
    ('usuarios', 'nivel_desde', 'DATE'),
]


def backup():
    marca = datetime.now().strftime('%Y%m%d_%H%M%S')
    destino = os.path.join(BASE_DIR, 'instance', f'saludables_backup_{marca}.db')
    shutil.copy2(DB_PATH, destino)
    kb = os.path.getsize(destino) / 1024
    print(f'  Backup: {os.path.basename(destino)}  ({kb:,.0f} KB)')


def columnas_de(cur, tabla):
    cur.execute(f'PRAGMA table_info({tabla})')
    return {f[1] for f in cur.fetchall()}


def nivel_por_vendido(vendido):
    clave = NIVELES[0][0]
    for c, desde in NIVELES:
        if vendido >= desde:
            clave = c
    return clave


def main():
    print()
    print('=' * 68)
    print(f'  MIGRACION {VERSION} — Motor de niveles de comisiones')
    print('=' * 68)
    print()

    if not os.path.exists(DB_PATH):
        print(f'  ERROR: no encuentro la base en {DB_PATH}')
        print('  Corre este script desde la RAIZ (donde esta config.py).')
        sys.exit(1)

    print(f'  Base: {DB_PATH}')
    backup()
    print()

    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # ---------- COLUMNAS ----------
    print('  COLUMNAS')
    print('  ' + '-' * 62)
    existentes = columnas_de(cur, 'usuarios')
    agregadas = 0
    for tabla, col, tipo in COLUMNAS:
        if col in existentes:
            print(f'  ·  ya existe   {tabla}.{col}')
        else:
            cur.execute(f'ALTER TABLE {tabla} ADD COLUMN {col} {tipo}')
            print(f'  +  AGREGADA    {tabla}.{col}')
            agregadas += 1
    con.commit()

    # ---------- INICIALIZAR revendedoras existentes ----------
    # Solo las que todavia NO tienen nivel cargado (idempotente: si ya corrio,
    # no las vuelve a pisar).
    print()
    print('  INICIALIZANDO revendedoras existentes')
    print('  ' + '-' * 62)

    cur.execute("""
        SELECT id, nombre, creado FROM usuarios
        WHERE rol = 'REVENDEDORA' AND (nivel_actual IS NULL OR nivel_actual = '')
    """)
    revendedoras = cur.fetchall()

    if not revendedoras:
        print('  (no hay revendedoras nuevas para inicializar)')
    for uid, nombre, creado in revendedoras:
        # Cuanto vendio (neto aprobado)
        cur.execute("""
            SELECT COALESCE(SUM(neto_total), 0) FROM pedidos
            WHERE revendedora_id = ? AND estado IN ('CONFIRMADO', 'ENTREGADO')
        """, (uid,))
        vendido = float(cur.fetchone()[0] or 0)
        nivel = nivel_por_vendido(vendido)

        # nivel_desde = fecha de alta (para que la gracia cuente desde el inicio).
        # Si no hay fecha de alta, hoy.
        desde = (creado or '')[:10] or datetime.now().strftime('%Y-%m-%d')

        cur.execute("UPDATE usuarios SET nivel_actual = ?, nivel_desde = ? WHERE id = ?",
                    (nivel, desde, uid))
        print(f'  ·  {nombre:<24} -> {nivel:<8} (vendió ${vendido:,.0f}, desde {desde})')
    con.commit()

    # ---------- VERIFICACION ----------
    print()
    print('  VERIFICACION')
    print('  ' + '-' * 62)
    cols = columnas_de(cur, 'usuarios')
    ok = all(col in cols for _, col, _ in COLUMNAS)
    print('  Columnas nivel_actual + nivel_desde:', 'OK ✓' if ok else 'FALTAN ✗')

    cur.execute("SELECT COUNT(*) FROM usuarios")
    n_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM usuarios WHERE rol='REVENDEDORA'")
    n_rev = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM pedidos")
    n_ped = cur.fetchone()[0]
    con.close()

    print()
    print('  DATOS (tienen que ser los mismos que antes)')
    print('  ' + '-' * 62)
    print(f'  Usuarios        {n_users:>6}')
    print(f'  Revendedoras    {n_rev:>6}')
    print(f'  Pedidos         {n_ped:>6}')
    print()
    print('  ' + '=' * 62)
    print(f'  LISTO · {agregadas} columna(s) agregada(s) · '
          f'{len(revendedoras)} revendedora(s) inicializada(s)')
    print()
    print('  >>> AHORA hace el RELOAD desde la pestaña Web. <<<')
    print('  ' + '=' * 62)
    print()

    if not ok:
        sys.exit(1)


if __name__ == '__main__':
    main()
