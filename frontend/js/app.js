const HORAS = [
  "09:00",
  "10:00",
  "11:00",
  "12:00",
  "14:00",
  "15:00",
  "16:00",
  "17:00",
  "18:00",
];

let usuarioActual = null;
let serviciosDisponibles = [];
let barberosDisponibles = [];
let csrfToken = "";

function escapar(texto) {
  return String(texto ?? "").replace(/[&<>"']/g, (caracter) => ({
    "&": "&amp;",
    "<": "&lt;",
    ">": "&gt;",
    '"': "&quot;",
    "'": "&#39;",
  })[caracter]);
}

async function api(ruta, opciones = {}) {
  const headers = new Headers(opciones.headers || {});
  if (opciones.body) headers.set("Content-Type", "application/json");
  if (opciones.method && opciones.method !== "GET" && csrfToken) {
    headers.set("X-CSRFToken", csrfToken);
  }
  const response = await fetch(ruta, {
    ...opciones,
    headers,
    credentials: "same-origin",
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "No se pudo completar la operación.");
  return data;
}

async function cargarDatosIniciales() {
  const data = await api("/api/bootstrap/");
  csrfToken = data.csrfToken;
  usuarioActual = data.user;
  serviciosDisponibles = data.servicios;
  barberosDisponibles = data.barberos;
}

function mostrarAviso(el, tipo, texto) {
  if (!el) return;
  el.className = `msg ${tipo}`;
  el.textContent = texto;
}

function opciones(items, getVal, getTxt, placeholder) {
  const opts = items
    .map((item) => `<option value="${escapar(getVal(item))}">${escapar(getTxt(item))}</option>`)
    .join("");
  return placeholder ? `<option value="">${placeholder}</option>${opts}` : opts;
}

function fillSelect(id, items, getVal, getTxt, placeholder) {
  const select = document.getElementById(id);
  if (select) select.innerHTML = opciones(items, getVal, getTxt, placeholder);
}

async function logout() {
  try {
    await api("/api/logout/", { method: "POST", body: "{}" });
    location.href = "index.html";
  } catch (error) {
    mostrarAviso(document.getElementById("aviso"), "err", error.message);
  }
}

function pintarNav() {
  const element = document.getElementById("nav-links");
  if (!element) return;
  let extra = "";
  if (usuarioActual?.rol === "cliente") extra = '<a href="panel-cliente.html">Mis reservas</a>';
  if (usuarioActual?.rol === "barbero") extra = '<a href="panel-barbero.html">Agenda</a>';
  if (usuarioActual?.rol === "admin") extra = '<a href="panel-admin.html">Admin</a>';
  element.innerHTML = usuarioActual
    ? `${extra}<a href="#" id="btn-salir">Salir (${escapar(usuarioActual.nombre)})</a>`
    : `<a href="index.html">Reservar</a>
       <a href="registro.html">Registrarse</a>
       <a href="login.html">Cliente</a>
       <a href="login-staff.html">Personal</a>`;
  document.getElementById("btn-salir")?.addEventListener("click", (event) => {
    event.preventDefault();
    logout();
  });
}

function prepararFormReserva(form) {
  const barberSelect = document.getElementById("sel-barbero");
  const dateInput = form.querySelector('[name="fecha"]');
  const timeSelect = document.getElementById("sel-hora");
  const submitButton = form.querySelector('button[type="submit"]');
  if (usuarioActual?.rol === "cliente") {
    form.nombre.value = usuarioActual.nombre;
    form.email.value = usuarioActual.email;
    form.telefono.value = usuarioActual.telefono || "";
  }

  fillSelect("sel-servicio", serviciosDisponibles, (item) => item.id, (item) => item.nombre, "Elige un servicio");
  fillSelect("sel-barbero", barberosDisponibles, (item) => item.id, (item) => item.nombre, "Elige un barbero");

  let solicitudHorarios = 0;
  const actualizarHoras = async () => {
    const requestId = ++solicitudHorarios;
    const barberId = barberSelect.value;
    const selectedDate = dateInput.value;

    if (!barberId || !selectedDate) {
      fillSelect("sel-hora", HORAS, (hora) => hora, (hora) => hora, "Elige una hora");
      timeSelect.disabled = false;
      submitButton.disabled = false;
      return;
    }

    timeSelect.disabled = true;
    submitButton.disabled = true;
    mostrarAviso(document.getElementById("aviso"), "", "");
    try {
      const query = new URLSearchParams({ barberoId: barberId, fecha: selectedDate });
      const data = await api(`/api/availability/?${query}`);
      if (requestId !== solicitudHorarios) return;
      fillSelect("sel-hora", data.horas, (hora) => hora, (hora) => hora, "Elige una hora");
      if (!data.horas.length) {
        mostrarAviso(document.getElementById("aviso"), "err", "No quedan horarios disponibles para ese día y barbero.");
      }
    } catch (error) {
      if (requestId === solicitudHorarios) {
        fillSelect("sel-hora", [], (hora) => hora, (hora) => hora, "No se pudieron cargar los horarios");
        mostrarAviso(document.getElementById("aviso"), "err", error.message);
      }
    } finally {
      if (requestId === solicitudHorarios) {
        timeSelect.disabled = false;
        submitButton.disabled = false;
      }
    }
  };
  actualizarHoras();
  barberSelect.addEventListener("change", actualizarHoras);
  dateInput.addEventListener("change", actualizarHoras);

  const hoy = new Date();
  hoy.setMinutes(hoy.getMinutes() - hoy.getTimezoneOffset());
  dateInput.min = hoy.toISOString().slice(0, 10);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (submitButton.disabled) return;
    const data = Object.fromEntries(new FormData(form));
    const aviso = document.getElementById("aviso");
    submitButton.disabled = true;
    try {
      await api("/api/reservations/", {
        method: "POST",
        body: JSON.stringify(data),
      });
      mostrarAviso(aviso, "ok", "Reserva creada. Te esperamos en HSBarber.");
      form.reset();
      if (usuarioActual?.rol === "cliente") {
        form.nombre.value = usuarioActual.nombre;
        form.email.value = usuarioActual.email;
        form.telefono.value = usuarioActual.telefono || "";
      }
      await actualizarHoras();
      document.dispatchEvent(new CustomEvent("hs:reservas"));
    } catch (error) {
      mostrarAviso(aviso, "err", error.message);
      await actualizarHoras();
    } finally {
      submitButton.disabled = false;
    }
  });
}

