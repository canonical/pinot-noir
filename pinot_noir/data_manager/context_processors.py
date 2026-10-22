from .models import TeamSettings


def team(request):
    """Expose the current site's ``team_name`` (blank when unset) to all templates."""
    return {"team_name": TeamSettings.current().name}
