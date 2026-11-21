"""Validate seeded demo receipts against the date they simulate."""

from importlib import import_module

from django.db import migrations


previous = import_module("receiving.migrations.0015_csv_receipt_guards").updated
live_day = "(clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date"
receipt_day = """(CASE
           WHEN NEW.source = 'manual' AND v_role_name = 'manager'
                AND current_setting('tory.demo_receipt_token', true) = NEW.request_token::text
                AND NEW.received_at < clock_timestamp()
                AND NEW.received_at >= clock_timestamp() - interval '8 days'
                AND EXISTS (SELECT 1 FROM inventory_access_business
                            WHERE id = inventory_business_id AND name = 'Tory Demo')
           THEN (NEW.received_at AT TIME ZONE 'Asia/Singapore')::date
           ELSE (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date
       END)"""


class Migration(migrations.Migration):
    dependencies = [("receiving", "0021_stockout_request_token")]
    operations = [migrations.RunSQL(previous.replace(live_day, receipt_day, 1), previous)]
