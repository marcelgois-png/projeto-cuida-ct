from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Admin"
        OPERATOR = "operator", "Operador"
        DIRECTOR = "director", "Diretor"

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.OPERATOR,
        verbose_name="perfil",
    )
    nome_completo = models.CharField(max_length=255)
    matricula = models.CharField(max_length=50, blank=True)
    telefone = models.CharField(max_length=50)
    foto = models.ImageField(upload_to="usuarios/fotos/", blank=True, null=True)

    @property
    def is_admin(self) -> bool:
        return self.is_superuser or self.role == self.Role.ADMIN

    @property
    def is_operator(self) -> bool:
        return self.is_admin or self.role == self.Role.OPERATOR

    @property
    def is_director(self) -> bool:
        return self.is_admin or self.role == self.Role.DIRECTOR

    def save(self, *args, **kwargs):
        if self.is_admin:
            self.is_staff = True
        super().save(*args, **kwargs)

