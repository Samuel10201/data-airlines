/* Interfaz de Data-Delta Airlines. Una sola página; todo pasa por la API JSON /api/...
 * Recorrido A (cliente y agente): buscar vuelo -> reservar -> comprar tiquete -> cancelar.
 * Recorrido B (aeropuerto): abordaje -> recibir maletas -> escanear -> rastrear por etiqueta.
 * Recorrido C (todos): cargar el Data Warehouse desde la base y ver 4a, 4b y 4c. */
"use strict";

const estado = { actor: null, usuarios: null, vueloAeropuerto: null, aeropuertos: [], vista: "inicio", info: null,
  filtros: { origen: "", destino: "", fecha: "" }, clienteDelAgente: "", vuelos: null, rutas: null, precios: {},
  reporte: "ingresos", anioDw: "" };

const $ = (selector) => document.querySelector(selector);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const usd = (n) => new Intl.NumberFormat("es-CO", { style: "currency", currency: "USD" }).format(n);
const num = (n, decimales = 0) => new Intl.NumberFormat("es-CO", { maximumFractionDigits: decimales }).format(n);
const DIAS = ["dom", "lun", "mar", "mié", "jue", "vie", "sáb"];
const MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];
const aFecha = (t) => new Date(t.replace(" ", "T"));
const dia = (t) => { const d = aFecha(t); return `${DIAS[d.getDay()]} ${d.getDate()} ${MESES[d.getMonth()]}`; };
const hora = (t) => t.slice(11, 16);
const duracion = (a, b) => {
  const min = Math.round((aFecha(b) - aFecha(a)) / 60000);
  return `${Math.floor(min / 60)} h ${String(min % 60).padStart(2, "0")} min`;
};
const TIPO_ACTOR = { cliente: "Cliente", agente: "Agente de viaje", aeropuerto: "Aeropuerto" };
const reducirMovimiento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

/** Foto de la ciudad de un aeropuerto (Wikimedia Commons, con sus créditos al pie de la página). */
const foto = (codigo, mini = false) => `img/ciudades/${String(codigo).toLowerCase()}${mini ? "-mini" : ""}.jpg`;
const codigoDe = (texto) => (/\(([A-Z]{3})\)/.exec(texto) || [])[1];

const ILUSTRACION_MALETA = `<svg viewBox="0 0 120 130" aria-hidden="true"><rect x="14" y="34" width="92" height="82" rx="10" fill="var(--rojo)"/>
  <rect x="42" y="14" width="36" height="24" rx="6" fill="none" stroke="var(--tinta)" stroke-width="6"/>
  <rect x="30" y="34" width="10" height="82" fill="rgba(0,0,0,.2)"/><rect x="80" y="34" width="10" height="82" fill="rgba(0,0,0,.2)"/>
  <circle cx="60" cy="72" r="15" fill="var(--superficie)" stroke="var(--tinta)" stroke-width="2"/><path d="M51 74 67 65l-3 13-4-4z" fill="var(--azul)"/>
  <circle cx="97" cy="46" r="5" fill="var(--verde)"/><circle cx="23" cy="52" r="4" fill="var(--azul)"/>
  <rect x="20" y="116" width="14" height="8" rx="3" fill="var(--tinta)"/><rect x="86" y="116" width="14" height="8" rx="3" fill="var(--tinta)"/></svg>`;
const ILUSTRACION_AVION = `<svg viewBox="0 0 160 90" aria-hidden="true"><path d="M10 74 Q64 4 138 30" fill="none" stroke="var(--tinta)" stroke-width="2" stroke-dasharray="2 7" stroke-linecap="round"/>
  <path d="M132 20 156 28 134 44 138 31z" fill="var(--rojo)"/><path d="M138 31 156 28 140 38z" fill="var(--azul)"/><circle cx="10" cy="74" r="5" fill="var(--superficie)" stroke="var(--tinta)" stroke-width="2.4"/></svg>`;
const vacio = (texto) => `<div class="tarjeta vacio">${ILUSTRACION_AVION}${texto}</div>`;

/** Llama a la API. Lanza Error con el mensaje del servidor; 401 cierra la sesión local. */
async function api(metodo, ruta, cuerpo) {
  const respuesta = await fetch(ruta, {
    method: metodo, headers: cuerpo ? { "Content-Type": "application/json" } : {},
    body: cuerpo ? JSON.stringify(cuerpo) : undefined,
  });
  let datos;
  try { datos = await respuesta.json(); } catch { throw new Error("Respuesta no válida del servidor."); }
  if (respuesta.status === 401) { estado.actor = null; dibujarSesion(); dibujarNav(); }
  if (!respuesta.ok || datos.ok === false) throw new Error(datos.error || `Error ${respuesta.status}`);
  return datos;
}

function aviso(texto, tipo = "ok") {
  const nodo = document.createElement("div");
  nodo.className = `aviso aviso--${tipo}`;
  nodo.textContent = texto;
  const caja = $("#avisos");
  caja.append(nodo);
  while (caja.children.length > 3) caja.firstChild.remove();  // máximo 3 a la vez
  setTimeout(() => nodo.remove(), tipo === "error" ? 7000 : 4000);
}

/** Ejecuta una acción del usuario: muestra el mensaje de éxito o el error, nunca en silencio. */
async function hacer(accion) {
  try { await accion(); } catch (e) { console.error(e); aviso(e.message, "error"); }
}

/* ---------- tema de color: automático, claro u oscuro ---------- */

const TEMAS = ["auto", "claro", "oscuro"];
const temaActual = () => document.documentElement.dataset.tema || "auto";
function pintarBotonTema() {
  $("#tema").textContent = `Tema: ${{ auto: "Auto", claro: "Claro", oscuro: "Oscuro" }[temaActual()]}`;
}
function alternarTema() {
  const siguiente = TEMAS[(TEMAS.indexOf(temaActual()) + 1) % TEMAS.length];
  if (siguiente === "auto") delete document.documentElement.dataset.tema; else document.documentElement.dataset.tema = siguiente;
  try { siguiente === "auto" ? localStorage.removeItem("data-delta:tema") : localStorage.setItem("data-delta:tema", siguiente); } catch { /* sin almacenamiento */ }
  pintarBotonTema();
}

