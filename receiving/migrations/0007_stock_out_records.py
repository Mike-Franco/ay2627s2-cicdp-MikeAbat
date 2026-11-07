import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models
from django.db.models import F, Q


GUARDS = r"""
CREATE OR REPLACE FUNCTION receiving_prevent_batch_evidence_erasure()
RETURNS trigger AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND NEW.id = OLD.id AND NEW.actor_id = OLD.actor_id AND NEW.inventory_id = OLD.inventory_id
       AND NEW.product_id = OLD.product_id AND NEW.inventory_product_id = OLD.inventory_product_id
       AND NEW.source = OLD.source AND NEW.request_token = OLD.request_token
       AND NEW.input_fingerprint = OLD.input_fingerprint AND NEW.quantity_units = OLD.quantity_units
       AND NEW.unit_label_snapshot = OLD.unit_label_snapshot AND NEW.expiry_date IS NOT DISTINCT FROM OLD.expiry_date
       AND NEW.receipt_sequence = OLD.receipt_sequence AND NEW.received_at = OLD.received_at
       AND ((NEW.remaining_quantity_units < OLD.remaining_quantity_units
             AND NEW.quarantined_quantity_units = OLD.quarantined_quantity_units)
            OR (NEW.remaining_quantity_units = OLD.remaining_quantity_units
                AND NEW.quarantined_quantity_units > OLD.quarantined_quantity_units))
       AND NEW.remaining_quantity_units >= NEW.quarantined_quantity_units THEN
        RETURN NEW;
    END IF;
    RAISE EXCEPTION 'receipt batch identity is immutable' USING ERRCODE = '23514';
END;
$$ LANGUAGE plpgsql;

CREATE FUNCTION receiving_allow_stock_out_batch_update()
RETURNS trigger AS $$
BEGIN
    IF NEW.id <> OLD.id OR NEW.actor_id <> OLD.actor_id OR NEW.inventory_id <> OLD.inventory_id
       OR NEW.product_id <> OLD.product_id OR NEW.inventory_product_id <> OLD.inventory_product_id
       OR NEW.source <> OLD.source OR NEW.request_token <> OLD.request_token
       OR NEW.input_fingerprint <> OLD.input_fingerprint OR NEW.quantity_units <> OLD.quantity_units
       OR NEW.unit_label_snapshot <> OLD.unit_label_snapshot OR NEW.expiry_date IS DISTINCT FROM OLD.expiry_date
       OR NEW.receipt_sequence <> OLD.receipt_sequence OR NEW.received_at <> OLD.received_at
       OR (NEW.remaining_quantity_units >= OLD.remaining_quantity_units
           AND NOT (NEW.remaining_quantity_units = OLD.remaining_quantity_units
                    AND NEW.quarantined_quantity_units > OLD.quarantined_quantity_units))
       OR (NEW.quarantined_quantity_units <> OLD.quarantined_quantity_units
           AND NOT (NEW.remaining_quantity_units = OLD.remaining_quantity_units
                    AND NEW.quarantined_quantity_units > OLD.quarantined_quantity_units))
       OR NEW.remaining_quantity_units < NEW.quarantined_quantity_units THEN
        RAISE EXCEPTION 'only stock-out decrements or quarantine additions may update batch quantities' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER receiving_batch_stock_out_guard BEFORE UPDATE ON receiving_receivingbatch
FOR EACH ROW EXECUTE FUNCTION receiving_allow_stock_out_batch_update();

CREATE FUNCTION receiving_allow_stock_out_balance_update()
RETURNS trigger AS $$
BEGIN
    IF NEW.id <> OLD.id OR NEW.inventory_id <> OLD.inventory_id OR NEW.product_id <> OLD.product_id
       OR NEW.physical_quantity_units < 0
       OR NOT (
           (NEW.physical_quantity_units < OLD.physical_quantity_units
            AND NEW.last_receipt_sequence = OLD.last_receipt_sequence
            AND EXISTS (
                SELECT 1 FROM receiving_stockout s
                WHERE s.inventory_product_id = OLD.id
                  AND s.quantity_before_units = OLD.physical_quantity_units
                  AND s.quantity_after_units = NEW.physical_quantity_units
                  AND s.quantity_units = OLD.physical_quantity_units - NEW.physical_quantity_units
                  AND (SELECT COALESCE(SUM(a.quantity_units), 0)
                       FROM receiving_stockoutallocation a WHERE a.stock_out_id = s.id) = s.quantity_units
            ))
           OR
           (NEW.physical_quantity_units > OLD.physical_quantity_units
            AND NEW.last_receipt_sequence = OLD.last_receipt_sequence + 1
            AND pg_trigger_depth() >= 2)
       ) THEN
        RAISE EXCEPTION 'inventory product balance identity or range is invalid' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER receiving_stock_out_balance_guard AFTER UPDATE OF physical_quantity_units ON catalogue_inventoryproduct
FOR EACH ROW EXECUTE FUNCTION receiving_allow_stock_out_balance_update();
CREATE OR REPLACE FUNCTION catalogue_guard_inventory_product_stock_columns()
RETURNS trigger AS $$
BEGIN
    IF (OLD.physical_quantity_units IS DISTINCT FROM NEW.physical_quantity_units
        OR OLD.last_receipt_sequence IS DISTINCT FROM NEW.last_receipt_sequence)
       AND pg_trigger_depth() < 2 THEN
        -- A receipt insert enters this trigger through the batch trigger at depth 2.
        -- A manual stock-out is allowed only when its own BEFORE guard accepted it.
        IF NEW.physical_quantity_units < OLD.physical_quantity_units
           AND NEW.last_receipt_sequence = OLD.last_receipt_sequence
           AND pg_trigger_depth() = 1
           AND EXISTS (
                SELECT 1 FROM receiving_stockout s
                WHERE s.inventory_product_id = OLD.id
                  AND s.quantity_before_units = OLD.physical_quantity_units
                  AND s.quantity_after_units = NEW.physical_quantity_units
                  AND s.quantity_units = OLD.physical_quantity_units - NEW.physical_quantity_units
                  AND (SELECT COALESCE(SUM(a.quantity_units), 0)
                       FROM receiving_stockoutallocation a WHERE a.stock_out_id = s.id) = s.quantity_units
           ) THEN
            RETURN NEW;
        END IF;
        RAISE EXCEPTION 'receipt balance and sequence are maintained by authorized stock operations'
            USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE FUNCTION receiving_validate_demand_audit()
RETURNS trigger AS $$
DECLARE s receiving_stockout%ROWTYPE; balance bigint;
BEGIN
    SELECT * INTO s FROM receiving_stockout WHERE id = NEW.stock_out_id;
    SELECT physical_quantity_units INTO balance FROM catalogue_inventoryproduct WHERE id = s.inventory_product_id;
    IF s.id IS NULL OR NEW.actor_id <> s.actor_id OR NEW.inventory_id <> s.inventory_id
       OR NEW.product_id <> s.product_id OR NEW.business_id <> (SELECT business_id FROM catalogue_product WHERE id=s.product_id)
       OR NEW.quantity_change_units <> s.quantity_units OR NEW.quantity_before_units <> s.quantity_before_units
       OR NEW.quantity_after_units <> s.quantity_after_units OR NEW.quantity_after_units <> balance
       OR NEW.occurred_at <> s.occurred_at THEN
        RAISE EXCEPTION 'demand audit must match committed stock-out and balance' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER receiving_demand_audit_guard BEFORE INSERT ON receiving_demandauditevent
FOR EACH ROW EXECUTE FUNCTION receiving_validate_demand_audit();

CREATE FUNCTION receiving_stock_out_requires_audit()
RETURNS trigger AS $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM receiving_demandauditevent WHERE stock_out_id=NEW.id) THEN
        RAISE EXCEPTION 'every committed stock-out requires demand audit' USING ERRCODE='23514';
    END IF;
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;
CREATE CONSTRAINT TRIGGER receiving_stock_out_audit_required AFTER INSERT ON receiving_stockout
DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION receiving_stock_out_requires_audit();
"""

