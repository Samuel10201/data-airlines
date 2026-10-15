"""API del prototipo, parte independiente del transporte: tabla de rutas /api/... y su despachador.

La usan dos adaptadores con la MISMA lógica:
  - aerolinea/servidor.py: servidor local sobre http.server, sesión por cookie.
  - aerolinea/navegador.py: versión estática en el navegador (Pyodide), sesión en memoria.
"""
import json
import re
import traceback
from urllib.parse import parse_qs, urlparse

from . import aeropuerto, dw, sesion, ventas, vuelos
from .dominios import NOMBRE_AEROLINEA, ErrorNegocio, ErrorPermiso, ErrorSesion, validar_entero


def _entero_opcional(texto, campo):
    """Filtro numérico opcional de la URL: None si viene vacío; ErrorNegocio si no es un entero válido."""
    if texto in (None, ""):
        return None
    return validar_entero(texto, campo)


def construir_rutas():
    """Tabla de rutas: (método, patrón, función(ctx, **grupos))."""
    r = []

    def ruta(metodo, patron):
        def decorador(funcion):
            r.append((metodo, re.compile(f"^{patron}$"), funcion))
            return funcion
        return decorador

    @ruta("GET", "/api/info")
    def info(c):
        return {"esquema": c.resumen_esquema, "modo": c.modo, "aerolinea": NOMBRE_AEROLINEA}

    # --- sesión ("entrar como")
    @ruta("GET", "/api/demo/usuarios")
    def usuarios_demo(c):
        return sesion.listar_actores_demo(c.bd)

    @ruta("GET", "/api/sesion")
    def ver_sesion(c):
        return {"actor": c.actor}

    @ruta("POST", "/api/sesion")
    def entrar(c):
        actor = sesion.resolver_actor(c.bd, c.cuerpo.get("tipo"), c.cuerpo.get("id"))
        c.abrir_sesion(actor)
        return {"actor": actor, "mensaje": f"Entró como {actor['nombre']}."}

    @ruta("DELETE", "/api/sesion")
    def salir(c):
        c.cerrar_sesion()
        return {"mensaje": "Sesión cerrada."}

    # --- vuelos (públicos)
    @ruta("GET", "/api/aeropuertos")
    def aeropuertos(c):
        return {"aeropuertos": vuelos.listar_aeropuertos(c.bd)}

    @ruta("GET", "/api/vuelos")
    def buscar(c):
        return vuelos.buscar_vuelos(c.bd, _entero_opcional(c.consulta.get("origen"), "origen"),
                                    _entero_opcional(c.consulta.get("destino"), "destino"),
                                    c.consulta.get("fecha") or None)

    @ruta("GET", r"/api/vuelos/(?P<id>\d+)")
    def detalle(c, id):
        return vuelos.detalle_vuelo(c.bd, validar_entero(id, "id"))

    # --- recorrido A: reservar, comprar, cancelar
    @ruta("GET", "/api/reservas")
    def reservas(c):
        return ventas.mis_reservas(c.bd, c.actor)

    @ruta("POST", "/api/reservas")
    def reservar(c):
        return ventas.crear_reserva(c.bd, c.actor, c.cuerpo.get("id_vuelo"), c.cuerpo.get("id_cliente"))

    @ruta("POST", r"/api/reservas/(?P<id>\d+)/tiquete")
    def comprar(c, id):
        return ventas.comprar_tiquete(c.bd, c.actor, validar_entero(id, "id"))

    @ruta("POST", r"/api/tiquetes/(?P<id>\d+)/cancelar")
    def cancelar(c, id):
        return ventas.cancelar_tiquete(c.bd, c.actor, validar_entero(id, "id"))

    # --- recorrido B: abordaje, equipaje, escaneos
    @ruta("GET", "/api/tiquetes")
    def tiquetes(c):
        return aeropuerto.tiquetes_del_aeropuerto(c.bd, c.actor, _entero_opcional(c.consulta.get("vuelo"), "vuelo"))

    @ruta("POST", r"/api/tiquetes/(?P<id>\d+)/abordaje")
    def abordar(c, id):
        return aeropuerto.registrar_abordaje(c.bd, c.actor, validar_entero(id, "id"))

    @ruta("POST", r"/api/tiquetes/(?P<id>\d+)/equipaje")
    def recibir_maleta(c, id):
        return aeropuerto.registrar_equipaje(c.bd, c.actor, validar_entero(id, "id"), c.cuerpo.get("peso_kg"))

    @ruta("POST", r"/api/equipaje/(?P<id>\d+)/escaneos")
    def escanear(c, id):
        return aeropuerto.escanear_equipaje(c.bd, c.actor, validar_entero(id, "id"))

    @ruta("GET", "/api/equipaje")
    def rastrear(c):
        return aeropuerto.consultar_equipaje(c.bd, c.consulta.get("etiqueta"))

    # --- recorrido C: Data Warehouse
    @ruta("GET", "/api/dw")
    def estado_del_dw(c):
        return dw.estado_dw(c.bd)

    @ruta("POST", "/api/dw/cargar")
    def cargar_el_dw(c):
        return dw.cargar_dw(c.bd)

    @ruta("GET", "/api/dw/ingresos")
    def ingresos(c):
        return dw.reporte_ingresos(c.bd, _entero_opcional(c.consulta.get("anio"), "anio"))

    @ruta("GET", "/api/dw/reservaciones")
    def reservaciones(c):
        return dw.reporte_reservaciones(c.bd, _entero_opcional(c.consulta.get("anio"), "anio"))

    @ruta("GET", "/api/dw/millas")
    def millas(c):
        return dw.reporte_millas(c.bd, _entero_opcional(c.consulta.get("anio"), "anio"))

    return r


