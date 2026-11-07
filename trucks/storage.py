import os
import uuid

from django.conf import settings
from django.core.files.storage import FileSystemStorage


class PrivateStorage(FileSystemStorage):
    """Files kept in PRIVATE_MEDIA_ROOT, which is never served directly by the web server."""

    @property
    def base_location(self):
        return str(settings.PRIVATE_MEDIA_ROOT)

    @property
    def location(self):
        return os.path.abspath(self.base_location)


def get_photo_storage():
    return PrivateStorage()


def photo_path(instance, filename):
    return f'trucks/{instance.truck_id}/{uuid.uuid4().hex}.jpg'