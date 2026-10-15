"""Prueba del traductor T-SQL -> SQLite: el script de EA se aplica entero y el catálogo coincide.

Uso: python pruebas/prueba_esquema.py
"""
import sqlite3
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AQUI))

from aerolinea.esquema import conectar, crear_esquema, traducir_script  # noqa: E402

SCRIPT = AQUI / "sql" / "modelo-relacional-sqlserver.sql"
fallos = []


def comprobar(condicion, mensaje):
    print(("  ok   " if condicion else "  FALLA ") + mensaje)
    if not condicion:
        fallos.append(mensaje)


def debe_fallar(conexion, sql, parametros, mensaje):
    try:
        conexion.execute(sql, parametros)
    except sqlite3.IntegrityError:
        comprobar(True, mensaje)
    else:
        comprobar(False, mensaje)


def main():
    script = SCRIPT.read_text(encoding="utf-8")
    sentencias, declarado = traducir_script(script)
    print("Lo que declara el script:", declarado)
    comprobar(declarado["tablas"] == 26, "el script declara 26 tablas")
    comprobar(declarado["llaves_foraneas"] == 34, "el script declara 34 llaves foráneas")
    comprobar(declarado["unicos"] == 6, "el script declara 6 restricciones únicas")

    bd = conectar(":memory:")
    resumen = crear_esquema(bd, script)
    print("Lo que tiene SQLite:", resumen)
    comprobar(resumen["tablas"] == 26 and resumen["llaves_foraneas"] == 34 and resumen["unicos"] == 6,
              "el catálogo de SQLite coincide (26 tablas, 34 FK, 6 únicos)")

    print("Comportamiento de las restricciones:")
    bd.execute("INSERT INTO ciudad (nombre, pais, zona_horaria) VALUES ('A', 'P', 'Z'), ('B', 'P', 'Z')")
    comprobar([r[0] for r in bd.execute("SELECT id_ciudad FROM ciudad ORDER BY 1")] == [1, 2],
              "las llaves IDENTITY se autoincrementan")
    bd.execute("INSERT INTO aeropuerto (id_ciudad, codigo, nombre, latitud, longitud) VALUES (1,'AAA','a',0,0)")
    debe_fallar(bd, "INSERT INTO aeropuerto (id_ciudad, codigo, nombre, latitud, longitud) VALUES (1,'AAA','b',0,0)",
                (), "el código de aeropuerto repetido se rechaza (UNIQUE)")
    debe_fallar(bd, "INSERT INTO aeropuerto (id_ciudad, codigo, nombre, latitud, longitud) VALUES (99,'BBB','b',0,0)",
                (), "una ciudad inexistente se rechaza (FK)")
    debe_fallar(bd, "INSERT INTO ciudad (nombre, pais) VALUES ('C', 'P')", (), "una columna NOT NULL sin valor se rechaza")
    debe_fallar(bd, "INSERT INTO piloto (id_piloto) VALUES (7)", (), "un piloto que no es empleado se rechaza (llave compartida)")
    bd.execute("INSERT INTO empleado (nombre, documento, tipo) VALUES ('E', '1', 'piloto')")
    bd.execute("INSERT INTO piloto (id_piloto) VALUES (1)")
    debe_fallar(bd, "INSERT INTO piloto (id_piloto) VALUES (1)", (), "el mismo piloto dos veces se rechaza (PK)")
    bd.execute("INSERT INTO avion (matricula, modelo, capacidad) VALUES ('M', 'X', 10)")
    bd.execute("INSERT INTO aeropuerto (id_ciudad, codigo, nombre, latitud, longitud) VALUES (2,'BBB','b',1,1)")
    bd.execute("INSERT INTO vuelo (numero_vuelo, id_aeropuerto_origen, id_aeropuerto_destino, id_avion, "
               "salida_programada, llegada_programada) VALUES ('X1', 1, 2, 1, 'a', 'b')")
    bd.execute("INSERT INTO vuelo_piloto (id_vuelo, id_piloto) VALUES (1, 1)")
    debe_fallar(bd, "INSERT INTO vuelo_piloto (id_vuelo, id_piloto) VALUES (1, 1)", (),
                "la pareja vuelo-piloto repetida se rechaza (PK compuesta)")
    bd.execute("INSERT INTO cliente (nombre, documento, correo) VALUES ('C', 'D', 'c@x')")
    bd.execute("INSERT INTO reserva (id_cliente, id_vuelo, fecha) VALUES (1, 1, 'f')")
    bd.execute("INSERT INTO tiquete (id_reserva, valor, fecha_compra) VALUES (1, 10, 'f')")
    comprobar(bd.execute("SELECT cancelado FROM tiquete").fetchone()[0] == 0, "tiquete.cancelado vale 0 por defecto")
    debe_fallar(bd, "INSERT INTO tiquete (id_reserva, valor, fecha_compra) VALUES (1, 10, 'f')", (),
                "un segundo tiquete para la misma reserva se rechaza (UNIQUE)")

    mal = "CREATE TABLE x (a money NOT NULL)\nGO"
    try:
        traducir_script(mal)
    except ValueError:
        comprobar(True, "un tipo sin regla lanza error (no se ignora)")
    else:
        comprobar(False, "un tipo sin regla lanza error (no se ignora)")

    print("\n" + ("TODO BIEN" if not fallos else f"{len(fallos)} FALLO(S)"))
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
