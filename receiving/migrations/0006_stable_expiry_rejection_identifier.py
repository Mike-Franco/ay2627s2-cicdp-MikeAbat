from django.db import migrations


FORWARD_SQL = r"""
CREATE OR REPLACE FUNCTION receiving_check_batch_scope_and_update_balance()
RETURNS trigger AS $$
DECLARE
    actor_active boolean;
    v_membership_id bigint;
    inventory_business_id bigint;
    product_business_id bigint;
    inventory_active boolean;
    v_membership_active boolean;
    v_role_name varchar(12);
    v_assignment_active boolean;
    product_active boolean;
    expiry_required boolean;
    product_unit_label varchar(40);
    current_balance bigint;
    last_sequence bigint;
BEGIN
    SELECT is_active INTO actor_active
      FROM accounts_user WHERE id = NEW.actor_id FOR SHARE;
    SELECT id, is_active, role INTO v_membership_id, v_membership_active, v_role_name
      FROM inventory_access_businessmembership
      WHERE user_id = NEW.actor_id AND business_id = (
          SELECT business_id FROM inventory_access_inventory WHERE id = NEW.inventory_id
      ) FOR SHARE;
    SELECT is_active INTO v_assignment_active
      FROM inventory_access_inventoryassignment
      WHERE membership_id = v_membership_id AND inventory_id = NEW.inventory_id FOR SHARE;
    IF actor_active IS DISTINCT FROM TRUE OR v_membership_active IS DISTINCT FROM TRUE
       OR v_assignment_active IS DISTINCT FROM TRUE OR v_role_name NOT IN ('manager', 'staff') THEN
        RAISE EXCEPTION 'active assigned account required for receipt'
            USING ERRCODE = '23514';
    END IF;

    SELECT business_id, is_active, expiry_tracking_required, base_unit_label
      INTO product_business_id, product_active, expiry_required, product_unit_label
      FROM catalogue_product WHERE id = NEW.product_id FOR SHARE;
    SELECT business_id, is_active INTO inventory_business_id, inventory_active
      FROM inventory_access_inventory WHERE id = NEW.inventory_id FOR SHARE;
    IF product_business_id IS NULL OR inventory_business_id IS NULL
       OR product_business_id <> inventory_business_id
       OR inventory_active IS DISTINCT FROM TRUE
       OR product_business_id <> (
           SELECT business_id FROM inventory_access_businessmembership WHERE id = v_membership_id
       ) THEN
        RAISE EXCEPTION 'receipt scope must remain within one business'
            USING ERRCODE = '23514';
    END IF;
    IF product_active IS DISTINCT FROM TRUE OR expiry_required IS NULL
       OR product_unit_label IS NULL OR btrim(product_unit_label) = ''
       OR NEW.unit_label_snapshot IS DISTINCT FROM product_unit_label THEN
        RAISE EXCEPTION 'active product receiving configuration required'
            USING ERRCODE = '23514';
    END IF;
    IF expiry_required AND NEW.expiry_date IS NULL THEN
        RAISE EXCEPTION 'expiry date required for tracked product' USING ERRCODE = '23514';
    END IF;
    IF NEW.expiry_date IS NOT NULL
       AND NEW.expiry_date <= (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date THEN
        RAISE EXCEPTION 'receipt expiry must be after Singapore today'
            USING ERRCODE = '23514', CONSTRAINT = 'receiving_expiry_after_singapore_today';
    END IF;

    SELECT physical_quantity_units, last_receipt_sequence
      INTO current_balance, last_sequence
      FROM catalogue_inventoryproduct
      WHERE id = NEW.inventory_product_id
        AND inventory_id = NEW.inventory_id AND product_id = NEW.product_id
      FOR UPDATE;
    IF current_balance IS NULL THEN
        RAISE EXCEPTION 'active same-business inventory product link required'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.source <> 'manual' OR NEW.quantity_units < 1 OR NEW.quantity_units > 2147483647
       OR current_balance + NEW.quantity_units > 2147483647 THEN
        RAISE EXCEPTION 'receipt or physical balance exceeds approved range'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.remaining_quantity_units <> NEW.quantity_units
       OR NEW.quarantined_quantity_units <> 0 THEN
        RAISE EXCEPTION 'a new receipt begins fully physical and not quarantined'
            USING ERRCODE = '23514';
    END IF;
    IF NEW.receipt_sequence <> last_sequence + 1 THEN
        RAISE EXCEPTION 'receipt sequence must be the next committed sequence'
            USING ERRCODE = '23514';
    END IF;
    UPDATE catalogue_inventoryproduct
       SET physical_quantity_units = current_balance + NEW.quantity_units,
           last_receipt_sequence = NEW.receipt_sequence
     WHERE id = NEW.inventory_product_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

REVERSE_SQL = r"""
CREATE OR REPLACE FUNCTION receiving_check_batch_scope_and_update_balance()
RETURNS trigger AS $$
DECLARE
    actor_active boolean;
    v_membership_id bigint;
    inventory_business_id bigint;
    product_business_id bigint;
    inventory_active boolean;
    v_membership_active boolean;
    v_role_name varchar(12);
    v_assignment_active boolean;
    product_active boolean;
    expiry_required boolean;
    product_unit_label varchar(40);
    current_balance bigint;
    last_sequence bigint;