function filaReserva(reservation, actionsHtml) {
  const status = ["pendiente", "confirmada", "completada", "cancelada"].includes(reservation.estado)
    ? reservation.estado
    : "pendiente";
  return `<tr>
    <td>${escapar(reservation.fecha)} ${escapar(reservation.hora)}</td>
    <td>${escapar(reservation.servicioNombre)}</td>
    <td>${escapar(reservation.barberoNombre)}</td>
    <td>${escapar(reservation.nombre)}<br><small>${escapar(reservation.telefono)}</small></td>
    <td><span class="badge ${status}">${status}</span></td>
    <td>${actionsHtml}</td>
  </tr>`;
}

async function obtenerReservas() {
  const data = await api("/api/reservations/");
  return data.reservas;
}

function ordenarReservas(items) {
  return items.sort((a, b) => (a.fecha + a.hora).localeCompare(b.fecha + b.hora));
}

async function initHome() {
  const form = document.getElementById("form-reserva");
  if (form) prepararFormReserva(form);
  await initReviews();
}

function mostrarResenas(items) {
  const list = document.getElementById("lista-resenas");
  if (!list) return;
  list.innerHTML = items.length
    ? items.map((item) => `
      <article class="review">
        <div class="review-header">
          <strong>${escapar(item.nombre)}</strong>
          <span class="review-rating" aria-label="${item.calificacion} de 5 estrellas">${"★".repeat(item.calificacion)}<span>${"★".repeat(5 - item.calificacion)}</span></span>
        </div>
        <p>${escapar(item.comentario)}</p>
        <small>${escapar(item.fecha)}</small>
      </article>
    `).join("")
    : '<p class="muted">Aún no hay reseñas. ¡Sé el primero en compartir tu experiencia!</p>';
}

