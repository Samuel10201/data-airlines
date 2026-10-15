"""Dominios de valores, parámetros de negocio y errores del prototipo.

El script de Enterprise Architect no trae CHECK: los valores permitidos y los límites de negocio
viven aquí y los valida la aplicación (ver `contexto\\modelo-relacional-contexto.md`, sección 6).
"""
from datetime import datetime, timedelta
from math import isfinite

NOMBRE_AEROLINEA = "Data-Delta Airlines"
FORMATO_FECHA = "%Y-%m-%d %H:%M:%S"

TIPOS_EMPLEADO = ("piloto", "tcp", "agente_viaje", "tecnico_mantenimiento", "limpieza")
TIPOS_ACTOR = ("cliente", "agente", "aeropuerto")

# Parámetros de negocio: el modelo no tiene tarifas ni límites de equipaje, así que son configuración.
TARIFA_BASE = 45.0
TARIFA_POR_MILLA = 0.11
PESO_MAXIMO_KG = 32.0
MALETAS_POR_TIQUETE = 3
MAXIMO_ENTERO = 2 ** 63 - 1  # el entero más grande que SQLite acepta como parámetro


class ErrorNegocio(Exception):
    """Regla de negocio incumplida; el mensaje se muestra al usuario (HTTP 400)."""


class ErrorPermiso(Exception):
    """El actor no tiene el tipo o la propiedad necesaria (HTTP 403)."""


class ErrorSesion(Exception):
    """No hay sesión iniciada (HTTP 401)."""


def ahora_actual():
    """Fecha y hora local como texto `YYYY-MM-DD HH:MM:SS`."""
    return datetime.now().strftime(FORMATO_FECHA)


def sumar_horas(texto, horas):
    """Devuelve `texto` (fecha-hora) desplazada `horas` horas, en el mismo formato."""
    return (datetime.strptime(texto, FORMATO_FECHA) + timedelta(hours=horas)).strftime(FORMATO_FECHA)


def exigir_tipo(actor, *tipos):
    """Verifica que haya sesión y que el actor sea de alguno de los tipos dados; devuelve el actor."""
    if not actor:
        raise ErrorSesion("Entre como cliente, agente o aeropuerto para hacer esto.")
    if actor.get("tipo") not in tipos:
        nombres = {"cliente": "clientes", "agente": "agentes de viaje", "aeropuerto": "personal de aeropuerto"}
        raise ErrorPermiso("Esta acción es solo para " + " o ".join(nombres[t] for t in tipos) + ".")
    return actor


def validar_entero(valor, campo):
    """Convierte a entero positivo (que quepa en SQLite) o lanza ErrorNegocio.
    Rechaza booleanos, listas, decimales con parte fraccionaria y números fuera de rango."""
    if isinstance(valor, (bool, list, dict)) or (isinstance(valor, float) and not valor.is_integer()):
        raise ErrorNegocio(f"El campo {campo} debe ser un número entero.")
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        raise ErrorNegocio(f"El campo {campo} debe ser un número entero.") from None
    if numero <= 0:
        raise ErrorNegocio(f"El campo {campo} debe ser mayor que cero.")
    if numero > MAXIMO_ENTERO:
        raise ErrorNegocio(f"El campo {campo} no es un identificador válido.")
    return numero


def validar_peso(valor):
    """Valida el peso de una maleta (DECIMAL(5,2), positivo y dentro del límite de la aerolínea)."""
    if isinstance(valor, bool):
        raise ErrorNegocio("El peso debe ser un número.")
    try:
        peso = round(float(valor), 2)
    except (TypeError, ValueError):
        raise ErrorNegocio("El peso debe ser un número.") from None
    if not isfinite(peso):
        raise ErrorNegocio("El peso debe ser un número.")
    if peso <= 0:
        raise ErrorNegocio("El peso debe ser mayor que cero.")
    if peso > PESO_MAXIMO_KG:
        raise ErrorNegocio(f"Cada maleta admite máximo {PESO_MAXIMO_KG:g} kg.")
    return peso
