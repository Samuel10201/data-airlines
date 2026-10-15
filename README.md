# Data-Delta Airlines — prototipo

Prototipo del **punto 5 del Parcial 2** de Diseño de Software I (Universidad del Norte): una aplicación web
de una aerolínea ficticia que recorre la interfaz, la lógica y la persistencia sobre el **modelo relacional
del punto 3**. Todo corre sobre exactamente las 26 tablas del script que generó Enterprise Architect
(`sql/modelo-relacional-sqlserver.sql`), sin añadir ni cambiar ninguna. Un tercer recorrido carga el **Data Warehouse**
(7 tablas, `sql/modelo-dw-sqlserver.sql`, también generado por EA) desde esa base y responde los requerimientos 4a, 4b y 4c.

**Demo en línea:** https://samuel10201.github.io/data-airlines/

La demo no necesita servidor: el mismo código Python se ejecuta dentro del navegador con
[Pyodide](https://pyodide.org). La primera visita descarga unos 8 MB y tarda unos segundos; las siguientes
cargan desde la caché. Los datos se guardan en el `localStorage` de cada navegador.

## Identidad visual

La interfaz usa el vocabulario del correo aéreo: papel crema, tinta, el rojo y el azul de las cartas aéreas, franjas diagonales,
sellos y postales. Los pases de abordar, el tablero de salidas y las etiquetas de maleta están dibujados con CSS y SVG; el mapa de
rutas se calcula con las coordenadas de la tabla `aeropuerto`. La tipografía es Archivo en su versión ensanchada para títulos y códigos de aeropuerto, Public Sans para el texto y Overpass Mono para
horas, valores y etiquetas. Tiene tema claro y oscuro (el oscuro es el mismo papel de noche, con
los mismos matices) y un botón *Tema* que alterna entre Auto (el del sistema), Claro y Oscuro.

Las fotos de las ocho ciudades (`img/ciudades/`) son de Wikimedia Commons con licencia libre; el autor y la licencia de cada una están
en `img/ciudades/creditos.json` y en el pie de la página.

## Qué se puede hacer

No hay claves: el modelo relacional no tiene credenciales, así que se **entra como** un cliente, un agente de
viaje o un aeropuerto de la lista (esto es una demostración de roles, no seguridad).

**Recorrido A — Comprar y cancelar** (cliente o agente de viaje)
1. Buscar vuelos por origen, destino y fecha; ver avión y tripulación de cada uno.
2. Reservar (el agente lo hace a nombre de un cliente). El cupo no se ocupa todavía.
3. Comprar el tiquete: su valor sale de la distancia entre los dos aeropuertos (coordenadas del modelo).
4. Cancelar el tiquete mientras el pasajero no haya abordado y el vuelo no haya salido.

**Recorrido B — Abordaje y maletas** (personal de aeropuerto)
1. En el aeropuerto de origen: registrar el abordaje y recibir cada maleta (hasta 3 por tiquete, 32 kg); al
   recibirla queda su primera lectura.
2. En el aeropuerto de destino: escanear la maleta, solo si el pasajero abordó.
3. Cualquiera puede rastrear una maleta por su etiqueta y ver dónde está.

**Recorrido C — Analítica (Data Warehouse)** (todos)
1. Cargar el DW: una extracción, transformación y carga vacía las 7 tablas del DW y las vuelve a llenar desde la base en una sola
   transacción. Se puede repetir; da siempre las mismas filas.
2. Ver 4a (ingresos por ciudad y mes), 4b (reservaciones por ciudad y mes) y 4c (millas de vuelos nacionales por pasajero y mes),
   con la tabla de calor, el total por mes y la consulta que se ejecutó sobre el DW.
3. Cada reporte compara su total con el que se obtiene directamente de la base transaccional; deben coincidir.

## Qué tablas ejercita cada recorrido

| Recorrido | Escribe | Lee |
|---|---|---|
| A | `reserva`, `tiquete` | `cliente`, `agente_viaje`, `empleado`, `vuelo`, `aeropuerto`, `ciudad`, `avion`, `vuelo_piloto`, `vuelo_tcp`, `piloto`, `tcp`, `abordaje` |
| B | `abordaje`, `equipaje`, `escaneo` | `tiquete`, `reserva`, `cliente`, `vuelo`, `aeropuerto`, `ciudad` |
| C | las 7 tablas del DW (`dim_tiempo`, `dim_geografia`, `dim_cliente`, `dim_ruta`, `facts_ingresos`, `facts_reservaciones`, `facts_millas`) | `reserva`, `tiquete`, `abordaje`, `vuelo`, `aeropuerto`, `ciudad`, `cliente` |
| Solo semilla | `recurso`, `consumible`, `equipo`, `vuelo_recurso`, `equipo_avion`, `mantenimiento_avion`, `mantenimiento_equipo`, `mantenimiento_avion_tecnico`, `mantenimiento_equipo_tecnico`, `tecnico_mantenimiento` | — |

**Lo que el prototipo NO cubre:** el panel de operaciones (asignar tripulación, recursos y avión a un vuelo) y el
registro de mantenimientos. Esas tablas existen y tienen datos de demostración, pero ningún recorrido las modifica.

## Cómo correrlo

Requiere Python 3.11 o superior (solo biblioteca estándar).

```
python app.py                  # servidor local: http://127.0.0.1:8765
python app.py --reiniciar      # borra datos\ y regenera la BD desde el script
python -m http.server 8000     # como en GitHub Pages (estático, Python en el navegador; necesita internet)
python pruebas/prueba_esquema.py     # traductor del script y catálogo: 26 tablas, 34 FK, 6 únicos
python pruebas/prueba_recorrido.py   # los tres recorridos por HTTP (98 comprobaciones), los rechazos y el cuadre del DW con la base
```

La página detecta sola el modo: si el servidor local lo marca al entregar `index.html`, usa la API HTTP; si no,
arranca Pyodide.

## Arquitectura

```
index.html, estilos.css, app.js     SPA: interfaz por rol; todo pasa por la API JSON /api/...
arranque.js                         decide el modo; en modo estático carga Pyodide e intercepta /api/...
app.py                              punto de entrada del modo servidor local
sql/modelo-relacional-sqlserver.sql el script de EA de la base, intacto (fuente única del esquema transaccional)
sql/modelo-dw-sqlserver.sql         el script de EA del Data Warehouse (7 tablas), intacto
aerolinea/
    dominios.py    dominios y parámetros que el script no impone; errores de negocio
    esquema.py     traductor T-SQL (EA) -> SQLite, creación de la BD y verificación contra el catálogo
    geografia.py   millas (haversine) y tarifa: se derivan de las coordenadas, no se guardan
    semilla.py     datos de demostración, creados con las mismas funciones que usa la interfaz
    sesion.py      "entrar como"; vuelos.py, ventas.py, aeropuerto.py: la lógica de cada recorrido
    dw.py          el DW (esquema `dw`): carga desde la base, reportes 4a, 4b y 4c y su verificación contra la base
    rutas.py       tabla de rutas /api/... y despachador (sin transporte)
    servidor.py    adaptador HTTP (http.server)      navegador.py    adaptador del navegador (Pyodide)
pruebas/           prueba_esquema.py y prueba_recorrido.py
```

```
         app.js  --fetch('/api/...')-->
                              |
  modo servidor (python app.py)  |  modo estático (GitHub Pages)
  http.server + cookie           |  arranque.js intercepta fetch
  servidor.py                    |  navegador.py (Pyodide 0.29, Python 3.13)
          \______________________|______________________/
                                 v
                 rutas.despachar() -> vuelos / ventas / aeropuerto
                                 v
        SQLite creada desde modelo-relacional-sqlserver.sql
        (datos/aerolinea.db  |  memoria + localStorage)
```

En el modo estático, `arranque.js` descarga Pyodide 0.29.5 de jsDelivr, copia los `.py` y el script al sistema
de archivos virtual y crea la BD en memoria; tras cada petición que escribe, la BD se serializa
(`sqlite3.Connection.serialize()`) y se guarda en `localStorage`. Si al volver a abrir la página los vuelos
guardados ya pasaron, se regenera la semilla con fechas nuevas.

## Traducción automática del script T-SQL a SQLite

`aerolinea/esquema.py` lee el script tal como sale de EA y lo traduce lote por lote; si encuentra una
sentencia sin regla, falla con error (no la ignora). Al terminar compara el catálogo de SQLite con lo que el
script declaraba: **26 tablas, 34 llaves foráneas, 6 restricciones únicas, 22 índices**.

| Script T-SQL | SQLite | Motivo |
|---|---|---|
| `/* ... */`, `[nombre]`, lotes separados por `GO` | se quitan comentarios y corchetes; se parte por `GO` | SQLite no entiende el formato de lotes |
| `IF EXISTS ... DROP ...` (60 lotes) | se omiten | la BD siempre se crea desde cero |
| `int NOT NULL IDENTITY (1, 1)` + `PRIMARY KEY CLUSTERED` | `INTEGER PRIMARY KEY AUTOINCREMENT` | forma de SQLite para una llave autonumérica |
| `int`, `bit` / `datetime` | `INTEGER` / `TEXT` (ISO 8601) | SQLite no tiene tipos de fecha ni booleanos |
| `ALTER TABLE ... ADD CONSTRAINT` (PK, UNIQUE, FK) | restricción dentro del `CREATE TABLE` | SQLite no admite `ALTER TABLE ADD CONSTRAINT` |
| `CREATE NONCLUSTERED INDEX` | `CREATE INDEX` | no hay índices agrupados en SQLite |

## Reglas que valida la aplicación (el script no tiene `CHECK`)

- Un cliente reserva solo para sí; el agente indica el cliente. No hay dos reservas vivas del mismo cliente en un vuelo.
- Solo se reserva y se compra en vuelos que no han salido; el cupo se ocupa al comprar y el vuelo lleno rechaza la compra.
- `tiquete.valor` = tarifa base + millas del trayecto × tarifa por milla (parámetros en `dominios.py`).
- Cancelar solo antes del abordaje y de la salida; la cancelación es el atributo `tiquete.cancelado`.
- El abordaje y la recepción de maletas ocurren en el aeropuerto de origen; la lectura, en el origen o en el destino;
  en el destino solo si el pasajero abordó; no se lee dos veces seguidas en el mismo aeropuerto.
- Máximo 3 maletas por tiquete y 32 kg cada una; la etiqueta (`DL<tiquete>-<n>`) la genera la aplicación.
- Un vuelo es nacional cuando el origen y el destino tienen el mismo `pais`.

## Límites declarados

- **Sin autenticación:** "entrar como" es una demostración de roles. El modelo no guarda credenciales.
- **Datos por navegador:** en la versión estática cada navegador tiene su propia copia; no se comparten entre personas.
  El botón *Reiniciar datos de demostración* vuelve a la semilla.
- **SQLite en lugar de SQL Server:** el script se genera para SQL Server 2012 y se ejecuta traducido a SQLite;
  la lógica no depende del motor. Las llaves foráneas están activas (`PRAGMA foreign_keys = ON`).
- **El DW no se guarda en el navegador:** vive en una segunda base en memoria (esquema `dw`); tras recargar la página hay que
  volver a pulsar *Cargar el DW*. En modo servidor es un archivo (`datos/aerolinea-dw.db`).
- **DW de demostración en SQLite:** el script del DW se genera para SQL Server 2012 y se traduce igual que el de la base; no se
  desplegó en Snowflake.
- **Pagos simulados:** el modelo no tiene entidad de pago; el valor se guarda en `tiquete` y no hay pasarela.
- **Una salida por vuelo:** cada fila de `vuelo` es una salida concreta con su avión; la semilla se genera con
  fechas relativas al momento en que se abre la demo por primera vez.
