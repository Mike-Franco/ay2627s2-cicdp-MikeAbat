"""Schedule environment observation at a future Singapore midnight."""

from datetime import date

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from receiving.commit_times import current_xid, finalize_activation, lock_activation, tracking_enabled
from receiving.models import ObservationActivation


class Command(BaseCommand):
    help = "Activate demand observation from a future complete Singapore date."

    def add_arguments(self, parser):
        parser.add_argument("first_observed_date", help="Future Singapore date in YYYY-MM-DD format")

    def handle(self, *args, **options):
        try:
            first_day = date.fromisoformat(options["first_observed_date"])
        except ValueError as error:
            raise CommandError("Enter a valid ISO date.") from error
        if first_day <= timezone.localdate():
            raise CommandError("Observation must start on a future complete Singapore date.")
        if not tracking_enabled():
            raise CommandError("PostgreSQL commit-time tracking is required before coverage activation.")
        with transaction.atomic():
            lock_activation(shared=False)
            if ObservationActivation.objects.filter(environment=settings.DJANGO_ENV,
                                                     state__in=("pending", "active")).exists():
                raise CommandError("Observation activation already exists for this environment.")
            record = ObservationActivation.objects.create(
                environment=settings.DJANGO_ENV, first_observed_date=first_day,
                origin_xid=current_xid(),
            )
            transaction.on_commit(lambda: finalize_activation(record.pk), robust=True)
        self.stdout.write(f"Activation requested for {first_day}; verify finalization before use.")
