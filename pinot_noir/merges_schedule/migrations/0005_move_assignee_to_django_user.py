from django.conf import settings
from django.db import migrations, models


def move_assignee_links(apps, schema_editor):
    Merge = apps.get_model("merges_schedule", "Merge")
    User = apps.get_model(settings.AUTH_USER_MODEL)
    for merge in Merge.objects.all():
        user = User.objects.filter(username=merge.assignee, is_active=True).first()
        merge.assignee_django_user_id = user.pk if user else None
        merge.save(update_fields=["assignee_django_user"])


def restore_launchpad_links(apps, schema_editor):
    Merge = apps.get_model("merges_schedule", "Merge")
    LPUser = apps.get_model("launchpad", "LPUser")
    for merge in Merge.objects.all():
        if merge.assignee:
            LPUser.objects.get_or_create(username=merge.assignee)
            merge.assignee_user_id = merge.assignee
        else:
            merge.assignee_user_id = None
        merge.save(update_fields=["assignee_user"])


class Migration(migrations.Migration):
    dependencies = [
        ("launchpad", "0006_split_lpuser_roles"),
        ("merges_schedule", "0004_alter_merge_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="merge",
            name="assignee_django_user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="merges",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.RunPython(move_assignee_links, restore_launchpad_links),
        migrations.RemoveField(model_name="merge", name="assignee_user"),
        migrations.RenameField(
            model_name="merge",
            old_name="assignee_django_user",
            new_name="assignee_user",
        ),
    ]
