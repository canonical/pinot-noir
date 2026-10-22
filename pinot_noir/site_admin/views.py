from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render

from pinot_noir.data_manager.models import UserTokens

from .forms import TokensForm
from .sections import SECTIONS, section_entries


@staff_member_required
def index(request):
    return redirect(SECTIONS[0].url_name)


@staff_member_required
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
        return redirect("site_admin:tokens")
    return render(
        request,
        "site_admin/tokens.html",
        {
            "title": "My tokens",
            "form": form,
            "sections": section_entries(request.path),
        },
    )
