"""
app/utils/decorators.py — Decoradores de permisos (defensa en profundidad).
El backend SIEMPRE valida el rol, no se confia solo en ocultar botones en el front.
"""
from functools import wraps
from flask import abort
from flask_login import current_user


def admin_requerido(f):
    """Permite SUPER_ADMIN y ADMIN (Juliana)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.es_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def super_admin_requerido(f):
    """Solo Ivan (SUPER_ADMIN). Ej: importar planillas, borrar usuarios."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.es_super_admin:
            abort(403)
        return f(*args, **kwargs)
    return wrapper


def revendedora_requerido(f):
    """Solo REVENDEDORA. Es el portal propio de cada revendedora (v0.18)."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.es_revendedora:
            abort(403)
        return f(*args, **kwargs)
    return wrapper
