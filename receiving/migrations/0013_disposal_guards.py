"""Extend the existing stock guards without weakening receipt, issue or count paths.

The replacements below start from the frozen 0008/0011 migration definitions.
Reverse restores those exact definitions after removing disposal-only triggers.
"""

import importlib
import re

from django.db import migrations


prior_stock = importlib.import_module("receiving.migrations.0008_manager_stock_adjustments").ADJUSTMENT_GUARDS
prior_expiry = importlib.import_module("receiving.migrations.0011_expiry_quarantine_guards").FORWARD


def old_function(source, name):
    pattern = rf"CREATE(?: OR REPLACE)? FUNCTION {name}\(\)\s+RETURNS trigger AS \$\$.*?\$\$ LANGUAGE plpgsql;"
    match = re.search(pattern, source, re.DOTALL)
    if not match:
        raise ValueError(f"Missing frozen trigger function {name}")
    return match.group().replace("CREATE FUNCTION", "CREATE OR REPLACE FUNCTION", 1)


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise ValueError(f"Expected one migration insertion point: {old[:60]}")
    return source.replace(old, new)


names = (
    "receiving_prevent_batch_evidence_erasure",
    "receiving_allow_stock_out_batch_update",
    "catalogue_guard_inventory_product_stock_columns",
    "receiving_allow_stock_out_balance_update",
)
original = {name: old_function(prior_stock, name) for name in names}
original["receiving_guard_expiry_batch_update"] = old_function(prior_expiry, "receiving_guard_expiry_batch_update")
original["receiving_validate_expiry_event"] = old_function(prior_expiry, "receiving_validate_expiry_event")
updated = original.copy()

disposal_batch_match = """EXISTS (SELECT 1 FROM receiving_stockdisposal d
                        WHERE d.batch_id=OLD.id AND NOT d.batch_applied AND NOT d.balance_applied
                          AND d.inventory_product_id=OLD.inventory_product_id
                          AND d.batch_before_units=OLD.remaining_quantity_units
                          AND d.batch_after_units=NEW.remaining_quantity_units
                          AND d.stored_quarantine_before_units=OLD.quarantined_quantity_units
                          AND d.stored_quarantine_after_units=NEW.quarantined_quantity_units)"""

updated[names[0]] = replace_once(
    updated[names[0]],
    "           OR\n           (NEW.remaining_quantity_units = OLD.remaining_quantity_units",
    "           OR\n           (NEW.remaining_quantity_units < OLD.remaining_quantity_units\n"
    "            AND NEW.quarantined_quantity_units <= OLD.quarantined_quantity_units\n"
    f"            AND {disposal_batch_match})\n"
    "           OR\n           (NEW.remaining_quantity_units = OLD.remaining_quantity_units",
)

updated[names[1]] = replace_once(
    updated[names[1]], "DECLARE allocation_id bigint;", "DECLARE allocation_id bigint; disposal_id uuid;",
)
updated[names[1]] = replace_once(
    updated[names[1]],
    "AND NEW.quarantined_quantity_units>OLD.quarantined_quantity_units))",
    "AND NEW.quarantined_quantity_units>OLD.quarantined_quantity_units)\n"
    f"                    AND NOT {disposal_batch_match})",
)
updated[names[1]] = replace_once(
    updated[names[1]],
    "    SELECT a.id INTO allocation_id FROM receiving_stockadjustmentallocation a",
    "    SELECT d.id INTO disposal_id FROM receiving_stockdisposal d\n"
    "     WHERE d.batch_id=OLD.id AND NOT d.batch_applied AND NOT d.balance_applied\n"
    "       AND d.inventory_product_id=OLD.inventory_product_id\n"
    "       AND d.batch_before_units=OLD.remaining_quantity_units\n"
    "       AND d.batch_after_units=NEW.remaining_quantity_units\n"
    "       AND d.stored_quarantine_before_units=OLD.quarantined_quantity_units\n"
    "       AND d.stored_quarantine_after_units=NEW.quarantined_quantity_units\n"
    "     FOR UPDATE OF d;\n"
    "    IF disposal_id IS NOT NULL THEN\n"
    "        UPDATE receiving_stockdisposal SET batch_applied=TRUE WHERE id=disposal_id;\n"
    "        RETURN NEW;\n"
    "    END IF;\n"
    "    SELECT a.id INTO allocation_id FROM receiving_stockadjustmentallocation a",
)

