from django.conf import settings
from django.db import models


class Profile(models.Model):
    class Role(models.TextChoices):
        CLIENT = "cliente", "Cliente"
        BARBER = "barbero", "Barbero"
        ADMIN = "admin", "Administrador"

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    phone = models.CharField(max_length=30, blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Service(models.Model):
    name = models.CharField(max_length=100, unique=True)
    duration_minutes = models.PositiveSmallIntegerField(default=30)

    def __str__(self):
        return self.name


class Reservation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pendiente", "Pendiente"
        CONFIRMED = "confirmada", "Confirmada"
        COMPLETED = "completada", "Completada"
        CANCELLED = "cancelada", "Cancelada"

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=30)
    email = models.EmailField(blank=True)
    service = models.ForeignKey(Service, on_delete=models.PROTECT, related_name="reservations")
    barber = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="barber_reservations",
    )
    client = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="client_reservations",
    )
    date = models.DateField()
    time = models.TimeField()
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("date", "time")
        indexes = [
            models.Index(fields=("barber", "date", "time", "status")),
        ]

    def __str__(self):
        return f"{self.date} {self.time} - {self.name}"
