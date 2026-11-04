from django.db import migrations


FORWARD_SQL = """
CREATE FUNCTION catalogue_preserve_product_identity()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'product identity and SKU reservation are permanent'
            USING ERRCODE = '23514';
    END IF;
    IF TG_OP = 'INSERT' THEN
        NEW.sku := btrim(NEW.sku);
        IF NEW.sku = '' THEN
            RAISE EXCEPTION 'SKU is required' USING ERRCODE = '23514';
        END IF;
    ELSIF OLD.sku IS DISTINCT FROM NEW.sku
       OR OLD.business_id IS DISTINCT FROM NEW.business_id THEN
        RAISE EXCEPTION 'SKU and owning business cannot be reassigned'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER catalogue_product_identity_guard
BEFORE INSERT OR UPDATE OR DELETE ON catalogue_product
FOR EACH ROW EXECUTE FUNCTION catalogue_preserve_product_identity();

CREATE FUNCTION catalogue_check_inventory_product_business()
RETURNS trigger AS $$
DECLARE
    inventory_business_id bigint;
    product_business_id bigint;
BEGIN
    -- Fixed parent lock order serializes links against business-scope changes.
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

CREATE TRIGGER catalogue_inventory_product_business_guard
BEFORE INSERT OR UPDATE OF inventory_id, product_id ON catalogue_inventoryproduct
FOR EACH ROW EXECUTE FUNCTION catalogue_check_inventory_product_business();

CREATE FUNCTION catalogue_prevent_linked_business_move()
RETURNS trigger AS $$
BEGIN
    IF OLD.business_id IS DISTINCT FROM NEW.business_id THEN
        IF TG_TABLE_NAME = 'catalogue_product' AND EXISTS (
            SELECT 1 FROM catalogue_inventoryproduct WHERE product_id = OLD.id
        ) THEN
            RAISE EXCEPTION 'cannot move a product with inventory links'
                USING ERRCODE = '23514';
        ELSIF TG_TABLE_NAME = 'inventory_access_inventory' AND EXISTS (
            SELECT 1 FROM catalogue_inventoryproduct WHERE inventory_id = OLD.id
        ) THEN
            RAISE EXCEPTION 'cannot move an inventory with product links'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER catalogue_product_business_guard
BEFORE UPDATE OF business_id ON catalogue_product
FOR EACH ROW EXECUTE FUNCTION catalogue_prevent_linked_business_move();

CREATE TRIGGER catalogue_inventory_business_guard
BEFORE UPDATE OF business_id ON inventory_access_inventory
FOR EACH ROW EXECUTE FUNCTION catalogue_prevent_linked_business_move();
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS catalogue_inventory_business_guard ON inventory_access_inventory;
DROP TRIGGER IF EXISTS catalogue_product_business_guard ON catalogue_product;
DROP TRIGGER IF EXISTS catalogue_inventory_product_business_guard ON catalogue_inventoryproduct;
DROP TRIGGER IF EXISTS catalogue_product_identity_guard ON catalogue_product;
DROP FUNCTION IF EXISTS catalogue_prevent_linked_business_move();
DROP FUNCTION IF EXISTS catalogue_check_inventory_product_business();
DROP FUNCTION IF EXISTS catalogue_preserve_product_identity();
"""


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0001_initial")]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
