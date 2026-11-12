from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.db import migrations, models


def split_legacy_users(apps, schema_editor):
    """Copy review markers and team memberships into their distinct models."""
    LPUser = apps.get_model("launchpad", "LPUser")
    ReviewMarker = apps.get_model("launchpad", "ReviewMarker")
    User = apps.get_model(settings.AUTH_USER_MODEL)

    for legacy_user in LPUser.objects.all():
        if legacy_user.is_review_marker:
            ReviewMarker.objects.get_or_create(username=legacy_user.username)
        if not legacy_user.is_team_member:
            continue
        user = User.objects.filter(username=legacy_user.username).first()
        if user is None:
            user = User(username=legacy_user.username, is_active=True)
            user.password = make_password(None)
            user.save()
        elif not user.is_active:
            user.is_active = True
            user.save(update_fields=["is_active"])
        # Existing Django emails are retained. Legacy email MD5 hashes are
        # deliberately not copied: they are not reversible email addresses.


class Migration(migrations.Migration):
    dependencies = [
        ("launchpad", "0005_lpuser_is_team_member_lpuser_is_review_marker"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ReviewMarker",
            fields=[
                ("username", models.CharField(max_length=100, primary_key=True, serialize=False))
            ],
            options={"verbose_name": "Review marker", "verbose_name_plural": "Review markers"},
        ),
        migrations.RunPython(split_legacy_users, migrations.RunPython.noop),
    ]
