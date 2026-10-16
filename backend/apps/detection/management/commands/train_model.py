"""
FICHIER : apps/detection/management/commands/train_model.py

RÔLE
    Commande Django : python manage.py train_model
    Entraîne le modèle de détection sur le jeu de données synthétique (les événements
    de source « DATASET »), le sauvegarde dans backend/ml/artifacts/ et l'active en base
    (table MLModel). Affiche à la fin les résultats mesurés sur le jeu de TEST.

À LANCER APRÈS : python manage.py generate_dataset --reset
À LANCER AVANT : python manage.py score_events --reset
"""
from pathlib import Path

import joblib
import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.detection import dataio, training
from apps.detection.features import build_features
from apps.detection.models import MLModel
from apps.events.models import LoginEvent


class Command(BaseCommand):
    help = "Entraîne le modèle de détection sur le jeu de données synthétique et l'enregistre."

    def handle(self, *args, **options):
        # 1. Lecture des événements du jeu de données dans PostgreSQL.
        events = dataio.events_frame(LoginEvent.objects.filter(source=LoginEvent.Source.DATASET))
        if events.empty:
            raise CommandError("Aucun événement du jeu de données. Lancez d'abord : python manage.py generate_dataset --reset")
        users = dataio.users_frame(events["user_id"].unique())

        # 2. Calcul des features (voir features.py).
        self.stdout.write(f"Calcul des features sur {len(events)} événements...")
        feats = build_features(events, users)
        indexed = events.set_index("event_id")
        labels = indexed["label"].reindex(feats.index)  # étiquettes réelles, alignées sur les features
        timestamps = pd.to_datetime(indexed["timestamp"], utc=True).reindex(feats.index)

        # 3. Entraînement et évaluation (voir training.py).
        self.stdout.write("Entraînement du modèle (Isolation Forest + Random Forest)...")
        artifact, metrics = training.train_detector(feats, labels, timestamps)

        # 4. Sauvegarde du modèle sur le disque (dossier ignoré par Git : chacun entraîne le sien).
        folder = Path(settings.BASE_DIR) / "ml" / "artifacts"
        folder.mkdir(parents=True, exist_ok=True)
        version = "v" + timezone.now().strftime("%Y%m%d-%H%M")
        path = folder / f"detector_{version}.joblib"
        joblib.dump(artifact, path)

        # 5. Enregistrement en base : on désactive les anciens modèles et on active le nouveau.
        with transaction.atomic():
            MLModel.objects.update(is_active=False)
            MLModel.objects.create(version=version, algorithm="Règles + Isolation Forest + Random Forest",
                                   metrics=metrics, file_path=str(path), is_active=True)

        # 6. Résumé affiché dans le terminal.
        test = metrics["test"]
        self.stdout.write(self.style.SUCCESS(f"Modèle {version} enregistré et activé."))
        self.stdout.write(f"Seuils retenus (calibrés sur la validation) : {metrics['seuils']}")
        self.stdout.write(f"Découpage : {metrics['decoupage']}")
        self.stdout.write("Résultats sur le jeu de TEST (jamais vu à l'entraînement) :")
        for key, name in (("regles_seules", "Règles seules"), ("modele_seul", "Modèle seul "), ("hybride", "Hybride     ")):
            m = test[key]
            self.stdout.write(
                f"  {name} | F1 suspect {m['par_classe']['suspect']['f1']:.2f} | F1 haut risque "
                f"{m['par_classe']['haut_risque']['f1']:.2f} | alertes : précision {m['alertes']['precision']:.2f}, "
                f"rappel {m['alertes']['rappel']:.2f}")
        self.stdout.write(f"Matrice de confusion (hybride, test) : {test['hybride']['matrice_confusion']}")
        self.stdout.write("Attention : jeu de données synthétique, ces scores ne préjugent pas du réel.")