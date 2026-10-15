/* Interfaz de Data-Delta Airlines. Una sola página; todo pasa por la API JSON /api/...
 * Recorrido A (cliente y agente): buscar vuelo -> reservar -> comprar tiquete -> cancelar.
 * Recorrido B (aeropuerto): abordaje -> recibir maletas -> escanear -> rastrear por etiqueta. */
"use strict";

const estado = { actor: null, usuarios: null, vueloAeropuerto: null, aeropuertos: [], vista: "inicio", info: null,
  filtros: { origen: "", destino: "", fecha: "" }, clienteDelAgente: "", vuelos: null };

const $ = (selector) => document.querySelector(selector);
const esc = (t) => String(t ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const usd = (n) => new Intl.NumberFormat("es-CO", { style: "currency", currency: "USD" }).format(n);
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

/* ---------- sesión y navegación ---------- */

function menu() {
  if (!estado.actor) return [["inicio", "Inicio"], ["vuelos", "Vuelos"], ["rastreo", "Rastrear maleta"]];
  if (estado.actor.tipo === "aeropuerto") {
    return [["aeropuerto", "Embarque y equipaje"], ["vuelos", "Vuelos"], ["rastreo", "Rastrear maleta"]];
  }
  return [["vuelos", "Buscar vuelos"], ["reservas", "Mis reservas"], ["rastreo", "Rastrear maleta"]];
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
    ? `<span>Entró como <strong>${esc(a.nombre)}</strong> <span class="chip chip--info">${esc(TIPO_ACTOR[a.tipo])}</span></span>
       <button type="button" class="boton boton--sec boton--chico" data-accion="salir">Salir</button>`
    : `<label class="campo">
       <select id="selector-actor" aria-label="Entrar como">${opcionesActores()}</select></label>`;
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

/* ---------- vistas ---------- */

function vistaInicio() {
  const u = estado.usuarios;
  const tarjeta = (titulo, texto, tipo, opciones) => `
    <div class="tarjeta"><h2>${titulo}</h2><p class="ayuda">${texto}</p>
      <select data-entrada="${tipo}" aria-label="${esc(titulo)}">${opciones}</select>
      <button type="button" class="boton" data-accion="entrar-tarjeta" data-tipo="${tipo}">Entrar</button></div>`;
  $("#principal").innerHTML = `
    <section class="heroe">
      <h1>Reserve, compre y siga su maleta</h1>
      <p>Prototipo de Data-Delta Airlines sobre el modelo relacional del Parcial 2: dos recorridos completos, de la interfaz a la base de datos.
      No hay claves: elija con quién entrar.</p>
    </section>
    <div class="entradas">
      ${tarjeta("Soy cliente", "Busque un vuelo, reserve, compre su tiquete y cancélelo si cambia de plan.", "cliente",
        u.clientes.map((c) => `<option value="${c.id_cliente}">${esc(c.nombre)}</option>`).join(""))}
      ${tarjeta("Soy agente de viaje", "Reserve y venda a nombre de un cliente; gestiona sus tiquetes.", "agente",
        u.agentes.map((a) => `<option value="${a.id_agente_viaje}">${esc(a.nombre)}</option>`).join(""))}
      ${tarjeta("Trabajo en un aeropuerto", "Registre el abordaje, reciba maletas y escanéelas en el origen y en el destino.", "aeropuerto",
        u.aeropuertos.map((a) => `<option value="${a.id_aeropuerto}">${esc(a.ciudad)} (${esc(a.codigo)})</option>`).join(""))}
    </div>
    <div class="pasos">
      <div class="tarjeta"><h3>Recorrido A · Comprar y cancelar</h3><ol>
        <li>Buscar un vuelo por origen, destino y fecha.</li><li>Reservar (el cupo aún no se ocupa).</li>
        <li>Comprar el tiquete: el valor sale de la distancia entre aeropuertos.</li><li>Cancelar mientras no haya abordado.</li></ol></div>
      <div class="tarjeta"><h3>Recorrido B · Abordaje y maletas</h3><ol>
        <li>En el aeropuerto de origen: registrar el abordaje y recibir cada maleta (queda su primera lectura).</li>
        <li>En el destino: escanear la maleta (solo si el pasajero abordó).</li><li>Cualquiera puede rastrear una maleta por su etiqueta.</li></ol></div>
    </div>`;
}

const tarjetaVuelo = (v) => {
  const a = estado.actor;
  const puedeReservar = a && (a.tipo === "cliente" || a.tipo === "agente");
  return `<article class="tarjeta"><div class="vuelo">
    <div>
      <div class="ruta">
        <div class="ruta__ciudad"><strong>${esc(v.origen.codigo)}</strong><span>${esc(v.origen.ciudad)} · ${esc(hora(v.salida_programada))}</span></div>
        <span class="ruta__flecha" aria-hidden="true">→</span>
        <div class="ruta__ciudad"><strong>${esc(v.destino.codigo)}</strong><span>${esc(v.destino.ciudad)} · ${esc(hora(v.llegada_programada))}</span></div>
      </div>
      <div class="meta"><span>${esc(dia(v.salida_programada))}</span><span>Vuelo ${esc(v.numero_vuelo)}</span>
        <span>${esc(duracion(v.salida_programada, v.llegada_programada))}</span><span>${v.millas.toLocaleString("es-CO")} millas</span>
        <span class="chip ${v.nacional ? "chip--info" : "chip--aviso"}">${v.nacional ? "Nacional" : "Internacional"}</span>
        <span class="chip ${v.cupos_libres > 10 ? "chip--ok" : v.cupos_libres > 0 ? "chip--aviso" : "chip--malo"}">${v.cupos_libres} cupos</span></div>
    </div>
    <div class="precio"><strong>${usd(v.valor)}</strong><span>por pasajero</span></div>
    <div class="acciones">
      ${puedeReservar ? `<button type="button" class="boton" data-accion="reservar" data-vuelo="${v.id_vuelo}">Reservar</button>` : ""}
      <button type="button" class="boton boton--sec" data-accion="detalle" data-vuelo="${v.id_vuelo}" aria-expanded="false">Ver detalle</button>
    </div>
    <div class="detalle" id="detalle-${v.id_vuelo}" hidden></div>
  </div></article>`;
};

async function vistaVuelos() {
  if (!estado.aeropuertos.length) estado.aeropuertos = (await api("GET", "/api/aeropuertos")).aeropuertos;
  const f = estado.filtros;
  const lista = (sel) => `<option value="">Cualquiera</option>` + estado.aeropuertos.map((a) =>
    `<option value="${a.id_aeropuerto}" ${String(a.id_aeropuerto) === String(sel) ? "selected" : ""}>${esc(a.ciudad)} (${esc(a.codigo)})</option>`).join("");
  const agente = estado.actor?.tipo === "agente";
  $("#principal").innerHTML = `
    <h1>Vuelos disponibles</h1>
    <form id="filtros" class="filtros">
      <label class="campo">Origen<select name="origen">${lista(f.origen)}</select></label>
      <label class="campo">Destino<select name="destino">${lista(f.destino)}</select></label>
      <label class="campo">Fecha<input type="date" name="fecha" value="${esc(f.fecha)}"></label>
      ${agente ? `<label class="campo">Reservar a nombre de<select name="cliente" id="cliente-agente">${
        estado.usuarios.clientes.map((c) => `<option value="${c.id_cliente}" ${String(c.id_cliente) === String(estado.clienteDelAgente) ? "selected" : ""}>${esc(c.nombre)}</option>`).join("")}</select></label>` : ""}
      <button type="submit" class="boton">Buscar</button>
    </form>
    <div id="resultados" class="rejilla"></div>
    ${estado.actor ? "" : '<p class="ayuda">Para reservar, entre como cliente o agente de viaje.</p>'}`;
  await buscarVuelos();
}

async function buscarVuelos() {
  const f = estado.filtros;
  const consulta = new URLSearchParams(Object.entries(f).filter(([, v]) => v)).toString();
  const { vuelos } = await api("GET", `/api/vuelos${consulta ? "?" + consulta : ""}`);
  estado.vuelos = vuelos;
  $("#resultados").innerHTML = vuelos.length ? vuelos.map(tarjetaVuelo).join("")
    : '<div class="tarjeta vacio">No hay vuelos con esos filtros. Pruebe con otra fecha o quite algún filtro.</div>';
}

async function alternarDetalle(id, boton) {
  const caja = $(`#detalle-${id}`);
  if (!caja.hidden) { caja.hidden = true; boton.setAttribute("aria-expanded", "false"); return; }
  const { vuelo: v } = await api("GET", `/api/vuelos/${id}`);
  caja.innerHTML = `<dl><dt>Avión</dt><dd>${esc(v.avion.modelo)} · ${esc(v.avion.matricula)} · ${v.avion.capacidad} asientos</dd>
    <dt>Pilotos</dt><dd>${v.pilotos.map(esc).join(", ") || "—"}</dd>
    <dt>Tripulación de cabina</dt><dd>${v.tcp.map(esc).join(", ") || "—"}</dd>
    <dt>Puerta</dt><dd>${esc(v.puerta || "por asignar")}</dd></dl>`;
  caja.hidden = false;
  boton.setAttribute("aria-expanded", "true");
}

const CHIP_ESTADO = { reservada: ["aviso", "Reservada"], comprado: ["ok", "Tiquete comprado"],
  abordado: ["info", "Abordó"], cancelado: ["malo", "Cancelado"] };

async function vistaReservas() {
  const { reservas } = await api("GET", "/api/reservas");
  const agente = estado.actor.tipo === "agente";
  const ahora = new Date();
  const tarjeta = (r) => {
    const [clase, texto] = CHIP_ESTADO[r.estado];
    const t = r.tiquete, v = r.vuelo;
    const yaSalio = aFecha(v.salida_programada) <= ahora;
    return `<article class="tarjeta"><div class="vuelo">
      <div>
        <div class="ruta"><div class="ruta__ciudad"><strong>${esc(v.origen.codigo)}</strong><span>${esc(v.origen.ciudad)} · ${esc(hora(v.salida_programada))}</span></div>
          <span class="ruta__flecha" aria-hidden="true">→</span>
          <div class="ruta__ciudad"><strong>${esc(v.destino.codigo)}</strong><span>${esc(v.destino.ciudad)} · ${esc(hora(v.llegada_programada))}</span></div></div>
        <div class="meta"><span>${esc(dia(v.salida_programada))}</span><span>Vuelo ${esc(v.numero_vuelo)}</span>
          ${agente ? `<span>Pasajero: <strong>${esc(r.cliente.nombre)}</strong></span>` : ""}
          <span>Reserva #${r.id_reserva}</span>${t ? `<span>Tiquete #${t.id_tiquete}</span>` : ""}
          ${t?.etiquetas.length ? `<span>Maletas: ${t.etiquetas.map((e) => `<a href="#" data-accion="rastrear" data-etiqueta="${esc(e)}">${esc(e)}</a>`).join(", ")}</span>` : ""}</div>
      </div>
      <div class="precio"><span class="chip chip--${clase}">${texto}</span><strong>${usd(t ? t.valor : v.valor)}</strong><span>${t ? "pagado" : "a pagar"}</span></div>
      <div class="acciones">
        ${r.estado === "reservada" && !yaSalio ? `<button type="button" class="boton" data-accion="comprar" data-reserva="${r.id_reserva}">Comprar tiquete</button>` : ""}
        ${r.estado === "comprado" && !yaSalio ? `<button type="button" class="boton boton--peligro" data-accion="cancelar" data-tiquete="${t.id_tiquete}">Cancelar tiquete</button>` : ""}
      </div></div></article>`;
  };
  const proximos = reservas.filter((r) => aFecha(r.vuelo.salida_programada) > ahora);
  const anteriores = reservas.filter((r) => aFecha(r.vuelo.salida_programada) <= ahora).reverse();
  const seccion = (titulo, lista) => lista.length ? `<h2>${titulo}</h2><div class="rejilla">${lista.map(tarjeta).join("")}</div>` : "";
  $("#principal").innerHTML = `<h1>Mis reservas y tiquetes</h1>
    ${seccion("Próximos viajes", proximos)}${seccion("Viajes anteriores", anteriores)}
    ${reservas.length ? "" : '<div class="tarjeta vacio">Todavía no tiene reservas. Busque un vuelo y reserve el primero.</div>'}`;
}

async function vistaAeropuerto(idVuelo = estado.vueloAeropuerto) {
  const consulta = idVuelo ? `?vuelo=${idVuelo}` : "";
  const { vuelos, seleccionado, tiquetes } = await api("GET", `/api/tiquetes${consulta}`);
  estado.vueloAeropuerto = seleccionado;
  const yo = estado.actor.id;
  const maleta = (m) => {
    const ult = m.escaneos[m.escaneos.length - 1];
    const aqui = ult && ult.id_aeropuerto === yo;
    return `<div class="maleta"><code>${esc(m.etiqueta)}</code><span>${m.peso_kg} kg</span>
      <span class="ayuda">${m.escaneos.map((s) => esc(s.codigo)).join(" → ")}</span>
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
  $("#principal").innerHTML = `<h1>Embarque y equipaje · ${esc(estado.actor.nombre)}</h1>
    <p class="ayuda">El abordaje y la recepción de maletas se hacen en el aeropuerto de origen del vuelo; la lectura de una maleta, en el origen o en el destino.</p>
    ${vuelos.length ? `<div class="filtros"><label class="campo">Vuelo<select id="selector-vuelo">${vuelos.map(opcion).join("")}</select></label></div>
      <section class="tarjeta grupo"><div class="grupo__titulo"><h2>${sale ? "Sale de aquí" : "Llega aquí"} · ${esc(actual.numero_vuelo)}</h2>
        <span class="ayuda">${esc(actual.o_ciudad)} → ${esc(actual.d_ciudad)}</span></div>
        ${tiquetes.map((r) => pasajero(r, sale)).join("")}</section>`
      : '<div class="tarjeta vacio">No hay tiquetes para vuelos de este aeropuerto. Compre uno como cliente para un vuelo que salga de aquí.</div>'}`;
}

function vistaRastreo(etiqueta = "") {
  $("#principal").innerHTML = `<h1>Rastrear una maleta</h1>
    <form id="form-rastreo" class="filtros"><label class="campo">Etiqueta de la maleta
      <input name="etiqueta" value="${esc(etiqueta)}" placeholder="Por ejemplo DL00012-1" autocomplete="off"></label>
      <button type="submit" class="boton">Rastrear</button></form>
    <div id="rastro"></div>`;
  if (etiqueta) return rastrear(etiqueta);
}

async function rastrear(etiqueta) {
  const { maleta: m } = await api("GET", `/api/equipaje?etiqueta=${encodeURIComponent(etiqueta)}`);
  $("#rastro").innerHTML = `<article class="tarjeta"><h2>${esc(m.etiqueta)} <span class="chip chip--info">${esc(m.estado)}</span></h2>
    <div class="meta"><span>Pasajero: ${esc(m.pasajero)}</span><span>Vuelo ${esc(m.vuelo)}</span>
      <span>${esc(m.origen)} → ${esc(m.destino)}</span><span>${m.peso_kg} kg</span></div>
    <ol class="linea-tiempo">${m.escaneos.map((s) => `<li><strong>${esc(s.ciudad)} (${esc(s.codigo)})</strong>
      <small>${esc(dia(s.fecha_hora))} · ${esc(hora(s.fecha_hora))}</small></li>`).join("")}</ol></article>`;
}

const VISTAS = { inicio: vistaInicio, vuelos: vistaVuelos, reservas: vistaReservas, aeropuerto: vistaAeropuerto, rastreo: () => vistaRastreo() };

/* ---------- eventos ---------- */

document.addEventListener("click", (e) => {
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
});

/* ---------- inicio ---------- */

async function iniciar() {
  try {
    estado.usuarios = await api("GET", "/api/demo/usuarios");
    estado.info = await api("GET", "/api/info");
    const e = estado.info.esquema;
    $("#pie-bd").textContent = `Base de datos verificada contra el script de Enterprise Architect: ${e.tablas} tablas · ${e.llaves_foraneas} llaves foráneas · ${e.unicos} restricciones únicas · modo ${estado.info.modo}.`;
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
