import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_staff_invitation")]

    operations = [
        migrations.CreateModel(
            name="PasswordResetAttempt",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("identity_key", models.CharField(db_index=True, max_length=64)),
                ("ip_key", models.CharField(db_index=True, max_length=64)),
                ("requested_at", models.DateTimeField(db_index=True)),
            ],
        ),
        migrations.CreateModel(
            name="PasswordResetLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token_digest", models.CharField(max_length=64, unique=True)),
                ("password_digest", models.CharField(max_length=64)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("superseded", "Superseded"), ("redeemed", "Redeemed")], default="pending", max_length=12)),
                ("issued_at", models.DateTimeField()),
                ("expires_at", models.DateTimeField()),
                ("redeemed_at", models.DateTimeField(blank=True, null=True)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="password_reset_links", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddConstraint(
            model_name="passwordresetlink",
            constraint=models.UniqueConstraint(fields=("user",), condition=Q(status="pending"), name="one_pending_password_reset_per_user"),
        ),
    ]