updated[names[2]] = replace_once(
    updated[names[2]],
    "        RAISE EXCEPTION 'receipt balance and sequence are maintained by authorized stock operations'",
    "        IF NEW.physical_quantity_units<OLD.physical_quantity_units\n"
    "           AND NEW.last_receipt_sequence=OLD.last_receipt_sequence AND pg_trigger_depth()=1\n"
    "           AND EXISTS (SELECT 1 FROM receiving_stockdisposal d\n"
    "             WHERE d.inventory_product_id=OLD.id AND d.batch_applied AND NOT d.balance_applied\n"
    "               AND d.physical_before_units=OLD.physical_quantity_units\n"
    "               AND d.physical_after_units=NEW.physical_quantity_units) THEN\n"
    "            RETURN NEW;\n"
    "        END IF;\n"
    "        RAISE EXCEPTION 'receipt balance and sequence are maintained by authorized stock operations'",
)

updated[names[3]] = replace_once(
    updated[names[3]], "DECLARE stock_out_id uuid; adjustment_id uuid;",
    "DECLARE stock_out_id uuid; adjustment_id uuid; disposal_id uuid;",
)
updated[names[3]] = replace_once(
    updated[names[3]],
    "    IF NEW.physical_quantity_units>OLD.physical_quantity_units",
    "    IF NEW.physical_quantity_units<OLD.physical_quantity_units\n"
    "       AND NEW.last_receipt_sequence=OLD.last_receipt_sequence THEN\n"
    "        SELECT d.id INTO disposal_id FROM receiving_stockdisposal d\n"
    "         WHERE d.inventory_product_id=OLD.id AND d.batch_applied AND NOT d.balance_applied\n"
    "           AND d.physical_before_units=OLD.physical_quantity_units\n"
    "           AND d.physical_after_units=NEW.physical_quantity_units\n"
    "         FOR UPDATE OF d;\n"
    "        IF disposal_id IS NOT NULL THEN\n"
    "            UPDATE receiving_stockdisposal SET balance_applied=TRUE WHERE id=disposal_id;\n"
    "            RETURN NEW;\n"
    "        END IF;\n"
    "    END IF;\n"
    "    IF NEW.physical_quantity_units>OLD.physical_quantity_units",
)

updated["receiving_guard_expiry_batch_update"] = replace_once(
    updated["receiving_guard_expiry_batch_update"],
    "BEGIN\n    IF NEW.quarantined_quantity_units",
    "BEGIN\n    IF NEW.remaining_quantity_units<OLD.remaining_quantity_units\n"
    "       AND EXISTS (SELECT 1 FROM receiving_stockdisposal d\n"
    "         WHERE d.batch_id=OLD.id AND d.batch_applied AND NOT d.balance_applied\n"
    "           AND d.batch_before_units=OLD.remaining_quantity_units\n"
    "           AND d.batch_after_units=NEW.remaining_quantity_units\n"
    "           AND d.stored_quarantine_before_units=OLD.quarantined_quantity_units\n"
    "           AND d.stored_quarantine_after_units=NEW.quarantined_quantity_units) THEN\n"
    "        RETURN NEW;\n"
    "    END IF;\n    IF NEW.quarantined_quantity_units",
)

updated["receiving_validate_expiry_event"] = replace_once(
    updated["receiving_validate_expiry_event"],
    "DECLARE b receiving_receivingbatch%ROWTYPE;",
    "DECLARE b receiving_receivingbatch%ROWTYPE; disposed_units bigint;",
)
updated["receiving_validate_expiry_event"] = replace_once(
    updated["receiving_validate_expiry_event"],
    "    IF b.id IS NULL OR b.expiry_date IS NULL",
    "    SELECT COALESCE(SUM(quantity_units),0) INTO disposed_units FROM receiving_stockdisposal WHERE batch_id=NEW.batch_id;\n"
    "    IF b.id IS NULL OR b.expiry_date IS NULL",
)
updated["receiving_validate_expiry_event"] = replace_once(
    updated["receiving_validate_expiry_event"],
    "       OR NEW.physical_quantity_units <> b.remaining_quantity_units",
    "       OR NEW.disposed_before_recording_units <> disposed_units\n"
    "       OR NEW.physical_quantity_units <> b.remaining_quantity_units",
)
updated["receiving_validate_expiry_event"] = replace_once(
    updated["receiving_validate_expiry_event"],
    "NEW.available_before_units <> b.remaining_quantity_units-b.quarantined_quantity_units",
    "NEW.available_before_units <> b.remaining_quantity_units+disposed_units-b.quarantined_quantity_units",
)

