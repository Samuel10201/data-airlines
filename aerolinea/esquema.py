"""Traducción automática del script T-SQL (generado desde Enterprise Architect) a SQLite.

El prototipo no declara tablas propias: todo sale de `sql/modelo-relacional-sqlserver.sql`.
Reglas de traducción (se repiten en el README):
  1. Se quitan los comentarios `/* */` y los corchetes `[ ]`; el script se parte en lotes por `GO`.
  2. Los lotes `IF EXISTS ... DROP` se omiten (la BD siempre se crea desde cero).
  3. `int NOT NULL IDENTITY (1, 1)` pasa a `INTEGER PRIMARY KEY AUTOINCREMENT` y se omite la PK
     de una sola columna que lo repetía.
  4. Tipos: int y bit -> INTEGER; datetime -> TEXT (ISO 8601); varchar, char y decimal se conservan.
  5. `ALTER TABLE ... ADD CONSTRAINT` (PK, UNIQUE y FK) se incorpora como restricción DENTRO del
     CREATE TABLE, porque SQLite no admite `ALTER TABLE ADD CONSTRAINT`.
  6. `CREATE NONCLUSTERED INDEX` pasa a `CREATE INDEX`; se quitan CLUSTERED, NONCLUSTERED, ASC.
  7. Toda sentencia sin regla lanza error: nada se ignora en silencio. Al terminar, el catálogo de
     SQLite se compara con lo que el script declaraba (tablas, FK, únicos).
"""
import re
import sqlite3
from pathlib import Path

RE_COMENTARIO = re.compile(r"/\*.*?\*/", re.S)
RE_GO = re.compile(r"^\s*GO\s*$", re.M | re.I)
RE_CREATE = re.compile(r"^CREATE TABLE (\w+)\s*\((.*)\)$", re.S | re.I)
RE_PK = re.compile(r"^ALTER TABLE (\w+)\s+ADD CONSTRAINT (\w+)\s+PRIMARY KEY CLUSTERED\s*\((.*)\)$", re.S | re.I)
RE_UNICO = re.compile(r"^ALTER TABLE (\w+)\s+ADD CONSTRAINT (\w+)\s+UNIQUE NONCLUSTERED\s*\((.*)\)$", re.S | re.I)
RE_FK = re.compile(
    r"^ALTER TABLE (\w+)\s+ADD CONSTRAINT (\w+)\s+FOREIGN KEY\s*\((.*?)\)\s*REFERENCES (\w+)\s*\((.*?)\)\s*"
    r"ON DELETE (No Action|Cascade|Set Null|Restrict)\s*ON UPDATE (No Action|Cascade|Set Null|Restrict)$",
    re.S | re.I)
RE_INDICE = re.compile(r"^CREATE NONCLUSTERED INDEX (\w+)\s+ON (\w+)\s*\((.*)\)$", re.S | re.I)
RE_COLUMNA = re.compile(
    r"^(\w+)\s+(\w+)(\s*\([\d\s,]+\))?\s+(NOT NULL|NULL)(\s+IDENTITY\s*\(\s*1\s*,\s*1\s*\))?(?:\s+DEFAULT\s+(.+))?$",
    re.I)
TIPOS = {"int": "INTEGER", "bit": "INTEGER", "datetime": "TEXT", "varchar": "VARCHAR", "char": "CHAR",
         "decimal": "DECIMAL"}


def _lotes(script):
    """Quita comentarios y corchetes y parte el script en lotes por `GO`."""
    limpio = RE_COMENTARIO.sub("", script).replace("[", "").replace("]", "")
    return [lote.strip() for lote in RE_GO.split(limpio) if lote.strip()]


def _columnas(lista):
    """`a ASC,b ASC` -> `a, b`."""
    return ", ".join(re.sub(r"\s+(ASC|DESC)$", "", c.strip(), flags=re.I) for c in lista.split(","))


def _traducir_columna(linea):
    """Devuelve (nombre, definición SQLite, es_identidad) a partir de una línea del CREATE TABLE."""
    m = RE_COLUMNA.match(linea)
    if not m:
        raise ValueError(f"Columna sin regla de traducción: {linea}")
    nombre, tipo, medida, nulidad, identidad, defecto = m.groups()
    if tipo.lower() not in TIPOS:
        raise ValueError(f"Tipo sin regla de traducción: {tipo} (columna {nombre})")
    if identidad:
        return nombre, f"{nombre} INTEGER PRIMARY KEY AUTOINCREMENT", True
    partes = [nombre, TIPOS[tipo.lower()] + (medida or "").replace(" ", ""), nulidad.upper()]
    if defecto:
        partes.append("DEFAULT " + defecto.strip())
    return nombre, " ".join(partes), False


