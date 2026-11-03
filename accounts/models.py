from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models.functions import Lower


class EmailUserManager(UserManager):
    """Django's ModelBackend calls get_by_natural_key for email login.

    The owner selected case-insensitive unique email identity for TORY-10;
    Manager provisioning and business roles remain separate decisions.
    """

    def normalize_email(self, email):
        return email.strip().casefold()

    def get_by_natural_key(self, username):
        return self.get(email__iexact=username.strip())

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("An email address is required")
        user = self.model(email=self.normalize_email(email), **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields["is_staff"] is not True or extra_fields["is_superuser"] is not True:
            raise ValueError("A superuser must have is_staff and is_superuser")
        return self.create_user(email, password, **extra_fields)


class User(AbstractUser):
    """The database constraint also rejects case collisions from direct ORM writes."""

    username = None
    email = models.EmailField(unique=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = EmailUserManager()

    class Meta:
        constraints = [models.UniqueConstraint(Lower("email"), name="unique_user_email_ci")]


class LoginFailure(models.Model):
    """Hashed throttle state, not the still-open G-09 security audit policy."""

    identity_key = models.CharField(max_length=64, db_index=True)
    ip_key = models.CharField(max_length=64, db_index=True)
    occurred_at = models.DateTimeField(db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["identity_key", "occurred_at"]),
            models.Index(fields=["ip_key", "occurred_at"]),
        ]