async function initReviews() {
  const form = document.getElementById("form-resena");
  if (!form) return;
  const cargar = async () => {
    const data = await api("/api/reviews/");
    mostrarResenas(data.resenas);
  };
  try {
    await cargar();
  } catch (error) {
    mostrarAviso(document.getElementById("aviso-resena"), "err", error.message);
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("button[type='submit']");
    submit.disabled = true;
    try {
      await api("/api/reviews/", {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(new FormData(form))),
      });
      mostrarAviso(document.getElementById("aviso-resena"), "ok", "Gracias por compartir tu opinión.");
      form.reset();
      await cargar();
    } catch (error) {
      mostrarAviso(document.getElementById("aviso-resena"), "err", error.message);
    } finally {
      submit.disabled = false;
    }
  });
}

function initRegistro() {
  document.getElementById("f")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    try {
      await api("/api/register/", { method: "POST", body: JSON.stringify(data) });
      location.href = "panel-cliente.html";
    } catch (error) {
      mostrarAviso(document.getElementById("aviso"), "err", error.message);
    }
  });
}

function initLogin(roles) {
  document.getElementById("f")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(event.currentTarget));
    try {
      const result = await api("/api/login/", {
        method: "POST",
        body: JSON.stringify({ ...data, roles }),
      });
      location.href = result.user.rol === "admin"
        ? "panel-admin.html"
        : result.user.rol === "barbero"
          ? "panel-barbero.html"
          : "panel-cliente.html";
    } catch (error) {
      mostrarAviso(document.getElementById("aviso"), "err", error.message);
    }
  });
}

function exigirRol(roles) {
  if (usuarioActual && roles.includes(usuarioActual.rol)) return true;
  location.href = roles.includes("cliente") ? "login.html" : "login-staff.html";
  return false;
}

async function actualizarEstado(id, estado) {
  await api(`/api/reservations/${id}/`, {
    method: "PATCH",
    body: JSON.stringify({ estado }),
  });
}

async function initPanelCliente() {
  if (!exigirRol(["cliente"])) return;
  const form = document.getElementById("form-reserva");
  if (form) prepararFormReserva(form);

  const render = async () => {
    try {
      const items = ordenarReservas(await obtenerReservas());
      const tbody = document.getElementById("tabla");
      tbody.innerHTML = items.map((item) => filaReserva(
        item,
        item.estado !== "cancelada" && item.estado !== "completada"
          ? `<button class="small secondary" data-cancel="${item.id}">Cancelar</button>`
          : ""
      )).join("") || '<tr><td colspan="6">Aún no tienes reservas.</td></tr>';
    } catch (error) {
      mostrarAviso(document.getElementById("aviso"), "err", error.message);
    }
  };

  document.getElementById("tabla")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-cancel]");
    if (!button) return;
    try {
      await actualizarEstado(button.dataset.cancel, "cancelada");
      await render();
    } catch (error) {
      mostrarAviso(document.getElementById("aviso"), "err", error.message);
    }
  });
  document.addEventListener("hs:reservas", render);
  await render();
}

async function initPanelBarbero() {
  if (!exigirRol(["barbero"])) return;

  const render = async () => {
    try {
      const items = ordenarReservas(await obtenerReservas());
      const tbody = document.getElementById("tabla");
      tbody.innerHTML = items.map((item) => {
        let actions = "";
        if (item.estado === "pendiente") {
          actions = `<button class="small" data-estado="confirmada" data-id="${item.id}">Confirmar</button>`;
        }
        if (item.estado === "pendiente" || item.estado === "confirmada") {
          actions += `<button class="small" data-estado="completada" data-id="${item.id}">Completada</button>
                      <button class="small secondary" data-estado="cancelada" data-id="${item.id}">Cancelar</button>`;
        }
        return filaReserva(item, `<div class="actions">${actions}</div>`);
      }).join("") || '<tr><td colspan="6">No hay citas asignadas.</td></tr>';
    } catch (error) {
      mostrarAviso(document.getElementById("aviso"), "err", error.message);
    }
  };

  document.getElementById("tabla")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-id][data-estado]");
    if (!button) return;
    try {
      await actualizarEstado(button.dataset.id, button.dataset.estado);
      await render();
    } catch (error) {
      mostrarAviso(document.getElementById("aviso"), "err", error.message);
    }
  });
  await render();
}

