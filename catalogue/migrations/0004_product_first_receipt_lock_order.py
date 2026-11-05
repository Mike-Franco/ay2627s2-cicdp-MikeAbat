from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION catalogue_check_inventory_product_business()
RETURNS trigger AS $$
DECLARE
    inventory_business_id bigint;
    product_business_id bigint;
BEGIN
    -- Receipt/deactivation share Product as the first parent lock.
    SELECT business_id INTO product_business_id
      FROM catalogue_product WHERE id = NEW.product_id FOR SHARE;
    SELECT business_id INTO inventory_business_id
      FROM inventory_access_inventory WHERE id = NEW.inventory_id FOR SHARE;
    IF inventory_business_id IS NULL OR product_business_id IS NULL
       OR inventory_business_id <> product_business_id THEN
        RAISE EXCEPTION 'inventory product link must remain within one business'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION catalogue_guard_inventory_product_stock_columns()
RETURNS trigger AS $$
BEGIN
    IF (OLD.physical_quantity_units IS DISTINCT FROM NEW.physical_quantity_units
        OR OLD.last_receipt_sequence IS DISTINCT FROM NEW.last_receipt_sequence)
       AND pg_trigger_depth() < 2 THEN
        RAISE EXCEPTION 'receipt balance and sequence are maintained by batch insertion'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER catalogue_inventory_product_stock_columns_guard
BEFORE UPDATE OF physical_quantity_units, last_receipt_sequence
ON catalogue_inventoryproduct
FOR EACH ROW EXECUTE FUNCTION catalogue_guard_inventory_product_stock_columns();
"""

REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS catalogue_inventory_product_stock_columns_guard ON catalogue_inventoryproduct;
DROP FUNCTION IF EXISTS catalogue_guard_inventory_product_stock_columns();

CREATE OR REPLACE FUNCTION catalogue_check_inventory_product_business()
RETURNS trigger AS $$
DECLARE
    inventory_business_id bigint;
    product_business_id bigint;
BEGIN
    SELECT business_id INTO inventory_business_id
      FROM inventory_access_inventory WHERE id = NEW.inventory_id FOR SHARE;
    SELECT business_id INTO product_business_id
      FROM catalogue_product WHERE id = NEW.product_id FOR SHARE;
    IF inventory_business_id IS NULL OR product_business_id IS NULL
       OR inventory_business_id <> product_business_id THEN
        RAISE EXCEPTION 'inventory product link must remain within one business'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0003_inventoryproduct_last_receipt_sequence_and_more"),
        ("receiving", "0002_receivingbatch_receiving_batch_fingerprint_sha256_and_more"),
    ]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
