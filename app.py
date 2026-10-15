"""Modo servidor local: crea la BD y el DW desde los scripts de EA y levanta el portal web.

La versión publicada (GitHub Pages) no usa este archivo: index.html ejecuta el mismo paquete
aerolinea/ en el navegador con Pyodide. Este modo sirve para desarrollo y para las pruebas HTTP.

Uso:
    python app.py                    # http://127.0.0.1:8765
    python app.py --reiniciar        # borra la BD y el DW y los regenera desde los scripts
    python app.py --puerto 9000 --bd datos/otra.db
"""
import argparse
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from aerolinea import semilla  # noqa: E402
from aerolinea.esquema import conectar, crear_esquema, crear_base, verificar  # noqa: E402
from aerolinea.servidor import crear_servidor  # noqa: E402

# Los scripts que generó Enterprise Architect, tal cual; los mismos que carga la versión del navegador.
SCRIPT_LOCAL = AQUI / "sql" / "modelo-relacional-sqlserver.sql"
SCRIPT_DW = AQUI / "sql" / "modelo-dw-sqlserver.sql"


def ruta_dw_de(ruta_bd):
    """El DW es otra base de datos: un archivo junto a la base transaccional."""
    ruta_bd = Path(ruta_bd)
    return ruta_bd.with_name(ruta_bd.stem + "-dw.db")


def preparar_bd(ruta_bd, script, reiniciar=False, script_dw=SCRIPT_DW):
    """Crea (y siembra) la BD y crea el esquema del DW (vacío) si no existen, o si se pide reiniciar.
    Devuelve el resumen verificado de la base ("esquema") y del DW ("dw")."""
    ruta_bd, ruta_dw = Path(ruta_bd), ruta_dw_de(ruta_bd)
    if reiniciar:
        for archivo in (ruta_bd, ruta_dw):
            archivo.unlink(missing_ok=True)
    if not ruta_bd.exists():
        resumen = crear_base(script, ruta_bd)
        conexion = conectar(ruta_bd)
        try:
            resumen["semilla"] = semilla.sembrar(conexion)
        except Exception:
            conexion.close()
            ruta_bd.unlink()  # no dejar una BD a medio sembrar
            raise
        conexion.close()
        print(f"BD creada desde {script.name}: {resumen['tablas']} tablas, {resumen['llaves_foraneas']} FK, "
              f"{resumen['unicos']} únicos.")
        print(f"  semilla: {resumen['semilla']}")
    else:
        conexion = conectar(ruta_bd)
        resumen = verificar(conexion)
        conexion.close()
        print(f"BD existente: {ruta_bd} ({resumen['tablas']} tablas, {resumen['llaves_foraneas']} FK).")
    conexion = conectar(ruta_bd, ruta_dw)
    try:
        if verificar(conexion, "dw")["tablas"] == 0:
            resumen["dw"] = crear_esquema(conexion, Path(script_dw).read_text(encoding="utf-8"), "dw")
            print(f"DW creado desde {Path(script_dw).name}: {resumen['dw']['tablas']} tablas, "
                  f"{resumen['dw']['llaves_foraneas']} FK (vacío: se carga desde la interfaz).")
        else:
            resumen["dw"] = verificar(conexion, "dw")
    finally:
        conexion.close()
    resumen["script"] = script.name
    return resumen


def main():
    parser = argparse.ArgumentParser(description="Prototipo de Data-Delta Airlines")
    parser.add_argument("--puerto", type=int, default=int(os.environ.get("PUERTO", 8765)))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--bd", default=str(AQUI / "datos" / "aerolinea.db"))
    parser.add_argument("--script", default=None, help="ruta del script T-SQL de la base (por defecto el de EA)")
    parser.add_argument("--reiniciar", action="store_true", help="borra la BD y el DW y los regenera desde los scripts")
    parser.add_argument("--silencioso", action="store_true", help="no imprime cada petición HTTP")
    args = parser.parse_args()

    script = Path(args.script) if args.script else SCRIPT_LOCAL
    resumen = preparar_bd(args.bd, script, args.reiniciar)
    servidor = crear_servidor(args.host, args.puerto, args.bd, ruta_dw_de(args.bd), AQUI, resumen, args.silencioso)
    print(f"Portal en http://{args.host}:{args.puerto}  (Ctrl+C para salir)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