/* ---------- mapa de rutas (con las coordenadas de aeropuerto del modelo) ---------- */

const MAPA = { lon0: -104, lon1: -70, lat0: 2, lat1: 36, ancho: 600 };
const KM = MAPA.ancho / (MAPA.lon1 - MAPA.lon0);
const proyectar = (lat, lon) => [(lon - MAPA.lon0) * KM, (MAPA.lat1 - lat) * KM];

/** Arco entre dos puntos proyectados: una curva cuadrática que se arquea hacia el norte. */
function arco([x1, y1], [x2, y2]) {
  const dx = x2 - x1, dy = y2 - y1, largo = Math.hypot(dx, dy) || 1;
  let nx = -dy / largo, ny = dx / largo;
  if (ny > 0) { nx = -nx; ny = -ny; }
  const cx = (x1 + x2) / 2 + nx * largo * 0.22, cy = (y1 + y2) / 2 + ny * largo * 0.22;
  return `M${x1.toFixed(1)} ${y1.toFixed(1)} Q${cx.toFixed(1)} ${cy.toFixed(1)} ${x2.toFixed(1)} ${y2.toFixed(1)}`;
}

/** Carta de navegación: malla de latitud y longitud, rutas del sistema (tenues) y las que se están viendo (rojo). */
function htmlMapa(vivas = new Set(), activo = null) {
  const puntos = new Map(estado.aeropuertos.map((a) => [a.id_aeropuerto, { ...a, p: proyectar(a.latitud, a.longitud) }]));
  const malla = [];
  for (let lon = -100; lon <= -70; lon += 5) {
    const x = (lon - MAPA.lon0) * KM;
    malla.push(`<line class="mapa__malla" x1="${x}" y1="0" x2="${x}" y2="${MAPA.ancho}"/><text class="mapa__etiqueta-malla" x="${x + 2}" y="595">${-lon}°W</text>`);
  }
  for (let lat = 5; lat <= 35; lat += 5) {
    const y = (MAPA.lat1 - lat) * KM;
    malla.push(`<line class="mapa__malla" x1="0" y1="${y}" x2="${MAPA.ancho}" y2="${y}"/><text class="mapa__etiqueta-malla" x="3" y="${y - 3}">${lat}°N</text>`);
  }
  const pares = estado.rutas ?? [];
  const rutas = pares.map(([o, d]) => {
    const a = puntos.get(o), b = puntos.get(d);
    return a && b ? `<path class="mapa__ruta ${vivas.has(`${o}-${d}`) ? "mapa__ruta--viva" : ""}" d="${arco(a.p, b.p)}"/>` : "";
  });
  const viva = pares.find(([o, d]) => vivas.has(`${o}-${d}`)) ?? pares[0];
  let avion = "";
  if (viva && !reducirMovimiento && puntos.get(viva[0]) && puntos.get(viva[1])) {
    avion = `<path class="mapa__avion" d="M-8 -6 L10 0 L-8 6 L-4 0z"><animateMotion dur="7s" repeatCount="indefinite" rotate="auto" path="${arco(puntos.get(viva[0]).p, puntos.get(viva[1]).p)}"/></path>`;
  }
  // Los aeropuertos colombianos quedan muy juntos: los del oeste llevan la etiqueta a la izquierda para que no se pisen.
  const marcas = [...puntos.values()].map((a) => {
    const [x, y] = a.p;
    const izquierda = a.longitud < -75 && a.longitud > -80;
    const lado = izquierda ? "end" : "start", dx = izquierda ? -10 : 10;
    return `<g data-accion="mapa-aeropuerto" data-id="${a.id_aeropuerto}"><title>${esc(a.ciudad)} (${esc(a.codigo)}) · ${esc(a.pais)}</title>
      <circle class="mapa__punto ${activo === a.id_aeropuerto ? "mapa__punto--activo" : ""}" cx="${x}" cy="${y}" r="6"/>
      <text class="mapa__codigo" text-anchor="${lado}" x="${x + dx}" y="${y + 5}">${esc(a.codigo)}</text>
      <text class="mapa__ciudad" text-anchor="${lado}" x="${x + dx}" y="${y + 18}">${esc(a.ciudad)}</text></g>`;
  });
  return `<div class="mapa"><svg viewBox="0 0 ${MAPA.ancho} ${MAPA.ancho}" role="img" aria-label="Mapa de rutas entre los aeropuertos del sistema">${malla.join("")}${rutas.join("")}${marcas.join("")}${avion}</svg>
    <div class="mapa__leyenda"><span>${pares.length} rutas · ${estado.aeropuertos.length} aeropuertos</span><span>coordenadas de <b>aeropuerto</b></span></div></div>`;
}

async function cargarRutas() {
  if (!estado.aeropuertos.length) estado.aeropuertos = (await api("GET", "/api/aeropuertos")).aeropuertos;
  if (!estado.rutas) {
    const { vuelos } = await api("GET", "/api/vuelos");
    estado.rutas = [...new Set(vuelos.map((v) => `${v.origen.id_aeropuerto}-${v.destino.id_aeropuerto}`))]
      .map((par) => par.split("-").map(Number));
    for (const v of vuelos) {  // el valor más bajo con que se llega a cada destino
      const actual = estado.precios[v.destino.codigo];
      if (actual === undefined || v.valor < actual) estado.precios[v.destino.codigo] = v.valor;
    }
  }
}

/* ---------- sesión y navegación ---------- */

function menu() {
  if (!estado.actor) return [["inicio", "Inicio"], ["vuelos", "Vuelos"], ["rastreo", "Rastrear maleta"], ["analitica", "Analítica"]];
  if (estado.actor.tipo === "aeropuerto") {
    return [["aeropuerto", "Embarque y equipaje"], ["vuelos", "Vuelos"], ["rastreo", "Rastrear maleta"], ["analitica", "Analítica"]];
  }
  return [["vuelos", "Buscar vuelos"], ["reservas", "Mis reservas"], ["rastreo", "Rastrear maleta"], ["analitica", "Analítica"]];
}

function dibujarNav() {
  $("#navegacion").innerHTML = menu().map(([id, texto]) =>
    `<button type="button" data-ir="${id}" ${estado.vista === id ? 'aria-current="page"' : ""}>${esc(texto)}</button>`).join("");
}

