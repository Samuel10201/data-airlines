"""Recorrido C: el Data Warehouse (esquema `dw`) se carga desde la base transaccional y responde 4a, 4b y 4c.

La carga (ETL) vacía las siete tablas del DW y las vuelve a llenar en una sola transacción, con las reglas de
`ecosistemas\\revision-dw.md`: nada entra al DW que la base no tenga. Cada reporte devuelve las cifras ya
organizadas por fila y mes, la consulta que se ejecutó sobre el DW y una verificación contra la base.
Lee: reserva, tiquete, abordaje, vuelo, aeropuerto, ciudad, cliente. Escribe: las tablas de `dw`.
"""
import re

from .dominios import ErrorNegocio, ahora_actual
from .esquema import transaccion
from .geografia import distancia_millas

TABLAS_DW = ("dim_tiempo", "dim_geografia", "dim_cliente", "dim_ruta",
             "facts_ingresos", "facts_reservaciones", "facts_millas")
MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre",
         "noviembre", "diciembre"]

CONSULTA_INGRESOS = """SELECT g.ciudad, t.mes_numero, SUM(f.monto_ingreso)
FROM facts_ingresos f
JOIN dim_geografia g ON g.id_geografia = f.id_geografia
JOIN dim_tiempo t ON t.id_tiempo = f.id_tiempo
WHERE t.anio = ?
GROUP BY g.ciudad, t.mes_numero"""
CONSULTA_RESERVACIONES = """SELECT g.ciudad, t.mes_numero, SUM(f.cantidad_reservaciones)
FROM facts_reservaciones f
JOIN dim_geografia g ON g.id_geografia = f.id_geografia
JOIN dim_tiempo t ON t.id_tiempo = f.id_tiempo
WHERE t.anio = ?
GROUP BY g.ciudad, t.mes_numero"""
CONSULTA_MILLAS = """SELECT c.nombre, t.mes_numero, SUM(f.millas_acumuladas)
FROM facts_millas f
JOIN dim_cliente c ON c.id_cliente = f.id_cliente
JOIN dim_tiempo t ON t.id_tiempo = f.id_tiempo
JOIN dim_ruta r ON r.id_ruta = f.id_ruta
WHERE r.nacional = 1 AND t.anio = ?
GROUP BY c.nombre, t.mes_numero"""


def estado_dw(conexion):
    """Filas de cada tabla del DW y si ya se cargó. Siempre responde, aunque el DW esté vacío."""
    filas = {t: conexion.execute(f"SELECT COUNT(*) FROM dw.{t}").fetchone()[0] for t in TABLAS_DW}
    meses = conexion.execute("SELECT MIN(anio * 100 + mes_numero), MAX(anio * 100 + mes_numero) FROM dw.dim_tiempo").fetchone()
    return {"filas": filas, "cargado": filas["dim_tiempo"] > 0,
            "primer_mes": meses[0], "ultimo_mes": meses[1],
            "anios": [r[0] for r in conexion.execute("SELECT DISTINCT anio FROM dw.dim_tiempo ORDER BY anio")]}


def cargar_dw(conexion):
    """Vacía y vuelve a llenar el DW desde la base transaccional. Devuelve {"filas": {...}, "mensaje": str}."""
    with transaccion(conexion):
        for tabla in reversed(TABLAS_DW):  # primero los hechos, luego las dimensiones
            conexion.execute(f"DELETE FROM dw.{tabla}")
        _cargar_dimensiones(conexion)
        _cargar_hechos(conexion)
    estado = estado_dw(conexion)
    total = sum(estado["filas"].values())
    return {"filas": estado["filas"], "mensaje": f"DW cargado: {total} filas en {len(TABLAS_DW)} tablas."}


def _cargar_dimensiones(conexion):
    anios = [r[0] for r in conexion.execute(
        "SELECT DISTINCT CAST(substr(f, 1, 4) AS INTEGER) FROM (SELECT fecha AS f FROM reserva "
        "UNION SELECT fecha_compra FROM tiquete UNION SELECT salida_programada FROM vuelo) ORDER BY 1")]
    for anio in anios:  # todos los meses de cada año presente, para que los reportes muestren el año completo
        for numero, nombre in enumerate(MESES, start=1):
            conexion.execute("INSERT INTO dw.dim_tiempo (anio, mes_numero, mes_nombre) VALUES (?, ?, ?)",
                             (anio, numero, nombre))
    conexion.execute("INSERT INTO dw.dim_geografia (id_geografia, ciudad, pais) SELECT id_ciudad, nombre, pais FROM ciudad")
    conexion.execute("INSERT INTO dw.dim_cliente (id_cliente, nombre, documento, correo) "
                     "SELECT id_cliente, nombre, documento, correo FROM cliente")
    conexion.execute(
        "INSERT INTO dw.dim_ruta (aeropuerto_origen, aeropuerto_destino, ciudad_origen, ciudad_destino, nacional) "
        "SELECT DISTINCT ao.codigo, ad.codigo, co.nombre, cd.nombre, co.pais = cd.pais FROM vuelo v "
        "JOIN aeropuerto ao ON ao.id_aeropuerto = v.id_aeropuerto_origen JOIN ciudad co ON co.id_ciudad = ao.id_ciudad "
        "JOIN aeropuerto ad ON ad.id_aeropuerto = v.id_aeropuerto_destino JOIN ciudad cd ON cd.id_ciudad = ad.id_ciudad")


