"""Stream authorized stock and audit evidence as spreadsheet-safe CSV."""

import csv

from django.db.models import BigIntegerField, Case, F, Sum, Value, When
from django.http import StreamingHttpResponse

from receiving.models import (
    DemandAuditEvent, DisposalAuditEvent, ExpiryQuarantineEvent, ReceiptAuditEvent, StockAdjustmentAuditEvent,
)
from receiving.services import SINGAPORE

from .models import ProductLifecycleAuditEvent


class _CsvBuffer:
    def write(self, row):
        return row


def _safe_cell(value):
    text = "" if value is None else str(value)
    return "'" + text if text.lstrip().startswith(("=", "+", "-", "@")) else text


def csv_download(filename, header, rows):
    def stream():
        writer = csv.writer(_CsvBuffer())
        yield writer.writerow(header)
        for row in rows:
            yield writer.writerow([_safe_cell(cell) for cell in row])

    response = StreamingHttpResponse(stream(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "private, no-store"
    return response


def stock_rows(links, *, today):
    balances = links.values(
        "product__sku", "product__name", "product__base_unit_label", "physical_quantity_units",
    ).annotate(quarantined=Sum(Case(
        When(receiving_batches__expiry_date__lte=today, then=F("receiving_batches__remaining_quantity_units")),
        default=F("receiving_batches__quarantined_quantity_units"),
    ), default=0, output_field=BigIntegerField())).order_by("product__sku", "pk").values_list(
        "product__sku", "product__name", "product__base_unit_label", "physical_quantity_units", "quarantined",
    )
    for sku, name, unit, physical, quarantined in balances.iterator(chunk_size=1000):
        yield sku, name, unit, physical, quarantined, physical - quarantined


def history_rows(scope):
    def events(model, action, *, time="occurred_at", actor="actor__email",
               before=None, after=None, reason=None, note=None):
        return model.objects.filter(**scope).order_by().annotate(
            movement_at=F(time), movement=action, attributed_to=F(actor),
            balance_before=F(before) if before else Value(None, output_field=BigIntegerField()),
            balance_after=F(after) if after else Value(None, output_field=BigIntegerField()),
            event_reason=F(reason) if reason else Value(""),
            event_note=F(note) if note else Value(""),
        ).values_list("pk", "movement_at", "movement", "attributed_to", "balance_before", "balance_after",
                       "event_reason", "event_note")

    def physical_change(model, action, **kwargs):
        return events(model, Value(action), before="quantity_before_units", after="quantity_after_units", **kwargs)

    rows = physical_change(ReceiptAuditEvent, "receipt").union(
        physical_change(DemandAuditEvent, "issue"),
        physical_change(StockAdjustmentAuditEvent, "adjustment", reason="reason"),
        events(ExpiryQuarantineEvent, Value("expiry quarantine"), time="recorded_at", actor="actor_identity",
               before="physical_quantity_units", after="physical_quantity_units"),
        events(DisposalAuditEvent, Value("disposal"), before="physical_before_units",
               after="physical_after_units", reason="reason_code", note="reason_note"),
        events(ProductLifecycleAuditEvent, F("action")),
        all=True,
    ).order_by("-movement_at", "movement", "-pk")
    for _, at, action, actor, before, after, reason, note in rows.iterator(chunk_size=1000):
        yield at.astimezone(SINGAPORE).isoformat(), action, actor, before, after, reason, note