function opcionesActores() {
  const u = estado.usuarios;
  if (!u) return "";
  return `<option value="">Entrar como…</option>
    <optgroup label="Clientes">${u.clientes.map((c) => `<option value="cliente:${c.id_cliente}">${esc(c.nombre)}</option>`).join("")}</optgroup>
    <optgroup label="Agentes de viaje">${u.agentes.map((a) => `<option value="agente:${a.id_agente_viaje}">${esc(a.nombre)}</option>`).join("")}</optgroup>
    <optgroup label="Aeropuertos">${u.aeropuertos.map((a) => `<option value="aeropuerto:${a.id_aeropuerto}">${esc(a.ciudad)} (${esc(a.codigo)})</option>`).join("")}</optgroup>`;
}

function dibujarSesion() {
  const a = estado.actor;
  $("#sesion").innerHTML = a
    ? `<span>Entró como <strong>${esc(a.nombre)}</strong> <span class="chip">${esc(TIPO_ACTOR[a.tipo])}</span></span>
       <button type="button" class="boton boton--sec boton--chico" data-accion="salir">Salir</button>`
    : `<label class="campo"><select id="selector-actor" aria-label="Entrar como">${opcionesActores()}</select></label>`;
}

async function entrar(valor) {
  const [tipo, id] = valor.split(":");
  const datos = await api("POST", "/api/sesion", { tipo, id: Number(id) });
  estado.actor = datos.actor;
  try { sessionStorage.setItem("data-delta:actor", JSON.stringify({ tipo, id: Number(id) })); } catch { /* sin sessionStorage */ }
  aviso(datos.mensaje);
  dibujarSesion();
  await ir(datos.actor.tipo === "aeropuerto" ? "aeropuerto" : "vuelos");
}

async function salir() {
  await api("DELETE", "/api/sesion");
  estado.actor = null;
  try { sessionStorage.removeItem("data-delta:actor"); } catch { /* ignorado */ }
  dibujarSesion();
  await ir("inicio");
}

async function ir(vista) {
  estado.vista = vista;
  dibujarNav();
  await hacer(() => VISTAS[vista]());
  $("#principal").focus({ preventScroll: true });
}

/* ---------- inicio ---------- */

async function vistaInicio() {
  await cargarRutas();
  const u = estado.usuarios;
  const porCodigo = new Map(estado.aeropuertos.map((a) => [a.codigo, a]));
  const desde = (codigo) => (estado.precios[codigo] !== undefined ? `desde ${usd(estado.precios[codigo])}` : "");
  const hoy = new Date();
  const postal = (codigo, n, giro) => {
    const a = porCodigo.get(codigo);
    return a ? `<button type="button" class="postal postal--${n}" style="--giro:${giro}deg" data-accion="destino" data-id="${a.id_aeropuerto}" aria-label="Ver vuelos a ${esc(a.ciudad)}">
      <img src="${foto(codigo)}" alt="${esc(a.ciudad)}"><span class="sello-postal">${esc(codigo)}</span>
      <span class="postal__pie">${esc(a.ciudad)}<span>${desde(codigo)}</span></span></button>` : "";
  };
  const destino = (a) => `<button type="button" class="destino" data-accion="destino" data-id="${a.id_aeropuerto}">
      <img src="${foto(a.codigo, true)}" alt="${esc(a.ciudad)}" loading="lazy"><span class="sello-postal">${esc(a.codigo)}</span>
      <span class="destino__texto"><strong>${esc(a.ciudad)}</strong><span>${esc(a.pais)}</span><span>${desde(a.codigo)}</span></span></button>`;
  const mostrador = (titulo, codigo, texto, tipo, opciones) => `
    <div class="tarjeta mostrador"><h2>${titulo} <small>${codigo}</small></h2><p class="ayuda">${texto}</p>
      <select data-entrada="${tipo}" aria-label="${esc(titulo)}">${opciones}</select>
      <button type="button" class="boton" data-accion="entrar-tarjeta" data-tipo="${tipo}">Entrar</button></div>`;
  $("#principal").innerHTML = `
    <section class="heroe">
      <div>
        <h1>Reserve. Embarque.<br><em>Siga su maleta.</em></h1>
        <p>Prototipo de Data-Delta Airlines sobre el modelo relacional del Parcial 2: dos recorridos de la interfaz a la base de datos
        y un Data Warehouse que responde ingresos, reservaciones y millas. No hay claves: elija con quién entrar.</p>
        <button type="button" class="boton" data-ir="vuelos">Ver las salidas</button>
      </div>
      <div class="postales" aria-label="Destinos">${postal("CTG", 1, -5)}${postal("MEX", 2, 4)}${postal("MIA", 3, -2)}
        <div class="matasellos" aria-hidden="true">DATA-DELTA<br>${hoy.getDate()} ${MESES[hoy.getMonth()].toUpperCase()}<br>${hoy.getFullYear()}</div></div>
    </section>
    <div class="titulo-seccion"><h2>Destinos</h2><small>Toque uno para ver sus vuelos</small></div>
    <div class="destinos">${estado.aeropuertos.map(destino).join("")}</div>
    <div class="titulo-seccion"><h2>Entre al mostrador</h2><small>Sin claves: el modelo no las guarda</small></div>
    <div class="entradas">
      ${mostrador("Soy cliente", "A · 01", "Busque un vuelo, reserve, compre su tiquete y cancélelo si cambia de plan.", "cliente",
        u.clientes.map((c) => `<option value="${c.id_cliente}">${esc(c.nombre)}</option>`).join(""))}
      ${mostrador("Soy agente de viaje", "A · 02", "Reserve y venda a nombre de un cliente; gestiona sus tiquetes.", "agente",
        u.agentes.map((a) => `<option value="${a.id_agente_viaje}">${esc(a.nombre)}</option>`).join(""))}
      ${mostrador("Trabajo en un aeropuerto", "B · 01", "Registre el abordaje, reciba maletas y escanéelas en el origen y en el destino.", "aeropuerto",
        u.aeropuertos.map((a) => `<option value="${a.id_aeropuerto}">${esc(a.ciudad)} (${esc(a.codigo)})</option>`).join(""))}
    </div>
    <div class="titulo-seccion"><h2>La red de rutas</h2></div>
    <div class="red">${htmlMapa()}
      <div><p>El mapa se dibuja con las coordenadas de la tabla <b class="mono">aeropuerto</b> del modelo relacional: ninguna ruta está
      escrita a mano. Cada arco es una pareja origen-destino con vuelos programados; el avión recorre una de ellas.</p>
      <p class="ayuda">Toque un aeropuerto del mapa en la pantalla de salidas para usarlo como origen.</p></div></div>
    <div class="titulo-seccion"><h2>Tres recorridos</h2></div>
    <div class="pasos">
      <div class="tarjeta"><h3><span>A</span> Comprar y cancelar</h3><ol>
        <li>Buscar un vuelo por origen, destino y fecha.</li><li>Reservar (el cupo aún no se ocupa).</li>
        <li>Comprar el tiquete: el valor sale de la distancia entre aeropuertos.</li><li>Cancelar mientras no haya abordado.</li></ol></div>
      <div class="tarjeta"><h3><span>B</span> Abordaje y maletas</h3><ol>
        <li>En el origen: registrar el abordaje y recibir cada maleta (queda su primera lectura).</li>
        <li>En el destino: escanear la maleta, solo si el pasajero abordó.</li><li>Cualquiera rastrea una maleta por su etiqueta.</li></ol></div>
      <div class="tarjeta"><h3><span>C</span> Analítica</h3><ol>
        <li>Cargar el Data Warehouse desde la base.</li><li>Ver 4a ingresos y 4b reservaciones por ciudad y mes.</li>
        <li>Ver 4c millas nacionales por pasajero y mes, con la consulta ejecutada.</li></ol></div>
    </div>`;
}

