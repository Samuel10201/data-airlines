"""Datos de demostración. Todo lo que la aplicación opera (reservas, tiquetes, cancelaciones, abordajes,
maletas y escaneos) se crea con las MISMAS funciones que usa la interfaz, fijando `ahora`; así la semilla
respeta las reglas de negocio. Las tablas que la aplicación no opera (recursos, mantenimientos,
tripulación) se pueblan con INSERT directos.

Las fechas son relativas a `ahora`: hay vuelos recientes (con abordajes y maletas ya escaneadas), vuelos de
las próximas horas (para probar el abordaje) y vuelos de las próximas semanas (para reservar y comprar).
"""
import random
from datetime import datetime, timedelta

from . import aeropuerto, ventas
from .dominios import FORMATO_FECHA, ahora_actual
from .esquema import transaccion
from .geografia import distancia_millas

CIUDADES = [
    ("Barranquilla", "Colombia", "America/Bogota"), ("Bogotá", "Colombia", "America/Bogota"),
    ("Medellín", "Colombia", "America/Bogota"), ("Cartagena", "Colombia", "America/Bogota"),
    ("Miami", "Estados Unidos", "America/New_York"), ("Atlanta", "Estados Unidos", "America/New_York"),
    ("Ciudad de México", "México", "America/Mexico_City"), ("Panamá", "Panamá", "America/Panama"),
]
# (índice de ciudad, código, nombre, latitud, longitud)
AEROPUERTOS = [
    (0, "BAQ", "Ernesto Cortissoz", 10.8896, -74.7808), (1, "BOG", "El Dorado", 4.7016, -74.1469),
    (2, "MDE", "José María Córdova", 6.1645, -75.4231), (3, "CTG", "Rafael Núñez", 10.4424, -75.5130),
    (4, "MIA", "Miami International", 25.7959, -80.2870), (5, "ATL", "Hartsfield-Jackson", 33.6407, -84.4277),
    (6, "MEX", "Benito Juárez", 19.4363, -99.0721), (7, "PTY", "Tocumen", 9.0714, -79.3835),
]
AVIONES = [("N401DD", "Airbus A320", 180), ("N402DD", "Boeing 737-800", 160),
           ("N403DD", "Airbus A330-200", 260), ("N404DD", "Embraer E190", 100)]
PILOTOS = ["Andrés Felipe Castro", "María Paula Vergara", "Carlos Eduardo Lemus", "Juliana Posada Rey",
           "Ricardo Serrano Mora", "Natalia Cárdenas Ruiz"]
TCP = ["Sofía Hernández", "Luis Fernando Mejía", "Daniela Pineda", "Jorge Iván Salcedo", "Paola Andrea Ríos",
       "Esteban Tovar", "Marcela Quintero", "Camilo Arenas"]
AGENTES = ["Carolina Pérez Mejía", "Jorge Restrepo Vélez"]
TECNICOS = ["Hernán Lozano", "Adriana Fuentes"]
LIMPIEZA = ["Rosa Elena Barrios", "Wilson Cuesta"]
CLIENTES = [("Valentina Ospina Ruiz", "valentina.ospina@correo.co", "3105550101"),
            ("Santiago Herrera Díaz", "santiago.herrera@correo.co", "3105550102"),
            ("Laura Castaño Vélez", "laura.castano@correo.co", None),
            ("Daniel Ortega Pérez", "daniel.ortega@correo.co", "3105550104"),
            ("Camila Rojas Mejía", "camila.rojas@correo.co", "3105550105"),
            ("Mateo Gómez Arias", "mateo.gomez@correo.co", None)]
# Rutas (código de origen, código de destino): nacionales e internacionales.
RUTAS = [("BAQ", "BOG"), ("BOG", "BAQ"), ("BOG", "MDE"), ("MDE", "BOG"), ("BOG", "MIA"), ("MIA", "BOG"),
         ("BAQ", "MIA"), ("MIA", "BAQ"), ("ATL", "BOG"), ("BOG", "ATL"), ("CTG", "PTY"), ("PTY", "CTG"),
         ("MEX", "BOG"), ("BOG", "MEX"), ("MDE", "MIA"), ("BAQ", "MDE"), ("CTG", "BOG"), ("BOG", "CTG")]
