"""Recorrido B: abordaje, equipaje y escaneos de maletas en el aeropuerto.

El personal de aeropuerto entra como un aeropuerto concreto. El abordaje y el registro de maletas se hacen en
el aeropuerto de ORIGEN del vuelo; los escaneos, en el de origen o en el de destino. La primera lectura de
una maleta se registra al recibirla. Lee y escribe: abordaje, equipaje, escaneo. Lee: tiquete, reserva,
vuelo, aeropuerto, ciudad, cliente.
"""
from .dominios import (MALETAS_POR_TIQUETE, ErrorNegocio, ErrorPermiso, ahora_actual, exigir_tipo,
                       sumar_horas, validar_entero, validar_peso)
from .esquema import transaccion
from .ventas import consultar_reservas


def _tiquete_activo(conexion, id_tiquete):
    """(tiquete, vuelo) de un tiquete no cancelado. Lanza ErrorNegocio si no existe o está cancelado."""
    fila = conexion.execute(
        "SELECT t.id_tiquete, t.cancelado, v.id_vuelo, v.salida_programada, v.id_aeropuerto_origen, "
        "v.id_aeropuerto_destino FROM tiquete t JOIN reserva r ON r.id_reserva = t.id_reserva "
        "JOIN vuelo v ON v.id_vuelo = r.id_vuelo WHERE t.id_tiquete = ?", (id_tiquete,)).fetchone()
    if not fila:
        raise ErrorNegocio("Ese tiquete no existe.")
    if fila["cancelado"]:
        raise ErrorNegocio("El tiquete está cancelado.")
    return fila


def _exigir_origen(actor, fila):
    """El abordaje y la recepción de maletas ocurren en el aeropuerto de origen del vuelo."""
    if fila["id_aeropuerto_origen"] != actor["id"]:
        raise ErrorPermiso("Esto se hace en el aeropuerto de origen del vuelo, no en este.")


def _escaneos(conexion, id_equipaje):
    return [dict(r) for r in conexion.execute(
        "SELECT s.id_escaneo, s.fecha_hora, s.id_aeropuerto, a.codigo, c.nombre AS ciudad FROM escaneo s "
        "JOIN aeropuerto a ON a.id_aeropuerto = s.id_aeropuerto JOIN ciudad c ON c.id_ciudad = a.id_ciudad "
        "WHERE s.id_equipaje = ? ORDER BY s.fecha_hora, s.id_escaneo", (id_equipaje,))]


def maletas_del_tiquete(conexion, id_tiquete):
    """Maletas de un tiquete con su historial de escaneos."""
    return [{**dict(r), "escaneos": _escaneos(conexion, r["id_equipaje"])} for r in conexion.execute(
        "SELECT id_equipaje, etiqueta, peso_kg FROM equipaje WHERE id_tiquete = ? ORDER BY id_equipaje",
        (id_tiquete,))]


def tiquetes_del_aeropuerto(conexion, actor, id_vuelo=None, ahora=None):
    """Vuelos de este aeropuerto con tiquetes activos (de 2 días atrás a 60 adelante) y los pasajeros de uno.

    Devuelve {"vuelos": [...], "seleccionado": id|None, "tiquetes": [...]}. Si no se pide un vuelo, elige el
    más próximo que aún no ha salido (o, si no hay, el último). Cada tiquete trae su abordaje y sus maletas."""
    exigir_tipo(actor, "aeropuerto")
    ahora = ahora or ahora_actual()
    vuelos = [dict(r) for r in conexion.execute(
        "SELECT * FROM (SELECT v.id_vuelo, v.numero_vuelo, v.salida_programada, v.id_aeropuerto_origen, "
        "ao.codigo AS o_codigo, co.nombre AS o_ciudad, ad.codigo AS d_codigo, cd.nombre AS d_ciudad, "
        "(SELECT COUNT(*) FROM reserva r JOIN tiquete t ON t.id_reserva = r.id_reserva "
        " WHERE r.id_vuelo = v.id_vuelo AND t.cancelado = 0) AS pasajeros FROM vuelo v "
        "JOIN aeropuerto ao ON ao.id_aeropuerto = v.id_aeropuerto_origen JOIN ciudad co ON co.id_ciudad = ao.id_ciudad "
        "JOIN aeropuerto ad ON ad.id_aeropuerto = v.id_aeropuerto_destino JOIN ciudad cd ON cd.id_ciudad = ad.id_ciudad "
        "WHERE (v.id_aeropuerto_origen = ? OR v.id_aeropuerto_destino = ?) AND v.salida_programada BETWEEN ? AND ?) "
        "WHERE pasajeros > 0 ORDER BY salida_programada",
        (actor["id"], actor["id"], sumar_horas(ahora, -48), sumar_horas(ahora, 24 * 60)))]
    ids = [v["id_vuelo"] for v in vuelos]
    if id_vuelo is not None and int(id_vuelo) in ids:
        elegido = int(id_vuelo)
    else:
        proximos = [v["id_vuelo"] for v in vuelos if v["salida_programada"] >= sumar_horas(ahora, -6)]
        elegido = proximos[0] if proximos else (ids[-1] if ids else None)
    reservas = []
    if elegido is not None:
        reservas = consultar_reservas(conexion, "t.id_tiquete IS NOT NULL AND t.cancelado = 0 AND v.id_vuelo = ?",
                                      (elegido,))
        for r in reservas:
            r["tiquete"]["equipaje"] = maletas_del_tiquete(conexion, r["tiquete"]["id_tiquete"])
    return {"vuelos": vuelos, "seleccionado": elegido, "tiquetes": reservas}


