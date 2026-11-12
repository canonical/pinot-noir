from django.conf import settings
from django.db import migrations, models


def move_people_links(apps, schema_editor):
    Review = apps.get_model("reviews", "Review")
    User = apps.get_model(settings.AUTH_USER_MODEL)
    for review in Review.objects.all():
        for role in ("reviewer", "submitter"):
            username = getattr(review, role)
            user = User.objects.filter(username=username, is_active=True).first()
            setattr(review, f"{role}_django_user_id", user.pk if user else None)
        review.save(update_fields=["reviewer_django_user", "submitter_django_user"])


def restore_launchpad_links(apps, schema_editor):
    Review = apps.get_model("reviews", "Review")
    LPUser = apps.get_model("launchpad", "LPUser")
    for review in Review.objects.all():
        for role in ("reviewer", "submitter"):
            username = getattr(review, role)
            if username:
                LPUser.objects.get_or_create(username=username)
            setattr(review, f"{role}_user_id", username or None)
        review.save(update_fields=["reviewer_user", "submitter_user"])


def user_role_field(related_name):
    return models.ForeignKey(
        blank=True,
        null=True,
        on_delete=models.deletion.SET_NULL,
        related_name=related_name,
        to=settings.AUTH_USER_MODEL,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("launchpad", "0006_split_lpuser_roles"),
        ("reviews", "0003_alter_review_status"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="review",
            name="reviewer_django_user",
            field=user_role_field("assigned_reviews"),
        ),
        migrations.AddField(
            model_name="review",
            name="submitter_django_user",
            field=user_role_field("submitted_reviews"),
        ),
        migrations.RunPython(move_people_links, restore_launchpad_links),
        migrations.RemoveField(model_name="review", name="reviewer_user"),
        migrations.RemoveField(model_name="review", name="submitter_user"),
        migrations.RenameField(
            model_name="review", old_name="reviewer_django_user", new_name="reviewer_user"
        ),
        migrations.RenameField(
            model_name="review", old_name="submitter_django_user", new_name="submitter_user"
        ),
    ]
