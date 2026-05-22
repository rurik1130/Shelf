from django.conf import settings
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme


def get_redirect_response(request, default="/"):

    next_url = request.GET.get("next") or request.POST.get("next")

    if next_url and url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts=settings.ALLOWED_HOSTS,
    ):
        return redirect(next_url)

    return redirect(default)
