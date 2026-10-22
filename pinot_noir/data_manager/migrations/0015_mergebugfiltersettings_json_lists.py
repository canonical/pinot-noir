"""Store the bug filter tags and subscribers as JSON lists instead of comma-separated text."""

from django.db import migrations, models

# old comma-separated field -> new JSON field
LISTS = {
    "tags_combined": "tags",
    "subscribers_combined": "subscribers",
}


def _split(combined):
    return [part.strip() for part in combined.split(",") if part.strip()]


def to_json(apps, schema_editor):
    MergeBugFilterSettings = apps.get_model("data_manager", "MergeBugFilterSettings")
    for settings in MergeBugFilterSettings.objects.all():
        for old, new in LISTS.items():
            setattr(settings, new, _split(getattr(settings, old)))
        settings.save(update_fields=list(LISTS.values()))


def to_combined(apps, schema_editor):
    MergeBugFilterSettings = apps.get_model("data_manager", "MergeBugFilterSettings")
    for settings in MergeBugFilterSettings.objects.all():
        for old, new in LISTS.items():
            setattr(settings, old, ", ".join(getattr(settings, new) or []))
        settings.save(update_fields=list(LISTS))


class Migration(migrations.Migration):
    dependencies = [
        ("data_manager", "0014_teamsettings"),
    ]

    operations = [
        *(
            migrations.AddField(
                model_name="mergebugfiltersettings",
                name=new,
                field=models.JSONField(blank=True, default=list),
            )
            for new in LISTS.values()
        ),
        migrations.RunPython(to_json, to_combined),
        *(migrations.RemoveField(model_name="mergebugfiltersettings", name=old) for old in LISTS),
    ]
