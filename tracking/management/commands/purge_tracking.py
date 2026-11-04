from django.core.management.base import BaseCommand

from tracking.services import purge_old_pings


class Command(BaseCommand):
    help = 'Delete location history older than the retention period.'

    def handle(self, *args, **options):
        deleted = purge_old_pings()
        self.stdout.write(f'Deleted {deleted} old location points.')