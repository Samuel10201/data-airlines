/* Arranque del portal. Decide el modo y luego carga la SPA (app.js):
 *  - Modo servidor (python app.py): /api/... lo responde el servidor local; no hay nada que hacer.
 *  - Modo estático (GitHub Pages o python -m http.server): no hay servidor, así que el mismo código
 *    Python (paquete aerolinea/) corre en el navegador con Pyodide. Las llamadas a /api/... que hace
 *    app.js se interceptan y van al despachador Python (aerolinea/rutas.py); la BD SQLite vive en
 *    memoria y se guarda en localStorage tras cada operación que escribe.
 */
"use strict";

// 0.29.x (Python 3.13): la serie 314.x ya no trae hashlib con OpenSSL.
const PYODIDE_VERSION = "0.29.5";
const PYODIDE_URL = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;
const MODULOS = ["__init__", "dominios", "esquema", "geografia", "semilla", "sesion", "vuelos", "ventas",
  "aeropuerto", "rutas", "navegador"];
const SCRIPT_SQL = "sql/modelo-relacional-sqlserver.sql";
const CLAVE_BD = "data-delta:bd-v1";

const portalWeb = { modo: null, portal: null, guardadoFallido: false };

function pasoCarga(texto) {
  const nodo = document.getElementById("carga-paso");
  if (nodo) nodo.textContent = texto;
}

function errorCarga(mensaje) {
  document.getElementById("carga").classList.add("carga--error");
  document.getElementById("carga-titulo").textContent = "No se pudo arrancar el prototipo";
  pasoCarga(mensaje);
  console.error(mensaje);
}

function leerBdGuardada() {
  try { return localStorage.getItem(CLAVE_BD); } catch { return null; }
}

function guardarBd(base64) {
  try {
    localStorage.setItem(CLAVE_BD, base64);
    portalWeb.guardadoFallido = false;
  } catch (e) {
    // Nunca en silencio: se avisa en la franja superior (los datos siguen en memoria).
    portalWeb.guardadoFallido = true;
    console.error("No se pudo guardar la BD en localStorage:", e);
    const aviso = document.getElementById("franja-aviso");
    if (aviso) aviso.textContent = "Atención: este navegador no permite guardar; los cambios se pierden al recargar.";
  }
}

function cargarScript(src) {
  return new Promise((resolver, rechazar) => {
    const s = document.createElement("script");
    s.src = src;
    s.onload = resolver;
    s.onerror = () => rechazar(new Error(`No se pudo cargar ${src}`));
    document.body.append(s);
  });
}

async function textoDe(ruta) {
  const r = await fetch(ruta, { cache: "no-cache" });
  if (!r.ok) throw new Error(`No se encontró ${ruta} (HTTP ${r.status}).`);
  return r.text();
}

/** Deja que el navegador pinte antes de un paso que bloquea el hilo (Python es síncrono). */
const respirar = () => new Promise((r) => setTimeout(r, 30));

async function arrancarPyodide() {
  const t0 = performance.now();
  pasoCarga("Descargando Python para el navegador (Pyodide)…");
  await cargarScript(PYODIDE_URL + "pyodide.js");
  const pyodide = await loadPyodide({ indexURL: PYODIDE_URL });

  pasoCarga("Cargando SQLite y el código del prototipo…");
  const [fuentes, script] = await Promise.all([
    Promise.all(MODULOS.map((m) => textoDe(`aerolinea/${m}.py`))),
    textoDe(SCRIPT_SQL),
  ]);
  pyodide.FS.mkdirTree("/home/pyodide/aerolinea");
  MODULOS.forEach((m, i) => pyodide.FS.writeFile(`/home/pyodide/aerolinea/${m}.py`, fuentes[i]));
  await pyodide.loadPackage(["sqlite3"]);

  const guardada = leerBdGuardada();
  pasoCarga(guardada ? "Restaurando sus datos guardados en este navegador…"
    : "Creando la base de datos desde el script de Enterprise Architect y sembrando los datos de prueba…");
  await respirar();
  const crearPortal = pyodide.runPython(
    "import sys\nsys.path.insert(0, '/home/pyodide')\nfrom aerolinea.navegador import crear_portal\ncrear_portal");
  const portal = crearPortal(script, guardada);
  if (!portal.restaurada) guardarBd(portal.serializar());
  portalWeb.portal = portal;
  console.info(`Pyodide ${pyodide.version} listo en ${Math.round(performance.now() - t0)} ms`,
    portal.restaurada ? "(BD restaurada de localStorage)" : "(BD nueva desde el script)");

  // Intercepta las llamadas a /api/... que hace app.js y las pasa al despachador Python.
  const fetchOriginal = window.fetch.bind(window);
  window.fetch = async (recurso, opciones = {}) => {
    const url = typeof recurso === "string" ? recurso : recurso.url;
    if (!url.startsWith("/api/")) return fetchOriginal(recurso, opciones);
    await respirar();
    const salida = JSON.parse(portal.atender(opciones.method || "GET", url, opciones.body || ""));
    if (salida.bd) guardarBd(salida.bd);
    return new Response(JSON.stringify(salida.respuesta), {
      status: salida.estado, headers: { "Content-Type": "application/json; charset=utf-8" },
    });
  };
}

function mostrarFranja() {
  document.getElementById("franja-demo").hidden = false;
  document.getElementById("reiniciar-datos").addEventListener("click", () => {
    if (!confirm("¿Reiniciar los datos de demostración? Se borra todo lo que haya hecho en este navegador y se vuelve a la semilla.")) return;
    try { localStorage.removeItem(CLAVE_BD); } catch { /* sin almacenamiento: la recarga ya vuelve a la semilla */ }
    location.reload();
  });
}

async function arrancar() {
  try {
    if (window.MODO_SERVIDOR) {  // lo inyecta servidor.py al servir index.html
      portalWeb.modo = "servidor";
    } else {
      portalWeb.modo = "navegador";
      await arrancarPyodide();
      mostrarFranja();
    }
    await cargarScript("app.js");
    document.getElementById("carga").hidden = true;
  } catch (e) {
    errorCarga(`${e.message} Revise su conexión a internet (Pyodide se descarga de cdn.jsdelivr.net) y recargue la página.`);
  }
}

arrancar();