/* ---------- recorrido A: vuelos ---------- */

const filaVuelo = (v) => {
  const a = estado.actor;
  const puedeReservar = a && (a.tipo === "cliente" || a.tipo === "agente");
  const cupos = v.cupos_libres > 10 ? "ok" : v.cupos_libres > 0 ? "aviso" : "malo";
  return `<article class="fila-vuelo">
    <div class="fila-vuelo__hora">${esc(hora(v.salida_programada))}<span class="fila-vuelo__dia">${esc(dia(v.salida_programada))}</span></div>
    <div class="ruta">
      <div class="ruta__ciudad"><strong>${esc(v.origen.codigo)}</strong><span>${esc(v.origen.ciudad)}</span></div>
      <span class="ruta__flecha" aria-hidden="true">→</span>
      <div class="ruta__ciudad"><strong>${esc(v.destino.codigo)}</strong><span>${esc(v.destino.ciudad)} · ${esc(hora(v.llegada_programada))}</span></div>
    </div>
    <div class="fila-vuelo__meta">Vuelo <b>${esc(v.numero_vuelo)}</b><br>${esc(duracion(v.salida_programada, v.llegada_programada))} · ${num(v.millas, 0)} mi<br>
      <span class="chip ${v.nacional ? "chip--info" : "chip--aviso"}">${v.nacional ? "Nacional" : "Internacional"}</span></div>
    <div class="fila-vuelo__puerta">${esc(v.puerta || "—")}</div>
    <div><span class="chip chip--${cupos}">${v.cupos_libres} cupos</span></div>
    <div class="fila-vuelo__precio">${usd(v.valor)}<small>por pasajero</small></div>
    <div class="fila-vuelo__acciones">
      ${puedeReservar ? `<button type="button" class="boton boton--chico" data-accion="reservar" data-vuelo="${v.id_vuelo}">Reservar</button>` : ""}
      <button type="button" class="boton boton--sec boton--chico" data-accion="detalle" data-vuelo="${v.id_vuelo}" aria-expanded="false">Ver detalle</button>
    </div>
    <div class="detalle" id="detalle-${v.id_vuelo}" hidden></div>
  </article>`;
};

async function vistaVuelos() {
  await cargarRutas();
  const f = estado.filtros;
  const lista = (sel) => `<option value="">Cualquiera</option>` + estado.aeropuertos.map((a) =>
    `<option value="${a.id_aeropuerto}" ${String(a.id_aeropuerto) === String(sel) ? "selected" : ""}>${esc(a.ciudad)} (${esc(a.codigo)})</option>`).join("");
  const agente = estado.actor?.tipo === "agente";
  $("#principal").innerHTML = `
    <h1>Salidas</h1>
    <div class="vuelos-cabecera">
      <div><form id="filtros" class="filtros">
        <label class="campo">Origen<select name="origen">${lista(f.origen)}</select></label>
        <label class="campo">Destino<select name="destino">${lista(f.destino)}</select></label>
        <label class="campo">Fecha<input type="date" name="fecha" value="${esc(f.fecha)}"></label>
        ${agente ? `<label class="campo">Reservar a nombre de<select name="cliente" id="cliente-agente">${
          estado.usuarios.clientes.map((c) => `<option value="${c.id_cliente}" ${String(c.id_cliente) === String(estado.clienteDelAgente) ? "selected" : ""}>${esc(c.nombre)}</option>`).join("")}</select></label>` : ""}
        <button type="submit" class="boton">Buscar</button>
      </form>
      <p class="ayuda">Las rutas en rojo son las que cumplen la búsqueda. Haga clic en un aeropuerto del mapa para usarlo como origen, o elija un destino:</p>
      <div class="atajos">${estado.aeropuertos.map((a) => `<button type="button" class="atajo" data-accion="destino" data-id="${a.id_aeropuerto}"
        aria-pressed="${String(f.destino) === String(a.id_aeropuerto)}"><img src="${foto(a.codigo, true)}" alt=""><span>${esc(a.codigo)}</span></button>`).join("")}</div></div>
      <div id="mapa-vuelos"></div>
    </div>
    <div id="resultados"></div>
    ${estado.actor ? "" : '<p class="ayuda">Para reservar, entre como cliente o agente de viaje.</p>'}`;
  await buscarVuelos();
}

