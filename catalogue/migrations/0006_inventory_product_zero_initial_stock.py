from django.db import migrations


FORWARD_SQL = r"""
CREATE FUNCTION catalogue_require_zero_inventory_product_initial_stock()
RETURNS trigger AS $$
BEGIN
    IF NEW.physical_quantity_units IS DISTINCT FROM 0
       OR NEW.last_receipt_sequence IS DISTINCT FROM 0 THEN
        RAISE EXCEPTION 'inventory product links must start with zero stock and sequence'
            USING ERRCODE = '23514', CONSTRAINT = 'inventory_product_initial_stock_zero';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER catalogue_inventory_product_initial_stock_guard
BEFORE INSERT ON catalogue_inventoryproduct
FOR EACH ROW EXECUTE FUNCTION catalogue_require_zero_inventory_product_initial_stock();
"""

REVERSE_SQL = r"""
DROP TRIGGER IF EXISTS catalogue_inventory_product_initial_stock_guard ON catalogue_inventoryproduct;
DROP FUNCTION IF EXISTS catalogue_require_zero_inventory_product_initial_stock();
"""


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0005_product_product_unit_label_nonblank_or_unset")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