BEGIN
    SELECT is_active INTO actor_active FROM accounts_user WHERE id = NEW.actor_id FOR SHARE;
    SELECT id, is_active, role INTO v_membership_id, v_membership_active, v_role_name
      FROM inventory_access_businessmembership
      WHERE user_id = NEW.actor_id AND business_id = (
          SELECT business_id FROM inventory_access_inventory WHERE id = NEW.inventory_id
      ) FOR SHARE;
    SELECT is_active INTO v_assignment_active FROM inventory_access_inventoryassignment
      WHERE membership_id = v_membership_id AND inventory_id = NEW.inventory_id FOR SHARE;
    IF actor_active IS DISTINCT FROM TRUE OR v_membership_active IS DISTINCT FROM TRUE
       OR v_assignment_active IS DISTINCT FROM TRUE OR v_role_name NOT IN ('manager', 'staff') THEN
        RAISE EXCEPTION 'active assigned account required for receipt' USING ERRCODE = '23514';
    END IF;
    SELECT business_id, is_active, expiry_tracking_required, base_unit_label
      INTO product_business_id, product_active, expiry_required, product_unit_label
      FROM catalogue_product WHERE id = NEW.product_id FOR SHARE;
    SELECT business_id, is_active INTO inventory_business_id, inventory_active
      FROM inventory_access_inventory WHERE id = NEW.inventory_id FOR SHARE;
    IF product_business_id IS NULL OR inventory_business_id IS NULL
       OR product_business_id <> inventory_business_id OR inventory_active IS DISTINCT FROM TRUE
       OR product_business_id <> (
           SELECT business_id FROM inventory_access_businessmembership WHERE id = v_membership_id
       ) THEN
        RAISE EXCEPTION 'receipt scope must remain within one business' USING ERRCODE = '23514';
    END IF;
    IF product_active IS DISTINCT FROM TRUE OR expiry_required IS NULL
       OR product_unit_label IS NULL OR btrim(product_unit_label) = ''
       OR NEW.unit_label_snapshot IS DISTINCT FROM product_unit_label THEN
        RAISE EXCEPTION 'active product receiving configuration required' USING ERRCODE = '23514';
    END IF;
    IF expiry_required AND NEW.expiry_date IS NULL THEN
        RAISE EXCEPTION 'expiry date required for tracked product' USING ERRCODE = '23514';
    END IF;
    IF NEW.expiry_date IS NOT NULL
       AND NEW.expiry_date <= (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date THEN
        RAISE EXCEPTION 'receipt expiry must be after Singapore today' USING ERRCODE = '23514';
    END IF;
    SELECT physical_quantity_units, last_receipt_sequence INTO current_balance, last_sequence
      FROM catalogue_inventoryproduct WHERE id = NEW.inventory_product_id
        AND inventory_id = NEW.inventory_id AND product_id = NEW.product_id FOR UPDATE;
    IF current_balance IS NULL THEN
        RAISE EXCEPTION 'active same-business inventory product link required' USING ERRCODE = '23514';
    END IF;
    IF NEW.source <> 'manual' OR NEW.quantity_units < 1 OR NEW.quantity_units > 2147483647
       OR current_balance + NEW.quantity_units > 2147483647 THEN
        RAISE EXCEPTION 'receipt or physical balance exceeds approved range' USING ERRCODE = '23514';
    END IF;
    IF NEW.remaining_quantity_units <> NEW.quantity_units OR NEW.quarantined_quantity_units <> 0 THEN
        RAISE EXCEPTION 'a new receipt begins fully physical and not quarantined' USING ERRCODE = '23514';
    END IF;
    IF NEW.receipt_sequence <> last_sequence + 1 THEN
        RAISE EXCEPTION 'receipt sequence must be the next committed sequence' USING ERRCODE = '23514';
    END IF;
    UPDATE catalogue_inventoryproduct SET physical_quantity_units = current_balance + NEW.quantity_units,
        last_receipt_sequence = NEW.receipt_sequence WHERE id = NEW.inventory_product_id;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0006_inventory_product_zero_initial_stock"),
        ("receiving", "0005_receiptauditevent_receipt_audit_quantity_cap"),
    ]
    operations = [migrations.RunSQL(FORWARD_SQL, REVERSE_SQL)]
