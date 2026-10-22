from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from app.models import Profile, Service


class Command(BaseCommand):
    help = "Create the initial HSBarber services and demo staff accounts."

    def handle(self, *args, **options):
        for name, duration in (
            ("Corte", 30),
            ("Barba", 20),
            ("Corte + Barba", 45),
        ):
            Service.objects.get_or_create(
                name=name,
                defaults={"duration_minutes": duration},
            )

        for email, name, phone, password, role in (
            ("admin@hsbarber.com", "Admin HS", "0000000000", "admin123", Profile.Role.ADMIN),
            ("barbero@hsbarber.com", "Barbero HS", "1111111111", "barbero123", Profile.Role.BARBER),
        ):
            user, created = User.objects.get_or_create(
                username=email,
                defaults={
                    "email": email,
                    "first_name": name,
                    "is_active": True,
                },
            )
            if created:
                user.set_password(password)
                user.save(update_fields=("password",))
            Profile.objects.get_or_create(
                user=user,
                defaults={"role": role, "phone": phone},
            )

        self.stdout.write(self.style.SUCCESS("Servicios y cuentas iniciales listos."))
