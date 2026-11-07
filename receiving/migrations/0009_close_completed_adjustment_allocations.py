from django.db import migrations


FORWARD = r"""
CREATE OR REPLACE FUNCTION receiving_guard_stock_adjustment_allocation_insert()
RETURNS trigger AS $$
DECLARE parent_applied boolean;
BEGIN
    -- Serialize allocation insertion with the parent's balance_applied update.
    SELECT balance_applied INTO parent_applied
      FROM receiving_stockadjustment WHERE id=NEW.adjustment_id FOR UPDATE;
    IF parent_applied IS DISTINCT FROM FALSE
       OR NEW.applied IS DISTINCT FROM FALSE
       OR NEW.manager_confirmed_identity IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION 'allocation requires an unapplied adjustment and confirmed batch identity'
            USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""

REVERSE = r"""
CREATE OR REPLACE FUNCTION receiving_guard_stock_adjustment_allocation_insert()
RETURNS trigger AS $$
BEGIN
    IF NEW.applied IS DISTINCT FROM FALSE OR NEW.manager_confirmed_identity IS DISTINCT FROM TRUE THEN
        RAISE EXCEPTION 'adjustment allocation must start unapplied with Manager batch confirmation' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
"""


class Migration(migrations.Migration):
    dependencies = [('receiving', '0008_manager_stock_adjustments')]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
