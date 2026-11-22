from django import forms
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.db.models import Exists, OuterRef
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from accounts.sessions import protected_view
from inventory_access.authorization import manager_memberships

from .forms import PlainLabelsMixin
from .models import Category, Product


class CategoryForm(PlainLabelsMixin, forms.ModelForm):
    class Meta:
        model = Category
        fields = ("name", "colour")
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "colour": forms.TextInput(attrs={"class": "form-control", "placeholder": "#306DB0"}),
        }


def _business(request, business_id):
    return get_object_or_404(
        manager_memberships(request.user).select_related("business"), business_id=business_id,
    ).business


@protected_view
@require_GET
def category_list(request, business_id):
    business = _business(request, business_id)
    categories = business.categories.annotate(in_use=Exists(Product.objects.filter(category_id=OuterRef("pk"))))
    return render(request, "catalogue/category_list.html", {"business": business, "categories": categories})


@protected_view
@require_http_methods(["GET", "POST"])
def category_edit(request, business_id, category_id=None):
    business = _business(request, business_id)
    category = (get_object_or_404(business.categories, pk=category_id) if category_id is not None
                else Category(business=business))
    form = CategoryForm(request.POST if request.method == "POST" else None, instance=category)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                # Serialize writes within a business, including competing renames.
                type(business).objects.select_for_update().get(pk=business.pk)
                if category_id is not None:
                    get_object_or_404(business.categories.select_for_update(), pk=category_id)
                category.name = form.cleaned_data["name"]
                category.colour = form.cleaned_data["colour"]
                category.save()
        except IntegrityError as error:
            if getattr(getattr(error.__cause__, "diag", None), "constraint_name", None) != "unique_business_category_name":
                raise
            form.add_error("name", "A category with this name already exists in this business.")
        except forms.ValidationError as error:
            form.add_error(None, error)
        else:
            return redirect("category-list", business_id=business.pk)
    return render(request, "catalogue/category_form.html", {
        "business": business, "category": category, "form": form,
    }, status=400 if request.method == "POST" else 200)


@protected_view
@require_POST
def category_delete(request, business_id, category_id):
    business = _business(request, business_id)
    try:
        with transaction.atomic():
            type(business).objects.select_for_update().get(pk=business.pk)
            category = get_object_or_404(business.categories.select_for_update(), pk=category_id)
            category.delete()
    except (ProtectedError, IntegrityError):
        messages.error(request, "Remove this category from its products before deleting it.")
    return redirect("category-list", business_id=business.pk)