def registrar_abordaje(conexion, actor, id_tiquete, ahora=None):
    """Registra el abordaje de un tiquete en el aeropuerto de origen, antes de la salida.

    Lanza ErrorPermiso si no es el aeropuerto de origen y ErrorNegocio si el tiquete está cancelado,
    ya abordó o el vuelo ya salió."""
    exigir_tipo(actor, "aeropuerto")
    ahora = ahora or ahora_actual()
    id_tiquete = validar_entero(id_tiquete, "tiquete")
    with transaccion(conexion):
        fila = _tiquete_activo(conexion, id_tiquete)
        _exigir_origen(actor, fila)
        if conexion.execute("SELECT 1 FROM abordaje WHERE id_tiquete = ?", (id_tiquete,)).fetchone():
            raise ErrorNegocio("Este tiquete ya abordó.")
        if fila["salida_programada"] <= ahora:
            raise ErrorNegocio("El vuelo ya salió: el abordaje está cerrado.")
        conexion.execute("INSERT INTO abordaje (id_tiquete, fecha_hora) VALUES (?, ?)", (id_tiquete, ahora))
    return {"mensaje": "Abordaje registrado."}


def registrar_equipaje(conexion, actor, id_tiquete, peso_kg, ahora=None):
    """Recibe una maleta en el aeropuerto de origen: crea el equipaje con su etiqueta y registra la
    primera lectura. Devuelve {"equipaje": {...}, "mensaje": str}.

    Lanza ErrorNegocio si el peso no es válido, el tiquete está cancelado, el vuelo ya salió o ya
    tiene el máximo de maletas."""
    exigir_tipo(actor, "aeropuerto")
    ahora = ahora or ahora_actual()
    id_tiquete = validar_entero(id_tiquete, "tiquete")
    peso = validar_peso(peso_kg)
    with transaccion(conexion):
        fila = _tiquete_activo(conexion, id_tiquete)
        _exigir_origen(actor, fila)
        if fila["salida_programada"] <= ahora:
            raise ErrorNegocio("El vuelo ya salió: no se reciben más maletas.")
        recibidas = conexion.execute("SELECT COUNT(*) FROM equipaje WHERE id_tiquete = ?", (id_tiquete,)).fetchone()[0]
        if recibidas >= MALETAS_POR_TIQUETE:
            raise ErrorNegocio(f"Cada tiquete admite máximo {MALETAS_POR_TIQUETE} maletas.")
        etiqueta = f"DL{id_tiquete:05d}-{recibidas + 1}"
        cursor = conexion.execute(
            "INSERT INTO equipaje (id_tiquete, etiqueta, peso_kg) VALUES (?, ?, ?)", (id_tiquete, etiqueta, peso))
        conexion.execute("INSERT INTO escaneo (id_equipaje, id_aeropuerto, fecha_hora) VALUES (?, ?, ?)",
                         (cursor.lastrowid, actor["id"], ahora))
    return {"equipaje": {"id_equipaje": cursor.lastrowid, "etiqueta": etiqueta, "peso_kg": peso},
            "mensaje": f"Maleta recibida con la etiqueta {etiqueta}."}


