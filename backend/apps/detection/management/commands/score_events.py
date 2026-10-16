"""
FICHIER : apps/detection/management/commands/score_events.py

RÔLE
    Commande Django : python manage.py score_events [--reset] [--open-days N]
    Calcule le risque de TOUS les événements de la base avec le modèle actif, enregistre
    une évaluation par événement (table RiskEvaluation) et crée une alerte (table Alert)
    pour chaque événement suspect ou à haut risque.

    Pour le jeu de données historique, les alertes plus anciennes que N jours avant le
    dernier événement (3 par défaut) sont marquées « traitées » avec un commentaire
    explicite : seules les alertes récentes restent ouvertes dans le tableau de bord.

OPTIONS
    --reset        supprime d'abord toutes les évaluations et alertes existantes
    --open-days N  nombre de jours d'alertes laissées ouvertes (3 par défaut)

À LANCER APRÈS : python manage.py train_model
"""
from datetime import timedelta

import pandas as pd
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Count

from apps.alerts.models import Alert, AlertStatus, Severity
from apps.detection import dataio
from apps.detection.engine import Detector
from apps.detection.features import build_features
from apps.detection.models import MLModel, RiskEvaluation, RiskLevel
from apps.events.models import LoginEvent

# Correspondance entre les niveaux du moteur (minuscules) et ceux de la base (majuscules).
LEVEL_MAP = {"normal": RiskLevel.NORMAL, "suspect": RiskLevel.SUSPECT, "haut_risque": RiskLevel.HAUT_RISQUE}


class Command(BaseCommand):
    help = "Évalue le risque de tous les événements non encore évalués et crée les alertes."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Supprime d'abord toutes les évaluations et alertes")
        parser.add_argument("--open-days", type=int, default=3,
                            help="Les alertes plus anciennes que N jours avant le dernier événement sont clôturées")

    def handle(self, *args, **options):
        # 1. Chargement du modèle actif (créé par train_model).
        model = MLModel.objects.filter(is_active=True).first()
        if model is None:
            raise CommandError("Aucun modèle actif. Lancez d'abord : python manage.py train_model")
        detector = Detector.load(model.file_path, version=model.version)

        # 2. Option --reset : on repart de zéro (les alertes sont supprimées en cascade).
        if options["reset"]:
            self.stdout.write("Suppression des anciennes évaluations et alertes...")
            RiskEvaluation.objects.all().delete()

        # 3. Lecture de tous les événements et calcul des features.
        events = dataio.events_frame(LoginEvent.objects.all())
        if events.empty:
            raise CommandError("Aucun événement à évaluer.")
        users = dataio.users_frame(events["user_id"].unique())

        self.stdout.write(f"Calcul des features sur {len(events)} événements...")
        feats = build_features(events, users)
        self.stdout.write("Évaluation du risque...")
        results = detector.evaluate(feats)

        # 4. On ne garde que les événements qui n'ont pas encore d'évaluation.
        existing = set(RiskEvaluation.objects.values_list("event_id", flat=True))
        ts_map = pd.to_datetime(events.set_index("event_id")["timestamp"], utc=True)
        cutoff = ts_map.max() - timedelta(days=options["open_days"])  # date limite des alertes laissées ouvertes
        todo = [r for r in results if r["event_id"] not in existing]

        # 5. Enregistrement en base, en une seule transaction (tout ou rien).
        self.stdout.write(f"Enregistrement de {len(todo)} évaluations...")
        with transaction.atomic():
            evaluations = [
                RiskEvaluation(event_id=r["event_id"], score=r["score"], level=LEVEL_MAP[r["level"]],
                               ml_score=r["ml_score"], rules_score=r["rules_score"],
                               triggered_rules=r["triggered_rules"], reasons=r["reasons"],
                               model_version=detector.version,
                               computed_at=ts_map[r["event_id"]].to_pydatetime())
                for r in todo
            ]
            RiskEvaluation.objects.bulk_create(evaluations, batch_size=5000)

            # Une alerte par évaluation suspecte ou à haut risque.
            alerts = []
            for ev in evaluations:
                if ev.level == RiskLevel.NORMAL:
                    continue
                created = ev.computed_at
                old = ts_map[ev.event_id] < cutoff  # alerte ancienne : clôturée automatiquement
                alerts.append(Alert(
                    evaluation=ev,
                    severity=Severity.CRITIQUE if ev.level == RiskLevel.HAUT_RISQUE else Severity.MOYENNE,
                    status=AlertStatus.TRAITEE if old else AlertStatus.NOUVELLE,
                    created_at=created,
                    handled_at=(created + timedelta(hours=1)) if old else None,
                    comment="Historique du jeu de données : clôturée automatiquement." if old else "",
                ))
            Alert.objects.bulk_create(alerts, batch_size=5000)

        # 6. Résumé affiché dans le terminal.
        self.stdout.write(self.style.SUCCESS(f"{len(evaluations)} évaluations et {len(alerts)} alertes créées."))
        for row in RiskEvaluation.objects.order_by().values("level").annotate(n=Count("id")).order_by("-n"):
            self.stdout.write(f"  {row['level']}: {row['n']}")
        for row in Alert.objects.order_by().values("status").annotate(n=Count("id")).order_by("-n"):
            self.stdout.write(f"  alertes {row['status']}: {row['n']}")