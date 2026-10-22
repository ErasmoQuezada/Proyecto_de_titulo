import json
import logging
import os
from datetime import date, time
from functools import wraps
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .models import Profile, Reservation, Service

logger = logging.getLogger(__name__)
RESERVATION_HOURS = (
    "09:00",
    "10:00",
    "11:00",
    "12:00",
    "14:00",
    "15:00",
    "16:00",
    "17:00",
    "18:00",
)


def home(request):
    return render(request, "index.html")


def frontend_page(request, page):
    return render(request, f"{page}.html")


def parse_json(request):
    if len(request.body) > 16_384:
        return None, JsonResponse({"error": "La solicitud es demasiado grande."}, status=413)
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse({"error": "La solicitud no contiene JSON válido."}, status=400)
    if not isinstance(payload, dict):
        return None, JsonResponse({"error": "La solicitud no es válida."}, status=400)
    return payload, None


def user_data(user):
    profile = user.profile
    return {
        "id": user.id,
        "nombre": user.get_full_name() or user.username,
        "email": user.email,
        "telefono": profile.phone,
        "rol": profile.role,
    }


def reservation_data(reservation):
    return {
        "id": reservation.id,
        "nombre": reservation.name,
        "telefono": reservation.phone,
        "email": reservation.email,
        "servicio": reservation.service_id,
        "servicioNombre": reservation.service.name,
        "barberoId": reservation.barber_id,
        "barberoNombre": reservation.barber.get_full_name() or reservation.barber.username,
        "clienteId": reservation.client_id,
        "fecha": reservation.date.isoformat(),
        "hora": reservation.time.strftime("%H:%M"),
        "estado": reservation.status,
    }


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return JsonResponse({"error": "Debes iniciar sesión."}, status=401)
            if not hasattr(request.user, "profile") or request.user.profile.role not in roles:
                return JsonResponse({"error": "No tienes permiso para esta operación."}, status=403)
            return view(request, *args, **kwargs)
        return wrapped
    return decorator


@require_GET
def bootstrap(request):
    current_user = (
        user_data(request.user)
        if request.user.is_authenticated and hasattr(request.user, "profile")
        else None
    )
    return JsonResponse({
        "csrfToken": get_token(request),
        "user": current_user,
        "servicios": [
            {"id": item.id, "nombre": item.name, "minutos": item.duration_minutes}
            for item in Service.objects.order_by("id")
        ],
        "barberos": [
            {
                "id": profile.user_id,
                "nombre": profile.user.get_full_name() or profile.user.username,
                "email": profile.user.email,
                "telefono": profile.phone,
            }
            for profile in Profile.objects.filter(role=Profile.Role.BARBER).select_related("user")
        ],
    })


@require_POST
def register(request):
    payload, error = parse_json(request)
    if error:
        return error
    name = payload.get("nombre", "").strip() if isinstance(payload.get("nombre"), str) else ""
    email = payload.get("email", "").strip().lower() if isinstance(payload.get("email"), str) else ""
    phone = payload.get("telefono", "").strip() if isinstance(payload.get("telefono"), str) else ""
    password = payload.get("password")
    if (
        not name
        or len(name) > 150
        or not email
        or len(email) > 150
        or not phone
        or len(phone) > 30
        or not isinstance(password, str)
    ):
        return JsonResponse({"error": "Completa todos los campos obligatorios."}, status=400)
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"error": "Escribe un correo válido."}, status=400)
    if len(password) < 8:
        return JsonResponse({"error": "La contraseña debe tener al menos 8 caracteres."}, status=400)
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=name[:150],
            )
            Profile.objects.create(user=user, role=Profile.Role.CLIENT, phone=phone[:30])
    except IntegrityError:
        return JsonResponse({"error": "Ese correo ya está registrado."}, status=409)
    login(request, user)
    return JsonResponse({"user": user_data(user)}, status=201)


@require_POST
def login_user(request):
    payload, error = parse_json(request)
    if error:
        return error
    email = payload.get("email", "").strip().lower() if isinstance(payload.get("email"), str) else ""
    password = payload.get("password")
    expected_roles = payload.get("roles")
    if not email or len(email) > 150 or not isinstance(password, str):
        return JsonResponse({"error": "Ingresa tu correo y contraseña."}, status=400)
    user = authenticate(request, username=email, password=password)
    if not user or not hasattr(user, "profile"):
        return JsonResponse({"error": "Correo o contraseña incorrectos."}, status=401)
    if isinstance(expected_roles, list) and user.profile.role not in expected_roles:
        return JsonResponse({"error": "Este acceso no corresponde a tu rol."}, status=403)
    login(request, user)
    return JsonResponse({"user": user_data(user)})