_TIEMPO = ("JOIN dw.dim_tiempo dt ON dt.anio = CAST(substr({fecha}, 1, 4) AS INTEGER) "
           "AND dt.mes_numero = CAST(substr({fecha}, 6, 2) AS INTEGER) ")
_ORIGEN = ("JOIN vuelo v ON v.id_vuelo = r.id_vuelo JOIN aeropuerto ao ON ao.id_aeropuerto = v.id_aeropuerto_origen ")


def _cargar_hechos(conexion):
    # 4a: un tiquete no cancelado; el mes es el de la compra y la ciudad la de origen del vuelo
    conexion.execute(
        "INSERT INTO dw.facts_ingresos (id_tiempo, id_geografia, id_cliente, monto_ingreso) "
        "SELECT dt.id_tiempo, ao.id_ciudad, r.id_cliente, t.valor FROM tiquete t "
        "JOIN reserva r ON r.id_reserva = t.id_reserva " + _ORIGEN + _TIEMPO.format(fecha="t.fecha_compra") +
        "WHERE t.cancelado = 0")
    # 4b: una reserva, llegue o no a tiquete; el mes es el de la reserva
    conexion.execute(
        "INSERT INTO dw.facts_reservaciones (id_tiempo, id_geografia, id_cliente, cantidad_reservaciones) "
        "SELECT dt.id_tiempo, ao.id_ciudad, r.id_cliente, 1 FROM reserva r " + _ORIGEN + _TIEMPO.format(fecha="r.fecha"))
    # 4c: un abordaje; las millas son la distancia del trayecto y el mes es el de la salida del vuelo
    meses = {(r[1], r[2]): r[0] for r in conexion.execute("SELECT id_tiempo, anio, mes_numero FROM dw.dim_tiempo")}
    rutas = {(r[1], r[2]): r[0] for r in conexion.execute("SELECT id_ruta, aeropuerto_origen, aeropuerto_destino FROM dw.dim_ruta")}
    for fila in _abordajes(conexion):
        id_tiempo = meses[(int(fila["salida"][:4]), int(fila["salida"][5:7]))]
        conexion.execute(
            "INSERT INTO dw.facts_millas (id_tiempo, id_cliente, id_ruta, millas_acumuladas) VALUES (?, ?, ?, ?)",
            (id_tiempo, fila["id_cliente"], rutas[(fila["o_codigo"], fila["d_codigo"])], fila["millas"]))


def _abordajes(conexion):
    """Una fila por abordaje con el cliente, la salida del vuelo, los aeropuertos, el país y las millas del trayecto."""
    filas = conexion.execute(
        "SELECT r.id_cliente, v.salida_programada AS salida, ao.codigo AS o_codigo, ad.codigo AS d_codigo, "
        "co.pais AS o_pais, cd.pais AS d_pais, ao.latitud AS o_lat, ao.longitud AS o_lon, ad.latitud AS d_lat, "
        "ad.longitud AS d_lon FROM abordaje ab JOIN tiquete t ON t.id_tiquete = ab.id_tiquete "
        "JOIN reserva r ON r.id_reserva = t.id_reserva JOIN vuelo v ON v.id_vuelo = r.id_vuelo "
        "JOIN aeropuerto ao ON ao.id_aeropuerto = v.id_aeropuerto_origen JOIN ciudad co ON co.id_ciudad = ao.id_ciudad "
        "JOIN aeropuerto ad ON ad.id_aeropuerto = v.id_aeropuerto_destino JOIN ciudad cd ON cd.id_ciudad = ad.id_ciudad").fetchall()
    return [{**dict(f), "millas": round(distancia_millas(f["o_lat"], f["o_lon"], f["d_lat"], f["d_lon"]), 1)}
            for f in filas]


