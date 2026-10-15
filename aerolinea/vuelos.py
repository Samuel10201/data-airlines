"""Búsqueda de vuelos y detalle de un vuelo (avión y tripulación, solo lectura).

Cubre el inicio del recorrido A. Lee: vuelo, aeropuerto, ciudad, avion, tiquete, reserva,
vuelo_piloto, vuelo_tcp, empleado.
"""
from .dominios import ErrorNegocio, ahora_actual
from .geografia import distancia_millas, tarifa

_BASE = """
SELECT v.id_vuelo, v.numero_vuelo, v.salida_programada, v.llegada_programada, v.salida_real,
       v.llegada_real, v.puerta, v.id_aeropuerto_origen, v.id_aeropuerto_destino,
       ao.codigo AS o_codigo, ao.latitud AS o_lat, ao.longitud AS o_lon, co.nombre AS o_ciudad, co.pais AS o_pais,
       ad.codigo AS d_codigo, ad.latitud AS d_lat, ad.longitud AS d_lon, cd.nombre AS d_ciudad, cd.pais AS d_pais,
       av.matricula, av.modelo, av.capacidad,
       (SELECT COUNT(*) FROM tiquete t JOIN reserva r ON r.id_reserva = t.id_reserva
         WHERE r.id_vuelo = v.id_vuelo AND t.cancelado = 0) AS vendidos
FROM vuelo v
JOIN aeropuerto ao ON ao.id_aeropuerto = v.id_aeropuerto_origen
JOIN ciudad co ON co.id_ciudad = ao.id_ciudad
JOIN aeropuerto ad ON ad.id_aeropuerto = v.id_aeropuerto_destino
JOIN ciudad cd ON cd.id_ciudad = ad.id_ciudad
JOIN avion av ON av.id_avion = v.id_avion
"""


def _formatear(f):
    """Convierte una fila de _BASE en el dict que ve la API (con millas, valor y cupos derivados)."""
    millas = round(distancia_millas(f["o_lat"], f["o_lon"], f["d_lat"], f["d_lon"]), 1)
    return {
        "id_vuelo": f["id_vuelo"], "numero_vuelo": f["numero_vuelo"],
        "origen": {"id_aeropuerto": f["id_aeropuerto_origen"], "codigo": f["o_codigo"],
                   "ciudad": f["o_ciudad"], "pais": f["o_pais"]},
        "destino": {"id_aeropuerto": f["id_aeropuerto_destino"], "codigo": f["d_codigo"],
                    "ciudad": f["d_ciudad"], "pais": f["d_pais"]},
        "salida_programada": f["salida_programada"], "llegada_programada": f["llegada_programada"],
        "salida_real": f["salida_real"], "llegada_real": f["llegada_real"], "puerta": f["puerta"],
        "millas": millas, "valor": tarifa(millas), "nacional": f["o_pais"] == f["d_pais"],
        "avion": {"matricula": f["matricula"], "modelo": f["modelo"], "capacidad": f["capacidad"]},
        "cupos_libres": max(f["capacidad"] - f["vendidos"], 0),
    }


def listar_aeropuertos(conexion):
    """Aeropuertos con su ciudad, país y coordenadas (para dibujar el mapa de rutas), ordenados por ciudad."""
    return [dict(r) for r in conexion.execute(
        "SELECT a.id_aeropuerto, a.codigo, a.nombre, a.latitud, a.longitud, c.nombre AS ciudad, c.pais FROM aeropuerto a "
        "JOIN ciudad c ON c.id_ciudad = a.id_ciudad ORDER BY c.nombre")]


def buscar_vuelos(conexion, origen=None, destino=None, fecha=None, ahora=None):
    """Vuelos que aún no han salido, filtrados por aeropuerto de origen, de destino y día (YYYY-MM-DD).

    Devuelve {"vuelos": [...]}. Lanza ErrorNegocio si el filtro de fecha no tiene el formato esperado."""
    ahora = ahora or ahora_actual()
    condiciones, parametros = ["v.salida_programada > ?"], [ahora]
    if origen:
        condiciones.append("v.id_aeropuerto_origen = ?")
        parametros.append(int(origen))
    if destino:
        condiciones.append("v.id_aeropuerto_destino = ?")
        parametros.append(int(destino))
    if fecha:
        if len(fecha) != 10 or fecha[4] != "-" or fecha[7] != "-":
            raise ErrorNegocio("La fecha debe tener el formato AAAA-MM-DD.")
        condiciones.append("substr(v.salida_programada, 1, 10) = ?")
        parametros.append(fecha)
    filas = conexion.execute(f"{_BASE} WHERE {' AND '.join(condiciones)} ORDER BY v.salida_programada LIMIT 60",
                             parametros).fetchall()
    return {"vuelos": [_formatear(f) for f in filas]}


def detalle_vuelo(conexion, id_vuelo):
    """Un vuelo con su tripulación: pilotos y TCP asignados. Lanza ErrorNegocio si no existe."""
    fila = conexion.execute(f"{_BASE} WHERE v.id_vuelo = ?", (id_vuelo,)).fetchone()
    if not fila:
        raise ErrorNegocio("Ese vuelo no existe.")
    vuelo = _formatear(fila)
    vuelo["pilotos"] = [r[0] for r in conexion.execute(
        "SELECT e.nombre FROM vuelo_piloto vp JOIN empleado e ON e.id_empleado = vp.id_piloto "
        "WHERE vp.id_vuelo = ? ORDER BY e.nombre", (id_vuelo,))]
    vuelo["tcp"] = [r[0] for r in conexion.execute(
        "SELECT e.nombre FROM vuelo_tcp vt JOIN empleado e ON e.id_empleado = vt.id_tcp "
        "WHERE vt.id_vuelo = ? ORDER BY e.nombre", (id_vuelo,))]
    return {"vuelo": vuelo}


def vuelo_para_venta(conexion, id_vuelo):
    """Fila cruda del vuelo (con capacidad y vendidos) para que ventas.py valide. Lanza ErrorNegocio si no existe."""
    fila = conexion.execute(f"{_BASE} WHERE v.id_vuelo = ?", (id_vuelo,)).fetchone()
    if not fila:
        raise ErrorNegocio("Ese vuelo no existe.")
    return fila