@require_POST
def logout_user(request):
    logout(request)
    return JsonResponse({"ok": True})


@require_GET
def available_slots(request):
    barber_id = request.GET.get("barberoId")
    selected_date = request.GET.get("fecha")
    if not barber_id or not selected_date:
        return JsonResponse({"horas": RESERVATION_HOURS})
    try:
        barber = User.objects.get(pk=barber_id, profile__role=Profile.Role.BARBER)
        reservation_date = date.fromisoformat(selected_date)
    except (User.DoesNotExist, TypeError, ValueError):
        return JsonResponse({"error": "Selecciona un barbero y una fecha válidos."}, status=400)
    if reservation_date < timezone.localdate():
        return JsonResponse({"error": "No puedes consultar horarios de una fecha pasada."}, status=400)
    occupied = set(
        Reservation.objects.filter(
            barber=barber,
            date=reservation_date,
        )
        .exclude(status=Reservation.Status.CANCELLED)
        .values_list("time", flat=True)
    )
    return JsonResponse({
        "horas": [
            hour
            for hour in RESERVATION_HOURS
            if time.fromisoformat(hour) not in occupied
        ]
    })


@require_http_methods(["GET", "POST"])
def reservations(request):
    if request.method == "GET":
        if not request.user.is_authenticated or not hasattr(request.user, "profile"):
            return JsonResponse({"error": "Debes iniciar sesión."}, status=401)
        role = request.user.profile.role
        records = Reservation.objects.select_related("service", "barber", "client")
        if role == Profile.Role.CLIENT:
            records = records.filter(
                Q(client=request.user) | Q(client__isnull=True, email__iexact=request.user.email)
            )
        elif role == Profile.Role.BARBER:
            records = records.filter(barber=request.user)
        elif role != Profile.Role.ADMIN:
            return JsonResponse({"error": "No tienes permiso para consultar reservas."}, status=403)
        return JsonResponse({"reservas": [reservation_data(item) for item in records]})

    payload, error = parse_json(request)
    if error:
        return error
    name = payload.get("nombre", "").strip() if isinstance(payload.get("nombre"), str) else ""
    phone = payload.get("telefono", "").strip() if isinstance(payload.get("telefono"), str) else ""
    email = payload.get("email", "").strip() if isinstance(payload.get("email"), str) else ""
    if not name or len(name) > 150 or not phone or len(phone) > 30:
        return JsonResponse({"error": "Indica tu nombre y teléfono."}, status=400)
    try:
        service = Service.objects.get(pk=payload.get("servicio"))
        barber = User.objects.select_related("profile").get(
            pk=payload.get("barberoId"),
            profile__role=Profile.Role.BARBER,
        )
        reservation_date = date.fromisoformat(payload.get("fecha", ""))
        reservation_time = time.fromisoformat(payload.get("hora", ""))
    except (Service.DoesNotExist, User.DoesNotExist, TypeError, ValueError):
        return JsonResponse({"error": "Selecciona un servicio, barbero, fecha y hora válidos."}, status=400)
    if reservation_date < timezone.localdate():
        return JsonResponse({"error": "No puedes reservar una fecha pasada."}, status=400)
    if reservation_time.strftime("%H:%M") not in RESERVATION_HOURS:
        return JsonResponse({"error": "El horario seleccionado no está disponible."}, status=400)
    if email:
        if len(email) > 254:
            return JsonResponse({"error": "El correo no puede superar los 254 caracteres."}, status=400)
        try:
            validate_email(email)
        except ValidationError:
            return JsonResponse({"error": "Escribe un correo válido."}, status=400)

    with transaction.atomic():
        User.objects.select_for_update().get(pk=barber.pk)
        occupied = Reservation.objects.filter(
            barber=barber,
            date=reservation_date,
            time=reservation_time,
        ).exclude(status=Reservation.Status.CANCELLED).exists()
        if occupied:
            return JsonResponse({"error": "Ese horario ya está ocupado con ese barbero."}, status=409)
        record = Reservation.objects.create(
            name=name[:150],
            phone=phone[:30],
            email=email,
            service=service,
            barber=barber,
            client=request.user if request.user.is_authenticated else None,
            date=reservation_date,
            time=reservation_time,
        )
    record = Reservation.objects.select_related("service", "barber", "client").get(pk=record.pk)
    return JsonResponse({"reserva": reservation_data(record)}, status=201)