async function buscarVuelos() {
  const f = estado.filtros;
  const consulta = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
  const { vuelos } = await api("GET", `/api/vuelos${consulta ? "?" + consulta : ""}`);
  estado.vuelos = vuelos;
  const vivas = new Set(vuelos.map((v) => `${v.origen.id_aeropuerto}-${v.destino.id_aeropuerto}`));
  $("#mapa-vuelos").innerHTML = htmlMapa(vivas, f.origen ? Number(f.origen) : null);
  $("#resultados").innerHTML = vuelos.length
    ? `<div class="tablero">${vuelos.map(filaVuelo).join("")}</div>`
    : vacio("No hay vuelos con esos filtros. Pruebe con otra fecha o quite algún filtro.");
}

async function alternarDetalle(id, boton) {
  const caja = $(`#detalle-${id}`);
  if (!caja.hidden) { caja.hidden = true; boton.setAttribute("aria-expanded", "false"); return; }
  const { vuelo: v } = await api("GET", `/api/vuelos/${id}`);
  caja.innerHTML = `<dl><dt>Avión</dt><dd>${esc(v.avion.modelo)} · ${esc(v.avion.matricula)} · ${v.avion.capacidad} asientos</dd>
    <dt>Pilotos</dt><dd>${v.pilotos.map(esc).join(", ") || "—"}</dd>
    <dt>Cabina</dt><dd>${v.tcp.map(esc).join(", ") || "—"}</dd>
    <dt>Puerta</dt><dd>${esc(v.puerta || "por asignar")}</dd></dl>`;
  caja.hidden = false;
  boton.setAttribute("aria-expanded", "true");
}

/* ---------- recorrido A: pases de abordar ---------- */

const SELLO = { reservada: ["aviso", "Reservada"], comprado: ["ok", "Comprado"], abordado: ["info", "Abordó"], cancelado: ["malo", "Cancelado"] };

