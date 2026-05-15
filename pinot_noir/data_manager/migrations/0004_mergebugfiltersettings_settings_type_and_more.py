import django.db.models.deletion
from django.db import migrations, models


def _set_backport_settings_type(apps, schema_editor):
    """Mark existing BackportBugFilterSettings rows as backport type."""
    BackportBugFilterSettings = apps.get_model("data_manager", "BackportBugFilterSettings")
    MergeBugFilterSettings = apps.get_model("data_manager", "MergeBugFilterSettings")

    backport_pks = list(BackportBugFilterSettings.objects.values_list("pk", flat=True))
    MergeBugFilterSettings.objects.filter(pk__in=backport_pks).update(settings_type="backport")


class Migration(migrations.Migration):
    dependencies = [
        ("data_manager", "0003_backportbugfiltersettings_and_more"),
        ("sites", "0002_alter_domain_unique"),
    ]

    operations = [
        # 1. Add settings_type; default "merge" covers all existing rows.
        migrations.AddField(
            model_name="mergebugfiltersettings",
            name="settings_type",
            field=models.CharField(
                choices=[("merge", "merge"), ("backport", "backport")],
                default="merge",
                max_length=20,
            ),
        ),
        # 2. Mark rows that belong to BackportBugFilterSettings as "backport".
        migrations.RunPython(
            _set_backport_settings_type,
            migrations.RunPython.noop,
        ),
        # 3. Drop the now-redundant BackportBugFilterSettings concrete table.
        migrations.DeleteModel(
            name="BackportBugFilterSettings",
        ),
        # 4. Relax the unique constraint on site alone (OneToOneField → ForeignKey).
        migrations.AlterField(
            model_name="mergebugfiltersettings",
            name="site",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="sites.site",
            ),
        ),
        # 5. Enforce one entry per (site, settings_type).
        migrations.AddConstraint(
            model_name="mergebugfiltersettings",
            constraint=models.UniqueConstraint(
                fields=["site", "settings_type"],
                name="unique_bug_filter_settings_per_site_and_type",
            ),
        ),
    ]
