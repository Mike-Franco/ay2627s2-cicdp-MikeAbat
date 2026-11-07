from django.http import Http404
from django.shortcuts import render

from accounts.sessions import protected_view
from inventory_access.models import BusinessMembership, Inventory

from .authorization import visible_inventory_product_links, visible_product_links


@protected_view
def product_catalogue(request):
    return render(
        request,
        "catalogue/product_catalogue.html",
        {"product_links": visible_product_links(request.user)},
    )


@protected_view
def inventory_products(request, inventory_id):
    try:
        inventory, product_links = visible_inventory_product_links(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    return render(
        request,
        "catalogue/inventory_products.html",
        {"inventory": inventory, "product_links": product_links,
         "can_adjust_stock": BusinessMembership.objects.filter(
             user=request.user, business=inventory.business,
             role=BusinessMembership.Role.MANAGER, is_active=True,
             inventory_assignments__inventory=inventory,
             inventory_assignments__is_active=True,
         ).exists()},
    )
