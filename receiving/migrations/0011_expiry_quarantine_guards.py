from django.db import migrations


FORWARD = r"""
CREATE FUNCTION receiving_validate_expiry_event()
RETURNS trigger AS $$
DECLARE b receiving_receivingbatch%ROWTYPE;
BEGIN
    SELECT * INTO b FROM receiving_receivingbatch WHERE id=NEW.batch_id FOR UPDATE;
    IF b.id IS NULL OR b.expiry_date IS NULL
       OR b.expiry_date > (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date
       OR NEW.effective_at IS DISTINCT FROM (b.expiry_date::timestamp AT TIME ZONE 'Asia/Singapore')
       OR NEW.recorded_at > clock_timestamp() + interval '5 seconds'
       OR NEW.business_id IS DISTINCT FROM (SELECT business_id FROM catalogue_product WHERE id=b.product_id)
       OR NEW.inventory_id IS DISTINCT FROM b.inventory_id OR NEW.product_id IS DISTINCT FROM b.product_id
       OR NEW.actor_identity <> 'system:expiry_quarantine' OR NEW.action <> 'expiry_quarantine'
       OR NEW.classification <> 'non_demand'
       OR NEW.physical_quantity_units <> b.remaining_quantity_units
       OR NEW.quarantine_before_units <> b.quarantined_quantity_units
       OR NEW.available_before_units <> b.remaining_quantity_units-b.quarantined_quantity_units
       OR NEW.available_after_units <> 0
       OR NEW.quarantine_after_units <> b.remaining_quantity_units THEN
        RAISE EXCEPTION 'expiry evidence must match the due batch and current residual stock' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER receiving_expiry_event_insert_guard BEFORE INSERT ON receiving_expiryquarantineevent
FOR EACH ROW EXECUTE FUNCTION receiving_validate_expiry_event();

CREATE FUNCTION receiving_guard_expiry_batch_update()
RETURNS trigger AS $$
BEGIN
    IF NEW.quarantined_quantity_units IS DISTINCT FROM OLD.quarantined_quantity_units THEN
        IF NEW.remaining_quantity_units IS DISTINCT FROM OLD.remaining_quantity_units
           OR OLD.expiry_date IS NULL
           OR OLD.expiry_date > (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date
           OR NEW.quarantined_quantity_units <> OLD.remaining_quantity_units
           OR NOT EXISTS (
               SELECT 1 FROM receiving_expiryquarantineevent e
               WHERE e.batch_id=OLD.id
                 AND e.effective_at=(OLD.expiry_date::timestamp AT TIME ZONE 'Asia/Singapore')
                 AND e.quarantine_before_units=OLD.quarantined_quantity_units
                 AND e.quarantine_after_units=NEW.quarantined_quantity_units
           ) THEN
            RAISE EXCEPTION 'quarantine state requires matching expiry evidence' USING ERRCODE='23514';
        END IF;
    ELSIF NEW.remaining_quantity_units IS DISTINCT FROM OLD.remaining_quantity_units
          AND OLD.expiry_date IS NOT NULL
          AND OLD.expiry_date <= (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date THEN
        RAISE EXCEPTION 'expired batches cannot be issued or count-adjusted' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER receiving_expiry_batch_update_guard BEFORE UPDATE ON receiving_receivingbatch
FOR EACH ROW EXECUTE FUNCTION receiving_guard_expiry_batch_update();

CREATE FUNCTION receiving_recheck_issue_expiry_at_commit()
RETURNS trigger AS $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM receiving_receivingbatch b
        WHERE b.id=NEW.batch_id AND b.expiry_date IS NOT NULL
          AND b.expiry_date <= (clock_timestamp() AT TIME ZONE 'Asia/Singapore')::date
    ) THEN
        RAISE EXCEPTION 'expired units cannot be committed as ordinary issue' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER receiving_issue_expiry_commit_guard
AFTER INSERT ON receiving_stockoutallocation DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION receiving_recheck_issue_expiry_at_commit();

CREATE FUNCTION receiving_expiry_event_requires_state()
RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM receiving_receivingbatch b
        WHERE b.id=NEW.batch_id AND b.remaining_quantity_units=NEW.physical_quantity_units
          AND b.quarantined_quantity_units=NEW.quarantine_after_units
    ) THEN
        RAISE EXCEPTION 'expiry event and quarantine state must commit together' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER receiving_expiry_event_state_required
AFTER INSERT ON receiving_expiryquarantineevent DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW EXECUTE FUNCTION receiving_expiry_event_requires_state();

CREATE FUNCTION receiving_protect_expiry_event()
RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'expiry quarantine history is immutable' USING ERRCODE='23514';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER receiving_expiry_event_immutable_guard BEFORE UPDATE OR DELETE ON receiving_expiryquarantineevent
FOR EACH ROW EXECUTE FUNCTION receiving_protect_expiry_event();
"""

REVERSE = r"""
DROP TRIGGER IF EXISTS receiving_issue_expiry_commit_guard ON receiving_stockoutallocation;
DROP FUNCTION IF EXISTS receiving_recheck_issue_expiry_at_commit();
DROP TRIGGER IF EXISTS receiving_expiry_event_immutable_guard ON receiving_expiryquarantineevent;
DROP FUNCTION IF EXISTS receiving_protect_expiry_event();
DROP TRIGGER IF EXISTS receiving_expiry_event_state_required ON receiving_expiryquarantineevent;
DROP FUNCTION IF EXISTS receiving_expiry_event_requires_state();
DROP TRIGGER IF EXISTS receiving_expiry_batch_update_guard ON receiving_receivingbatch;
DROP FUNCTION IF EXISTS receiving_guard_expiry_batch_update();
DROP TRIGGER IF EXISTS receiving_expiry_event_insert_guard ON receiving_expiryquarantineevent;
DROP FUNCTION IF EXISTS receiving_validate_expiry_event();
"""


class Migration(migrations.Migration):
    dependencies = [("receiving", "0010_expiryquarantineevent")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