async function vistaReservas() {
  await cargarRutas();
  const { reservas } = await api("GET", "/api/reservas");
  const agente = estado.actor.tipo === "agente";
  const ahora = new Date();
  const pase = (r) => {
    const [clase, texto] = SELLO[r.estado];
    const t = r.tiquete, v = r.vuelo;
    const yaSalio = aFecha(v.salida_programada) <= ahora;
    return `<article class="pase ${t ? "" : "pase--reserva"}">
      <span class="pase__notch pase__notch--a"></span><span class="pase__notch pase__notch--b"></span>
      <div class="pase__cuerpo">
        <div class="pase__marca">Data-Delta Airlines · ${t ? "Pase de abordar" : "Reserva"}</div>
        <span class="sello sello--${clase}">${texto}</span>
        <div class="ruta">
          <div class="ruta__ciudad"><strong>${esc(v.origen.codigo)}</strong><span>${esc(v.origen.ciudad)}</span></div>
          <span class="ruta__flecha" aria-hidden="true">✈</span>
          <div class="ruta__ciudad"><strong>${esc(v.destino.codigo)}</strong><span>${esc(v.destino.ciudad)}</span></div>
        </div>
        <dl class="pase__datos">
          <div><dt>Pasajero</dt><b>${esc(r.cliente.nombre)}</b></div>
          <div><dt>Vuelo</dt><b>Vuelo ${esc(v.numero_vuelo)}</b></div>
          <div><dt>Salida</dt><b>${esc(dia(v.salida_programada))} ${esc(hora(v.salida_programada))}</b></div>
          <div><dt>Llegada</dt><b>${esc(hora(v.llegada_programada))}</b></div>
          <div><dt>Puerta</dt><b>${esc(v.puerta || "—")}</b></div>
          <div><dt>Millas</dt><b>${num(v.millas, 0)}</b></div>
          <div><dt>Reserva</dt><b>#${r.id_reserva}</b></div>
          ${t?.etiquetas.length ? `<div><dt>Maletas</dt><b>${t.etiquetas.map((e) => `<a href="#" data-accion="rastrear" data-etiqueta="${esc(e)}">${esc(e)}</a>`).join(" · ")}</b></div>` : ""}
        </dl>
      </div>
      <div class="pase__talon">
        <div class="pase__talon-cuerpo">
          <div class="pase__valor"><small>${t ? "Pagado" : "A pagar"}</small>${usd(t ? t.valor : v.valor)}</div>
          ${t ? `<div class="codigo-barras" role="img" aria-label="Código de barras del tiquete ${t.id_tiquete}" style="background-position:${(t.id_tiquete * 7) % 13}px 0"></div>
          <div class="mono ayuda">TIQUETE #${t.id_tiquete}</div>` : '<div class="ayuda">Aún sin tiquete</div>'}
        </div>
      </div>
      ${(r.estado === "reservada" || r.estado === "comprado") && !yaSalio ? `<div class="pase__acciones">
        ${r.estado === "reservada" ? `<button type="button" class="boton" data-accion="comprar" data-reserva="${r.id_reserva}">Comprar tiquete</button>` : ""}
        ${r.estado === "comprado" ? `<button type="button" class="boton boton--peligro" data-accion="cancelar" data-tiquete="${t.id_tiquete}">Cancelar tiquete</button>` : ""}
      </div>` : ""}
    </article>`;
  };
  const proximos = reservas.filter((r) => aFecha(r.vuelo.salida_programada) > ahora);
  const anteriores = reservas.filter((r) => aFecha(r.vuelo.salida_programada) <= ahora).reverse();
  const seccion = (titulo, lista) => lista.length ? `<h2 style="margin-top:1.5rem">${titulo}</h2><div class="rejilla">${lista.map(pase).join("")}</div>` : "";
  $("#principal").innerHTML = `<h1>Mis reservas y tiquetes</h1>
    ${agente ? '<p class="ayuda">Reservas que usted gestiona, a nombre de sus clientes.</p>' : ""}
    ${seccion("Próximos viajes", proximos)}${seccion("Viajes anteriores", anteriores)}
    ${reservas.length ? "" : vacio("Todavía no tiene reservas. Busque un vuelo y reserve el primero.")}`;
}

/* ---------- recorrido B: aeropuerto ---------- */

async function vistaAeropuerto(idVuelo = estado.vueloAeropuerto) {
  const consulta = idVuelo ? `?vuelo=${idVuelo}` : "";
  const { vuelos, seleccionado, tiquetes } = await api("GET", `/api/tiquetes${consulta}`);
  estado.vueloAeropuerto = seleccionado;
  const yo = estado.actor.id;
  const maleta = (m) => {
    const ult = m.escaneos[m.escaneos.length - 1];
    const aqui = ult && ult.id_aeropuerto === yo;
    return `<div class="maleta"><code>${esc(m.etiqueta)}</code><span>${m.peso_kg} kg</span>
      <span class="ayuda mono">${m.escaneos.map((s) => esc(s.codigo)).join(" → ")}</span>
      <button type="button" class="boton boton--sec boton--chico" data-accion="escanear" data-equipaje="${m.id_equipaje}" ${aqui ? 'disabled title="Ya se leyó aquí por última vez"' : ""}>Escanear aquí</button></div>`;
  };
  const pasajero = (r, sale) => {
    const t = r.tiquete;
    return `<div class="pasajero"><div class="pasajero__cabecera">
        <span><strong>${esc(r.cliente.nombre)}</strong> · tiquete #${t.id_tiquete}</span>
        <span class="chip ${t.abordado ? "chip--ok" : "chip--aviso"}">${t.abordado ? "Abordó" : "Sin abordar"}</span></div>
      ${t.equipaje.map(maleta).join("")}
      ${sale ? `<div class="recibir">
        ${t.abordado ? "" : `<button type="button" class="boton boton--chico" data-accion="abordar" data-tiquete="${t.id_tiquete}">Registrar abordaje</button>`}
        ${t.equipaje.length < 3 ? `<input type="number" min="1" max="32" step="0.5" value="15" aria-label="Peso de la maleta en kg" id="peso-${t.id_tiquete}">
          <button type="button" class="boton boton--sec boton--chico" data-accion="recibir" data-tiquete="${t.id_tiquete}">Recibir maleta</button>` : '<span class="ayuda">Máximo de maletas alcanzado</span>'}
      </div>` : ""}</div>`;
  };
  const opcion = (v) => {
    const sale = v.id_aeropuerto_origen === yo;
    return `<option value="${v.id_vuelo}" ${v.id_vuelo === seleccionado ? "selected" : ""}>${esc(dia(v.salida_programada))} ${esc(hora(v.salida_programada))} · ${esc(v.numero_vuelo)} · ${
      sale ? `sale hacia ${esc(v.d_ciudad)}` : `llega desde ${esc(v.o_ciudad)}`} (${v.pasajeros} pasajeros)</option>`;
  };
  const actual = vuelos.find((v) => v.id_vuelo === seleccionado);
  const sale = actual && actual.id_aeropuerto_origen === yo;
  const codigo = codigoDe(estado.actor.nombre);
  $("#principal").innerHTML = `<div class="banner"><img src="${foto(codigo)}" alt=""><div class="banner__texto">
      <h1>Embarque y equipaje</h1><p>${esc(estado.actor.nombre)}</p></div></div>
    <p class="ayuda">El abordaje y la recepción de maletas se hacen en el aeropuerto de origen del vuelo; la lectura de una maleta, en el origen o en el destino.</p>
    ${vuelos.length ? `<div class="filtros"><label class="campo">Vuelo<select id="selector-vuelo">${vuelos.map(opcion).join("")}</select></label></div>
      <section class="tarjeta grupo"><div class="grupo__titulo"><h2>${sale ? "Sale de aquí" : "Llega aquí"} · ${esc(actual.numero_vuelo)}</h2>
        <span class="ayuda mono">${esc(actual.o_ciudad)} → ${esc(actual.d_ciudad)}</span></div>
        ${tiquetes.map((r) => pasajero(r, sale)).join("")}</section>`
      : vacio("No hay tiquetes para vuelos de este aeropuerto. Compre uno como cliente para un vuelo que salga de aquí.")}`;
}

function vistaRastreo(etiqueta = "") {
  $("#principal").innerHTML = `<h1>Rastrear una maleta</h1>
    <div class="rastro-hero"><form id="form-rastreo" class="filtros"><label class="campo">Etiqueta de la maleta
      <input name="etiqueta" value="${esc(etiqueta)}" placeholder="Por ejemplo DL00012-1" autocomplete="off"></label>
      <button type="submit" class="boton">Rastrear</button></form>${ILUSTRACION_MALETA}</div>
    <div id="rastro"></div>`;
  if (etiqueta) return rastrear(etiqueta);
}

async function rastrear(etiqueta) {
  const { maleta: m } = await api("GET", `/api/equipaje?etiqueta=${encodeURIComponent(etiqueta)}`);
  $("#rastro").innerHTML = `<article class="tarjeta"><span class="etiqueta-maleta">${esc(m.etiqueta)}</span>
    <h2 style="margin-top:.6rem"><span class="chip chip--info">${esc(m.estado)}</span></h2>
    <div class="ayuda mono">Pasajero: ${esc(m.pasajero)} · Vuelo ${esc(m.vuelo)} · ${esc(m.origen)} → ${esc(m.destino)} · ${m.peso_kg} kg</div>
    <ol class="linea-tiempo">${m.escaneos.map((s) => `<li><strong>${esc(s.ciudad)} (${esc(s.codigo)})</strong>
      <small>${esc(dia(s.fecha_hora))} · ${esc(hora(s.fecha_hora))}</small></li>`).join("")}</ol></article>`;
}

/* ---------- recorrido C: analítica (Data Warehouse) ---------- */

const REPORTES = {
  ingresos: { req: "4a", titulo: "Ingresos por venta de tiquetes", fila: "Ciudad", unidad: (v) => usd(v), celda: (v) => num(v),
    nota: "Un registro por tiquete no cancelado; el mes es el de la compra y la ciudad la de origen del vuelo." },
  reservaciones: { req: "4b", titulo: "Reservaciones", fila: "Ciudad", unidad: (v) => num(v), celda: (v) => num(v),
    nota: "Un registro por reserva, haya llegado o no a tiquete; el mes es el de la reserva y la ciudad la de origen del vuelo." },
  millas: { req: "4c", titulo: "Millas acumuladas en vuelos nacionales", fila: "Pasajero", unidad: (v) => `${num(v, 1)} mi`, celda: (v) => num(v),
    nota: "Un registro por abordaje; las millas son la distancia del trayecto y solo cuentan los vuelos cuyo origen y destino están en el mismo país." },
};

function tablaCalor(rep, def) {
  const max = Math.max(1, ...rep.filas.flatMap((f) => f.valores));
  const celda = (v) => {
    if (!v) return '<td class="celda" style="color:var(--suave)">·</td>';
    const alfa = 0.1 + 0.82 * (v / max);
    return `<td class="celda" style="background:color-mix(in srgb, var(--rojo) ${Math.round(alfa * 100)}%, transparent);${alfa > 0.55 ? "color:var(--rojo-sobre)" : ""}">${def.celda(v)}</td>`;
  };
  const etiqueta = (f) => {
    const a = estado.aeropuertos.find((x) => x.ciudad === f.etiqueta);
    return a ? `<span class="persona"><img src="${foto(a.codigo, true)}" alt=""><span>${esc(f.etiqueta)}<small>${esc(f.detalle)}</small></span></span>`
      : `${esc(f.etiqueta)}<small>${esc(f.detalle)}</small>`;
  };
  return `<div class="mapa-calor"><table><thead><tr><th>${def.fila}</th>${rep.meses.map((m) => `<th>${m}</th>`).join("")}<th>Total</th></tr></thead>
    <tbody>${rep.filas.map((f) => `<tr><td>${etiqueta(f)}</td>${f.valores.map(celda).join("")}<td class="total">${def.celda(f.total)}</td></tr>`).join("")}</tbody>
    <tfoot><tr><td>Total</td>${rep.totales_mes.map((v) => `<td>${v ? def.celda(v) : "·"}</td>`).join("")}<td class="total">${def.celda(rep.total)}</td></tr></tfoot></table></div>`;
}

function graficoMeses(rep) {
  const max = Math.max(1, ...rep.totales_mes), alto = 120;
  const barras = rep.totales_mes.map((v, i) => {
    const h = (v / max) * alto, x = 14 + i * 47;
    return `<rect class="barra-m ${v === max && v > 0 ? "barra-m--max" : ""}" x="${x}" y="${alto - h + 12}" width="34" height="${Math.max(h, 1)}"><title>${rep.meses[i]}: ${v}</title></rect>
      <text x="${x + 17}" y="${alto + 28}" text-anchor="middle">${rep.meses[i]}</text>${v ? `<text x="${x + 17}" y="${alto - h + 8}" text-anchor="middle">${num(v)}</text>` : ""}`;
  });
  return `<div class="barras"><svg viewBox="0 0 580 ${alto + 36}" role="img" aria-label="Total por mes">${barras.join("")}</svg></div>`;
}

async function vistaAnalitica() {
  await cargarRutas();
  const dw = await api("GET", "/api/dw");
  const e = estado.info.esquema, filas = dw.filas;
  const nombres = Object.keys(filas);
  const caja = `<div class="tarjeta flujo__caja"><h2>Data Warehouse <small>${e.dw.tablas} tablas · ${e.dw.llaves_foraneas} FK</small></h2>
    <table class="tabla-dw">${nombres.map((n) => `<tr class="${n.startsWith("facts") ? "hecho" : ""}"><td>${n}</td><td>${num(filas[n])}</td></tr>`).join("")}</table></div>`;
  const flecha = `<div class="flujo__flecha"><svg viewBox="0 0 160 26" aria-hidden="true"><path d="M2 13 H148 M138 4 L152 13 L138 22" fill="none" stroke="currentColor" stroke-width="2.5"/></svg>
    <button type="button" class="boton" data-accion="cargar-dw">${dw.cargado ? "Recargar el DW" : "Cargar el DW"}</button>
    <span class="ayuda">Extracción, transformación y carga desde la base</span></div>`;
  const base = `<div class="tarjeta flujo__caja"><h2>Base transaccional <small>${e.tablas} tablas · ${e.llaves_foraneas} FK</small></h2>
    <p class="ayuda">Aquí se vende, se aborda y se escanean las maletas. El DW solo recibe lo que la base ya tiene.</p>
    <table class="tabla-dw"><tr><td>reserva</td><td>→ facts_reservaciones</td></tr><tr><td>tiquete</td><td>→ facts_ingresos</td></tr>
    <tr><td>abordaje, vuelo</td><td>→ facts_millas</td></tr><tr><td>ciudad, cliente, vuelo</td><td>→ dimensiones</td></tr></table></div>`;
  let cuerpo = '<p class="ayuda">El Data Warehouse está vacío. Cárguelo para ver los reportes de ingresos, reservaciones y millas.</p>';
  if (dw.cargado) {
    const rep = await api("GET", `/api/dw/${estado.reporte}${estado.anioDw ? `?anio=${estado.anioDw}` : ""}`);
    estado.anioDw = rep.anio;
    const def = REPORTES[estado.reporte];
    const v = rep.verificacion;
    cuerpo = `<div class="segmentos" role="group" aria-label="Reporte">${Object.entries(REPORTES).map(([id, d]) =>
        `<button type="button" data-accion="reporte" data-reporte="${id}" aria-pressed="${id === estado.reporte}">${d.req} ${d.titulo.split(" ")[0]}</button>`).join("")}</div>
      <div class="tarjeta"><div class="reporte__cabecera"><div><h2>${def.req} · ${def.titulo}</h2><p class="ayuda">${def.nota}</p></div>
        <label class="campo">Año<select id="anio-dw">${rep.anios.map((a) => `<option ${a === rep.anio ? "selected" : ""}>${a}</option>`).join("")}</select></label></div>
        <p class="cuadre ${v.coinciden ? "cuadre--ok" : "cuadre--mal"}">${v.coinciden ? "✓" : "✗"} Total del DW ${def.unidad(v.dw)} · calculado directo en la base ${def.unidad(v.base)}
          ${v.coinciden ? "· coinciden" : "· NO coinciden"}</p>
        ${tablaCalor(rep, def)}${graficoMeses(rep)}
        ${estado.reporte === "millas" ? `<p class="ayuda">Quedaron fuera ${num(rep.millas_internacionales_excluidas, 1)} millas de vuelos internacionales.</p>` : ""}
        <details class="consulta"><summary>Consulta ejecutada sobre el DW</summary><pre>${esc(rep.consulta)}</pre></details></div>`;
  }
  $("#principal").innerHTML = `<h1>Analítica · Data Warehouse</h1>
    <div class="flujo">${base}${flecha}${caja}</div>${cuerpo}`;
}

const VISTAS = { inicio: vistaInicio, vuelos: vistaVuelos, reservas: vistaReservas, aeropuerto: vistaAeropuerto,
  rastreo: () => vistaRastreo(), analitica: vistaAnalitica };

/* ---------- eventos ---------- */

document.addEventListener("click", (e) => {
  if (e.target.closest("#tema")) return void alternarTema();
  const ir_ = e.target.closest("[data-ir]");
  if (ir_) return void ir(ir_.dataset.ir);
  const boton = e.target.closest("[data-accion]");
  if (!boton) return;
  e.preventDefault();
  const d = boton.dataset;
  hacer(async () => {
    switch (d.accion) {
      case "salir": return salir();
      case "entrar-tarjeta": {
        const id = $(`[data-entrada="${d.tipo}"]`).value;
        return entrar(`${d.tipo}:${id}`);
      }
      case "mapa-aeropuerto":
        estado.filtros.origen = String(estado.filtros.origen) === d.id ? "" : d.id;
        return ir("vuelos");
      case "destino":
        estado.filtros = { origen: "", destino: d.id, fecha: "" };
        return ir("vuelos");
      case "detalle": return alternarDetalle(d.vuelo, boton);
      case "reservar": {
        const cuerpo = { id_vuelo: Number(d.vuelo) };
        if (estado.actor.tipo === "agente") {
          estado.clienteDelAgente = $("#cliente-agente").value;
          cuerpo.id_cliente = Number(estado.clienteDelAgente);
        }
        const r = await api("POST", "/api/reservas", cuerpo);
        aviso(r.mensaje);
        return ir("reservas");
      }
      case "comprar": aviso((await api("POST", `/api/reservas/${d.reserva}/tiquete`)).mensaje); return vistaReservas();
      case "cancelar":
        if (!confirm("¿Cancelar este tiquete? El cupo queda libre y no podrá deshacerse.")) return;
        aviso((await api("POST", `/api/tiquetes/${d.tiquete}/cancelar`)).mensaje);
        return vistaReservas();
      case "abordar": aviso((await api("POST", `/api/tiquetes/${d.tiquete}/abordaje`)).mensaje); return vistaAeropuerto();
      case "recibir": {
        const peso = $(`#peso-${d.tiquete}`).value;
        aviso((await api("POST", `/api/tiquetes/${d.tiquete}/equipaje`, { peso_kg: Number(peso) })).mensaje);
        return vistaAeropuerto();
      }
      case "escanear": aviso((await api("POST", `/api/equipaje/${d.equipaje}/escaneos`)).mensaje); return vistaAeropuerto();
      case "rastrear": estado.vista = "rastreo"; dibujarNav(); return vistaRastreo(d.etiqueta);
      case "cargar-dw": aviso((await api("POST", "/api/dw/cargar")).mensaje); return vistaAnalitica();
      case "reporte": estado.reporte = d.reporte; return vistaAnalitica();
    }
  });
});