FORWARD = r"""
CREATE FUNCTION receiving_guard_disposal_insert()
RETURNS trigger AS $$
DECLARE actor_active boolean; v_membership_id bigint; member_active boolean; member_role varchar(12);
        assignment_active boolean; product_business_id bigint; product_active boolean;
        inventory_business_id bigint; inventory_active boolean;
        link_inventory_id bigint; link_product_id bigint; current_balance bigint;
        b receiving_receivingbatch%ROWTYPE;
BEGIN
    IF NEW.batch_applied IS DISTINCT FROM FALSE OR NEW.balance_applied IS DISTINCT FROM FALSE
       OR NEW.reason_code NOT IN ('Expired','Damaged','Other')
       OR (NEW.reason_code='Other' AND btrim(NEW.reason_note)='') THEN
        RAISE EXCEPTION 'disposal starts unapplied with an approved reason' USING ERRCODE='23514';
    END IF;
    SELECT is_active INTO actor_active FROM accounts_user WHERE id=NEW.actor_id FOR SHARE;
    SELECT id,is_active,role INTO v_membership_id,member_active,member_role
      FROM inventory_access_businessmembership WHERE user_id=NEW.actor_id
        AND business_id=(SELECT business_id FROM inventory_access_inventory WHERE id=NEW.inventory_id) FOR SHARE;
    SELECT is_active INTO assignment_active FROM inventory_access_inventoryassignment
      WHERE inventory_access_inventoryassignment.membership_id=v_membership_id
        AND inventory_access_inventoryassignment.inventory_id=NEW.inventory_id FOR SHARE;
    SELECT business_id,is_active INTO product_business_id,product_active
      FROM catalogue_product WHERE id=NEW.product_id FOR SHARE;
    SELECT business_id,is_active INTO inventory_business_id,inventory_active
      FROM inventory_access_inventory WHERE id=NEW.inventory_id FOR SHARE;
    SELECT inventory_id,product_id,physical_quantity_units INTO link_inventory_id,link_product_id,current_balance
      FROM catalogue_inventoryproduct WHERE id=NEW.inventory_product_id FOR SHARE;
    SELECT * INTO b FROM receiving_receivingbatch WHERE id=NEW.batch_id FOR SHARE;
    IF actor_active IS DISTINCT FROM TRUE OR member_active IS DISTINCT FROM TRUE
       OR member_role IS DISTINCT FROM 'manager' OR assignment_active IS DISTINCT FROM TRUE
       OR product_active IS DISTINCT FROM TRUE OR inventory_active IS DISTINCT FROM TRUE
       OR product_business_id IS DISTINCT FROM inventory_business_id
       OR link_inventory_id IS DISTINCT FROM NEW.inventory_id OR link_product_id IS DISTINCT FROM NEW.product_id
       OR b.id IS NULL OR b.inventory_product_id IS DISTINCT FROM NEW.inventory_product_id
       OR b.expiry_date IS NULL OR b.expiry_date > (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date
       OR NEW.quantity_units > b.remaining_quantity_units
       OR b.quarantined_quantity_units NOT IN (0,b.remaining_quantity_units)
       OR NEW.batch_before_units <> b.remaining_quantity_units
       OR NEW.stored_quarantine_before_units <> b.quarantined_quantity_units
       OR NEW.stored_quarantine_after_units <> b.quarantined_quantity_units-LEAST(b.quarantined_quantity_units,NEW.quantity_units)
       OR NEW.physical_before_units <> current_balance
       OR NEW.occurred_at < (b.expiry_date::timestamp AT TIME ZONE 'Asia/Singapore')
       OR NEW.occurred_at > clock_timestamp()+interval '5 seconds' THEN
        RAISE EXCEPTION 'disposal requires an assigned Manager and current quarantined units' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER receiving_disposal_insert_guard BEFORE INSERT ON receiving_stockdisposal
FOR EACH ROW EXECUTE FUNCTION receiving_guard_disposal_insert();

CREATE FUNCTION receiving_guard_disposal_update()
RETURNS trigger AS $$
BEGIN
    IF NEW.id<>OLD.id OR NEW.actor_id<>OLD.actor_id OR NEW.inventory_id<>OLD.inventory_id
       OR NEW.product_id<>OLD.product_id OR NEW.inventory_product_id<>OLD.inventory_product_id
       OR NEW.batch_id<>OLD.batch_id OR NEW.quantity_units<>OLD.quantity_units
       OR NEW.batch_before_units<>OLD.batch_before_units OR NEW.batch_after_units<>OLD.batch_after_units
       OR NEW.stored_quarantine_before_units<>OLD.stored_quarantine_before_units
       OR NEW.stored_quarantine_after_units<>OLD.stored_quarantine_after_units
       OR NEW.physical_before_units<>OLD.physical_before_units OR NEW.physical_after_units<>OLD.physical_after_units
       OR NEW.reason_code<>OLD.reason_code OR NEW.reason_note<>OLD.reason_note OR NEW.occurred_at<>OLD.occurred_at
       OR pg_trigger_depth()<2
       OR NOT ((NOT OLD.batch_applied AND NEW.batch_applied AND NOT OLD.balance_applied AND NOT NEW.balance_applied)
               OR (OLD.batch_applied AND NEW.batch_applied AND NOT OLD.balance_applied AND NEW.balance_applied)) THEN
        RAISE EXCEPTION 'disposal evidence is immutable; markers apply once through stock triggers' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER receiving_disposal_update_guard BEFORE UPDATE ON receiving_stockdisposal
FOR EACH ROW EXECUTE FUNCTION receiving_guard_disposal_update();

CREATE FUNCTION receiving_validate_disposal_audit()
RETURNS trigger AS $$
DECLARE d receiving_stockdisposal%ROWTYPE; actual_balance bigint; batch_balance bigint;
BEGIN
    SELECT * INTO d FROM receiving_stockdisposal WHERE id=NEW.disposal_id;
    SELECT physical_quantity_units INTO actual_balance FROM catalogue_inventoryproduct WHERE id=d.inventory_product_id;
    SELECT remaining_quantity_units INTO batch_balance FROM receiving_receivingbatch WHERE id=d.batch_id;
    IF d.id IS NULL OR NOT d.batch_applied OR NOT d.balance_applied
       OR NEW.actor_id<>d.actor_id OR NEW.business_id<>(SELECT business_id FROM catalogue_product WHERE id=d.product_id)
       OR NEW.inventory_id<>d.inventory_id OR NEW.product_id<>d.product_id OR NEW.batch_id<>d.batch_id
       OR NEW.quantity_units<>d.quantity_units OR NEW.batch_before_units<>d.batch_before_units
       OR NEW.batch_after_units<>d.batch_after_units OR NEW.batch_after_units<>batch_balance
       OR NEW.physical_before_units<>d.physical_before_units OR NEW.physical_after_units<>d.physical_after_units
       OR NEW.physical_after_units<>actual_balance OR NEW.reason_code<>d.reason_code
       OR NEW.reason_note<>d.reason_note OR NEW.occurred_at<>d.occurred_at
       OR NEW.action<>'disposal' OR NEW.classification<>'non_demand' THEN
        RAISE EXCEPTION 'disposal audit must match the committed batch and physical movement' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER receiving_disposal_audit_guard BEFORE INSERT ON receiving_disposalauditevent
FOR EACH ROW EXECUTE FUNCTION receiving_validate_disposal_audit();

CREATE FUNCTION receiving_disposal_requires_audit()
RETURNS trigger AS $$
DECLARE d receiving_stockdisposal%ROWTYPE;
BEGIN
    SELECT * INTO d FROM receiving_stockdisposal WHERE id=NEW.id;
    IF d.id IS NULL OR NOT d.batch_applied OR NOT d.balance_applied
       OR NOT EXISTS (SELECT 1 FROM receiving_disposalauditevent WHERE disposal_id=NEW.id) THEN
        RAISE EXCEPTION 'every committed disposal requires batch, balance and non-demand audit' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER receiving_disposal_audit_required AFTER INSERT ON receiving_stockdisposal
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION receiving_disposal_requires_audit();

CREATE FUNCTION receiving_protect_disposal_history()
RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'disposal history is immutable' USING ERRCODE='23514'; END; $$ LANGUAGE plpgsql;
CREATE TRIGGER receiving_disposal_delete_guard BEFORE DELETE ON receiving_stockdisposal
FOR EACH ROW EXECUTE FUNCTION receiving_protect_disposal_history();
CREATE TRIGGER receiving_disposal_audit_immutable_guard BEFORE UPDATE OR DELETE ON receiving_disposalauditevent
FOR EACH ROW EXECUTE FUNCTION receiving_protect_disposal_history();
""" + "\n".join(updated.values())

REVERSE = r"""
DROP TRIGGER IF EXISTS receiving_disposal_audit_immutable_guard ON receiving_disposalauditevent;
DROP TRIGGER IF EXISTS receiving_disposal_delete_guard ON receiving_stockdisposal;
DROP FUNCTION IF EXISTS receiving_protect_disposal_history();
DROP TRIGGER IF EXISTS receiving_disposal_audit_required ON receiving_stockdisposal;
DROP FUNCTION IF EXISTS receiving_disposal_requires_audit();
DROP TRIGGER IF EXISTS receiving_disposal_audit_guard ON receiving_disposalauditevent;
DROP FUNCTION IF EXISTS receiving_validate_disposal_audit();
DROP TRIGGER IF EXISTS receiving_disposal_update_guard ON receiving_stockdisposal;
DROP FUNCTION IF EXISTS receiving_guard_disposal_update();
DROP TRIGGER IF EXISTS receiving_disposal_insert_guard ON receiving_stockdisposal;
DROP FUNCTION IF EXISTS receiving_guard_disposal_insert();
""" + "\n".join(original.values())


class Migration(migrations.Migration):
    dependencies = [("receiving", "0012_disposalauditevent_stockdisposal_and_more")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