class Contexto:
    """Datos de una petición que reciben las rutas, independientes del transporte.
    La ruta abre o cierra la sesión con abrir_sesion/cerrar_sesion; el adaptador
    (cookie en HTTP, memoria en el navegador) aplica el cambio leyendo `cambio_sesion`."""

    def __init__(self, bd, cuerpo, consulta, actor, resumen_esquema, modo):
        self.bd, self.cuerpo, self.consulta = bd, cuerpo, consulta
        self.actor, self.resumen_esquema, self.modo = actor, resumen_esquema, modo
        self.cambio_sesion = None  # None | ("abrir", actor) | ("cerrar", None)

    def abrir_sesion(self, actor):
        self.actor = actor
        self.cambio_sesion = ("abrir", actor)

    def cerrar_sesion(self):
        self.actor = None
        self.cambio_sesion = ("cerrar", None)


def leer_cuerpo(crudo):
    """Convierte el cuerpo de la petición (bytes o str con JSON) en dict."""
    if not crudo:
        return {}
    try:
        cuerpo = json.loads(crudo)
    except ValueError:
        raise ErrorNegocio("JSON inválido.") from None
    if not isinstance(cuerpo, dict):
        raise ErrorNegocio("El cuerpo de la petición debe ser un objeto JSON.")
    return cuerpo


def despachar(rutas, metodo, url, crudo, bd, actor, resumen_esquema, modo="servidor"):
    """Busca la ruta, la ejecuta y devuelve (código HTTP, respuesta JSON, contexto o None).
    ErrorNegocio -> 400, ErrorSesion -> 401, ErrorPermiso -> 403, sin ruta -> 404,
    cualquier otra excepción -> 500 con la traza en consola (nunca en silencio)."""
    partes = urlparse(url)
    consulta = {k: v[0] for k, v in parse_qs(partes.query).items()}
    try:
        cuerpo = leer_cuerpo(crudo)
    except ErrorNegocio as e:
        return 400, {"ok": False, "error": str(e)}, None
    for verbo, patron, funcion in rutas:
        coincide = patron.match(partes.path)
        if verbo == metodo and coincide:
            ctx = Contexto(bd, cuerpo, consulta, actor, resumen_esquema, modo)
            try:
                return 200, {"ok": True, **funcion(ctx, **coincide.groupdict())}, ctx
            except ErrorNegocio as e:
                return 400, {"ok": False, "error": str(e)}, ctx
            except ErrorSesion as e:
                return 401, {"ok": False, "error": str(e)}, ctx
            except ErrorPermiso as e:
                return 403, {"ok": False, "error": str(e)}, ctx
            except Exception:  # noqa: BLE001 — se registra y se informa, nunca en silencio
                traceback.print_exc()
                return 500, {"ok": False, "error": "Ocurrió un error interno; revise la consola."}, ctx
    return 404, {"ok": False, "error": "Ruta no encontrada."}, None
