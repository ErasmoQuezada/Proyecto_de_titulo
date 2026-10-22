import json
from datetime import date, time
from io import BytesIO
from urllib.error import HTTPError
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import Client, TestCase
from django.urls import reverse
from django.contrib.staticfiles import finders

from .models import Profile, Reservation, Service


class FrontendRouteTests(TestCase):
    def test_home_renders_frontend(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reserva tu corte")
        self.assertContains(response, "/static/js/chatbot.js")

    def test_index_html_alias_renders_home(self):
        response = self.client.get("/index.html")

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reserva tu corte")

    def test_all_frontend_pages_render(self):
        pages = (
            "login.html",
            "registro.html",
            "login-staff.html",
            "panel-cliente.html",
            "panel-barbero.html",
            "panel-admin.html",
        )
        for page in pages:
            with self.subTest(page=page):
                self.assertEqual(self.client.get(f"/{page}").status_code, 200)

    def test_frontend_assets_are_discoverable(self):
        self.assertTrue(finders.find("css/styles.css"))
        self.assertTrue(finders.find("js/chatbot.js"))


class ChatApiTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.url = reverse("chat")

    def post_chat(self, payload):
        csrf_response = self.client.get(self.url)
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            HTTP_X_CSRFTOKEN=csrf_response.json()["csrfToken"],
        )

    def test_get_returns_csrf_token(self):
        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["csrfToken"])
        self.assertIn("csrftoken", response.cookies)

    def test_post_requires_valid_message(self):
        response = self.post_chat({"message": " "})

        self.assertEqual(response.status_code, 400)

    @patch("app.views.settings.GEMINI_API_KEY", "")
    def test_post_returns_local_reply_when_gemini_key_is_missing(self):
        response = self.post_chat({"message": "¿Cuál es el horario?"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("lunes a sábado", response.json()["reply"])

    @patch("app.views.urlopen")
    @patch("app.views.settings.GEMINI_API_KEY", "test-key")
    def test_post_returns_gemini_reply_and_context(self, mock_urlopen):
        provider_response = mock_urlopen.return_value.__enter__.return_value
        provider_response.read.return_value = json.dumps({
            "candidates": [{
                "content": {"parts": [{"text": "Abrimos de lunes a sábado."}]}
            }]
        }).encode("utf-8")

        response = self.post_chat({
            "message": "¿Y el domingo?",
            "history": [{"role": "user", "text": "¿Cuál es el horario?"}],
        })

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["reply"], "Abrimos de lunes a sábado.")
        request = mock_urlopen.call_args.args[0]
        payload = json.loads(request.data)
        self.assertEqual(payload["contents"][0]["role"], "user")
        self.assertEqual(payload["contents"][1]["parts"][0]["text"], "¿Y el domingo?")
        self.assertIn("gemini-3.6-flash", request.full_url)

    @patch("app.views.urlopen", side_effect=HTTPError(
        "https://generativelanguage.googleapis.com",
        404,
        "Not Found",
        {},
        BytesIO(b'{"error":"model not found"}'),
    ))
    @patch("app.views.settings.GEMINI_API_KEY", "test-key")
    def test_post_returns_local_reply_instead_of_gateway_error(self, mock_urlopen):
        response = self.post_chat({"message": "¿Cuánto cuesta el corte?"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json()["reply"],
            "Precios de referencia: corte $10000, barba $6000 y corte + barba $14000.",
        )


class ReservationApiTests(TestCase):
    def setUp(self):
        self.barber = User.objects.create_user(
            username="barber@example.com",
            email="barber@example.com",
            password="strong-password",
            first_name="Barbero",
        )
        Profile.objects.create(
            user=self.barber,
            role=Profile.Role.BARBER,
            phone="1111111111",
        )
        self.service = Service.objects.create(name="Corte", duration_minutes=30)
        self.reservation_data = {
            "nombre": "Cliente de prueba",
            "telefono": "5551234",
            "email": "cliente@example.com",
            "servicio": self.service.pk,
            "barberoId": self.barber.pk,
            "fecha": "2099-05-20",
            "hora": "10:00",
        }

    def test_guest_can_create_reservation_saved_in_database(self):
        response = self.client.post(
            reverse("api-reservations"),
            data=json.dumps(self.reservation_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Reservation.objects.count(), 1)
        self.assertEqual(response.json()["reserva"]["servicioNombre"], "Corte")

    def test_prevents_booking_the_same_slot_twice(self):
        self.client.post(
            reverse("api-reservations"),
            data=json.dumps(self.reservation_data),
            content_type="application/json",
        )
        response = self.client.post(
            reverse("api-reservations"),
            data=json.dumps(self.reservation_data),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 409)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_availability_hides_reserved_slots(self):
        Reservation.objects.create(
            name="Cliente anterior",
            phone="5550000",
            email="",
            service=self.service,
            barber=self.barber,
            date=date(2099, 5, 20),
            time=time(10, 0),
        )

        response = self.client.get(reverse("api-availability"), {
            "barberoId": self.barber.pk,
            "fecha": "2099-05-20",
        })

        self.assertEqual(response.status_code, 200)
        self.assertNotIn("10:00", response.json()["horas"])
        self.assertIn("11:00", response.json()["horas"])

    def test_cancelled_reservation_releases_its_slot(self):
        Reservation.objects.create(
            name="Cliente anterior",
            phone="5550000",
            email="",
            service=self.service,
            barber=self.barber,
            date=date(2099, 5, 20),
            time=time(10, 0),
            status=Reservation.Status.CANCELLED,
        )

        response = self.client.get(reverse("api-availability"), {
            "barberoId": self.barber.pk,
            "fecha": "2099-05-20",
        })

        self.assertEqual(response.status_code, 200)
        self.assertIn("10:00", response.json()["horas"])

    def test_register_creates_hashed_password_and_authenticated_session(self):
        response = self.client.post(
            reverse("api-register"),
            data=json.dumps({
                "nombre": "Nueva Cliente",
                "email": "new@example.com",
                "telefono": "5559876",
                "password": "a-secure-password",
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(username="new@example.com")
        self.assertTrue(user.check_password("a-secure-password"))
        self.assertEqual(user.profile.role, Profile.Role.CLIENT)
        self.assertEqual(response.json()["user"]["rol"], Profile.Role.CLIENT)

    def test_staff_login_checks_requested_role(self):
        response = self.client.post(
            reverse("api-login"),
            data=json.dumps({
                "email": "barber@example.com",
                "password": "strong-password",
                "roles": ["admin", "barbero"],
            }),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["user"]["rol"], Profile.Role.BARBER)

    def test_customer_cannot_read_all_reservations(self):
        response = self.client.get(reverse("api-reservations"))

        self.assertEqual(response.status_code, 401)

    def test_seed_command_creates_demo_accounts_and_is_repeatable(self):
        call_command("seed_hsbarber", verbosity=0)
        call_command("seed_hsbarber", verbosity=0)

        admin = User.objects.get(username="admin@hsbarber.com")
        barber = User.objects.get(username="barbero@hsbarber.com")
        self.assertTrue(admin.check_password("admin123"))
        self.assertEqual(admin.profile.role, Profile.Role.ADMIN)
        self.assertTrue(barber.check_password("barbero123"))
        self.assertEqual(Service.objects.filter(name="Corte").count(), 1)