# Salidas relativas a `ahora`, en horas. Negativas: ya ocurrieron (con horas reales).
HORAS_PASADAS = [-2400, -2150, -1900, -1700, -1450, -1200, -980, -760, -560, -400, -300, -220, -150, -100, -60, -30, -12, -6]
HORAS_FUTURAS = [3, 5, 9, 22, 28, 34, 52, 75, 100, 125, 150, 200, 250, 310, 380, 450, 520, 600]


def _texto(momento):
    return momento.strftime(FORMATO_FECHA)


def _insertar(conexion, sql, filas):
    """Inserta varias filas y devuelve sus ids en orden."""
    ids = []
    for fila in filas:
        ids.append(conexion.execute(sql, fila).lastrowid)
    return ids


def _poblar_catalogos(conexion):
    """Ciudades, aeropuertos, aviones, empleados (con su tipo) y clientes."""
    ciudades = _insertar(conexion, "INSERT INTO ciudad (nombre, pais, zona_horaria) VALUES (?, ?, ?)", CIUDADES)
    aeropuertos = {}
    for i, (c, codigo, nombre, lat, lon) in enumerate(AEROPUERTOS):
        aeropuertos[codigo] = conexion.execute(
            "INSERT INTO aeropuerto (id_ciudad, codigo, nombre, latitud, longitud) VALUES (?, ?, ?, ?, ?)",
            (ciudades[c], codigo, nombre, lat, lon)).lastrowid
    aviones = _insertar(conexion, "INSERT INTO avion (matricula, modelo, capacidad) VALUES (?, ?, ?)", AVIONES)

    empleados = {}
    numero = 0
    for tipo, tabla, columna, nombres in (("piloto", "piloto", "id_piloto", PILOTOS), ("tcp", "tcp", "id_tcp", TCP),
                                          ("agente_viaje", "agente_viaje", "id_agente_viaje", AGENTES),
                                          ("tecnico_mantenimiento", "tecnico_mantenimiento",
                                           "id_tecnico_mantenimiento", TECNICOS),
                                          ("limpieza", None, None, LIMPIEZA)):
        ids = []
        for nombre in nombres:
            numero += 1
            id_empleado = conexion.execute("INSERT INTO empleado (nombre, documento, tipo) VALUES (?, ?, ?)",
                                           (nombre, f"90000{numero:04d}", tipo)).lastrowid
            if tabla:  # `limpieza` es solo un valor de empleado.tipo, sin tabla propia
                conexion.execute(f"INSERT INTO {tabla} ({columna}) VALUES (?)", (id_empleado,))
            ids.append(id_empleado)
        empleados[tipo] = ids

    clientes = []
    for i, (nombre, correo, telefono) in enumerate(CLIENTES):
        clientes.append(conexion.execute(
            "INSERT INTO cliente (nombre, documento, correo, telefono) VALUES (?, ?, ?, ?)",
            (nombre, f"10{i + 1:08d}", correo, telefono)).lastrowid)
    return aeropuertos, aviones, empleados, clientes


def _crear_vuelos(conexion, ahora, aeropuertos, aviones, empleados, coords):
    """Vuelos pasados y futuros con su avión, pilotos y TCP. Devuelve una lista de dicts."""
    vuelos = []
    for i, horas in enumerate(sorted(HORAS_PASADAS + HORAS_FUTURAS)):
        origen, destino = RUTAS[i % len(RUTAS)]
        millas = distancia_millas(*coords[origen], *coords[destino])
        salida = ahora + timedelta(hours=horas)
        llegada = salida + timedelta(minutes=int(40 + millas / 8))
        real = horas < 0
        retraso = timedelta(minutes=(i * 7) % 25)
        id_vuelo = conexion.execute(
            "INSERT INTO vuelo (numero_vuelo, id_aeropuerto_origen, id_aeropuerto_destino, id_avion, "
            "salida_programada, llegada_programada, salida_real, llegada_real, puerta) VALUES (?,?,?,?,?,?,?,?,?)",
            (f"DD{100 + i * 7}", aeropuertos[origen], aeropuertos[destino], aviones[i % len(aviones)],
             _texto(salida), _texto(llegada), _texto(salida + retraso) if real else None,
             _texto(llegada + retraso) if real else None, f"{'ABCD'[i % 4]}{10 + i % 20}")).lastrowid
        for p in range(2):
            conexion.execute("INSERT INTO vuelo_piloto (id_vuelo, id_piloto) VALUES (?, ?)",
                             (id_vuelo, empleados["piloto"][(i + p) % len(empleados["piloto"])]))
        for t in range(3):
            conexion.execute("INSERT INTO vuelo_tcp (id_vuelo, id_tcp) VALUES (?, ?)",
                             (id_vuelo, empleados["tcp"][(i * 2 + t) % len(empleados["tcp"])]))
        vuelos.append({"id": id_vuelo, "salida": salida, "llegada": llegada, "origen": aeropuertos[origen],
                       "destino": aeropuertos[destino], "pasado": real})
    return vuelos