document.addEventListener("submit", (e) => {
  if (e.target.id === "filtros") {
    e.preventDefault();
    const datos = new FormData(e.target);
    estado.filtros = { origen: datos.get("origen"), destino: datos.get("destino"), fecha: datos.get("fecha") };
    hacer(buscarVuelos);
  } else if (e.target.id === "form-rastreo") {
    e.preventDefault();
    hacer(() => rastrear(new FormData(e.target).get("etiqueta")));
  }
});

document.addEventListener("change", (e) => {
  if (e.target.id === "selector-actor" && e.target.value) hacer(() => entrar(e.target.value));
  if (e.target.id === "cliente-agente") estado.clienteDelAgente = e.target.value;
  if (e.target.id === "selector-vuelo") hacer(() => vistaAeropuerto(Number(e.target.value)));
  if (e.target.id === "anio-dw") { estado.anioDw = e.target.value; hacer(vistaAnalitica); }
});

/* ---------- inicio ---------- */

/** Créditos de las fotos (autor y licencia de Wikimedia Commons) al pie de la página. */
async function pintarCreditos() {
  try {
    const r = await fetch("img/ciudades/creditos.json", { cache: "no-cache" });
    const creditos = await r.json();
    $("#creditos").innerHTML = "Fotografías de Wikimedia Commons: " + Object.values(creditos).map((c) =>
      `${esc(c.ciudad)}, <a href="${esc(c.pagina)}" target="_blank" rel="noopener">${esc(c.autor.replace(/\s*\(more photos\)\s*/i, ""))}</a> (${esc(c.licencia)})`).join("; ") + ".";
  } catch (e) { console.error("No se pudieron leer los créditos de las fotos", e); }
}

