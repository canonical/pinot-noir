"""Store the StartriageTeam list settings as JSON lists instead of comma-separated text."""

from django.db import migrations, models

# old comma-separated field -> new JSON field
LISTS = {
    "lp_ignore_packages_combined": "lp_ignore_packages",
    "discourse_categories_combined": "discourse_categories",
    "discourse_triage_categories_combined": "discourse_triage_categories",
    "github_todo_labels_combined": "github_todo_labels",
    "github_ignore_labels_combined": "github_ignore_labels",
    "proposed_migration_teams_combined": "proposed_migration_teams",
}

# blank means unset (startriage's default) rather than an empty list
NULLABLE = {"github_todo_labels", "github_ignore_labels"}


def _split(combined):
    return [part.strip() for part in combined.split(",") if part.strip()]


def to_json(apps, schema_editor):
    StartriageTeam = apps.get_model("bug_triage", "StartriageTeam")
    for team in StartriageTeam.objects.all():
        for old, new in LISTS.items():
            values = _split(getattr(team, old))
            setattr(team, new, values or (None if new in NULLABLE else []))
        team.save(update_fields=list(LISTS.values()))


def to_combined(apps, schema_editor):
    StartriageTeam = apps.get_model("bug_triage", "StartriageTeam")
    for team in StartriageTeam.objects.all():
        for old, new in LISTS.items():
            setattr(team, old, ", ".join(getattr(team, new) or []))
        team.save(update_fields=list(LISTS))


class Migration(migrations.Migration):
    dependencies = [
        ("bug_triage", "0002_remove_startriageaisettings_permission_and_more"),
    ]

    operations = [
        *(
            migrations.AddField(
                model_name="startriageteam",
                name=new,
                field=(
                    models.JSONField(blank=True, null=True)
                    if new in NULLABLE
                    else models.JSONField(blank=True, default=list)
                ),
            )
            for new in LISTS.values()
        ),
        migrations.RunPython(to_json, to_combined),
        *(migrations.RemoveField(model_name="startriageteam", name=old) for old in LISTS),
    ]
