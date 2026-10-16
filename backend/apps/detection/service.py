"""
FICHIER : apps/detection/service.py

RÔLE
    Évaluation « en direct » du risque : prend des événements de connexion qui viennent d'être
    créés (simulateur ou connexion réelle), calcule leurs features avec tout l'historique de
    l'utilisateur, applique le moteur hybride (règles + ML), enregistre l'évaluation et crée
    l'alerte si le niveau est suspect ou haut risque.

    C'est le MÊME moteur (Detector) et les MÊMES features que pour l'entraînement : le
    simulateur et la connexion réelle se comportent donc de façon identique.

UTILISÉ PAR : apps/events/views.py (simulateur)
"""
from datetime import timedelta

from django.db import transaction
from django.db.models import Q

from apps.alerts.models import Alert, Severity
from apps.events.models import LoginEvent

from . import dataio
from .engine import Detector
from .features import build_features
from .models import MLModel, RiskEvaluation, RiskLevel

LEVEL_MAP = {"normal": RiskLevel.NORMAL, "suspect": RiskLevel.SUSPECT, "haut_risque": RiskLevel.HAUT_RISQUE}

_cache = {"version": None, "detector": None}  # le modèle est chargé une seule fois par version


class NoActiveModel(Exception):
    """Aucun modèle actif en base : il faut lancer `python manage.py train_model`."""


def get_detector():
    model = MLModel.objects.filter(is_active=True).first()
    if model is None:
        raise NoActiveModel("Aucun modèle actif. Lancez : python manage.py train_model")
    if _cache["version"] != model.version:
        _cache["detector"] = Detector.load(model.file_path, version=model.version)
        _cache["version"] = model.version
    return _cache["detector"]


def evaluate_events(new_events, alert_event_ids=None):
    """Évalue des événements déjà enregistrés (LoginEvent sans évaluation).

    new_events      : liste de LoginEvent (sauvegardés)
    alert_event_ids : ids pour lesquels une alerte peut être créée (None = tous).
    Retourne {event_id: RiskEvaluation}.
    """
    detector = get_detector()
    ids = [e.id for e in new_events]
    user_ids = {e.user_id for e in new_events}
    ips = {e.ip_hash for e in new_events}
    since_ip = min(e.timestamp for e in new_events) - timedelta(hours=1)

    # Historique complet des utilisateurs concernés + connexions récentes des mêmes sources (IP).
    qs = LoginEvent.objects.filter(Q(user_id__in=user_ids) | Q(ip_hash__in=ips, timestamp__gte=since_ip))
    events = dataio.events_frame(qs)
    users = dataio.users_frame(events["user_id"].unique())
    feats = build_features(events, users)
    results = {r["event_id"]: r for r in detector.evaluate(feats.loc[ids])}

    out = {}
    with transaction.atomic():
        for ev in new_events:
            r = results[ev.id]
            level = LEVEL_MAP[r["level"]]
            evaluation = RiskEvaluation.objects.create(
                event=ev, score=r["score"], level=level, ml_score=r["ml_score"], rules_score=r["rules_score"],
                triggered_rules=r["triggered_rules"], reasons=r["reasons"], model_version=detector.version)
            out[ev.id] = evaluation
            wants_alert = alert_event_ids is None or ev.id in alert_event_ids
            if wants_alert and level != RiskLevel.NORMAL:
                Alert.objects.create(
                    evaluation=evaluation,
                    severity=Severity.CRITIQUE if level == RiskLevel.HAUT_RISQUE else Severity.MOYENNE)
    return out