@require_http_methods(["PATCH"])
def update_reservation(request, reservation_id):
    payload, error = parse_json(request)
    if error:
        return error
    status = payload.get("estado")
    if status not in Reservation.Status.values:
        return JsonResponse({"error": "El estado de la reserva no es válido."}, status=400)
    try:
        record = Reservation.objects.select_related("service", "barber", "client").get(pk=reservation_id)
    except Reservation.DoesNotExist:
        return JsonResponse({"error": "No se encontró la reserva."}, status=404)
    if not request.user.is_authenticated or not hasattr(request.user, "profile"):
        return JsonResponse({"error": "Debes iniciar sesión."}, status=401)
    role = request.user.profile.role
    if role == Profile.Role.CLIENT:
        if (
            status != Reservation.Status.CANCELLED
            or not (
                record.client_id == request.user.id
                or (record.client_id is None and record.email.lower() == request.user.email.lower())
            )
            or record.status not in (Reservation.Status.PENDING, Reservation.Status.CONFIRMED)
        ):
            return JsonResponse({"error": "No tienes permiso para modificar esta reserva."}, status=403)
    elif role == Profile.Role.BARBER:
        allowed_statuses = {
            Reservation.Status.PENDING: (
                Reservation.Status.CONFIRMED,
                Reservation.Status.COMPLETED,
                Reservation.Status.CANCELLED,
            ),
            Reservation.Status.CONFIRMED: (
                Reservation.Status.COMPLETED,
                Reservation.Status.CANCELLED,
            ),
        }
        if (
            record.barber_id != request.user.id
            or status not in allowed_statuses.get(record.status, ())
        ):
            return JsonResponse({"error": "No tienes permiso para modificar esta reserva."}, status=403)
    elif role != Profile.Role.ADMIN:
        return JsonResponse({"error": "No tienes permiso para modificar esta reserva."}, status=403)
    record.status = status
    record.save(update_fields=("status",))
    return JsonResponse({"reserva": reservation_data(record)})


@require_POST
@role_required(Profile.Role.ADMIN)
def create_barber(request):
    payload, error = parse_json(request)
    if error:
        return error
    name = payload.get("nombre", "").strip() if isinstance(payload.get("nombre"), str) else ""
    email = payload.get("email", "").strip().lower() if isinstance(payload.get("email"), str) else ""
    phone = payload.get("telefono", "").strip() if isinstance(payload.get("telefono"), str) else ""
    password = payload.get("password")
    if (
        not name
        or len(name) > 150
        or not email
        or len(email) > 150
        or not phone
        or len(phone) > 30
        or not isinstance(password, str)
        or len(password) < 8
    ):
        return JsonResponse({"error": "Completa los datos y usa una contraseña de al menos 8 caracteres."}, status=400)
    try:
        validate_email(email)
    except ValidationError:
        return JsonResponse({"error": "Escribe un correo válido."}, status=400)
    try:
        with transaction.atomic():
            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
                first_name=name[:150],
            )
            profile = Profile.objects.create(
                user=user,
                role=Profile.Role.BARBER,
                phone=phone[:30],
            )
    except IntegrityError:
        return JsonResponse({"error": "Ese correo ya está registrado."}, status=409)
    return JsonResponse({
        "barbero": {
            "id": user.id,
            "nombre": user.get_full_name(),
            "email": user.email,
            "telefono": profile.phone,
        }
    }, status=201)


@require_POST
@role_required(Profile.Role.ADMIN)
def create_service(request):
    payload, error = parse_json(request)
    if error:
        return error
    name = payload.get("nombre", "").strip() if isinstance(payload.get("nombre"), str) else ""
    try:
        duration = int(payload.get("minutos", 30))
    except (TypeError, ValueError):
        return JsonResponse({"error": "La duración debe ser un número de minutos."}, status=400)
    if not name or len(name) > 100 or not 10 <= duration <= 240:
        return JsonResponse({"error": "Indica un servicio y una duración entre 10 y 240 minutos."}, status=400)
    try:
        service = Service.objects.create(name=name[:100], duration_minutes=duration)
    except IntegrityError:
        return JsonResponse({"error": "Ya existe un servicio con ese nombre."}, status=409)
    return JsonResponse({
        "servicio": {
            "id": service.id,
            "nombre": service.name,
            "minutos": service.duration_minutes,
        }
    }, status=201)


