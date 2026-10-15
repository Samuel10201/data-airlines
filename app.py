"""Modo servidor local: crea la BD desde el script de EA y levanta el portal web.

La versión publicada (GitHub Pages) no usa este archivo: index.html ejecuta el mismo paquete
aerolinea/ en el navegador con Pyodide. Este modo sirve para desarrollo y para las pruebas HTTP.

Uso:
    python app.py                    # http://127.0.0.1:8765
    python app.py --reiniciar        # borra la BD y la regenera desde el script
    python app.py --puerto 9000 --bd datos/otra.db
"""
import argparse
import os
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))

from aerolinea import semilla  # noqa: E402
from aerolinea.esquema import conectar, crear_base, verificar  # noqa: E402
from aerolinea.servidor import crear_servidor  # noqa: E402

# El script que generó Enterprise Architect, tal cual; el mismo que carga la versión del navegador.
SCRIPT_LOCAL = AQUI / "sql" / "modelo-relacional-sqlserver.sql"


def preparar_bd(ruta_bd, script, reiniciar=False):
    """Crea (y siembra) la BD si no existe o si se pide reiniciar. Devuelve el resumen verificado."""
    ruta_bd = Path(ruta_bd)
    if reiniciar and ruta_bd.exists():
        ruta_bd.unlink()
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
        print(f"BD existente: {ruta_bd} ({resumen['tablas']} tablas, {resumen['llaves_foraneas']} FK). "
              "Use --reiniciar para regenerarla.")
    resumen["script"] = script.name
    return resumen


def main():
    parser = argparse.ArgumentParser(description="Prototipo de Data-Delta Airlines")
    parser.add_argument("--puerto", type=int, default=int(os.environ.get("PUERTO", 8765)))
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--bd", default=str(AQUI / "datos" / "aerolinea.db"))
    parser.add_argument("--script", default=None, help="ruta del script T-SQL (por defecto el de EA)")
    parser.add_argument("--reiniciar", action="store_true", help="borra la BD y la regenera desde el script")
    parser.add_argument("--silencioso", action="store_true", help="no imprime cada petición HTTP")
    args = parser.parse_args()

    script = Path(args.script) if args.script else SCRIPT_LOCAL
    resumen = preparar_bd(args.bd, script, args.reiniciar)
    servidor = crear_servidor(args.host, args.puerto, args.bd, AQUI, resumen, args.silencioso)
    print(f"Portal en http://{args.host}:{args.puerto}  (Ctrl+C para salir)")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        print("\nServidor detenido.")
    finally:
        servidor.server_close()


if __name__ == "__main__":
    main()
