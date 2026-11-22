from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.core.paginator import Paginator
from django.db.models import Q

from accounts.dashboard import reorder_alerts


PAGE_SIZE = 25


def paginate(request, rows):
    return Paginator(rows, PAGE_SIZE).get_page(request.GET.get("page"))


@dataclass(frozen=True)
class TableControls:
    query: str
    sort: str

    @classmethod
    def from_request(cls, request, sorts, *, default):
        sort = request.GET.get("sort", default)
        if sort.removeprefix("-") not in sorts:
            sort = default
        return cls(request.GET.get("q", "").strip()[:200], sort)

    def order(self, sorts):
        field = sorts[self.sort.removeprefix("-")]
        if isinstance(field, str):
            return ("-" if self.sort.startswith("-") else "") + field
        return field.desc(nulls_last=True) if self.sort.startswith("-") else field.asc(nulls_last=True)

    def toolbar(self, request, page, *, search_label, filters=(), sort_choices=()):
        keys = {"q", "sort", "page", *(key for key, _, _ in filters)}
        passthrough = [(key, value) for key, values in request.GET.lists()
                       if key not in keys for value in values]
        clear = request.GET.copy()
        for key in keys - {"sort"}:
            clear.pop(key, None)
        return {
            "query": self.query, "sort": self.sort, "search_label": search_label,
            "filters": [{"key": key, "label": label, "choices": choices, "value": request.GET.get(key, "")}
                        for key, label, choices in filters],
            "sort_choices": sort_choices, "count": page.paginator.count, "hidden": passthrough,
            "clear_url": "?" + clear.urlencode() if clear else request.path,
            "is_filtered": bool(self.query or any(request.GET.get(key) for key, _, _ in filters)),
        }


def search_rows(rows, query, *fields):
    if query:
        return rows.filter(Q(*[Q(**{f"{field}__icontains": query}) for field in fields], _connector=Q.OR))
    return rows


def stock_positions(links, *, at):
    quarantined, low_links, checked = reorder_alerts(links, at=at)
    low_ids = {link.pk for link, _ in low_links}
    for link in links:
        link.available_units = link.physical_quantity_units - quarantined.get(link.pk, 0)
        link.out_of_stock = link.product.is_active and link.available_units == 0
        link.low_stock = link.pk in low_ids and not link.out_of_stock
    return checked


@dataclass
class CatalogueRow:
    product: object
    links: list

    @property
    def inventory_id(self):
        return self.links[0].inventory_id

    @property
    def available_units(self):
        return sum(link.available_units for link in self.links)

    @property
    def prices(self):
        return sorted({link.selling_price for link in self.links if link.selling_price is not None})

    @property
    def status(self):
        if not self.product.is_active:
            return "Inactive"
        if any(link.out_of_stock for link in self.links):
            return "Out of stock"
        if any(link.low_stock for link in self.links):
            return "Low stock"
        return "In stock"


CATALOGUE_SORTS = {
    "name": lambda row: row.product.name.casefold(),
    "sku": lambda row: row.product.sku.casefold(),
    "available": lambda row: row.available_units,
    "category": lambda row: row.product.category.name.casefold() if row.product.category_id else "",
}
CATALOGUE_STATUSES = (
    ("", "All statuses"), ("active", "Active"), ("inactive", "Inactive"),
    ("low", "Low stock"), ("out", "Out of stock"),
)


def catalogue_rows(links, *, at, status, sort):
    links = list(links)
    stock_positions(links, at=at)
    by_product = defaultdict(list)
    for link in links:
        by_product[link.product_id].append(link)
    rows = [CatalogueRow(product_links[0].product, product_links) for product_links in by_product.values()]
    if status == "low":
        rows = [row for row in rows if any(link.low_stock for link in row.links)]
    if status == "out":
        rows = [row for row in rows if any(link.out_of_stock for link in row.links)]
    rows.sort(key=lambda row: row.product.pk)
    rows.sort(key=CATALOGUE_SORTS[sort.removeprefix("-")], reverse=sort.startswith("-"))
    return rows


@dataclass
class InventoryStats:
    products: int = 0
    low: int = 0
    out: int = 0
    value: Decimal = Decimal(0)


INVENTORY_SORTS = {
    "name": lambda inventory: inventory.name.casefold(),
    "low": lambda inventory: inventory.stock.low + inventory.stock.out,
    "value": lambda inventory: inventory.stock.value,
}
INVENTORY_SORT_CHOICES = (
    ("name", "Name (A–Z)"), ("-name", "Name (Z–A)"),
    ("-low", "Most low or out of stock"), ("low", "Fewest low or out of stock"),
    ("-value", "Highest retail value"), ("value", "Lowest retail value"),
)


def prepare_inventory_cards(inventories, links, *, at, sort):
    stock_positions(links, at=at)
    stats = defaultdict(InventoryStats)
    for link in links:
        row = stats[link.inventory_id]
        row.products += 1
        row.low += link.low_stock
        row.out += link.out_of_stock
        if link.selling_price is not None:
            row.value += link.available_units * link.selling_price
    for inventory in inventories:
        inventory.stock = stats[inventory.pk]
    inventories.sort(key=lambda inventory: inventory.pk)
    inventories.sort(key=INVENTORY_SORTS[sort.removeprefix("-")], reverse=sort.startswith("-"))
    return inventories
