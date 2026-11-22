from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from types import SimpleNamespace

from django.test import SimpleTestCase

from catalogue.metrics import (
    DailyMovement, StockPosition, complete_days, daily_on_hand, days_of_supply, kpis, movement_metrics,
    retail_value, singapore_day, status_bucket, stock_to_sales, turnover, week_start,
)
from receiving.demand import ForecastResult


class StockMetricTests(SimpleTestCase):
    def test_singapore_date_and_monday_change_at_utc_1600(self):
        midnight = datetime(2026, 11, 22, 16, tzinfo=timezone.utc)
        self.assertEqual(singapore_day(midnight - timedelta(seconds=1)), date(2026, 11, 22))
        self.assertEqual(singapore_day(midnight), date(2026, 11, 23))
        self.assertEqual(week_start(singapore_day(midnight - timedelta(seconds=1))), date(2026, 11, 16))
        self.assertEqual(week_start(singapore_day(midnight)), date(2026, 11, 23))
        self.assertEqual(complete_days(midnight, 30)[-1], date(2026, 11, 22))

    def test_days_of_supply_uses_unrounded_verified_average(self):
        available = ForecastResult(True, "", (), Fraction(3, 7))
        self.assertEqual(days_of_supply(6, available), (Decimal(14), ""))
        self.assertEqual(days_of_supply(0, available), (Decimal(0), ""))
        zero = ForecastResult(True, "", (), Fraction(0))
        self.assertEqual(days_of_supply(6, zero), (None, "Verified average demand is zero."))
        self.assertEqual(days_of_supply(6, ForecastResult(False, "Unverified", ())), (None, "Unverified"))
        self.assertIsNone(days_of_supply(0, None)[0])

    def test_stock_to_sales_turnover_and_daily_rewind(self):
        today = date(2026, 11, 23)
        days = tuple(today - timedelta(days=offset) for offset in (3, 2, 1))
        self.assertEqual(daily_on_hand(19, {today: 3, days[-1]: -4, days[1]: 10}, days, today=today), (10, 20, 16))
        self.assertEqual(stock_to_sales(19, 4), Decimal("4.75"))
        self.assertIsNone(stock_to_sales(19, 0))
        self.assertEqual(turnover(4, (10, 10)), Decimal("0.4"))
        self.assertEqual(turnover(0, (10, 10)), 0)
        self.assertIsNone(turnover(0, (0, 0)))
        self.assertIsNone(turnover(0, ()))
        self.assertEqual(DailyMovement(received=10, issued=4, adjusted=-1, disposed=2).net, 3)

    def test_turnover_excludes_current_partial_day_and_uses_on_hand(self):
        at = datetime(2026, 11, 22, 16, 30, tzinfo=timezone.utc)
        last_complete = complete_days(at, 30)[-1]
        link = SimpleNamespace(pk=1, physical_quantity_units=14)
        movements = {1: {
            singapore_day(at): DailyMovement(received=10),
            last_complete: DailyMovement(issued=6),
        }}
        ratio, turns = movement_metrics([StockPosition(link, 3, 0, None, None, "")], movements, at=at)
        self.assertEqual(ratio, Decimal(14) / 6)
        self.assertEqual(turns, Decimal(180) / 294)

    def test_value_unpriced_product_and_status_precedence(self):
        self.assertEqual(retail_value(20, Decimal("3.25")), Decimal("65.00"))
        self.assertEqual(retail_value(0, Decimal("0")), 0)
        self.assertIsNone(retail_value(20, None))
        base = dict(active=True, available=4, reorder_point=4, expiring=0, quarantined=0)
        for overrides, expected in (
            ({}, "low"), ({"available": 0}, "out"), ({"available": 5}, "healthy"),
            ({"expiring": 1}, "expiring"), ({"expiring": 1, "quarantined": 2}, "quarantined"),
            ({"active": False, "available": 0}, "healthy"),
        ):
            with self.subTest(expected=expected):
                self.assertEqual(status_bucket(**{**base, **overrides}), expected)
        product = SimpleNamespace(is_active=True)
        zero = StockPosition(SimpleNamespace(physical_quantity_units=0, product=product, selling_price=None),
                             0, 0, None, None, "")
        inactive = StockPosition(SimpleNamespace(physical_quantity_units=0, product=SimpleNamespace(is_active=False),
                                                 selling_price=Decimal("2.50")), 0, 0, None, None, "")
        cards = {card["label"]: card for card in kpis([zero, inactive], turnover_30d=None, unverified=None)}
        self.assertEqual(cards["Out of stock"]["value"], 1)
        self.assertEqual(cards["Retail stock value"]["note"], "1 without a selling price")
        self.assertIsNone(cards["Median days of supply"]["value"])
        self.assertIsNone(cards["Unverified demand days"]["value"])
