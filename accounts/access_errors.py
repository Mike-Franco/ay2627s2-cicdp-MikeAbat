"""Friendly responses for expected account administration 404s, even in DEBUG."""
from functools import wraps
from django.http import Http404
from django.shortcuts import render

def account_not_found(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except Http404:
            return render(request, "accounts/not_found.html", status=404)
    return wrapped