async function iniciar() {
  try {
    pintarBotonTema();
    pintarCreditos();
    estado.usuarios = await api("GET", "/api/demo/usuarios");
    estado.info = await api("GET", "/api/info");
    const e = estado.info.esquema;
    $("#pie-bd").textContent = `Base verificada contra el script de Enterprise Architect: ${e.tablas} tablas · ${e.llaves_foraneas} llaves foráneas · ${e.unicos} únicas. Data Warehouse: ${e.dw.tablas} tablas · ${e.dw.llaves_foraneas} llaves foráneas. Modo ${estado.info.modo}.`;
    const guardado = (() => { try { return JSON.parse(sessionStorage.getItem("data-delta:actor")); } catch { return null; } })();
    if (guardado) {
      try { estado.actor = (await api("POST", "/api/sesion", guardado)).actor; } catch { estado.actor = null; }
    } else {
      estado.actor = (await api("GET", "/api/sesion")).actor;
    }
    dibujarSesion();
    await ir(!estado.actor ? "inicio" : estado.actor.tipo === "aeropuerto" ? "aeropuerto" : "vuelos");
  } catch (e) {
    console.error(e);
    $("#principal").innerHTML = `<div class="tarjeta vacio"><h2>No se pudo cargar el prototipo</h2><p>${esc(e.message)}</p></div>`;
  }
}

iniciar();