REVERSE_GUARDS = r"""
CREATE OR REPLACE FUNCTION catalogue_guard_inventory_product_stock_columns()
RETURNS trigger AS $$
BEGIN
    IF (OLD.physical_quantity_units IS DISTINCT FROM NEW.physical_quantity_units
        OR OLD.last_receipt_sequence IS DISTINCT FROM NEW.last_receipt_sequence)
       AND pg_trigger_depth() < 2 THEN
        RAISE EXCEPTION 'receipt balance and sequence are maintained by batch insertion' USING ERRCODE = '23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS receiving_stock_out_audit_required ON receiving_stockout;
DROP FUNCTION IF EXISTS receiving_stock_out_requires_audit();
DROP TRIGGER IF EXISTS receiving_demand_audit_guard ON receiving_demandauditevent;
DROP FUNCTION IF EXISTS receiving_validate_demand_audit();
DROP TRIGGER IF EXISTS receiving_stock_out_balance_guard ON catalogue_inventoryproduct;
DROP FUNCTION IF EXISTS receiving_allow_stock_out_balance_update();
DROP TRIGGER IF EXISTS receiving_batch_stock_out_guard ON receiving_receivingbatch;
DROP FUNCTION IF EXISTS receiving_allow_stock_out_batch_update();
"""


