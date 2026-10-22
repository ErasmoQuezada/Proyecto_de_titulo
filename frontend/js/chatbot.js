const CHAT_DICCIONARIO = [
  {
    claves: ["horario", "hora", "abren", "cierran", "abierto", "atencion", "dias"],
    respuesta:
      "HSBarber atiende de lunes a sábado, de 9:00 a 13:00 y de 14:00 a 19:00. Los domingos permanecemos cerrados.",
  },
  {
    claves: ["direccion", "ubicacion", "donde", "local", "mapa", "llegar"],
    respuesta:
      "Estamos en Avenida Principal 120, local 4. Hay parada de bus a una cuadra y estacionamiento cercano.",
  },
  {
    claves: ["precio", "cuesta", "costo", "tarifa", "cuanto"],
    respuesta:
      "Precios de referencia: corte $10000, barba $6000 y corte + barba $14000. El precio final se confirma en el local.",
  },
  {
    claves: ["servicio", "servicios", "corte", "barba", "combo", "ofrecen"],
    respuesta:
      "Ofrecemos corte, arreglo de barba y el combo corte + barba. Puedes ver las opciones al crear una reserva.",
  },
  {
    claves: ["reservar", "reserva", "cita", "agendar", "turno"],
    respuesta:
      "Puedes reservar sin cuenta desde la página de inicio. Elige servicio, barbero, fecha y hora. Si te registras, también puedes ver y cancelar tus reservas.",
  },
  {
    claves: ["cancelar", "cancelacion", "cambiar", "modificar"],
    respuesta:
      "Si inicias sesión como cliente, en Mis reservas puedes cancelar una cita pendiente. Si reservaste como invitado, llama al local o escribe al WhatsApp de la barbería.",
  },
  {
    claves: ["pago", "pagar", "efectivo", "tarjeta", "transferencia"],
    respuesta:
      "Aceptamos efectivo y tarjeta. El pago se realiza al finalizar el servicio.",
  },
  {
    claves: ["barbero", "barberos", "quien", "estilista"],
    respuesta:
      "Puedes elegir al barbero al reservar. El administrador puede agregar más barberos desde el panel.",
  },
  {
    claves: ["cuenta", "registro", "registrar", "iniciar", "sesion", "login"],
    respuesta:
      "Los clientes se registran en Registrarse e inician sesión en Cliente. Barberos y administradores usan el acceso de Personal.",
  },
  {
    claves: ["nino", "ninos", "infantil", "menor", "hijo"],
    respuesta:
      "Atendemos cortes infantiles. Recomendamos reservar y acompañar al menor durante el servicio.",
  },
  {
    claves: ["sin cita", "walk", "esperar", "fila"],
    respuesta:
      "Aceptamos clientes sin cita si hay espacio, pero la reserva tiene prioridad. Lo más seguro es agendar con anticipación.",
  },
  {
    claves: ["contacto", "telefono", "whatsapp", "llamar", "correo"],
    respuesta:
      "Teléfono y WhatsApp: +1 555 010 1234. Correo: hola@hsbarber.com",
  },
  {
    claves: ["estacionamiento", "parking", "auto", "parquear"],
    respuesta:
      "Hay estacionamiento público a media cuadra del local. El espacio es limitado en horas pico.",
  },
  {
    claves: ["higiene", "limpieza", "covid", "herramientas"],
    respuesta:
      "Desinfectamos peines, máquinas y sillas entre cada cliente. El local se limpia durante el día.",
  },
  {
    claves: ["hola", "buenas", "hey", "saludos"],
    respuesta: "Hola, soy el asistente de HSBarber. Pregúntame por horarios, precios, reservas o ubicación.",
  },
  {
    claves: ["gracias", "ok", "perfecto"],
    respuesta: "Con gusto. Si necesitas otra indicación, escríbeme.",
  },
];

const CHAT_SUGERENCIAS = ["Horario", "Precios", "Cómo reservar", "Ubicación"];
const CHAT_API_URL = "/api/chat/";
const CHAT_HOLA =
  "Hola, soy el asistente de HSBarber. Pregúntame por horarios, precios, reservas o ubicación.";
let chatEnviando = false;
const chatHistorial = [];

