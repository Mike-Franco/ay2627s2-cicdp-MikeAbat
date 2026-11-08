"""Minimal authentication routes."""

from django.urls import path

from accounts import views
from inventory_access import views as inventory_views
from catalogue import views as catalogue_views
from receiving import views as receiving_views

urlpatterns = [
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("inventories/", inventory_views.inventory_list, name="inventory-list"),
    path("inventories/<int:inventory_id>/", inventory_views.inventory_detail, name="inventory-detail"),
    path("catalogue/", catalogue_views.product_catalogue, name="product-catalogue"),
    path("inventories/<int:inventory_id>/products/", catalogue_views.inventory_products, name="inventory-products"),
    path("inventories/<int:inventory_id>/import/", receiving_views.import_stock_csv_view, name="import-stock-csv"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/history/", catalogue_views.stock_history, name="stock-history"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/receive/", receiving_views.receive_batch, name="receive-batch"),
    path("receipts/<uuid:receipt_id>/", receiving_views.receipt_confirmation, name="receipt-confirmation"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/issue/", receiving_views.issue_stock_view, name="issue-stock"),
    path("stock-outs/<uuid:stock_out_id>/", receiving_views.stock_out_confirmation, name="stock-out-confirmation"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/adjust/", receiving_views.adjust_stock_view, name="adjust-stock"),
    path("stock-adjustments/<uuid:adjustment_id>/", receiving_views.stock_adjustment_confirmation, name="stock-adjustment-confirmation"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/dispose/", receiving_views.dispose_stock_view, name="dispose-stock"),
    path("stock-disposals/<uuid:disposal_id>/", receiving_views.disposal_confirmation, name="disposal-confirmation"),
]
