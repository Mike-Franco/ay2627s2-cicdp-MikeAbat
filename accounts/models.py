from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models
from django.db.models import Q
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


class StaffInvitation(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUPERSEDED = "superseded", "Superseded"
        REVOKED = "revoked", "Revoked"
        REDEEMED = "redeemed", "Redeemed"
        EXPIRED = "expired", "Expired"

    target_email = models.EmailField(max_length=254)
    business = models.ForeignKey(
        "inventory_access.Business",
        on_delete=models.PROTECT,
        related_name="staff_invitations",
    )
    manager_membership = models.ForeignKey(
        "inventory_access.BusinessMembership",
        on_delete=models.PROTECT,
        related_name="sent_staff_invitations",
    )
    invited_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="staff_invitations_sent",
    )
    inventories = models.ManyToManyField(
        "inventory_access.Inventory",
        through="StaffInvitationInventory",
        related_name="staff_invitations",
    )
    token_digest = models.CharField(max_length=64, unique=True)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    redeemed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                Lower("target_email"),
                condition=Q(status="pending"),
                name="one_pending_staff_invite_per_email_ci",
            ),
        ]
        indexes = [
            models.Index(
                fields=["invited_by", "issued_at"],
                name="staffinv_by_issued_idx",
            ),
        ]


class StaffInvitationInventory(models.Model):
    invitation = models.ForeignKey(
        StaffInvitation,
        on_delete=models.CASCADE,
        related_name="inventory_links",
    )
    inventory = models.ForeignKey(
        "inventory_access.Inventory",
        on_delete=models.PROTECT,
        related_name="staff_invitation_links",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["invitation", "inventory"],
                name="unique_staff_invitation_inventory",
            ),
        ]


class PasswordResetAttempt(models.Model):
    """A permitted request, including requests for unknown or inactive identities."""

    identity_key = models.CharField(max_length=64, db_index=True)
    ip_key = models.CharField(max_length=64, db_index=True)
    requested_at = models.DateTimeField(db_index=True)


class PasswordResetLink(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SUPERSEDED = "superseded", "Superseded"
        REDEEMED = "redeemed", "Redeemed"

    user = models.ForeignKey("accounts.User", on_delete=models.PROTECT, related_name="password_reset_links")
    token_digest = models.CharField(max_length=64, unique=True)
    password_digest = models.CharField(max_length=64)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    issued_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    redeemed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(
            fields=["user"], condition=Q(status="pending"), name="one_pending_password_reset_per_user"
        )]
