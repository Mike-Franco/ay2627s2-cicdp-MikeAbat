from django.db import migrations


FORWARD_SQL = """
CREATE FUNCTION inventory_access_check_assignment_business()
RETURNS trigger AS $$
DECLARE
    membership_business_id bigint;
    inventory_business_id bigint;
BEGIN
    -- Lock both scope rows in a stable order; parent business moves use
    -- conflicting row locks, so concurrent inserts cannot race the check.
    SELECT business_id INTO membership_business_id
      FROM inventory_access_businessmembership WHERE id = NEW.membership_id FOR SHARE;
    SELECT business_id INTO inventory_business_id
      FROM inventory_access_inventory WHERE id = NEW.inventory_id FOR SHARE;
    IF membership_business_id IS NULL OR inventory_business_id IS NULL
       OR membership_business_id <> inventory_business_id THEN
        RAISE EXCEPTION 'inventory assignment must remain within one business'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER inventory_access_assignment_business_guard
BEFORE INSERT OR UPDATE OF membership_id, inventory_id
ON inventory_access_inventoryassignment
FOR EACH ROW EXECUTE FUNCTION inventory_access_check_assignment_business();

CREATE FUNCTION inventory_access_prevent_assigned_business_move()
RETURNS trigger AS $$
BEGIN
    IF OLD.business_id IS DISTINCT FROM NEW.business_id THEN
        IF TG_TABLE_NAME = 'inventory_access_businessmembership' AND EXISTS (
            SELECT 1 FROM inventory_access_inventoryassignment
            WHERE membership_id = OLD.id
        ) THEN
            RAISE EXCEPTION 'cannot move a membership with inventory assignments'
                USING ERRCODE = '23514';
        ELSIF TG_TABLE_NAME = 'inventory_access_inventory' AND EXISTS (
            SELECT 1 FROM inventory_access_inventoryassignment
            WHERE inventory_id = OLD.id
        ) THEN
            RAISE EXCEPTION 'cannot move an inventory with assignments'
                USING ERRCODE = '23514';
        END IF;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER inventory_access_membership_business_guard
BEFORE UPDATE OF business_id ON inventory_access_businessmembership
FOR EACH ROW EXECUTE FUNCTION inventory_access_prevent_assigned_business_move();

CREATE TRIGGER inventory_access_inventory_business_guard
BEFORE UPDATE OF business_id ON inventory_access_inventory
FOR EACH ROW EXECUTE FUNCTION inventory_access_prevent_assigned_business_move();
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS inventory_access_inventory_business_guard ON inventory_access_inventory;
DROP TRIGGER IF EXISTS inventory_access_membership_business_guard ON inventory_access_businessmembership;
DROP TRIGGER IF EXISTS inventory_access_assignment_business_guard ON inventory_access_inventoryassignment;
DROP FUNCTION IF EXISTS inventory_access_prevent_assigned_business_move();
DROP FUNCTION IF EXISTS inventory_access_check_assignment_business();
"""


class Migration(migrations.Migration):
    dependencies = [("inventory_access", "0001_initial")]

    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
