"""Distancias y tarifas: las millas y el valor del tiquete se DERIVAN de las coordenadas de los aeropuertos.

El modelo no guarda millas ni tarifas (decisión del punto 2): `aeropuerto` lleva latitud y longitud y el
resto se calcula aquí. No lee la BD: recibe las coordenadas.
"""
from math import asin, cos, radians, sin, sqrt

from .dominios import TARIFA_BASE, TARIFA_POR_MILLA

RADIO_TIERRA_MILLAS = 3958.8


def distancia_millas(lat1, lon1, lat2, lon2):
    """Distancia del círculo máximo (haversine) entre dos coordenadas, en millas."""
    d_lat, d_lon = radians(lat2 - lat1), radians(lon2 - lon1)
    a = sin(d_lat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(d_lon / 2) ** 2
    return 2 * RADIO_TIERRA_MILLAS * asin(sqrt(a))


def tarifa(millas):
    """Valor del tiquete para un trayecto de `millas` (DECIMAL(10,2))."""
    return round(TARIFA_BASE + millas * TARIFA_POR_MILLA, 2)
