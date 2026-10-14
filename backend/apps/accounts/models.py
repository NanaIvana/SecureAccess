from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


class Role(models.TextChoices):
    UTILISATEUR = "UTILISATEUR", "Utilisateur"
    ADMIN = "ADMIN", "Administrateur"
    RESPONSABLE = "RESPONSABLE", "Responsable d'institution"


class WorkProfile(models.TextChoices):
    JOURNEE = "JOURNEE", "Journée (7h-18h)"
    SOIREE = "SOIREE", "Soirée (17h-23h)"
    MIXTE = "MIXTE", "Mixte"


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, email, password=None, **extra):
        if not email:
            raise ValueError("L'e-mail est obligatoire")
        user = self.model(email=self.normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", Role.ADMIN)
        return self.create_user(email, password, **extra)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.UTILISATEUR)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    blocked_until = models.DateTimeField(null=True, blank=True)
    home_city = models.CharField(max_length=100, blank=True)
    home_country = models.CharField(max_length=100, blank=True)
    home_lat = models.FloatField(null=True, blank=True)
    home_lon = models.FloatField(null=True, blank=True)
    work_profile = models.CharField(max_length=10, choices=WorkProfile.choices, default=WorkProfile.JOURNEE)
    created_at = models.DateTimeField(default=timezone.now)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    def is_blocked(self):
        return self.blocked_until is not None and self.blocked_until > timezone.now()

    def __str__(self):
        return self.email

