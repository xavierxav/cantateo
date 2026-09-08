import json
import os
from django.core.management.base import BaseCommand
from django.db import transaction
from django.conf import settings
from psaumes.models import Psaume, Partition, Compositeur, MomentLiturgique, SiteBanner

class Command(BaseCommand):
    help = 'Restaurer les données depuis data_backup.json vers le nouveau schéma Psaume/Partition'

    def add_arguments(self, parser):
        parser.add_argument('--file', type=str, default='data_backup.json', help='Chemin vers le fichier backup')

    def handle(self, *args, **options):
        file_path = options['file']
        if not os.path.isabs(file_path):
            file_path = os.path.join(settings.BASE_DIR, file_path)

        if not os.path.exists(file_path):
            self.stderr.write(f"Fichier non trouvé : {file_path}")
            return

        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Organiser les données par modèle
        backup_by_model = {}
        for entry in data:
            model = entry['model']
            if model not in backup_by_model:
                backup_by_model[model] = []
            backup_by_model[model].append(entry)

        self.stdout.write(f"Chargement de {len(data)} entrées...")

        with transaction.atomic():
            # 0. Nettoyage des tables existantes pour éviter les doublons/conflits
            self.stdout.write("Nettoyage des tables existantes...")
            # On vide dans l'ordre inverse des FK
            MomentLiturgique.objects.all().delete()
            Partition.objects.all().delete()
            Psaume.objects.all().delete()
            # On ne vide pas Compositeur car ils peuvent être partagés

            # 1. Compositeurs
            self.stdout.write("Restauration des compositeurs...")
            for entry in backup_by_model.get('psaumes.compositeur', []):
                Compositeur.objects.get_or_create(
                    id=entry['pk'],
                    defaults={
                        'nom': entry['fields']['nom'],
                        'description': entry['fields']['description']
                    }
                )

            # 2. Chants (Base pour partitions)
            legacy_psaume_data = {entry['pk']: entry['fields'] for entry in backup_by_model.get('psaumes.chant', [])}

            # Map to keep track of legacy chant ID (backup JSON key 'psaumes.chant') -> new objects
            old_to_new_psaume = {}
            old_to_new_partition = {}

            # 3. Psaumes
            self.stdout.write("Restauration des psaumes...")
            for entry in backup_by_model.get('psaumes.psaume', []):
                pk = entry['pk']
                fields = entry['fields']
                psaume_fields = legacy_psaume_data.get(pk, {})
                
                p = Psaume.objects.create(
                    psaume_or_cantique='psaume',
                    numero=fields.get('numero'),
                    titre=psaume_fields.get('titre', ''),
                    slug=psaume_fields.get('slug', ''),
                    nom_psaume=f"Psaume {fields.get('numero')}" if fields.get('numero') else psaume_fields.get('titre')
                )
                old_to_new_psaume[pk] = p

                if pk in legacy_psaume_data:
                    part = Partition.objects.create(
                        psaume=p,
                        titre=psaume_fields.get('titre', ''),
                        refrain=psaume_fields.get('refrain', ''),
                        versets=psaume_fields.get('versets', ''),
                        partition_pdf=psaume_fields.get('partition_pdf'),
                        partition_mxl=psaume_fields.get('partition_mxl'),
                        compositeur_id=psaume_fields.get('compositeur'),
                        slug=psaume_fields.get('slug', '')
                    )
                    old_to_new_partition[pk] = part

            # 4. Cantiques
            self.stdout.write("Restauration des cantiques...")
            for entry in backup_by_model.get('psaumes.cantique', []):
                pk = entry['pk']
                fields = entry['fields']
                psaume_fields = legacy_psaume_data.get(pk, {})
                
                p = Psaume.objects.create(
                    psaume_or_cantique='cantique',
                    reference_biblique=fields.get('reference_biblique'),
                    titre=psaume_fields.get('titre', ''),
                    slug=psaume_fields.get('slug', ''),
                    nom_psaume=f"Cantique {fields.get('reference_biblique')}" or psaume_fields.get('titre')
                )
                old_to_new_psaume[pk] = p

                if pk in legacy_psaume_data:
                    part = Partition.objects.create(
                        psaume=p,
                        titre=psaume_fields.get('titre', ''),
                        refrain=psaume_fields.get('refrain', ''),
                        versets=psaume_fields.get('versets', ''),
                        partition_pdf=psaume_fields.get('partition_pdf'),
                        partition_mxl=psaume_fields.get('partition_mxl'),
                        compositeur_id=psaume_fields.get('compositeur'),
                        slug=psaume_fields.get('slug', '')
                    )
                    old_to_new_partition[pk] = part

            # 5. Moments Liturgiques
            self.stdout.write("Restauration des moments liturgiques...")
            for entry in backup_by_model.get('psaumes.momentliturgique', []):
                fields = entry['fields']
                old_psaume_id = fields.get('chant')
                if old_psaume_id in old_to_new_psaume:
                    MomentLiturgique.objects.create(
                        psaume=old_to_new_psaume[old_psaume_id],
                        temps=fields.get('temps', ''),
                        semaine=fields.get('semaine'),
                        jour=fields.get('jour'),
                        parite=fields.get('parite', ''),
                        annee=fields.get('annee', ''),
                        nom_fete=fields.get('nom_fete', ''),
                        nom_complet_recherche=fields.get('nom_complet_recherche', '')
                    )

            # 6. Fichiers Audio
            self.stdout.write("Restauration des fichiers audio...")
            field_map = {
                'S': 'audio_soprano',
                'A': 'audio_alto',
                'T': 'audio_tenor',
                'B': 'audio_basse',
                'I': 'audio_instrumental',
                'M': 'audio_mix',
            }
            for entry in backup_by_model.get('psaumes.fichieraudio', []):
                fields = entry['fields']
                old_psaume_id = fields.get('chant')
                if old_psaume_id in old_to_new_partition:
                    partition = old_to_new_partition[old_psaume_id]
                    type_voix = fields.get('type_voix')
                    field_name = field_map.get(type_voix)
                    if field_name:
                        setattr(partition, field_name, fields.get('fichier'))
                    if fields.get('est_synthetique'):
                        partition.mp3_synthetiques = True
                    partition.save()

            # 7. Site Banners
            self.stdout.write("Restauration des bannières...")
            for entry in backup_by_model.get('psaumes.sitebanner', []):
                fields = entry['fields']
                SiteBanner.objects.create(
                    text=fields.get('text'),
                    active=fields.get('active', False),
                    start_date=fields.get('start_date'),
                    end_date=fields.get('end_date')
                )

        self.stdout.write(self.style.SUCCESS("Restauration terminée avec succès !"))
