"""
Management command to refresh search fields (nom_complet_recherche) and slugs for all models.
"""
from django.core.management.base import BaseCommand
from psaumes.models import Psaume, MomentLiturgique, Partition, Ordinaire


class Command(BaseCommand):
    help = 'Refresh nom_complet_recherche and slugs for Psaume, MomentLiturgique, Ordinaire and Partition'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Preview which records would be updated without actually updating',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No records will be updated'))

        # Update Psaumes
        self.stdout.write('Refreshing Psaumes (Slugs & Search)...')
        psaumes = Psaume.objects.all()
        count = psaumes.count()
        if not dry_run:
            for p in psaumes:
                p.save() # Triggers slug generation and pre_save search field update
            self.stdout.write(self.style.SUCCESS(f'  [OK] Updated {count} Psaumes'))
        else:
            self.stdout.write(f'  [DRY] Would update {count} Psaumes')

        # Update MomentLiturgique
        self.stdout.write('Refreshing MomentLiturgique (Search)...')
        moments = MomentLiturgique.objects.all()
        count = moments.count()
        if not dry_run:
            for m in moments:
                m.save() # Triggers pre_save search field update
            self.stdout.write(self.style.SUCCESS(f'  [OK] Updated {count} Moments'))
        else:
            self.stdout.write(f'  [DRY] Would update {count} Moments')

        # Update Partitions
        self.stdout.write('Refreshing Partitions (Slugs)...')
        partitions = Partition.objects.all()
        count = partitions.count()
        if not dry_run:
            for p in partitions:
                p.save() # Triggers slug generation
            self.stdout.write(self.style.SUCCESS(f'  [OK] Updated {count} Partitions'))
        else:
            self.stdout.write(f'  [DRY] Would update {count} Partitions')

        # Update Ordinaires
        self.stdout.write('Refreshing Ordinaires (Slugs & Search)...')
        ordinaires = Ordinaire.objects.all()
        count = ordinaires.count()
        if not dry_run:
            for o in ordinaires:
                o.save()  # Triggers slug + pre_save search field update
            self.stdout.write(self.style.SUCCESS(f'  [OK] Updated {count} Ordinaires'))
        else:
            self.stdout.write(f'  [DRY] Would update {count} Ordinaires')

        self.stdout.write(self.style.SUCCESS('\nFinished refreshing data.'))
