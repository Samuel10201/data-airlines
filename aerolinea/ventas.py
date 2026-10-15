"""Recorrido A: reservar, comprar el tiquete y cancelarlo.

Una reserva es de un cliente para un vuelo (la puede dejar un agente de viaje); puede no llegar a tiquete.
El tiquete es el que guarda el valor y la cancelación (atributo `cancelado`). Los cupos solo se ocupan al
comprar. Lee y escribe: reserva, tiquete. Lee: cliente, vuelo, aeropuerto, ciudad, abordaje, equipaje.
"""
from .dominios import ErrorNegocio, ErrorPermiso, ahora_actual, exigir_tipo, validar_entero
from .esquema import transaccion
from .geografia import distancia_millas, tarifa
from .vuelos import _formatear as resumen_vuelo
from .vuelos import vuelo_para_venta

_CONSULTA = """
SELECT r.id_reserva, r.fecha, r.id_cliente, c.nombre AS cliente, r.id_agente_viaje,
       t.id_tiquete, t.valor, t.cancelado, t.fecha_compra,
       (SELECT COUNT(*) FROM abordaje ab WHERE ab.id_tiquete = t.id_tiquete) AS abordado,
       (SELECT COUNT(*) FROM equipaje q WHERE q.id_tiquete = t.id_tiquete) AS maletas,
       (SELECT group_concat(q.etiqueta, ',') FROM equipaje q WHERE q.id_tiquete = t.id_tiquete) AS etiquetas,
       v.id_vuelo, v.numero_vuelo, v.salida_programada, v.llegada_programada, v.puerta,
       v.id_aeropuerto_origen, v.id_aeropuerto_destino,
       ao.codigo AS o_codigo, ao.latitud AS o_lat, ao.longitud AS o_lon, co.nombre AS o_ciudad, co.pais AS o_pais,
       ad.codigo AS d_codigo, ad.latitud AS d_lat, ad.longitud AS d_lon, cd.nombre AS d_ciudad, cd.pais AS d_pais
FROM reserva r
JOIN cliente c ON c.id_cliente = r.id_cliente
JOIN vuelo v ON v.id_vuelo = r.id_vuelo
JOIN aeropuerto ao ON ao.id_aeropuerto = v.id_aeropuerto_origen
JOIN ciudad co ON co.id_ciudad = ao.id_ciudad
JOIN aeropuerto ad ON ad.id_aeropuerto = v.id_aeropuerto_destino
JOIN ciudad cd ON cd.id_ciudad = ad.id_ciudad
LEFT JOIN tiquete t ON t.id_reserva = r.id_reserva
"""


def _formatear(f):
    """Convierte una fila de _CONSULTA en el dict de la API, con el estado derivado del viaje."""
    millas = round(distancia_millas(f["o_lat"], f["o_lon"], f["d_lat"], f["d_lon"]), 1)
    tiquete = None
    estado = "reservada"
    if f["id_tiquete"] is not None:
        tiquete = {"id_tiquete": f["id_tiquete"], "valor": f["valor"], "cancelado": bool(f["cancelado"]),
                   "fecha_compra": f["fecha_compra"], "abordado": bool(f["abordado"]), "maletas": f["maletas"],
                   "etiquetas": f["etiquetas"].split(",") if f["etiquetas"] else []}
        estado = "cancelado" if f["cancelado"] else "abordado" if f["abordado"] else "comprado"
    return {
        "id_reserva": f["id_reserva"], "fecha": f["fecha"], "estado": estado,
        "cliente": {"id_cliente": f["id_cliente"], "nombre": f["cliente"]},
        "gestionada_por": f["id_agente_viaje"],
        "vuelo": {"id_vuelo": f["id_vuelo"], "numero_vuelo": f["numero_vuelo"], "puerta": f["puerta"],
                  "origen": {"id_aeropuerto": f["id_aeropuerto_origen"], "codigo": f["o_codigo"],
                             "ciudad": f["o_ciudad"], "pais": f["o_pais"]},
                  "destino": {"id_aeropuerto": f["id_aeropuerto_destino"], "codigo": f["d_codigo"],
                              "ciudad": f["d_ciudad"], "pais": f["d_pais"]},
                  "salida_programada": f["salida_programada"], "llegada_programada": f["llegada_programada"],
                  "millas": millas, "valor": tarifa(millas), "nacional": f["o_pais"] == f["d_pais"]},
        "tiquete": tiquete,
    }


