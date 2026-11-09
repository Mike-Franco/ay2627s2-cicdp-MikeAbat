"""Retry commit-time finalization after a process crash or callback failure."""

from django.core.management.base import BaseCommand

from receiving.commit_times import finalize_activation, finalize_stock_import, tracking_enabled
from receiving.models import ObservationActivation, StockImport


class Command(BaseCommand):
    help = "Finalize pending PostgreSQL commit timestamps without changing stock."

    def handle(self, *args, **options):
        if not tracking_enabled():
            self.stdout.write("Commit-time tracking is unavailable; pending records remain unresolved.")
            return
        activations = list(ObservationActivation.objects.filter(state="pending").values_list("pk", flat=True))
        imports = list(StockImport.objects.filter(commit_attribution="pending").values_list("pk", flat=True))
        completed = sum(finalize_activation(pk) for pk in activations)
        completed += sum(finalize_stock_import(pk) for pk in imports)
        self.stdout.write(f"Finalized {completed}; unresolved {len(activations) + len(imports) - completed}.")
