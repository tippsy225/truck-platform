from django.apps import AppConfig


class ReachConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'reach'

    def ready(self):
        from . import signals  # noqa: F401