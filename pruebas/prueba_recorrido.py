"""Prueba de los dos recorridos por HTTP, incluidos los rechazos. Levanta su propio servidor sobre una BD
temporal (no necesita consolas aparte ni toca datos/).

Uso: python pruebas/prueba_recorrido.py
"""
import json
import sqlite3
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

AQUI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AQUI))
sys.stdout.reconfigure(encoding="utf-8")

from aerolinea.servidor import crear_servidor  # noqa: E402
from app import SCRIPT_LOCAL, preparar_bd  # noqa: E402

fallos = []
total = [0]


class Sesion:
    """Un navegador con su propia cookie de sesión."""

    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

    def pedir(self, metodo, ruta, cuerpo=None):
        datos = json.dumps(cuerpo).encode() if cuerpo is not None else None
        peticion = urllib.request.Request(self.base + ruta, data=datos, method=metodo,
                                          headers={"Content-Type": "application/json"})
        try:
            with self.opener.open(peticion) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def entrar(self, tipo, id_actor):
        estado, _ = self.pedir("POST", "/api/sesion", {"tipo": tipo, "id": id_actor})
        assert estado == 200, f"no se pudo entrar como {tipo} {id_actor}"
        return self


def comprobar(condicion, mensaje):
    total[0] += 1
    print(("  ok   " if condicion else "  FALLA ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


def esperar(sesion, metodo, ruta, cuerpo, estado_esperado, mensaje, contiene=None):
    """Hace la petición y comprueba el código HTTP (y, si se pide, que el error contenga un texto)."""
    estado, resp = sesion.pedir(metodo, ruta, cuerpo)
    bien = estado == estado_esperado and (contiene is None or contiene.lower() in json.dumps(resp, ensure_ascii=False).lower())
    comprobar(bien, f"{mensaje} [{estado}]" + ("" if bien else f" -> {resp}"))
    return resp


def main():
    carpeta = tempfile.mkdtemp(prefix="delta-prueba-")
    ruta_bd = Path(carpeta) / "prueba.db"
    resumen = preparar_bd(ruta_bd, SCRIPT_LOCAL)
    servidor = crear_servidor("127.0.0.1", 0, ruta_bd, AQUI, resumen, silencioso=True)
    threading.Thread(target=servidor.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{servidor.server_address[1]}"
    publico = Sesion(base)

    print("\nInformación y acceso")
    info = esperar(publico, "GET", "/api/info", None, 200, "GET /api/info responde")
    e = info["esquema"]
    comprobar((e["tablas"], e["llaves_foraneas"], e["unicos"]) == (26, 34, 6), "la BD en ejecución tiene 26 tablas, 34 FK y 6 únicos")
    esperar(publico, "GET", "/api/reservas", None, 401, "sin sesión, /api/reservas devuelve 401")
    esperar(publico, "POST", "/api/sesion", {"tipo": "cliente", "id": 9999}, 400, "entrar como un cliente inexistente se rechaza")
    esperar(publico, "POST", "/api/sesion", {"tipo": "gerente", "id": 1}, 400, "entrar con un tipo desconocido se rechaza")
    usuarios = publico.pedir("GET", "/api/demo/usuarios")[1]
    clientes, agentes, aeropuertos = usuarios["clientes"], usuarios["agentes"], usuarios["aeropuertos"]
    comprobar(len(clientes) >= 3 and agentes and len(aeropuertos) == 8, "hay actores de demostración (clientes, agentes, 8 aeropuertos)")

    print("\nRecorrido A: buscar, reservar, comprar, cancelar")
    ana = Sesion(base).entrar("cliente", clientes[0]["id_cliente"])
    otro = Sesion(base).entrar("cliente", clientes[1]["id_cliente"])
    vuelos = publico.pedir("GET", "/api/vuelos")[1]["vuelos"]
    comprobar(len(vuelos) >= 10, f"la búsqueda sin filtros trae vuelos futuros ({len(vuelos)})")
    lejano = vuelos[-1]
    primero = vuelos[0]
    filtrado = publico.pedir("GET", f"/api/vuelos?origen={lejano['origen']['id_aeropuerto']}&destino={lejano['destino']['id_aeropuerto']}")[1]["vuelos"]
    comprobar(filtrado and all(v["origen"]["id_aeropuerto"] == lejano["origen"]["id_aeropuerto"] for v in filtrado), "el filtro por origen y destino funciona")
    esperar(publico, "GET", "/api/vuelos?fecha=hoy", None, 400, "una fecha mal escrita se rechaza")
    detalle = esperar(publico, "GET", f"/api/vuelos/{lejano['id_vuelo']}", None, 200, "detalle de vuelo")["vuelo"]
    comprobar(len(detalle["pilotos"]) == 2 and len(detalle["tcp"]) == 3, "el detalle muestra 2 pilotos y 3 TCP")
    comprobar(lejano["millas"] > 0 and lejano["valor"] > 45, "el valor del tiquete sale de las millas")
    nacional = {v["nacional"] for v in vuelos}
    comprobar(nacional == {True, False}, "hay vuelos nacionales e internacionales")

    esperar(ana, "POST", "/api/reservas", {"id_vuelo": lejano["id_vuelo"], "id_cliente": clientes[1]["id_cliente"]}, 403, "un cliente no puede reservar para otro")
    reserva = esperar(ana, "POST", "/api/reservas", {"id_vuelo": lejano["id_vuelo"]}, 200, "el cliente reserva un vuelo")["reserva"]
    comprobar(reserva["estado"] == "reservada" and reserva["tiquete"] is None, "la reserva nueva no tiene tiquete")
    esperar(ana, "POST", "/api/reservas", {"id_vuelo": lejano["id_vuelo"]}, 400, "no se repite la reserva viva del mismo vuelo", "ya existe")
    esperar(otro, "POST", f"/api/reservas/{reserva['id_reserva']}/tiquete", None, 403, "otro cliente no puede comprar esa reserva")
    compra = esperar(ana, "POST", f"/api/reservas/{reserva['id_reserva']}/tiquete", None, 200, "el cliente compra el tiquete")["reserva"]
    comprobar(compra["tiquete"]["valor"] == lejano["valor"] and compra["estado"] == "comprado", "el tiquete guarda el valor calculado")
    esperar(ana, "POST", f"/api/reservas/{reserva['id_reserva']}/tiquete", None, 400, "no se compra dos veces la misma reserva", "ya tiene tiquete")
    id_tiquete = compra["tiquete"]["id_tiquete"]
    mias = esperar(ana, "GET", "/api/reservas", None, 200, "mis reservas")["reservas"]
    comprobar(any(r["id_reserva"] == reserva["id_reserva"] for r in mias), "la compra aparece en mis reservas")

    esperar(otro, "POST", f"/api/tiquetes/{id_tiquete}/cancelar", None, 403, "otro cliente no puede cancelar ese tiquete")
    esperar(ana, "POST", f"/api/tiquetes/{id_tiquete}/cancelar", None, 200, "el cliente cancela su tiquete")
    esperar(ana, "POST", f"/api/tiquetes/{id_tiquete}/cancelar", None, 400, "no se cancela dos veces", "ya está cancelado")
    nueva = esperar(ana, "POST", "/api/reservas", {"id_vuelo": lejano["id_vuelo"]}, 200, "tras cancelar se puede reservar de nuevo")["reserva"]
    compra2 = esperar(ana, "POST", f"/api/reservas/{nueva['id_reserva']}/tiquete", None, 200, "y comprar el nuevo tiquete")["reserva"]
    id_tiquete = compra2["tiquete"]["id_tiquete"]

    # clientes sin reserva en el primer vuelo (la semilla ya reservó a varios)
    bd_prueba = sqlite3.connect(ruta_bd)
    libres = [r[0] for r in bd_prueba.execute(
        "SELECT id_cliente FROM cliente WHERE id_cliente NOT IN (SELECT id_cliente FROM reserva WHERE id_vuelo = ?) "
        "ORDER BY id_cliente", (primero["id_vuelo"],))]
    bd_prueba.close()
    comprobar(len(libres) >= 2, f"hay al menos 2 clientes libres en el primer vuelo ({len(libres)})")
    agente = Sesion(base).entrar("agente", agentes[0]["id_agente_viaje"])
    esperar(agente, "POST", "/api/reservas", {"id_vuelo": primero["id_vuelo"]}, 400, "el agente debe indicar el cliente")
    r_ag = esperar(agente, "POST", "/api/reservas", {"id_vuelo": primero["id_vuelo"], "id_cliente": libres[0]}, 200, "el agente reserva a nombre de un cliente")["reserva"]
    comprobar(r_ag["gestionada_por"] == agentes[0]["id_agente_viaje"], "la reserva queda gestionada por el agente")
    esperar(Sesion(base).entrar("cliente", libres[0]), "POST", f"/api/reservas/{r_ag['id_reserva']}/tiquete", None, 200, "el cliente titular también puede comprarla")
    esperar(Sesion(base).entrar("agente", agentes[1]["id_agente_viaje"]), "POST", f"/api/tiquetes/1/cancelar", None, 403, "un agente no cancela tiquetes que no gestiona")

    pasado = sqlite3.connect(ruta_bd).execute("SELECT id_vuelo FROM vuelo WHERE salida_programada < datetime('now','localtime') LIMIT 1").fetchone()[0]
    esperar(ana, "POST", "/api/reservas", {"id_vuelo": pasado}, 400, "no se reserva un vuelo que ya salió", "ya salió")
    esperar(Sesion(base).entrar("aeropuerto", aeropuertos[0]["id_aeropuerto"]), "POST", "/api/reservas", {"id_vuelo": lejano["id_vuelo"]}, 403, "el personal de aeropuerto no reserva")

    # vuelo lleno: se ajusta la capacidad del avión directamente en la BD de prueba
    conexion = sqlite3.connect(ruta_bd)
    vendidos = conexion.execute("SELECT COUNT(*) FROM tiquete t JOIN reserva r ON r.id_reserva=t.id_reserva WHERE r.id_vuelo=? AND t.cancelado=0", (primero["id_vuelo"],)).fetchone()[0]
    conexion.execute("UPDATE avion SET capacidad = ? WHERE id_avion = (SELECT id_avion FROM vuelo WHERE id_vuelo = ?)", (vendidos, primero["id_vuelo"]))
    conexion.commit()
    conexion.close()
    sin_reserva = Sesion(base).entrar("cliente", libres[1])
    r_lleno = esperar(sin_reserva, "POST", "/api/reservas", {"id_vuelo": primero["id_vuelo"]}, 200, "se puede reservar un vuelo lleno (el cupo se ocupa al comprar)")["reserva"]
    esperar(sin_reserva, "POST", f"/api/reservas/{r_lleno['id_reserva']}/tiquete", None, 400, "no se compra en un vuelo lleno", "lleno")

    print("\nRecorrido B: abordaje, equipaje y escaneos")
    origen_id, destino_id = lejano["origen"]["id_aeropuerto"], lejano["destino"]["id_aeropuerto"]
    ajeno_id = next(a["id_aeropuerto"] for a in aeropuertos if a["id_aeropuerto"] not in (origen_id, destino_id))
    en_origen = Sesion(base).entrar("aeropuerto", origen_id)
    en_destino = Sesion(base).entrar("aeropuerto", destino_id)
    en_ajeno = Sesion(base).entrar("aeropuerto", ajeno_id)
    esperar(ana, "POST", f"/api/tiquetes/{id_tiquete}/abordaje", None, 403, "un cliente no registra abordajes")
    esperar(en_destino, "POST", f"/api/tiquetes/{id_tiquete}/abordaje", None, 403, "el abordaje solo se hace en el aeropuerto de origen")
    listado = esperar(en_origen, "GET", "/api/tiquetes", None, 200, "el aeropuerto lista sus tiquetes")["tiquetes"]
    comprobar(isinstance(listado, list), "el listado del aeropuerto es una lista")
    esperar(en_origen, "POST", f"/api/tiquetes/{id_tiquete}/equipaje", {"peso_kg": 99}, 400, "una maleta de 99 kg se rechaza", "máximo")
    esperar(en_origen, "POST", f"/api/tiquetes/{id_tiquete}/equipaje", {"peso_kg": "abc"}, 400, "un peso que no es número se rechaza")
    m1 = esperar(en_origen, "POST", f"/api/tiquetes/{id_tiquete}/equipaje", {"peso_kg": 18.5}, 200, "se recibe una maleta")["equipaje"]
    comprobar(m1["etiqueta"] == f"DL{id_tiquete:05d}-1", "la etiqueta se genera sola")
    m2 = esperar(en_origen, "POST", f"/api/tiquetes/{id_tiquete}/equipaje", {"peso_kg": 10}, 200, "se recibe la segunda maleta")["equipaje"]
    esperar(en_origen, "POST", f"/api/tiquetes/{id_tiquete}/equipaje", {"peso_kg": 5}, 200, "se recibe la tercera maleta")
    esperar(en_origen, "POST", f"/api/tiquetes/{id_tiquete}/equipaje", {"peso_kg": 5}, 400, "la cuarta maleta se rechaza", "máximo")

    esperar(en_origen, "POST", f"/api/equipaje/{m1['id_equipaje']}/escaneos", None, 400, "la maleta ya fue leída en el origen al recibirla", "ya fue leída")
    esperar(en_destino, "POST", f"/api/equipaje/{m1['id_equipaje']}/escaneos", None, 400, "sin abordaje, la maleta no puede leerse en el destino", "no abordó")
    esperar(en_ajeno, "POST", f"/api/equipaje/{m1['id_equipaje']}/escaneos", None, 403, "un aeropuerto fuera del trayecto no la lee")
    esperar(en_origen, "POST", f"/api/tiquetes/{id_tiquete}/abordaje", None, 200, "el aeropuerto de origen registra el abordaje")
    esperar(en_origen, "POST", f"/api/tiquetes/{id_tiquete}/abordaje", None, 400, "no se aborda dos veces", "ya abordó")
    esperar(ana, "POST", f"/api/tiquetes/{id_tiquete}/cancelar", None, 400, "con abordaje hecho, el tiquete no se cancela", "abordó")
    lecturas = esperar(en_destino, "POST", f"/api/equipaje/{m1['id_equipaje']}/escaneos", None, 200, "el destino lee la maleta tras el abordaje")["escaneos"]
    comprobar(len(lecturas) == 2, "la maleta tiene 2 lecturas (origen y destino)")
    esperar(en_destino, "POST", f"/api/equipaje/{m1['id_equipaje']}/escaneos", None, 400, "no se lee dos veces seguidas en el mismo aeropuerto", "ya fue leída")

    ubicacion = esperar(publico, "GET", f"/api/equipaje?etiqueta={m1['etiqueta'].lower()}", None, 200, "se rastrea una maleta por su etiqueta (sin importar mayúsculas)")["maleta"]
    comprobar(ubicacion["estado"].startswith("Llegó a") and len(ubicacion["escaneos"]) == 2, "el rastreo dice que llegó al destino")
    pendiente = esperar(publico, "GET", f"/api/equipaje?etiqueta={m2['etiqueta']}", None, 200, "se rastrea la maleta que aún no llegó")["maleta"]
    comprobar("a la espera del vuelo" in pendiente["estado"] or "tránsito" in pendiente["estado"], f"la otra maleta aún no llegó ({pendiente['estado']})")
    esperar(publico, "GET", "/api/equipaje?etiqueta=XX999", None, 400, "una etiqueta inexistente se rechaza", "no hay ninguna")
    esperar(publico, "GET", "/api/equipaje", None, 400, "sin etiqueta se pide la etiqueta")

    # tiquete cancelado: ni abordaje ni maletas
    cancelado = esperar(ana, "POST", "/api/reservas", {"id_vuelo": vuelos[3]["id_vuelo"]}, 200, "reserva de un tercer vuelo")["reserva"]
    t3 = esperar(ana, "POST", f"/api/reservas/{cancelado['id_reserva']}/tiquete", None, 200, "compra del tercer tiquete")["reserva"]["tiquete"]["id_tiquete"]
    esperar(ana, "POST", f"/api/tiquetes/{t3}/cancelar", None, 200, "se cancela el tercer tiquete")
    esperar(Sesion(base).entrar("aeropuerto", vuelos[3]["origen"]["id_aeropuerto"]), "POST", f"/api/tiquetes/{t3}/abordaje", None, 400, "un tiquete cancelado no aborda", "cancelado")

    print("\nCierre de sesión")
    esperar(ana, "DELETE", "/api/sesion", None, 200, "se cierra la sesión")
    esperar(ana, "GET", "/api/reservas", None, 401, "después de salir, /api/reservas vuelve a pedir sesión")

    servidor.shutdown()
    print(f"\n{total[0]} comprobaciones: " + ("TODO BIEN" if not fallos else f"{len(fallos)} FALLO(S)"))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
