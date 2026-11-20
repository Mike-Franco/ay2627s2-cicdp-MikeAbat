from django.apps import apps
from django.contrib import admin
from django.contrib.admin.models import LogEntry
from django.contrib.auth.forms import AuthenticationForm

from catalogue.models import InventoryProduct, Product
from inventory_access.models import Business, BusinessMembership, Inventory, InventoryAssignment


class OpsAdminAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser:
            raise self.get_invalid_login_error()


class OpsAdminSite(admin.AdminSite):
    site_header = "Tory operations"
    login_form = OpsAdminAuthenticationForm

    def has_permission(self, request):
        return request.user.is_active and request.user.is_superuser


ops_admin_site = OpsAdminSite()


class ReadOnlyAdmin(admin.ModelAdmin):
    actions = None

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Business, site=ops_admin_site)
class BusinessAdmin(admin.ModelAdmin):
    list_display = ("name", "created_at")
    search_fields = ("name",)
    list_filter = ("created_at",)


@admin.register(Inventory, site=ops_admin_site)
class InventoryAdmin(admin.ModelAdmin):
    list_display = ("name", "business", "is_active")
    list_select_related = ("business",)
    search_fields = ("name", "business__name")
    list_filter = ("is_active", "business")

    def get_readonly_fields(self, request, obj=None):
        return ("business",) if obj else ()


@admin.register(Product, site=ops_admin_site)
class ProductAdmin(ReadOnlyAdmin):
    list_display = ("sku", "name", "business", "is_active", "expiry_tracking_required")
    list_select_related = ("business",)
    search_fields = ("sku", "name", "business__name")
    list_filter = ("is_active", "expiry_tracking_required", "business")


@admin.register(InventoryProduct, site=ops_admin_site)
class InventoryProductAdmin(ReadOnlyAdmin):
    list_display = ("inventory", "product", "physical_quantity_units")
    list_select_related = ("inventory__business", "product")
    search_fields = ("inventory__name", "product__sku", "product__name")
    list_filter = ("inventory__business", "inventory", "product__is_active")


@admin.register(BusinessMembership, site=ops_admin_site)
class BusinessMembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "business", "role", "is_active")
    list_select_related = ("user", "business")
    search_fields = ("user__email", "business__name")
    list_filter = ("role", "is_active", "business")

    def get_readonly_fields(self, request, obj=None):
        return ("business", "user") if obj else ()


@admin.register(InventoryAssignment, site=ops_admin_site)
class InventoryAssignmentAdmin(admin.ModelAdmin):
    list_display = ("membership", "inventory", "is_active", "assigned_at")
    list_select_related = ("membership__user", "membership__business", "inventory__business")
    search_fields = ("membership__user__email", "inventory__name", "inventory__business__name")
    list_filter = ("is_active", "membership__role", "inventory__business")


# Receiving models record stock state, movements, or the evidence behind them.
ops_admin_site.register(apps.get_app_config("receiving").get_models(), ReadOnlyAdmin)
for model in apps.get_app_config("catalogue").get_models():
    if model.__name__.endswith("AuditEvent"):
        ops_admin_site.register(model, ReadOnlyAdmin)
ops_admin_site.register(LogEntry, ReadOnlyAdmin)
