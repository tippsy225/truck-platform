import io

from django.conf import settings
from django.core.files.base import ContentFile
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_PHOTOS = 6
MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 50_000_000
MIN_WIDTH, MIN_HEIGHT = 400, 300
MAIN_SIZE = 1600
THUMB_SIZE = 480
ALLOWED_FORMATS = ('JPEG', 'PNG', 'WEBP')


class PhotoError(Exception):
    pass


def _encode(image, size):
    copy = image.copy()
    copy.thumbnail((size, size))
    buffer = io.BytesIO()
    copy.save(buffer, 'JPEG', quality=85, optimize=True)
    return ContentFile(buffer.getvalue())


def process(upload):
    """Check an uploaded photo and return (full size, thumbnail) as clean JPEG files.

    The photo is fully decoded and saved again, so its hidden data (such as the GPS
    position that phone cameras store inside a photo) is dropped, and anything that
    only pretends to be an image is refused.
    """
    if upload.size > MAX_BYTES:
        raise PhotoError('The photo is larger than 10 MB. Choose a smaller one, or take it again at a lower quality.')
    try:
        upload.seek(0)
        image = Image.open(upload)
        if image.format not in ALLOWED_FORMATS:
            raise PhotoError('Upload a JPG, PNG or WebP photo.')
        width, height = image.size
        if width * height > MAX_PIXELS:
            raise PhotoError('That photo has too many pixels. Resize it and try again.')
        if width < MIN_WIDTH or height < MIN_HEIGHT:
            raise PhotoError(f'The photo is too small. It should be at least {MIN_WIDTH} by {MIN_HEIGHT} '
                             f'pixels so cargo owners can see the truck clearly.')
        image = ImageOps.exif_transpose(image)
        image = image.convert('RGB')
    except PhotoError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, SyntaxError, Image.DecompressionBombError):
        raise PhotoError('That file could not be read as a photo. Upload a JPG, PNG or WebP image.')
    return _encode(image, MAIN_SIZE), _encode(image, THUMB_SIZE)


def photo_requirement_message(truck):
    """When REQUIRE_TRUCK_PHOTOS is on, a truck needs a photo before it can bid or post a trip."""
    if not getattr(settings, 'REQUIRE_TRUCK_PHOTOS', False):
        return None
    if truck.photos.exists():
        return None
    return ('Add at least one photo of this truck before you use it. '
            'Cargo owners want to see the truck they are dealing with.')