def consultar_reservas(conexion, donde, parametros):
    """Reservas (con su tiquete, si lo hay) que cumplen `donde`, ordenadas por salida del vuelo.
    `donde` sale siempre de código propio, nunca de datos del usuario."""
    filas = conexion.execute(f"{_CONSULTA} WHERE {donde} ORDER BY v.salida_programada, r.id_reserva", parametros)
    return [_formatear(f) for f in filas.fetchall()]


def _reserva_del_actor(conexion, actor, id_reserva):
    """Fila de la reserva si el actor es su cliente o el agente que la gestiona; ErrorPermiso si no."""
    fila = conexion.execute("SELECT * FROM reserva WHERE id_reserva = ?", (id_reserva,)).fetchone()
    if not fila:
        raise ErrorNegocio("Esa reserva no existe.")
    if actor["tipo"] == "cliente" and fila["id_cliente"] != actor["id"]:
        raise ErrorPermiso("Esa reserva es de otro cliente.")
    if actor["tipo"] == "agente" and fila["id_agente_viaje"] != actor["id"]:
        raise ErrorPermiso("Esa reserva la gestiona otro agente.")
    return fila


def mis_reservas(conexion, actor):
    """Reservas del cliente, o las que gestiona el agente de viaje."""
    exigir_tipo(actor, "cliente", "agente")
    if actor["tipo"] == "cliente":
        return {"reservas": consultar_reservas(conexion, "r.id_cliente = ?", (actor["id"],))}
    return {"reservas": consultar_reservas(conexion, "r.id_agente_viaje = ?", (actor["id"],))}


def crear_reserva(conexion, actor, id_vuelo, id_cliente=None, ahora=None):
    """Reserva un vuelo que aún no ha salido. El cliente reserva para sí; el agente, para un cliente.

    Devuelve {"reserva": {...}, "mensaje": str}. Lanza ErrorNegocio si el vuelo no existe, ya salió o el
    cliente ya tiene una reserva viva en él; ErrorPermiso si un cliente reserva para otro."""
    exigir_tipo(actor, "cliente", "agente")
    ahora = ahora or ahora_actual()
    id_vuelo = validar_entero(id_vuelo, "vuelo")
    if actor["tipo"] == "cliente":
        if id_cliente not in (None, "", actor["id"]):
            raise ErrorPermiso("Un cliente solo puede reservar para sí mismo.")
        id_cliente, id_agente = actor["id"], None
    else:
        id_cliente, id_agente = validar_entero(id_cliente, "cliente"), actor["id"]
    with transaccion(conexion):
        if not conexion.execute("SELECT 1 FROM cliente WHERE id_cliente = ?", (id_cliente,)).fetchone():
            raise ErrorNegocio("Ese cliente no existe.")
        vuelo = vuelo_para_venta(conexion, id_vuelo)
        if vuelo["salida_programada"] <= ahora:
            raise ErrorNegocio("Ese vuelo ya salió; no se puede reservar.")
        viva = conexion.execute(
            "SELECT 1 FROM reserva r LEFT JOIN tiquete t ON t.id_reserva = r.id_reserva "
            "WHERE r.id_cliente = ? AND r.id_vuelo = ? AND (t.id_tiquete IS NULL OR t.cancelado = 0)",
            (id_cliente, id_vuelo)).fetchone()
        if viva:
            raise ErrorNegocio("Ya existe una reserva de este cliente para este vuelo.")
        cursor = conexion.execute(
            "INSERT INTO reserva (id_cliente, id_vuelo, id_agente_viaje, fecha) VALUES (?, ?, ?, ?)",
            (id_cliente, id_vuelo, id_agente, ahora))
    reserva = consultar_reservas(conexion, "r.id_reserva = ?", (cursor.lastrowid,))[0]
    return {"reserva": reserva, "mensaje": "Reserva creada. Compre el tiquete para asegurar su cupo."}


