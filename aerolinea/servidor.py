"""Adaptador HTTP: sirve la SPA y atiende /api/... sobre http.server (sesión por cookie).
El enrutado vive en aerolinea/rutas.py y lo comparte con la versión del navegador."""
import json
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from .esquema import conectar
from .rutas import construir_rutas, despachar
from .sesion import Sesiones

LIMITE_CUERPO = 1_000_000  # bytes; ninguna petición legítima del prototipo se acerca
TIPOS_MIME = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
              ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml", ".png": "image/png",
              ".jpg": "image/jpeg", ".json": "application/json; charset=utf-8"}


class Manejador(BaseHTTPRequestHandler):
    """Adaptador HTTP: archivos estáticos y API con la sesión en una cookie."""
    server_version = "DataDelta/1.0"

    def log_message(self, formato, *args):
        if not self.server.silencioso:
            super().log_message(formato, *args)

    def token_sesion(self):
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        return cookie["sesion"].value if "sesion" in cookie else None

    def _responder(self, estado, cuerpo, tipo="application/json; charset=utf-8", cookie=None):
        datos = cuerpo if isinstance(cuerpo, bytes) else json.dumps(cuerpo, ensure_ascii=False, default=str).encode()
        self.send_response(estado)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(datos)))
        self.send_header("Cache-Control", "no-store")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(datos)

    def _estatico(self, ruta):
        nombre = "index.html" if ruta in ("", "/") else ruta.lstrip("/")
        archivo = (self.server.carpeta_web / nombre).resolve()
        # Solo tipos conocidos: la BD (datos/*.db) y el código Python no se sirven en este modo.
        if (self.server.carpeta_web not in archivo.parents or not archivo.is_file()
                or archivo.suffix not in TIPOS_MIME):
            return self._responder(404, {"ok": False, "error": "No encontrado."})
        contenido = archivo.read_bytes()
        if archivo.name == "index.html":  # marca para arranque.js: hay servidor, no hace falta Pyodide
            contenido = contenido.replace(b"<!--MODO_SERVIDOR-->", b"<script>window.MODO_SERVIDOR = true;</script>")
        self._responder(200, contenido, TIPOS_MIME[archivo.suffix])

    def _api(self, metodo):
        ruta = urlparse(self.path).path
        if not ruta.startswith("/api/"):
            return self._estatico(ruta) if metodo == "GET" else self._responder(405, {"ok": False})
        try:
            largo = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._responder(400, {"ok": False, "error": "Content-Length inválido."})
        if largo < 0:
            return self._responder(400, {"ok": False, "error": "Content-Length inválido."})
        if largo > LIMITE_CUERPO:
            return self._responder(413, {"ok": False, "error": "La petición es demasiado grande."})
        crudo = self.rfile.read(largo) if largo else b""
        sesiones = self.server.sesiones
        token = self.token_sesion()
        actor = sesiones.obtener(token) if token else None
        bd = conectar(self.server.ruta_bd)
        try:
            estado, respuesta, ctx = despachar(self.server.rutas, metodo, self.path, crudo, bd, actor,
                                               self.server.resumen_esquema, "servidor")
        finally:
            bd.close()
        cookie = None
        if ctx and ctx.cambio_sesion:
            accion, actor_nuevo = ctx.cambio_sesion
            if token:
                sesiones.cerrar(token)
            if accion == "abrir":
                cookie = f"sesion={sesiones.abrir(actor_nuevo)}; Path=/; HttpOnly; SameSite=Lax"
            else:
                cookie = "sesion=; Path=/; Max-Age=0"
        self._responder(estado, respuesta, cookie=cookie)

    def do_GET(self):
        self._api("GET")

    def do_POST(self):
        self._api("POST")

    def do_PUT(self):
        self._api("PUT")

    def do_DELETE(self):
        self._api("DELETE")


def crear_servidor(host, puerto, ruta_bd, carpeta_web, resumen_esquema, silencioso=False):
    """Crea el servidor HTTP con sus rutas, sesiones y configuración."""
    servidor = ThreadingHTTPServer((host, puerto), Manejador)
    servidor.rutas = construir_rutas()
    servidor.sesiones = Sesiones()
    servidor.ruta_bd = ruta_bd
    servidor.carpeta_web = Path(carpeta_web).resolve()
    servidor.resumen_esquema = resumen_esquema
    servidor.silencioso = silencioso
    return servidor
