"""
Auto-generated migration to add `assignee_user` ForeignKey to Merge.
We keep `assignee` as a legacy, then populate `assignee_user` in a subsequent data
migration.
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("merges_schedule", "0001_initial"), ("launchpad", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="merge",
            name="assignee_user",
            field=models.ForeignKey(
                to="launchpad.lpuser",
                on_delete=models.SET_NULL,
                null=True,
                blank=True,
                related_name="merges",
            ),
        ),
    ]
