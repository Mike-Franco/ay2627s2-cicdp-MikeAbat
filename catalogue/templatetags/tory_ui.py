"""Layout tags for the v1.2 interface (TORY-62).

``{% page_header %}`` renders ``includes/page_header.html``: the page title, an
actions slot, and the breadcrumb trail underneath::

    {% load tory_ui %}
    {% page_header %}Stock history{% header_actions %}<a class="btn" href="…">Export CSV</a>{% endpage_header %}

Breadcrumbs come from the view context as ``breadcrumbs``: a list of
``(label, url)`` pairs, where the last pair is the current page (url ``None``)
and a label may be an Inventory (shown with its badge). Without them the trail
is Dashboard › current inventory › ``crumb`` (default: the title text).
"""

from django import template
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

register = template.Library()


def crumb(label, url=None):
    from inventory_access.models import Inventory  # imported late: template builtins load before apps in some tools

    item = {"url": url, "inventory": None, "label": label}
    if isinstance(label, Inventory):
        item.update(inventory=label, label=label.name)
    return item


def default_breadcrumbs(context, current):
    request = context.get("request")
    if request is not None and request.resolver_match and request.resolver_match.url_name == "home":
        return [("Dashboard", None)]
    trail = [("Dashboard", reverse("home"))]
    inventory = context.get("workspace_inventory")
    if inventory is not None:
        trail.append((inventory, reverse("inventory-products", args=[inventory.pk])))
        product = context.get("product")
        on_product_page = request is not None and request.resolver_match and (
            request.resolver_match.url_name == "product-stock")
        if getattr(product, "pk", None) and not on_product_page:
            trail.append((product.name, reverse("product-stock", args=[inventory.pk, product.pk])))
    trail.append((current, None))
    return trail


class PageHeaderNode(template.Node):
    def __init__(self, title, actions, current):
        self.title, self.actions, self.current = title, actions, current

    def render(self, context):
        title = self.title.render(context).strip()
        actions = self.actions.render(context).strip() if self.actions is not None else ""
        trail = context.get("breadcrumbs")
        if trail is None:
            current = self.current.resolve(context) if self.current is not None else strip_tags(title)
            trail = default_breadcrumbs(context, current)
        crumbs = [crumb(*pair) for pair in trail]
        if crumbs:
            crumbs[-1]["current"] = True
        return render_to_string("includes/page_header.html", {
            "title": mark_safe(title), "actions": mark_safe(actions), "crumbs": crumbs,
        })


@register.tag
def page_header(parser, token):
    bits = token.split_contents()
    current = None
    for bit in bits[1:]:
        name, _, value = bit.partition("=")
        if name != "crumb" or not value:
            raise template.TemplateSyntaxError("page_header only takes crumb=<label>")
        current = parser.compile_filter(value)
    title = parser.parse(("header_actions", "endpage_header"))
    actions = None
    if parser.next_token().contents == "header_actions":
        actions = parser.parse(("endpage_header",))
        parser.delete_first_token()
    return PageHeaderNode(title, actions, current)