def respuesta_local_chat(message):
    normalized = "".join(
        character
        for character in unicodedata.normalize("NFD", message.lower())
        if unicodedata.category(character) != "Mn"
    )
    respuestas = (
        (("horario", "hora", "abren", "cierran", "atencion", "dias"),
         "Atendemos de lunes a sábado, de 9:00 a 13:00 y de 14:00 a 19:00. Los domingos cerramos."),
        (("direccion", "ubicacion", "donde", "local", "mapa", "llegar"),
         "Estamos en Avenida Principal 120, local 4."),
        (("precio", "cuesta", "costo", "tarifa", "cuanto"),
         "Precios de referencia: corte $10000, barba $6000 y corte + barba $14000."),
        (("servicio", "corte", "barba", "combo", "ofrecen"),
         "Ofrecemos corte, arreglo de barba y el combo corte + barba."),
        (("reservar", "reserva", "cita", "agendar", "turno"),
         "Puedes reservar desde la página eligiendo servicio, barbero, fecha y hora."),
        (("cancelar", "cancelacion", "cambiar", "modificar"),
         "Si tienes cuenta, puedes cancelar una cita pendiente desde Mis reservas. Para otras reservas, contacta al local."),
        (("pago", "pagar", "efectivo", "tarjeta"),
         "Aceptamos efectivo y tarjeta. El pago se realiza al finalizar el servicio."),
        (("barbero", "barberos", "estilista"),
         "Puedes elegir al barbero al reservar."),
        (("contacto", "telefono", "whatsapp", "llamar", "correo"),
         "Teléfono y WhatsApp: +1 555 010 1234. Correo: hola@hsbarber.com."),
        (("hola", "buenas", "hey", "saludos"),
         "¡Hola! Puedo ayudarte con horarios, precios, reservas o ubicación de HSBarber."),
        (("gracias", "ok", "perfecto"),
         "¡Con gusto! Si necesitas otra indicación, escríbeme."),
    )
    for keywords, answer in respuestas:
        if any(keyword in normalized for keyword in keywords):
            return answer
    return (
        "Ahora no puedo consultar al asistente inteligente, pero puedo ayudarte con "
        "horarios, precios, reservas, servicios, pagos o ubicación."
    )


@require_http_methods(["GET", "POST"])
def chat(request):
    if request.method == "GET":
        return JsonResponse({"csrfToken": get_token(request)})

    if len(request.body) > 16_384:
        return JsonResponse({"error": "El mensaje es demasiado largo."}, status=413)

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"error": "La solicitud no contiene JSON válido."}, status=400)

    if not isinstance(data, dict):
        return JsonResponse({"error": "La solicitud no es válida."}, status=400)

    message = data.get("message")
    if not isinstance(message, str) or not message.strip() or len(message) > 1000:
        return JsonResponse({"error": "Escribe un mensaje de hasta 1000 caracteres."}, status=400)

    history = data.get("history", [])
    if not isinstance(history, list):
        return JsonResponse({"error": "El historial no es válido."}, status=400)

    api_key = settings.GEMINI_API_KEY
    if not api_key:
        logger.warning("Gemini chat is not configured; returning local response")
        return JsonResponse({"reply": respuesta_local_chat(message)})

    contents = []
    for item in history[-10:]:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        text = item.get("text")
        if role in ("user", "model") and isinstance(text, str) and text.strip():
            contents.append({"role": role, "parts": [{"text": text[:1000]}]})
    contents.append({"role": "user", "parts": [{"text": message.strip()}]})

    payload = {
        "system_instruction": {
            "parts": [{
                "text": (
                    "Eres el asistente virtual de HSBarber. Responde siempre en español, "
                    "con tono amable, natural y conciso. Responde solo sobre la barbería "
                    "y no inventes información: horarios lunes a sábado de 9:00 a 13:00 "
                    "y de 14:00 a 19:00 (domingo cerrado); dirección Avenida Principal "
                    "120, local 4; precios de referencia corte $10000, barba $6000 y "
                    "combo $14000; servicios corte, barba y combo; pago en efectivo o "
                    "tarjeta al finalizar; teléfono/WhatsApp +1 555 010 1234 y "
                    "hola@hsbarber.com. Las reservas se realizan desde la página "
                    "eligiendo servicio, barbero, fecha y hora. Si no sabes algo, dilo "
                    "y recomienda contactar al local."
                )
            }]
        },
        "contents": contents,
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 300},
    }
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"{settings.GEMINI_MODEL}:generateContent"
    )
    provider_request = Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "X-goog-api-key": api_key,
        },
        method="POST",
    )

    try:
        with urlopen(provider_request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
        answer = " ".join(
            part["text"]
            for part in result["candidates"][0]["content"]["parts"]
            if isinstance(part.get("text"), str)
        ).strip()
        if not answer:
            raise ValueError("Gemini returned no text")
    except (HTTPError, URLError, TimeoutError, OSError, ValueError, KeyError, IndexError) as error:
        logger.warning("Gemini chat request failed: %s", error)
        return JsonResponse({"reply": respuesta_local_chat(message)})

    return JsonResponse({"reply": answer})