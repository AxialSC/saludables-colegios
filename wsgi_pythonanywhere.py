# =====================================================================
# wsgi_pythonanywhere.py  ·  ARCHIVO DE REFERENCIA (NO se sube al repo)
# =====================================================================
# Copiá el contenido de abajo dentro del archivo WSGI que te da
# PythonAnywhere (pestaña "Web" -> link del WSGI configuration file),
# borrando TODO lo que venga por defecto.
#
# Ajustá la variable 'project_home' a TU usuario de PythonAnywhere y
# al nombre exacto de la carpeta donde clonaste el repo.
# ---------------------------------------------------------------------

import sys

# CAMBIAR 'TU_USUARIO' por tu usuario real de PythonAnywhere
project_home = '/home/TU_USUARIO/saludables-colegios'

if project_home not in sys.path:
    sys.path.insert(0, project_home)

from app import create_app
application = create_app('prod')
