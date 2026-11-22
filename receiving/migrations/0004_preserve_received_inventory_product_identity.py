from django.db import migrations


FORWARD_SQL = r"""
CREATE FUNCTION receiving_preserve_inventory_product_identity()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        -- Row UPDATE locks precede BEFORE triggers; rejecting reassignment here
        -- avoids taking parent locks in the reverse order of receipt writers.
        RAISE EXCEPTION 'inventory product identity cannot be reassigned'
            USING ERRCODE = '23514';
    END IF;
    IF OLD.physical_quantity_units > 0 OR EXISTS (
        SELECT 1 FROM receiving_receivingbatch WHERE inventory_product_id = OLD.id
    ) THEN
        RAISE EXCEPTION 'inventory product link with physical stock or receipt history is retained'
            USING ERRCODE = '23514';
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER a_receiving_inventory_product_identity_guard
BEFORE UPDATE OF inventory_id, product_id OR DELETE ON catalogue_inventoryproduct
FOR EACH ROW EXECUTE FUNCTION receiving_preserve_inventory_product_identity();
"""

REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS a_receiving_inventory_product_identity_guard ON catalogue_inventoryproduct;
DROP FUNCTION IF EXISTS receiving_preserve_inventory_product_identity();
"""


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0005_product_product_unit_label_nonblank_or_unset"),
        ("receiving", "0003_receipt_integrity_and_audit_guards"),
    ]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
