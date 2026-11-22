from django.contrib.auth.models import AbstractUser, UserManager
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower

from config.palette import DEFAULT_TONE, TONE_CHOICES, TONE_KEYS


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


# Loose on purpose (Singapore and international formats): an optional leading
# +, then digits with spaces, brackets or dashes, holding 6 to 15 digits (E.164).
PHONE_VALIDATOR = RegexValidator(
    r"^(?=(?:\D*\d){6,15}\D*$)\+?[0-9(][0-9 ()\-]{5,23}$",
    "Enter a phone number using digits, spaces, brackets or dashes, for example +65 6123 4567.",
)


class User(AbstractUser):
    """The database constraint also rejects case collisions from direct ORM writes.

    Profile fields (TORY-55) live on the user row so every page that already
    loads a user can show their name and avatar without another query.
    """

    username = None
    email = models.EmailField(unique=True)
    display_name = models.CharField(max_length=60, blank=True)
    job_title = models.CharField(max_length=60, blank=True)
    phone = models.CharField(max_length=24, blank=True, validators=[PHONE_VALIDATOR])
    avatar_colour = models.CharField(max_length=12, choices=TONE_CHOICES, default=DEFAULT_TONE)
    # Written only by config.media (re-encoded WebP, random name).
    photo = models.FileField(upload_to="avatars/", max_length=120, blank=True)
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = EmailUserManager()

    class Meta:
        constraints = [
            models.UniqueConstraint(Lower("email"), name="unique_user_email_ci"),
            models.CheckConstraint(condition=Q(avatar_colour__in=sorted(TONE_KEYS)), name="user_avatar_colour_preset"),
        ]

    @property
    def display_label(self):
        """The name to show for this user: display name, full name, then email."""
        return self.display_name.strip() or self.get_full_name().strip() or self.email

    @property
    def initials(self):
        """Up to two letters for the avatar circle, taken from the display label."""
        label = self.display_name.strip() or self.get_full_name().strip()
        if label:
            words = [word for word in label.split() if word[:1].isalnum()]
            letters = "".join(word[0] for word in (words[:1] + words[1:][-1:]))
            if letters:
                return letters.upper()
        return (self.email[:1] or "?").upper()


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
