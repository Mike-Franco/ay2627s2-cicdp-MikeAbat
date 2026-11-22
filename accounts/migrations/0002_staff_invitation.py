import django.db.models.deletion
import django.db.models.functions.text
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0001_initial"),
        ("inventory_access", "0002_enforce_assignment_business_match"),
    ]

    operations = [
        migrations.CreateModel(
            name="StaffInvitation",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("target_email", models.EmailField(max_length=254)),
                ("token_digest", models.CharField(max_length=64, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("superseded", "Superseded"),
                            ("revoked", "Revoked"),
                            ("redeemed", "Redeemed"),
                            ("expired", "Expired"),
                        ],
                        default="pending",
                        max_length=12,
                    ),
                ),
                ("issued_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField()),
                ("redeemed_at", models.DateTimeField(blank=True, null=True)),
                (
                    "business",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="staff_invitations",
                        to="inventory_access.business",
                    ),
                ),
                (
                    "invited_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="staff_invitations_sent",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "manager_membership",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="sent_staff_invitations",
                        to="inventory_access.businessmembership",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="StaffInvitationInventory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "invitation",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="inventory_links",
                        to="accounts.staffinvitation",
                    ),
                ),
                (
                    "inventory",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="staff_invitation_links",
                        to="inventory_access.inventory",
                    ),
                ),
            ],
        ),
        migrations.AddField(
            model_name="staffinvitation",
            name="inventories",
            field=models.ManyToManyField(
                related_name="staff_invitations",
                through="accounts.StaffInvitationInventory",
                to="inventory_access.inventory",
            ),
        ),
        migrations.AddConstraint(
            model_name="staffinvitation",
            constraint=models.UniqueConstraint(
                django.db.models.functions.text.Lower("target_email"),
                condition=Q(status="pending"),
                name="one_pending_staff_invite_per_email_ci",
            ),
        ),
        migrations.AddConstraint(
            model_name="staffinvitationinventory",
            constraint=models.UniqueConstraint(
                fields=("invitation", "inventory"),
                name="unique_staff_invitation_inventory",
            ),
        ),
        migrations.AddIndex(
            model_name="staffinvitation",
            index=models.Index(
                fields=["invited_by", "issued_at"],
                name="staffinv_by_issued_idx",
            ),
        ),
    ]
