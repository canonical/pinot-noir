from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from pinot_noir.data_manager.models import UserTokens

from .forms import TokensForm


@login_required
def index(request):
    return redirect("user_settings:tokens")


@login_required
@require_http_methods(["GET", "POST"])
def tokens(request):
    """Let the signed-in user set their own tokens. Stored values are never shown."""
    instance = UserTokens.objects.filter(user=request.user).first() or UserTokens(
        user=request.user
    )
    form = TokensForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        changed = form.save()
        if changed:
            messages.success(request, f"Updated: {', '.join(changed)}.")
        else:
            messages.info(request, "No tokens changed.")
        return redirect("user_settings:tokens")
    return render(
        request,
        "user_settings/tokens.html",
        {
            "title": "My tokens",
            "form": form,
        },
    )
