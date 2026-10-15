"""'Entrar como': actores de demostración y sesiones del servidor local.

El modelo no guarda credenciales (ni en `cliente` ni en `empleado`), así que no hay claves: se elige un
cliente, un agente de viaje o un aeropuerto de la lista. Es una demostración de roles, no seguridad.
Lee: cliente, agente_viaje, empleado, aeropuerto, ciudad.
"""
import secrets

from .dominios import ErrorNegocio, TIPOS_ACTOR, validar_entero
from .vuelos import listar_aeropuertos


class Sesiones:
    """Sesiones del servidor local: token en cookie -> actor (en memoria)."""

    def __init__(self):
        self._actores = {}

    def abrir(self, actor):
        """Registra al actor y devuelve su token."""
        token = secrets.token_urlsafe(24)
        self._actores[token] = actor
        return token

    def obtener(self, token):
        """Devuelve el actor del token, o None."""
        return self._actores.get(token)

    def cerrar(self, token):
        """Olvida el token."""
        self._actores.pop(token, None)


def listar_actores_demo(conexion):
    """Clientes, agentes de viaje y aeropuertos con los que se puede entrar."""
    clientes = [dict(r) for r in conexion.execute(
        "SELECT id_cliente, nombre, documento FROM cliente ORDER BY nombre")]
    agentes = [dict(r) for r in conexion.execute(
        "SELECT a.id_agente_viaje, e.nombre FROM agente_viaje a "
        "JOIN empleado e ON e.id_empleado = a.id_agente_viaje ORDER BY e.nombre")]
    return {"clientes": clientes, "agentes": agentes, "aeropuertos": listar_aeropuertos(conexion)}


def resolver_actor(conexion, tipo, id_actor):
    """Valida que el actor exista en la BD y devuelve {tipo, id, nombre}. Lanza ErrorNegocio si no."""
    if tipo not in TIPOS_ACTOR:
        raise ErrorNegocio(f"Tipo de actor desconocido: {tipo!r}.")
    id_actor = validar_entero(id_actor, "id")
    if tipo == "cliente":
        fila = conexion.execute("SELECT nombre FROM cliente WHERE id_cliente = ?", (id_actor,)).fetchone()
        nombre = fila and fila["nombre"]
    elif tipo == "agente":
        fila = conexion.execute(
            "SELECT e.nombre FROM agente_viaje a JOIN empleado e ON e.id_empleado = a.id_agente_viaje "
            "WHERE a.id_agente_viaje = ?", (id_actor,)).fetchone()
        nombre = fila and fila["nombre"]
    else:
        fila = conexion.execute(
            "SELECT a.codigo, c.nombre AS ciudad FROM aeropuerto a JOIN ciudad c ON c.id_ciudad = a.id_ciudad "
            "WHERE a.id_aeropuerto = ?", (id_actor,)).fetchone()
        nombre = fila and f"{fila['ciudad']} ({fila['codigo']})"
    if not nombre:
        raise ErrorNegocio("Ese usuario ya no existe en la base de datos.")
    return {"tipo": tipo, "id": id_actor, "nombre": nombre}
