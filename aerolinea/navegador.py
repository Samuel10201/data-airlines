"""Adaptador del navegador: la versión estática (GitHub Pages) corre este módulo en Pyodide.

Reemplaza a http.server sin tocar la lógica: la BD SQLite vive en memoria, la sesión es un atributo del
portal (memoria de la pestaña, sin cookie) y cada petición /api/... que intercepta el JavaScript pasa por
el MISMO despachador y la MISMA tabla de rutas de aerolinea/rutas.py. Tras cada petición que escribe,
la BD se serializa (sqlite3 serialize) en base64 para que el JavaScript la guarde en localStorage.
"""
import base64
import json

from . import semilla
from .dominios import ahora_actual
from .esquema import conectar, crear_esquema, verificar
from .rutas import construir_rutas, despachar

VUELOS_FUTUROS_MINIMOS = 6  # con menos, la BD guardada "caducó" y se vuelve a sembrar con fechas nuevas


class PortalNavegador:
    """Una BD en memoria + la sesión del usuario de esta pestaña."""

    def __init__(self, script_sql, bd_guardada=None):
        """Restaura la BD guardada (base64) o la crea desde el script T-SQL y la siembra."""
        self.rutas = construir_rutas()
        self.actor = None
        self.script = script_sql
        self.restaurada = False
        self.aviso = None
        self.conexion = conectar(":memory:")
        if bd_guardada:
            try:
                self._restaurar(bd_guardada)
                self.restaurada = True
            except Exception as e:  # noqa: BLE001 — se informa y se vuelve a la semilla
                self.aviso = f"No se pudo restaurar la BD guardada ({e}); se regeneró desde el script."
                print(self.aviso)
                self.conexion.close()
                self.conexion = conectar(":memory:")
        if not self.restaurada:
            self.resumen = crear_esquema(self.conexion, script_sql)
            self.resumen["semilla"] = semilla.sembrar(self.conexion)
        else:
            self.resumen = verificar(self.conexion)
        self.resumen["script"] = "modelo-relacional-sqlserver.sql"

    def _restaurar(self, bd_base64):
        self.conexion.deserialize(base64.b64decode(bd_base64))
        self.conexion.execute("PRAGMA foreign_keys = ON")
        resumen = verificar(self.conexion)
        if resumen["tablas"] != 26:
            raise ValueError(f"la BD guardada tiene {resumen['tablas']} tablas")
        futuros = self.conexion.execute("SELECT COUNT(*) FROM vuelo WHERE salida_programada > ?",
                                        (ahora_actual(),)).fetchone()[0]
        if futuros < VUELOS_FUTUROS_MINIMOS:
            raise ValueError("los vuelos guardados ya pasaron; se generan fechas nuevas")

    def atender(self, metodo, url, cuerpo):
        """Atiende una petición /api/... y devuelve JSON: {estado, respuesta, bd?}.
        `bd` (base64) solo viene cuando la petición cambió datos, para guardarla."""
        cambios_antes = self.conexion.total_changes
        estado, respuesta, ctx = despachar(self.rutas, metodo.upper(), url, cuerpo or "", self.conexion,
                                           self.actor, self.resumen, "navegador")
        if ctx and ctx.cambio_sesion:
            self.actor = ctx.cambio_sesion[1]
        salida = {"estado": estado, "respuesta": respuesta}
        if self.conexion.total_changes != cambios_antes:
            salida["bd"] = self.serializar()
        return json.dumps(salida, ensure_ascii=False, default=str)

    def serializar(self):
        """La BD completa en base64 (sqlite3.Connection.serialize, Python 3.11+)."""
        return base64.b64encode(self.conexion.serialize()).decode("ascii")


def crear_portal(script_sql, bd_guardada=None):
    """Punto de entrada que llama el JavaScript de arranque."""
    return PortalNavegador(script_sql, bd_guardada or None)
