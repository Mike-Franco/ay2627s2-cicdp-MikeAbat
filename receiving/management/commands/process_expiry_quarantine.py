from django.core.management.base import BaseCommand

from receiving.services import process_expiry_quarantine


class Command(BaseCommand):
    help = "Record due expiry quarantine transitions, safely repeatable."

    def handle(self, *args, **options):
        created = process_expiry_quarantine()
        self.stdout.write(f"Recorded {created} expiry quarantine event(s).")