def _poblar_recursos_y_mantenimiento(conexion, ahora, aeropuertos, aviones, empleados, vuelos):
    """Recursos, mantenimientos y sus técnicos: tablas que los recorridos no operan, pero que existen en el modelo."""
    recursos = [("Combustible Jet A-1", "BOG", "consumible"), ("Comidas a bordo", "BOG", "consumible"),
                ("Barra de remolque", "BOG", "equipo"), ("Escalera de abordaje", "BAQ", "equipo"),
                ("Unidad de potencia en tierra", "MIA", "equipo")]
    ids = []
    for nombre, codigo, tipo in recursos:
        id_recurso = conexion.execute("INSERT INTO recurso (id_aeropuerto, nombre) VALUES (?, ?)",
                                      (aeropuertos[codigo], nombre)).lastrowid
        conexion.execute(f"INSERT INTO {tipo} (id_{tipo}) VALUES (?)", (id_recurso,))
        ids.append((id_recurso, tipo))
    for i, vuelo in enumerate(vuelos[:10]):
        conexion.execute("INSERT INTO vuelo_recurso (id_vuelo, id_recurso) VALUES (?, ?)", (vuelo["id"], ids[i % 2][0]))
    equipos = [r for r, t in ids if t == "equipo"]
    for i, avion in enumerate(aviones):
        conexion.execute("INSERT INTO equipo_avion (id_equipo, id_avion) VALUES (?, ?)", (equipos[i % len(equipos)], avion))
    tecnicos = empleados["tecnico_mantenimiento"]
    for i, avion in enumerate(aviones):
        id_mant = conexion.execute(
            "INSERT INTO mantenimiento_avion (id_avion, id_vuelo, fecha, descripcion) VALUES (?, ?, ?, ?)",
            (avion, vuelos[i * 3]["id"] if i % 2 == 0 else None, _texto(ahora - timedelta(days=10 + i * 9)),
             "Revisión previa al vuelo" if i % 2 == 0 else "Revisión periódica de 500 horas")).lastrowid
        conexion.execute("INSERT INTO mantenimiento_avion_tecnico (id_mantenimiento_avion, id_tecnico_mantenimiento) "
                         "VALUES (?, ?)", (id_mant, tecnicos[i % len(tecnicos)]))
    for i, equipo in enumerate(equipos):
        id_mant = conexion.execute(
            "INSERT INTO mantenimiento_equipo (id_equipo, fecha, descripcion) VALUES (?, ?, ?)",
            (equipo, _texto(ahora - timedelta(days=20 + i * 6)), "Inspección y lubricación")).lastrowid
        conexion.execute("INSERT INTO mantenimiento_equipo_tecnico (id_mantenimiento_equipo, "
                         "id_tecnico_mantenimiento) VALUES (?, ?)", (id_mant, tecnicos[(i + 1) % len(tecnicos)]))


