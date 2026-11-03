"""Minimal authentication routes."""

from django.urls import path

from accounts import views
from inventory_access import views as inventory_views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("inventories/", inventory_views.inventory_list, name="inventory-list"),
    path("inventories/<int:inventory_id>/", inventory_views.inventory_detail, name="inventory-detail"),
]
