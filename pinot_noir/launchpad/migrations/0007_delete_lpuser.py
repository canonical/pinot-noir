from django.conf import settings
from django.db import migrations


def restore_lp_users(apps, schema_editor):
    """Reconstruct the legacy combined table when rolling this migration back."""
    LPUser = apps.get_model("launchpad", "LPUser")
    ReviewMarker = apps.get_model("launchpad", "ReviewMarker")
    User = apps.get_model(settings.AUTH_USER_MODEL)

    for user in User.objects.filter(is_active=True):
        LPUser.objects.get_or_create(username=user.username, defaults={"is_team_member": True})
    for marker in ReviewMarker.objects.all():
        legacy_user, _ = LPUser.objects.get_or_create(username=marker.username)
        legacy_user.is_review_marker = True
        legacy_user.save(update_fields=["is_review_marker"])


class Migration(migrations.Migration):
    dependencies = [
        ("launchpad", "0006_split_lpuser_roles"),
        ("merges_schedule", "0005_move_assignee_to_django_user"),
        ("reviews", "0004_move_people_to_django_users"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, restore_lp_users),
        migrations.RemoveField(model_name="lpuser", name="email_md5"),
        migrations.RemoveField(model_name="lpuser", name="is_team_member"),
        migrations.RemoveField(model_name="lpuser", name="is_review_marker"),
        migrations.DeleteModel(name="LPUser"),
    ]