def _vender(conexion, azar, ahora, vuelos, clientes, agentes, nombres):
    """Reservas, tiquetes, cancelaciones, abordajes, maletas y escaneos, con las funciones de la aplicación."""
    conteo = {"reservas": 0, "tiquetes": 0, "cancelados": 0, "abordajes": 0, "maletas": 0, "escaneos_destino": 0}
    for n, vuelo in enumerate(vuelos):
        if vuelo["pasado"]:
            compradores = azar.sample(clientes, azar.randint(2, 4))
        elif n % 3 == 0 or vuelo["salida"] - ahora < timedelta(hours=40):
            compradores = azar.sample(clientes, azar.randint(1, 3))
        else:
            compradores = azar.sample(clientes, azar.randint(0, 1))
        for cliente in compradores:
            antes = vuelo["salida"] - timedelta(days=azar.randint(2, 25), hours=azar.randint(0, 20))
            t_reserva = min(antes, ahora - timedelta(minutes=5))
            cliente_actor = {"tipo": "cliente", "id": cliente, "nombre": nombres[cliente]}
            if azar.random() < 0.3:  # reserva gestionada por un agente de viaje
                actor = {"tipo": "agente", "id": azar.choice(agentes), "nombre": "Agente"}
                reserva = ventas.crear_reserva(conexion, actor, vuelo["id"], cliente, _texto(t_reserva))
            else:
                actor = cliente_actor
                reserva = ventas.crear_reserva(conexion, actor, vuelo["id"], None, _texto(t_reserva))
            conteo["reservas"] += 1
            id_reserva = reserva["reserva"]["id_reserva"]
            if azar.random() < 0.15 and not vuelo["pasado"]:
                continue  # reserva sin pagar: el modelo permite que no llegue a tiquete
            t_compra = _texto(min(t_reserva + timedelta(hours=1), ahora))
            compra = ventas.comprar_tiquete(conexion, actor, id_reserva, t_compra)
            conteo["tiquetes"] += 1
            id_tiquete = compra["reserva"]["tiquete"]["id_tiquete"]
            if azar.random() < 0.12:
                ventas.cancelar_tiquete(conexion, actor, id_tiquete, _texto(min(vuelo["salida"] - timedelta(hours=30), ahora)))
                conteo["cancelados"] += 1
                continue
            llegan_hoy = vuelo["pasado"] or vuelo["salida"] - ahora < timedelta(hours=6)
            if not llegan_hoy:
                continue  # los vuelos lejanos solo tienen reserva y tiquete: aún no hay nada que hacer en el aeropuerto
            origen = {"tipo": "aeropuerto", "id": vuelo["origen"], "nombre": "origen"}
            destino = {"tipo": "aeropuerto", "id": vuelo["destino"], "nombre": "destino"}
            aborda = azar.random() < (0.9 if vuelo["pasado"] else 0.4)
            if aborda or (not vuelo["pasado"] and azar.random() < 0.6):
                for _ in range(azar.choice([1, 1, 2])):
                    t_maleta = _texto(min(vuelo["salida"] - timedelta(minutes=80), ahora))
                    aeropuerto.registrar_equipaje(conexion, origen, id_tiquete, round(azar.uniform(8, 27), 1), t_maleta)
                    conteo["maletas"] += 1
            if aborda:
                aeropuerto.registrar_abordaje(conexion, origen, id_tiquete,
                                              _texto(min(vuelo["salida"] - timedelta(minutes=45), ahora)))
                conteo["abordajes"] += 1
                if vuelo["pasado"]:
                    for maleta in aeropuerto.maletas_del_tiquete(conexion, id_tiquete):
                        aeropuerto.escanear_equipaje(conexion, destino, maleta["id_equipaje"],
                                                     _texto(vuelo["llegada"] + timedelta(minutes=25)))
                        conteo["escaneos_destino"] += 1
    return conteo


def sembrar(conexion, ahora=None):
    """Puebla las 26 tablas. Devuelve un resumen con lo que se creó. `ahora` fija la fecha de referencia."""
    ahora_texto = ahora or ahora_actual()
    momento = datetime.strptime(ahora_texto, FORMATO_FECHA)
    azar = random.Random(2026)
    coords = {codigo: (lat, lon) for _, codigo, _, lat, lon in AEROPUERTOS}
    with transaccion(conexion):
        aeropuertos, aviones, empleados, clientes = _poblar_catalogos(conexion)
        vuelos = _crear_vuelos(conexion, momento, aeropuertos, aviones, empleados, coords)
        _poblar_recursos_y_mantenimiento(conexion, momento, aeropuertos, aviones, empleados, vuelos)
    nombres = {r["id_cliente"]: r["nombre"] for r in conexion.execute("SELECT id_cliente, nombre FROM cliente")}
    conteo = _vender(conexion, azar, momento, vuelos, clientes, empleados["agente_viaje"], nombres)
    vacias = [t for (t,) in conexion.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        if conexion.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] == 0]
    conteo["vuelos"] = len(vuelos)
    conteo["tablas_vacias"] = vacias
    return conteo
