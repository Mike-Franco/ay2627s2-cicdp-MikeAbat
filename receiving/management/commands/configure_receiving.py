from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from catalogue.models import Product

from receiving.models import ReceivingBatch


class Command(BaseCommand):
    help = "Set the required receiving unit and expiry policy for one unconfigured product."

    def add_arguments(self, parser):
        parser.add_argument("product_id", type=int)
        parser.add_argument("--base-unit-label", required=True)
        parser.add_argument(
            "--expiry-tracking-required", required=True, choices=("true", "false")
        )

    def handle(self, *args, **options):
        label = options["base_unit_label"].strip()
        if not label:
            raise CommandError("Base-unit label cannot be blank.")
        if len(label) > Product._meta.get_field("base_unit_label").max_length:
            raise CommandError("Base-unit label is too long.")

        with transaction.atomic():
            try:
                product = Product.objects.select_for_update().get(pk=options["product_id"])
            except Product.DoesNotExist as error:
                raise CommandError("Product does not exist.") from error
            if product.base_unit_label is not None or product.expiry_tracking_required is not None:
                raise CommandError("Product receiving configuration is already set.")
            if ReceivingBatch.objects.filter(product=product).exists():
                raise CommandError("A product with receipt history cannot be configured by this command.")
            product.base_unit_label = label
            product.expiry_tracking_required = options["expiry_tracking_required"] == "true"
            product.save(update_fields=["base_unit_label", "expiry_tracking_required"])
        self.stdout.write(self.style.SUCCESS(f"Receiving configured for product {product.pk}."))