def comprar_tiquete(conexion, actor, id_reserva, ahora=None):
    """Compra el tiquete de una reserva y fija su valor según la distancia del trayecto.

    Recibe la conexión, el actor con sesión y el id de la reserva. Devuelve {"reserva": {...},
    "mensaje": str}. Lanza ErrorPermiso si la reserva no es del actor y ErrorNegocio si ya tiene
    tiquete, el vuelo ya salió o no quedan cupos."""
    exigir_tipo(actor, "cliente", "agente")
    ahora = ahora or ahora_actual()
    id_reserva = validar_entero(id_reserva, "reserva")
    with transaccion(conexion):
        reserva = _reserva_del_actor(conexion, actor, id_reserva)
        if conexion.execute("SELECT 1 FROM tiquete WHERE id_reserva = ?", (id_reserva,)).fetchone():
            raise ErrorNegocio("Esta reserva ya tiene tiquete.")
        vuelo = vuelo_para_venta(conexion, reserva["id_vuelo"])
        if vuelo["salida_programada"] <= ahora:
            raise ErrorNegocio("El vuelo ya salió; no se puede comprar el tiquete.")
        if vuelo["vendidos"] >= vuelo["capacidad"]:
            raise ErrorNegocio("El vuelo está lleno: no quedan cupos.")
        valor = resumen_vuelo(vuelo)["valor"]
        conexion.execute(
            "INSERT INTO tiquete (id_reserva, valor, cancelado, fecha_compra) VALUES (?, ?, 0, ?)",
            (id_reserva, valor, ahora))
    return {"reserva": consultar_reservas(conexion, "r.id_reserva = ?", (id_reserva,))[0],
            "mensaje": f"Tiquete comprado por {valor:,.2f} USD."}


def cancelar_tiquete(conexion, actor, id_tiquete, ahora=None):
    """Marca un tiquete como cancelado (atributo `cancelado`; el modelo no tiene entidad de cancelación).

    Lanza ErrorPermiso si el tiquete no es del actor y ErrorNegocio si ya está cancelado, ya se usó
    para abordar o el vuelo ya salió."""
    exigir_tipo(actor, "cliente", "agente")
    ahora = ahora or ahora_actual()
    id_tiquete = validar_entero(id_tiquete, "tiquete")
    with transaccion(conexion):
        tiquete = conexion.execute("SELECT * FROM tiquete WHERE id_tiquete = ?", (id_tiquete,)).fetchone()
        if not tiquete:
            raise ErrorNegocio("Ese tiquete no existe.")
        reserva = _reserva_del_actor(conexion, actor, tiquete["id_reserva"])
        if tiquete["cancelado"]:
            raise ErrorNegocio("El tiquete ya está cancelado.")
        if conexion.execute("SELECT 1 FROM abordaje WHERE id_tiquete = ?", (id_tiquete,)).fetchone():
            raise ErrorNegocio("El pasajero ya abordó: el tiquete no se puede cancelar.")
        if vuelo_para_venta(conexion, reserva["id_vuelo"])["salida_programada"] <= ahora:
            raise ErrorNegocio("El vuelo ya salió: el tiquete no se puede cancelar.")
        conexion.execute("UPDATE tiquete SET cancelado = 1 WHERE id_tiquete = ?", (id_tiquete,))
    return {"reserva": consultar_reservas(conexion, "r.id_reserva = ?", (reserva["id_reserva"],))[0],
            "mensaje": "Tiquete cancelado. El cupo quedó libre."}
