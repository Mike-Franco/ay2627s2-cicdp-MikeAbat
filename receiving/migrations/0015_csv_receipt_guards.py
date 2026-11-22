"""Permit only linked CSV receipts while retaining the existing stock guard."""

import importlib
import re

from django.db import migrations


prior = importlib.import_module("receiving.migrations.0006_stable_expiry_rejection_identifier")
pattern = (r"CREATE OR REPLACE FUNCTION receiving_check_batch_scope_and_update_balance\(\)"
           r"\s+RETURNS trigger AS \$\$.*?\$\$ LANGUAGE plpgsql;")
original = re.search(pattern, prior.FORWARD_SQL, re.DOTALL).group()
updated = original.replace("NEW.source <> 'manual'", "NEW.source NOT IN ('manual','csv')", 1)
updated = updated.replace(
    "    SELECT physical_quantity_units, last_receipt_sequence",
    """    IF (NEW.source='manual' AND (NEW.import_record_id IS NOT NULL OR NEW.import_row_number IS NOT NULL))
       OR (NEW.source='csv' AND (NEW.import_record_id IS NULL OR NEW.import_row_number IS NULL OR NEW.import_row_number < 2
            OR NOT EXISTS (SELECT 1 FROM receiving_stockimport i
                           WHERE i.id=NEW.import_record_id AND i.actor_id=NEW.actor_id
                             AND i.inventory_id=NEW.inventory_id))) THEN
        RAISE EXCEPTION 'receipt import identity is invalid' USING ERRCODE='23514';
    END IF;
    IF NEW.source='csv' AND (v_role_name <> 'manager' OR expiry_required IS DISTINCT FROM FALSE
                             OR NEW.expiry_date IS NOT NULL) THEN
        RAISE EXCEPTION 'CSV receipt requires a Manager and an undated non-tracked product'
            USING ERRCODE='23514';
    END IF;
    SELECT physical_quantity_units, last_receipt_sequence""",
    1,
)

forward = updated + r"""
CREATE FUNCTION receiving_guard_csv_stockout_identity()
RETURNS trigger AS $$
BEGIN
    IF (NEW.import_record_id IS NULL AND NEW.import_row_number IS NOT NULL)
       OR (NEW.import_record_id IS NOT NULL AND
           (NEW.import_row_number IS NULL OR NEW.import_row_number < 2
            OR NOT EXISTS (SELECT 1 FROM receiving_stockimport i
                           WHERE i.id=NEW.import_record_id AND i.actor_id=NEW.actor_id
                             AND i.inventory_id=NEW.inventory_id))) THEN
        RAISE EXCEPTION 'issue import identity is invalid' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER receiving_csv_stockout_identity_guard BEFORE INSERT ON receiving_stockout
FOR EACH ROW EXECUTE FUNCTION receiving_guard_csv_stockout_identity();
"""

reverse = r"""
DROP TRIGGER IF EXISTS receiving_csv_stockout_identity_guard ON receiving_stockout;
DROP FUNCTION IF EXISTS receiving_guard_csv_stockout_identity();
""" + original


class Migration(migrations.Migration):
    dependencies = [("receiving", "0014_receivingbatch_import_row_number_and_more")]
    operations = [migrations.RunSQL(forward, reverse)]