function normalizarTexto(texto) {
  return String(texto)
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[¿?¡!.,;:()]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function responderChat(pregunta) {
  const q = normalizarTexto(pregunta);
  if (!q) return "Escribe tu pregunta sobre HSBarber.";

  let mejor = null;
  let puntaje = 0;
  for (const item of CHAT_DICCIONARIO) {
    const puntos = item.claves.reduce((acc, clave) => {
      const k = normalizarTexto(clave);
      return acc + (q.includes(k) ? (k.length > 4 ? 2 : 1) : 0);
    }, 0);
    if (puntos > puntaje) {
      puntaje = puntos;
      mejor = item;
    }
  }

  if (!mejor || puntaje === 0) {
    return "No encontré esa consulta en el diccionario. Puedes preguntar por horario, precios, reservas, cancelación, pagos, barberos o ubicación.";
  }
  return mejor.respuesta;
}

function agregarMensajeChat(rol, texto) {
  const caja = document.getElementById("chat-mensajes");
  if (!caja) return;
  const burbuja = document.createElement("div");
  burbuja.className = `chat-msg ${rol}`;
  burbuja.textContent = texto;
  caja.appendChild(burbuja);
  caja.scrollTop = caja.scrollHeight;
}

async function obtenerRespuestaChat(pregunta) {
  try {
    const csrfResponse = await fetch(CHAT_API_URL, { method: "GET" });
    if (!csrfResponse.ok) throw new Error("No se pudo iniciar el chat.");
    const { csrfToken } = await csrfResponse.json();

    const response = await fetch(CHAT_API_URL, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": csrfToken,
      },
      body: JSON.stringify({ message: pregunta, history: chatHistorial }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "El asistente no está disponible.");
    return data.reply;
  } catch {
    return `No pude conectar con el asistente inteligente. ${responderChat(pregunta)}`;
  }
}

async function enviarChat(texto) {
  const pregunta = String(texto || "").trim();
  if (!pregunta || chatEnviando) return;

  chatEnviando = true;
  agregarMensajeChat("user", pregunta);
  const submit = document.querySelector("#chat-form button[type='submit']");
  if (submit) submit.disabled = true;
  const input = document.getElementById("chat-input");
  if (input) input.disabled = true;

  try {
    const respuesta = await obtenerRespuestaChat(pregunta);
    agregarMensajeChat("bot", respuesta);
    chatHistorial.push(
      { role: "user", text: pregunta },
      { role: "model", text: respuesta }
    );
    if (chatHistorial.length > 10) chatHistorial.splice(0, chatHistorial.length - 10);
  } finally {
    chatEnviando = false;
    if (submit) submit.disabled = false;
    if (input) input.disabled = false;
    input?.focus();
  }
}

function initChatbot() {
  if (document.getElementById("chatbot")) return;

  const root = document.createElement("div");
  root.id = "chatbot";
  root.innerHTML = `
    <button type="button" class="chat-toggle" id="chat-toggle" aria-label="Abrir asistente">Chat</button>
    <section class="chat-panel" id="chat-panel" hidden>
      <header class="chat-header">
        <strong>Asistente HSBarber</strong>
        <button type="button" class="chat-cerrar" id="chat-cerrar" aria-label="Cerrar">×</button>
      </header>
      <div class="chat-mensajes" id="chat-mensajes"></div>
      <div class="chat-sugerencias" id="chat-sugerencias"></div>
      <form class="chat-form" id="chat-form">
        <input id="chat-input" type="text" placeholder="Escribe tu pregunta..." autocomplete="off" />
        <button type="submit">Enviar</button>
      </form>
    </section>
  `;
  document.body.appendChild(root);

  const panel = document.getElementById("chat-panel");
  const toggle = document.getElementById("chat-toggle");
  const abrir = () => {
    panel.hidden = false;
    document.getElementById("chat-input")?.focus();
  };
  const cerrar = () => {
    panel.hidden = true;
  };

  toggle.addEventListener("click", () => {
    if (panel.hidden) abrir();
    else cerrar();
  });
  document.getElementById("chat-cerrar").addEventListener("click", cerrar);

  const sugerencias = document.getElementById("chat-sugerencias");
  sugerencias.innerHTML = CHAT_SUGERENCIAS.map(
    (s) => `<button type="button" class="chat-chip" data-q="${s}">${s}</button>`
  ).join("");
  sugerencias.addEventListener("click", (e) => {
    const q = e.target.dataset.q;
    if (!q) return;
    enviarChat(q);
  });

  document.getElementById("chat-form").addEventListener("submit", (e) => {
    e.preventDefault();
    const input = document.getElementById("chat-input");
    enviarChat(input.value);
    input.value = "";
  });

  agregarMensajeChat("bot", CHAT_HOLA);
}

document.addEventListener("DOMContentLoaded", initChatbot);
