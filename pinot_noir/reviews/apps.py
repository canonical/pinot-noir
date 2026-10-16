from django.apps import AppConfig

from pinot_noir.pages.registry import Page

PAGE_SLUG = "reviews"


class ReviewsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "pinot_noir.reviews"
    label = "reviews"
    page = Page(
        slug=PAGE_SLUG,
        label="Reviews",
        refresh_task="pinot_noir.reviews.tasks.refresh_reviews",
        order=20,
    )
