"""
app/utils/validaciones.py — Validaciones offline (sin depender de internet).
"""
import re


def limpiar_cuit(cuit):
    """Deja solo digitos."""
    return re.sub(r'\D', '', cuit or '')


def validar_cuit(cuit):
    """
    Valida un CUIT/CUIL argentino por su digito verificador (modulo 11).
    Es 100% offline y gratis. Filtra CUITs inventados o mal tipeados.
    (La consulta online contra ARCA, que confirma el nombre, requiere cuenta
    paga de PythonAnywhere; queda para esa etapa.)
    """
    c = limpiar_cuit(cuit)
    if len(c) != 11 or not c.isdigit():
        return False

    multiplicadores = [5, 4, 3, 2, 7, 6, 5, 4, 3, 2]
    nums = [int(d) for d in c]
    suma = sum(m * n for m, n in zip(multiplicadores, nums[:10]))
    resto = suma % 11
    dv = 11 - resto
    if dv == 11:
        dv = 0
    elif dv == 10:
        dv = 9
    return dv == nums[10]


def formatear_cuit(cuit):
    """20123456786 -> 20-12345678-6"""
    c = limpiar_cuit(cuit)
    if len(c) == 11:
        return f'{c[:2]}-{c[2:10]}-{c[10]}'
    return cuit
