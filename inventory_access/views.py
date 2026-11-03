from django.http import Http404
from django.shortcuts import render

from accounts.sessions import protected_view

from .authorization import authorized_inventories, get_authorized_inventory
from .models import Inventory


@protected_view
def inventory_list(request):
    return render(
        request,
        "inventory_access/inventory_list.html",
        {"inventories": authorized_inventories(request.user)},
    )


@protected_view
def inventory_detail(request, inventory_id):
    try:
        inventory = get_authorized_inventory(request.user, inventory_id)
    except Inventory.DoesNotExist as error:
        raise Http404 from error
    return render(request, "inventory_access/inventory_detail.html", {"inventory": inventory})
