from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Rotate Django SECRET_KEY"

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.WARNING(
                "SECRET_KEY rotation not implemented yet."
            )
        )