def _anio(conexion, anio):
    """Año pedido (o el más reciente con datos) y los años disponibles. Lanza ErrorNegocio si el DW está vacío."""
    anios = estado_dw(conexion)["anios"]
    if not anios:
        raise ErrorNegocio("El Data Warehouse está vacío: cárguelo primero.")
    if anio in (None, ""):
        return anios[-1], anios
    try:
        anio = int(anio)
    except (TypeError, ValueError):
        raise ErrorNegocio("El año debe ser un número.") from None
    if anio not in anios:
        raise ErrorNegocio(f"El DW no tiene el año {anio}; hay datos de {', '.join(map(str, anios))}.")
    return anio, anios


def _en_dw(consulta):
    """La consulta se muestra como se escribiría dentro del DW; para ejecutarla se califican sus tablas con `dw.`."""
    return re.sub(r"\b(FROM|JOIN) (facts_|dim_)", r"\1 dw.\2", consulta)


def _pivote(conexion, consulta, anio, etiquetas):
    """Ejecuta `consulta` sobre el DW y la organiza en filas (una por etiqueta) y 12 columnas (los meses)."""
    celdas = {(r[0], r[1]): r[2] for r in conexion.execute(_en_dw(consulta), (anio,))}
    filas = []
    for etiqueta, detalle in etiquetas:
        valores = [celdas.get((etiqueta, mes), 0) or 0 for mes in range(1, 13)]
        filas.append({"etiqueta": etiqueta, "detalle": detalle, "valores": valores, "total": round(sum(valores), 2)})
    totales_mes = [round(sum(f["valores"][m] for f in filas), 2) for m in range(12)]
    return {"anio": anio, "meses": [m[:3] for m in MESES], "filas": filas, "totales_mes": totales_mes,
            "total": round(sum(totales_mes), 2), "consulta": consulta.replace("?", str(anio))}


def _etiquetas(conexion, sql):
    return [(r[0], r[1]) for r in conexion.execute(sql)]


def reporte_ingresos(conexion, anio=None):
    """4a: ingresos por venta de tiquetes, por ciudad y mes, desde el DW; con la verificación contra la base."""
    anio, anios = _anio(conexion, anio)
    informe = _pivote(conexion, CONSULTA_INGRESOS, anio, _etiquetas(conexion, "SELECT ciudad, pais FROM dw.dim_geografia ORDER BY ciudad"))
    base = conexion.execute(
        "SELECT COALESCE(SUM(valor), 0) FROM tiquete WHERE cancelado = 0 AND CAST(substr(fecha_compra, 1, 4) AS INTEGER) = ?",
        (anio,)).fetchone()[0]
    return {**informe, "anios": anios, "verificacion": _verificar(informe["total"], base)}


def reporte_reservaciones(conexion, anio=None):
    """4b: reservaciones por ciudad y mes, desde el DW; con la verificación contra la base."""
    anio, anios = _anio(conexion, anio)
    informe = _pivote(conexion, CONSULTA_RESERVACIONES, anio, _etiquetas(conexion, "SELECT ciudad, pais FROM dw.dim_geografia ORDER BY ciudad"))
    base = conexion.execute(
        "SELECT COUNT(*) FROM reserva WHERE CAST(substr(fecha, 1, 4) AS INTEGER) = ?", (anio,)).fetchone()[0]
    return {**informe, "anios": anios, "verificacion": _verificar(informe["total"], base)}


def reporte_millas(conexion, anio=None):
    """4c: millas acumuladas por pasajero y mes en vuelos nacionales, desde el DW; con la verificación contra la base
    y las millas internacionales que se dejaron fuera."""
    anio, anios = _anio(conexion, anio)
    informe = _pivote(conexion, CONSULTA_MILLAS, anio, _etiquetas(conexion, "SELECT nombre, documento FROM dw.dim_cliente ORDER BY nombre"))
    del_anio = [f for f in _abordajes(conexion) if int(f["salida"][:4]) == anio]
    base = round(sum(f["millas"] for f in del_anio if f["o_pais"] == f["d_pais"]), 2)
    internacionales = round(sum(f["millas"] for f in del_anio if f["o_pais"] != f["d_pais"]), 2)
    return {**informe, "anios": anios, "verificacion": _verificar(informe["total"], base),
            "millas_internacionales_excluidas": internacionales}


def _verificar(en_dw, en_base):
    """Compara el total que da el DW con el que da la base: tienen que coincidir."""
    return {"dw": round(en_dw, 2), "base": round(en_base, 2), "coinciden": abs(en_dw - en_base) < 0.01}
