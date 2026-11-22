"""Keep Manager coverage evidence append-only."""

from django.db import migrations


FORWARD = """
CREATE FUNCTION receiving_protect_coverage_event() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'demand coverage evidence is immutable' USING ERRCODE='23514';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER receiving_coverage_event_immutable
BEFORE UPDATE OR DELETE ON receiving_demandcoverageevent
FOR EACH ROW EXECUTE FUNCTION receiving_protect_coverage_event();
"""

REVERSE = """
DROP TRIGGER IF EXISTS receiving_coverage_event_immutable ON receiving_demandcoverageevent;
DROP FUNCTION IF EXISTS receiving_protect_coverage_event();
"""


class Migration(migrations.Migration):
    dependencies = [("receiving", "0017_demandcoverageevent_demand_coverage_event_reason")]
    operations = [migrations.RunSQL(FORWARD, REVERSE)]