class Migration(migrations.Migration):
    dependencies = [
        ('receiving', '0006_stable_expiry_rejection_identifier'),
        ('catalogue', '0006_inventory_product_zero_initial_stock'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(name='StockOut', fields=[
            ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ('quantity_units', models.PositiveIntegerField()), ('quantity_before_units', models.PositiveBigIntegerField()),
            ('quantity_after_units', models.PositiveBigIntegerField()), ('occurred_at', models.DateTimeField()),
            ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_outs', to=settings.AUTH_USER_MODEL)),
            ('inventory', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_outs', to='inventory_access.inventory')),
            ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_outs', to='catalogue.product')),
            ('inventory_product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_outs', to='catalogue.inventoryproduct')),
        ], options={'constraints': [models.CheckConstraint(condition=Q(quantity_units__gte=1) & Q(quantity_units__lte=2147483647), name='stock_out_quantity_range'), models.CheckConstraint(condition=Q(quantity_after_units=F('quantity_before_units') - F('quantity_units')), name='stock_out_quantity_reconciles')]}),
        migrations.CreateModel(name='StockOutAllocation', fields=[
            ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')), ('quantity_units', models.PositiveIntegerField()),
            ('batch', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='stock_out_allocations', to='receiving.receivingbatch')),
            ('stock_out', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='allocations', to='receiving.stockout')),
        ], options={'constraints': [models.UniqueConstraint(fields=('stock_out', 'batch'), name='unique_stock_out_batch_allocation'), models.CheckConstraint(condition=Q(quantity_units__gte=1), name='stock_out_allocation_positive')]}),
        migrations.CreateModel(name='DemandAuditEvent', fields=[
            ('id', models.BigAutoField(primary_key=True, serialize=False)), ('quantity_before_units', models.PositiveBigIntegerField()),
            ('quantity_change_units', models.PositiveIntegerField()), ('quantity_after_units', models.PositiveBigIntegerField()), ('occurred_at', models.DateTimeField()),
            ('actor', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='demand_audit_events', to=settings.AUTH_USER_MODEL)),
            ('business', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='demand_audit_events', to='inventory_access.business')),
            ('inventory', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='demand_audit_events', to='inventory_access.inventory')),
            ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='demand_audit_events', to='catalogue.product')),
            ('stock_out', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='audit_event', to='receiving.stockout')),
        ], options={'constraints': [models.CheckConstraint(condition=Q(quantity_after_units=F('quantity_before_units') - F('quantity_change_units')), name='demand_audit_quantity_reconciles'), models.CheckConstraint(condition=Q(quantity_before_units__lte=2147483647) & Q(quantity_after_units__lte=2147483647) & Q(quantity_change_units__lte=2147483647), name='demand_audit_quantity_cap')]}),
        migrations.RunSQL(GUARDS, REVERSE_GUARDS),
    ]
