"""Minimal authentication routes."""

from django.conf import settings
from django.urls import path, re_path
from django.views.static import serve as serve_static

from accounts import views
from accounts import account_views
from accounts import invitation_views
from accounts import reset_views
from accounts import deactivation_views
from inventory_access import views as inventory_views
from config.health import healthz
from catalogue import categories, views as catalogue_views
from inventory_access import team_lists
from receiving import views as receiving_views

urlpatterns = [
    path("healthz", healthz, name="healthz"),
    path("", views.home, name="home"),
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),
    path("account/", account_views.account, name="account"),
    path("account/profile/", account_views.account_profile, name="account-profile"),
    path("businesses/<int:business_id>/staff-invitations/", team_lists.invitation_list, name="staff-invitations"),
    path("businesses/<int:business_id>/staff-invitations/<int:invitation_id>/<str:action>/", invitation_views.change_invitation, name="staff-invitation-change"),
    path("businesses/<int:business_id>/staff/", team_lists.staff_list, name="manager-staff"),
    path("businesses/<int:business_id>/staff/<int:target_id>/deactivate/confirm/", deactivation_views.confirm_staff_deactivation, name="confirm-staff-deactivation"),
    path("businesses/<int:business_id>/staff/<int:target_id>/deactivate/", deactivation_views.deactivate_staff_view, name="deactivate-staff"),
    path("staff/setup/", invitation_views.staff_invitation_setup, name="staff-invitation-setup"),
    path("password/reset/", reset_views.password_reset_request, name="password-reset-request"),
    path("password/reset/setup/", reset_views.password_reset_setup, name="password-reset-setup"),
    path("inventories/", inventory_views.inventory_list, name="inventory-list"),
    path("inventories/<int:inventory_id>/", inventory_views.inventory_detail, name="inventory-detail"),
    path("catalogue/", catalogue_views.product_catalogue, name="product-catalogue"),
    path("businesses/<int:business_id>/categories/", categories.category_list, name="category-list"),
    path("businesses/<int:business_id>/categories/new/", categories.category_edit, name="category-create"),
    path("businesses/<int:business_id>/categories/<int:category_id>/edit/", categories.category_edit, name="category-edit"),
    path("businesses/<int:business_id>/categories/<int:category_id>/delete/", categories.category_delete, name="category-delete"),
    path("inventories/<int:inventory_id>/products/", catalogue_views.inventory_products, name="inventory-products"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/", catalogue_views.product_stock, name="product-stock"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/lifecycle/", catalogue_views.product_lifecycle, name="product-lifecycle"),
    path("inventories/<int:inventory_id>/import/", receiving_views.import_stock_csv_view, name="import-stock-csv"),
    path("inventories/<int:inventory_id>/import/template.csv", receiving_views.import_template_csv,
         name="import-stock-csv-template"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/history/", catalogue_views.stock_history, name="stock-history"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/forecast/", catalogue_views.demand_forecast, name="demand-forecast"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/reorder-settings/", catalogue_views.reorder_settings, name="reorder-settings"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/receive/", receiving_views.receive_batch, name="receive-batch"),
    path("receipts/<uuid:receipt_id>/", receiving_views.receipt_confirmation, name="receipt-confirmation"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/issue/", receiving_views.issue_stock_view, name="issue-stock"),
    path("stock-outs/<uuid:stock_out_id>/", receiving_views.stock_out_confirmation, name="stock-out-confirmation"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/adjust/", receiving_views.adjust_stock_view, name="adjust-stock"),
    path("stock-adjustments/<uuid:adjustment_id>/", receiving_views.stock_adjustment_confirmation, name="stock-adjustment-confirmation"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/dispose/", receiving_views.dispose_stock_view, name="dispose-stock"),
    path("stock-disposals/<uuid:disposal_id>/", receiving_views.disposal_confirmation, name="disposal-confirmation"),
]

# Local development deliberately runs with DEBUG=false. Serve only this
# project's static directory in that environment so the workspace shell works.
# Staging/production still require their normal collected-static web serving.
if settings.DJANGO_ENV == "development" and not settings.DEBUG:
    urlpatterns += [re_path(r"^static/(?P<path>.*)$", serve_static, {
        "document_root": settings.BASE_DIR / "static", "show_indexes": False,
    })]
if settings.DJANGO_ENV == "development":
    # Uploaded pictures (TORY-53). Staging serves /media/ from Caddy instead.
    urlpatterns += [re_path(r"^media/(?P<path>.*)$", serve_static, {
        "document_root": settings.MEDIA_ROOT, "show_indexes": False,
    })]

urlpatterns += [
    path("inventories/<int:inventory_id>/products/stock.csv", catalogue_views.export_inventory_stock, name="export-inventory-stock"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/history.csv", catalogue_views.export_stock_history, name="export-stock-history"),
    path("inventories/<int:inventory_id>/products/new/", catalogue_views.product_create, name="product-create"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/edit/", catalogue_views.product_edit, name="product-edit"),
    path("inventories/<int:inventory_id>/products/<int:product_id>/price/", catalogue_views.selling_price,
         name="selling-price"),
]

from .ops_admin import ops_admin_site

urlpatterns += [path("ops-admin/", ops_admin_site.urls)]

urlpatterns += [
    path("businesses/<int:business_id>/inventories/new/", inventory_views.inventory_create, name="inventory-create"),
    path("inventories/<int:inventory_id>/rename/", inventory_views.inventory_rename, name="inventory-rename"),
    path("inventories/<int:inventory_id>/status/", inventory_views.inventory_status, name="inventory-status"),
    path("inventories/<int:inventory_id>/insights/", catalogue_views.inventory_insights,
         name="inventory-insights"),
]

urlpatterns += [
    path("inventories/<int:inventory_id>/demand/verify/", catalogue_views.bulk_verify_demand,
         name="bulk-verify-demand"),
]