async function initPanelAdmin() {
  if (!exigirRol(["admin"])) return;

  const renderReservas = async () => {
    try {
      const items = ordenarReservas(await obtenerReservas());
      document.getElementById("tabla").innerHTML = items.map((item) => filaReserva(
        item,
        `<div class="actions">
          <button class="small" data-id="${item.id}" data-estado="confirmada">Confirmar</button>
          <button class="small" data-id="${item.id}" data-estado="completada">Completada</button>
          <button class="small secondary" data-id="${item.id}" data-estado="cancelada">Cancelar</button>
        </div>`
      )).join("") || '<tr><td colspan="6">No hay reservas.</td></tr>';
    } catch (error) {
      mostrarAviso(document.getElementById("aviso"), "err", error.message);
    }
  };

  const renderBarberos = () => {
    const tbody = document.getElementById("tabla-barberos");
    tbody.innerHTML = barberosDisponibles.map((barber) => `<tr>
      <td>${escapar(barber.nombre)}</td>
      <td>${escapar(barber.email)}</td>
      <td>${escapar(barber.telefono)}</td>
    </tr>`).join("");
  };

  document.getElementById("tabla")?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-id][data-estado]");
    if (!button) return;
    try {
      await actualizarEstado(button.dataset.id, button.dataset.estado);
      await renderReservas();
    } catch (error) {
      mostrarAviso(document.getElementById("aviso"), "err", error.message);
    }
  });

  document.getElementById("form-barbero")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    const aviso = document.getElementById("aviso-barbero");
    try {
      await api("/api/barbers/", { method: "POST", body: JSON.stringify(data) });
      const bootstrap = await api("/api/bootstrap/");
      barberosDisponibles = bootstrap.barberos;
      renderBarberos();
      fillSelect("sel-barbero", barberosDisponibles, (item) => item.id, (item) => item.nombre, "Elige un barbero");
      mostrarAviso(aviso, "ok", "Barbero creado. Ya puede ingresar en Personal.");
      form.reset();
    } catch (error) {
      mostrarAviso(aviso, "err", error.message);
    }
  });

  document.getElementById("form-servicio")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    const aviso = document.getElementById("aviso-servicio");
    try {
      await api("/api/services/", { method: "POST", body: JSON.stringify(data) });
      const bootstrap = await api("/api/bootstrap/");
      serviciosDisponibles = bootstrap.servicios;
      fillSelect("sel-servicio", serviciosDisponibles, (item) => item.id, (item) => item.nombre, "Elige un servicio");
      mostrarAviso(aviso, "ok", "Servicio agregado.");
      form.reset();
    } catch (error) {
      mostrarAviso(aviso, "err", error.message);
    }
  });

  renderBarberos();
  await renderReservas();
}

async function iniciarAplicacion() {
  try {
    await cargarDatosIniciales();
  } catch (error) {
    mostrarAviso(document.getElementById("aviso"), "err", error.message);
    return;
  }
  pintarNav();
  const page = document.body.dataset.page;
  if (page === "home") await initHome();
  if (page === "registro") initRegistro();
  if (page === "login") initLogin(["cliente"]);
  if (page === "login-staff") initLogin(["admin", "barbero"]);
  if (page === "cliente") await initPanelCliente();
  if (page === "barbero") await initPanelBarbero();
  if (page === "admin") await initPanelAdmin();
}

document.addEventListener("DOMContentLoaded", iniciarAplicacion);