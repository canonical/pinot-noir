from django.db import migrations


def populate_assignee_user(apps, schema_editor):
    Merge = apps.get_model("merges_schedule", "Merge")
    LPUser = apps.get_model("launchpad", "LPUser")
    # For each merge with an assignee, create LPUser if missing and assign it.
    for merge in Merge.objects.all():
        username = (merge.assignee or "").strip()
        if not username:
            continue
        # Normalize username to lowercase
        username_l = username.lower()
        user, created = LPUser.objects.get_or_create(username=username_l)
        merge.assignee_user = user
        merge.save(update_fields=["assignee_user"])


class Migration(migrations.Migration):

    dependencies = [
        ("merges_schedule", "0002_add_assignee_user_fk"),
        ("launchpad", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(populate_assignee_user, reverse_code=migrations.RunPython.noop),
    ]