def traducir_script(script):
    """Devuelve (sentencias SQLite, resumen de lo que el script declara)."""
    tablas, orden, identidad, pks, unicos, fks, indices, omitidos = {}, [], {}, {}, {}, {}, [], 0
    for lote in _lotes(script):
        if lote.upper().startswith("IF EXISTS"):
            omitidos += 1
        elif m := RE_CREATE.match(lote):
            tabla = m.group(1)
            lineas = [l.strip().rstrip(",") for l in m.group(2).strip().splitlines() if l.strip()]
            columnas = [_traducir_columna(l) for l in lineas]
            tablas[tabla] = [c[1] for c in columnas]
            identidad[tabla] = next((c[0] for c in columnas if c[2]), None)
            orden.append(tabla)
        elif m := RE_PK.match(lote):
            pks[m.group(1)] = (m.group(2), _columnas(m.group(3)))
        elif m := RE_UNICO.match(lote):
            unicos.setdefault(m.group(1), []).append((m.group(2), _columnas(m.group(3))))
        elif m := RE_FK.match(lote):
            tabla, nombre, col, padre, colp, borrar, actualizar = m.groups()
            fks.setdefault(tabla, []).append(
                f"CONSTRAINT {nombre} FOREIGN KEY ({_columnas(col)}) REFERENCES {padre} ({_columnas(colp)}) "
                f"ON DELETE {borrar.upper()} ON UPDATE {actualizar.upper()}")
        elif m := RE_INDICE.match(lote):
            indices.append(f"CREATE INDEX {m.group(1)} ON {m.group(2)} ({_columnas(m.group(3))})")
        else:
            raise ValueError(f"Sentencia del script sin regla de traducción: {lote[:90]!r}")

    sentencias = []
    for tabla in orden:
        definiciones = list(tablas[tabla])
        nombre_pk, cols_pk = pks.get(tabla, (None, None))
        if cols_pk is None:
            raise ValueError(f"La tabla {tabla} no tiene llave primaria en el script.")
        if identidad[tabla] is None:
            definiciones.append(f"CONSTRAINT {nombre_pk} PRIMARY KEY ({cols_pk})")
        elif cols_pk != identidad[tabla]:
            raise ValueError(f"La llave primaria de {tabla} no coincide con su columna IDENTITY.")
        definiciones += [f"CONSTRAINT {n} UNIQUE ({c})" for n, c in unicos.get(tabla, [])]
        definiciones += fks.get(tabla, [])
        sentencias.append(f"CREATE TABLE {tabla} (\n    " + ",\n    ".join(definiciones) + "\n)")
    sentencias += indices
    declarado = {"tablas": len(orden), "llaves_foraneas": sum(len(v) for v in fks.values()),
                 "unicos": sum(len(v) for v in unicos.values()), "indices": len(indices),
                 "lotes_omitidos": omitidos}
    return sentencias, declarado


def verificar(conexion):
    """Lee el catálogo de SQLite y cuenta tablas, llaves foráneas, restricciones únicas e índices."""
    tablas = [r[0] for r in conexion.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    fks = sum(len(conexion.execute(f"PRAGMA foreign_key_list({t})").fetchall()) for t in tablas)
    unicos = sum(1 for t in tablas for i in conexion.execute(f"PRAGMA index_list({t})") if i[3] == "u")
    indices = conexion.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='index' AND sql IS NOT NULL").fetchone()[0]
    return {"tablas": len(tablas), "llaves_foraneas": fks, "unicos": unicos, "indices": indices}


def conectar(ruta_bd):
    """Abre una conexión con las llaves foráneas activas y filas tipo diccionario."""
    conexion = sqlite3.connect(ruta_bd, timeout=10, isolation_level=None)
    conexion.row_factory = sqlite3.Row
    conexion.execute("PRAGMA foreign_keys = ON")
    return conexion


class transaccion:
    """Bloque atómico: BEGIN IMMEDIATE ... COMMIT, o ROLLBACK si algo falla."""

    def __init__(self, conexion):
        self.conexion = conexion

    def __enter__(self):
        self.conexion.execute("BEGIN IMMEDIATE")
        return self.conexion

    def __exit__(self, tipo, valor, traza):
        self.conexion.execute("ROLLBACK" if tipo else "COMMIT")
        return False


def crear_esquema(conexion, script):
    """Ejecuta el script traducido sobre una conexión abierta y lo verifica contra el catálogo.
    Devuelve el resumen verificado; lanza ValueError si el catálogo no coincide con el script."""
    sentencias, declarado = traducir_script(script)
    conexion.execute("BEGIN")
    try:
        for sentencia in sentencias:
            conexion.execute(sentencia)
    except Exception:
        conexion.execute("ROLLBACK")
        raise
    conexion.execute("COMMIT")
    real = verificar(conexion)
    for clave in ("tablas", "llaves_foraneas", "unicos"):
        if real[clave] != declarado[clave]:
            raise ValueError(f"El catálogo de SQLite tiene {real[clave]} {clave} y el script declara {declarado[clave]}.")
    return {**real, "lotes_omitidos": declarado["lotes_omitidos"]}


def crear_base(ruta_script, ruta_bd):
    """Crea la BD SQLite (archivo) desde el script T-SQL y devuelve su resumen verificado."""
    script = Path(ruta_script).read_text(encoding="utf-8")
    Path(ruta_bd).parent.mkdir(parents=True, exist_ok=True)
    conexion = conectar(ruta_bd)
    try:
        return crear_esquema(conexion, script)
    finally:
        conexion.close()
