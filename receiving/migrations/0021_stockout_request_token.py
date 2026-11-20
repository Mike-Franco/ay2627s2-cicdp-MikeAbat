from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("receiving", "0020_alter_observationactivation_environment_and_more")]

    operations = [
        migrations.AddField(
            model_name="stockout",
            name="request_token",
            field=models.UUIDField(editable=False, null=True),
        ),
        migrations.AddConstraint(
            model_name="stockout",
            constraint=models.UniqueConstraint(
                fields=["actor", "request_token"],
                condition=models.Q(request_token__isnull=False),
                name="unique_actor_stock_out_request_token",
            ),
        ),
    ]