def escanear_equipaje(conexion, actor, id_equipaje, ahora=None):
    """Escanea una maleta en el aeropuerto del actor, que debe ser el de origen o el de destino del vuelo.

    Lanza ErrorPermiso si el aeropuerto no es parte del trayecto y ErrorNegocio si la maleta ya se leyó
    aquí por última vez o si, en el destino, el pasajero aún no ha abordado."""
    exigir_tipo(actor, "aeropuerto")
    ahora = ahora or ahora_actual()
    id_equipaje = validar_entero(id_equipaje, "equipaje")
    with transaccion(conexion):
        maleta = conexion.execute("SELECT id_equipaje, id_tiquete FROM equipaje WHERE id_equipaje = ?",
                                  (id_equipaje,)).fetchone()
        if not maleta:
            raise ErrorNegocio("Esa maleta no existe.")
        fila = _tiquete_activo(conexion, maleta["id_tiquete"])
        if actor["id"] not in (fila["id_aeropuerto_origen"], fila["id_aeropuerto_destino"]):
            raise ErrorPermiso("Este aeropuerto no forma parte del trayecto de la maleta.")
        ultimo = conexion.execute(
            "SELECT id_aeropuerto FROM escaneo WHERE id_equipaje = ? ORDER BY fecha_hora DESC, id_escaneo DESC LIMIT 1",
            (id_equipaje,)).fetchone()
        if ultimo and ultimo["id_aeropuerto"] == actor["id"]:
            raise ErrorNegocio("La maleta ya fue leída aquí; su última lectura es en este aeropuerto.")
        if actor["id"] == fila["id_aeropuerto_destino"] and not conexion.execute(
                "SELECT 1 FROM abordaje WHERE id_tiquete = ?", (maleta["id_tiquete"],)).fetchone():
            raise ErrorNegocio("El pasajero no abordó: la maleta no pudo llegar al destino.")
        conexion.execute("INSERT INTO escaneo (id_equipaje, id_aeropuerto, fecha_hora) VALUES (?, ?, ?)",
                         (id_equipaje, actor["id"], ahora))
    return {"escaneos": _escaneos(conexion, id_equipaje), "mensaje": "Lectura registrada."}


def consultar_equipaje(conexion, etiqueta, ahora=None):
    """Dónde está una maleta: sus lecturas y su ubicación actual, a partir de la etiqueta.

    Lanza ErrorNegocio si la etiqueta no existe."""
    ahora = ahora or ahora_actual()
    etiqueta = str(etiqueta or "").strip().upper()
    if not etiqueta:
        raise ErrorNegocio("Escriba la etiqueta de la maleta.")
    maleta = conexion.execute(
        "SELECT q.id_equipaje, q.etiqueta, q.peso_kg, t.id_tiquete, t.cancelado, c.nombre AS cliente, "
        "v.numero_vuelo, v.salida_programada, v.llegada_programada, v.id_aeropuerto_origen, "
        "v.id_aeropuerto_destino, co.nombre AS o_ciudad, cd.nombre AS d_ciudad FROM equipaje q "
        "JOIN tiquete t ON t.id_tiquete = q.id_tiquete JOIN reserva r ON r.id_reserva = t.id_reserva "
        "JOIN cliente c ON c.id_cliente = r.id_cliente JOIN vuelo v ON v.id_vuelo = r.id_vuelo "
        "JOIN aeropuerto ao ON ao.id_aeropuerto = v.id_aeropuerto_origen JOIN ciudad co ON co.id_ciudad = ao.id_ciudad "
        "JOIN aeropuerto ad ON ad.id_aeropuerto = v.id_aeropuerto_destino JOIN ciudad cd ON cd.id_ciudad = ad.id_ciudad "
        "WHERE q.etiqueta = ?", (etiqueta,)).fetchone()
    if not maleta:
        raise ErrorNegocio(f"No hay ninguna maleta con la etiqueta {etiqueta}.")
    escaneos = _escaneos(conexion, maleta["id_equipaje"])
    ultimo = escaneos[-1] if escaneos else None
    if maleta["cancelado"]:
        estado = "Tiquete cancelado"
    elif ultimo and ultimo["id_aeropuerto"] == maleta["id_aeropuerto_destino"]:
        estado = f"Llegó a {maleta['d_ciudad']}"
    elif maleta["salida_programada"] > ahora:
        estado = f"En {maleta['o_ciudad']}, a la espera del vuelo"
    else:
        estado = f"En tránsito a {maleta['d_ciudad']} (sin lectura en el destino todavía)"
    return {"maleta": {"etiqueta": maleta["etiqueta"], "peso_kg": maleta["peso_kg"], "pasajero": maleta["cliente"],
                       "vuelo": maleta["numero_vuelo"], "origen": maleta["o_ciudad"], "destino": maleta["d_ciudad"],
                       "salida_programada": maleta["salida_programada"], "estado": estado,
                       "id_equipaje": maleta["id_equipaje"], "escaneos": escaneos}}
