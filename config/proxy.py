"""Client address handling behind the deployment's own reverse proxy."""

import ipaddress


class TrustedProxyMiddleware:
    """Replace REMOTE_ADDR with the client address the reverse proxy reports.

    Installed only when DJANGO_TRUSTED_PROXY=true, which is safe only when the
    app is reachable solely through that proxy (the staging compose file
    publishes no app port). The proxy appends the peer it accepted the
    connection from, so the rightmost X-Forwarded-For entry is the one it
    vouches for; earlier entries are client-supplied and ignored. Without this,
    every visitor would share the proxy's address and therefore one login
    throttle IP bucket.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        candidate = forwarded.rsplit(",", 1)[-1].strip()
        if candidate:
            try:
                request.META["REMOTE_ADDR"] = str(ipaddress.ip_address(candidate))
            except ValueError:
                pass
        return self.get_response(request)
