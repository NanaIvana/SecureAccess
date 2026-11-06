import csv
import hashlib
import hmac
import io
import ipaddress
import re
from datetime import timedelta
from pathlib import Path

import joblib
import pandas as pd
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsAdminOrResponsable, IsAdminRole
from apps.alerts.models import Alert, AlertStatus, Severity
from apps.events.models import Device, LoginEvent

from . import dataio, training
from .engine import Detector
from .features import FEATURE_COLUMNS, build_features
from .models import (
    DetectionConfig,
    DetectionListEntry,
    DetectionRule,
    MLModel,
    RiskEvaluation,
    RiskLevel,
)
from .serializers import DetectionConfigSerializer, DetectionRuleSerializer, TrainingSerializer
from .service import LEVEL_MAP, NoActiveModel, build_scoring_policy, get_detector

FEATURE_LABELS = {
    "hour_of_day": "Heure de la journée",
    "is_weekend": "Week-end",
    "is_night": "Connexion de nuit",
    "success": "Connexion réussie",
    "is_new_country": "Nouveau pays",
    "is_new_device": "Nouvel appareil",
    "is_new_ip": "Nouvelle adresse IP",
    "distance_from_home_km": "Distance du domicile",
    "hours_since_last_login": "Temps depuis la dernière connexion",
    "speed_kmh": "Vitesse depuis la dernière connexion",
    "seconds_since_last_event": "Temps depuis l'événement précédent",
    "failed_10min": "Échecs sur 10 minutes",
    "failed_1h": "Échecs sur 1 heure",
    "distinct_users_from_ip_1h": "Comptes ciblés par la source en 1 heure",
    "hour_deviation": "Écart par rapport aux heures habituelles",
    "user_login_count": "Nombre de connexions précédentes",
}
IMPORT_COLUMNS = [
    "email", "timestamp", "ip", "country", "city", "latitude", "longitude",
    "success", "label", "attack_type", "device", "device_type", "os", "browser",
]
IMPORT_LABELS = ["normal", "suspect", "haut_risque"]


class ReadAdminOrResponsableWriteAdmin(APIView):
    def get_permissions(self):
        permission = IsAdminOrResponsable if self.request.method in ("GET", "HEAD", "OPTIONS") else IsAdminRole
        return [permission()]


class ListPagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 200


def _config_payload(config):
    return DetectionConfigSerializer(config).data


def _binary_metrics_from_confusion(confusion):
    if not confusion or len(confusion) != 3:
        return {
            "recall": None, "precision": None, "f1": None, "fpr": None,
            "roc_auc": None, "pr_auc": None, "accuracy": None,
        }
    total = sum(sum(row) for row in confusion)
    hits = sum(confusion[index][index] for index in range(3))
    tp = sum(sum(row[1:]) for row in confusion[1:])
    predicted = sum(sum(row[1:]) for row in confusion)
    positives = sum(sum(row) for row in confusion[1:])
    negatives = sum(confusion[0])
    false_positives = sum(confusion[0][1:])
    precision = tp / predicted if predicted else 0.0
    recall = tp / positives if positives else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "recall": recall,
        "precision": precision,
        "f1": f1,
        "fpr": false_positives / negatives if negatives else 0.0,
        "roc_auc": None,
        "pr_auc": None,
        "accuracy": hits / total if total else 0.0,
    }


def _legacy_frontend_metrics(raw):
    test = raw.get("test", {})
    components = [
        ("naive", "Prédiction majoritaire", None),
        ("baseline", "Règles seules", test.get("regles_seules")),
        ("ml", "Modèle seul", test.get("modele_seul")),
        ("final", "Hybride", test.get("hybride")),
    ]
    methods = {}
    for key, label, values in components:
        confusion = values.get("matrice_confusion") if values else None
        methods[key] = {**_binary_metrics_from_confusion(confusion), "label": label}
    hybrid = test.get("hybride") or {}
    final = methods["final"].copy()
    final["by_attack"] = {}
    matrix = hybrid.get("matrice_confusion")
    final["level_confusion"] = {
        "labels": ["normal", "suspect", "haut_risque"],
        "levels": ["NORMAL", "SUSPECT", "HAUT_RISQUE"],
        "matrix": matrix if matrix and len(matrix) == 3 else [],
    }
    split = raw.get("decoupage") or {}
    return {
        "split": f"Découpage {split.get('debut', '')}".strip(),
        "n_train": split.get("train"),
        "n_test": split.get("test"),
        "feature_importances": raw.get("importance_variables", {}),
        "methods": methods,
        "final": final,
    }


def _model_payload(model):
    metrics = model.metrics or {}
    return {
        "id": model.pk,
        "version": model.version,
        "algorithm": model.algorithm,
        "trained_at": model.trained_at,
        "is_active": model.is_active,
        "metrics": metrics.get("ui") or _legacy_frontend_metrics(metrics),
    }


def _list_payload(entry):
    return {
        "id": entry.pk,
        "list_type": entry.list_type,
        "kind": entry.kind,
        "value": entry.value,
        "label": entry.label,
        "comment": entry.comment,
        "created_by_email": entry.created_by.email if entry.created_by else "",
        "created_at": entry.created_at,
        "expires_at": entry.expires_at,
        "is_expired": entry.expires_at is not None and entry.expires_at <= timezone.now(),
    }


def _rescore_all():
    detector = get_detector()
    events = list(LoginEvent.objects.select_related("device").all().order_by("timestamp", "id"))
    if not events:
        return {"events": 0, "levels": {"SUSPECT": 0, "HAUT_RISQUE": 0, "CRITIQUE": 0}}

    frame = dataio.events_frame(LoginEvent.objects.filter(id__in=[event.pk for event in events]))
    users = dataio.users_frame(frame["user_id"].unique())
    feats = build_features(frame, users)
    config, rules, scoring_feats = build_scoring_policy(feats)
    results = detector.evaluate(scoring_feats, config, rules)
    event_by_id = {event.pk: event for event in events}
    level_counts = {RiskLevel.SUSPECT: 0, RiskLevel.HAUT_RISQUE: 0, RiskLevel.CRITIQUE: 0}
    existing = {
        evaluation.event_id: evaluation
        for evaluation in RiskEvaluation.objects.filter(event_id__in=event_by_id)
    }
    to_create, to_update = [], []
    evaluation_for_event = {}
    now = timezone.now()
    for result in results:
        level = LEVEL_MAP[result["level"]]
        level_counts[level] = level_counts.get(level, 0) + 1
        evaluation = existing.get(result["event_id"])
        if evaluation is None:
            evaluation = RiskEvaluation(event=event_by_id[result["event_id"]])
            to_create.append(evaluation)
        else:
            to_update.append(evaluation)
        evaluation.score = result["score"]
        evaluation.level = level
        evaluation.ml_score = result["ml_score"]
        evaluation.rules_score = result["rules_score"]
        evaluation.triggered_rules = result["triggered_rules"]
        evaluation.reasons = result["reasons"]
        evaluation.model_version = detector.version
        evaluation.computed_at = now
        evaluation_for_event[result["event_id"]] = evaluation

    with transaction.atomic():
        if to_create:
            RiskEvaluation.objects.bulk_create(to_create, batch_size=1000)
        if to_update:
            RiskEvaluation.objects.bulk_update(
                to_update, ["score", "level", "ml_score", "rules_score", "triggered_rules", "reasons",
                            "model_version", "computed_at"], batch_size=1000,
            )
        persisted = {
            evaluation.event_id: evaluation
            for evaluation in RiskEvaluation.objects.filter(event_id__in=event_by_id)
        }
        evaluation_for_event = {
            event_id: persisted[event_id] for event_id in evaluation_for_event
        }
        current_alerts = {
            alert.evaluation_id: alert
            for alert in Alert.objects.filter(evaluation__event_id__in=event_by_id)
        }
        new_alerts, update_alerts, remove_alert_ids = [], [], []
        for event_id, evaluation in evaluation_for_event.items():
            alert = current_alerts.get(evaluation.pk)
            if evaluation.level == RiskLevel.NORMAL:
                if alert and alert.status == AlertStatus.NOUVELLE:
                    remove_alert_ids.append(alert.pk)
                continue
            severity = Severity.CRITIQUE if evaluation.level in (
                RiskLevel.HAUT_RISQUE, RiskLevel.CRITIQUE,
            ) else Severity.MOYENNE
            if alert:
                alert.severity = severity
                update_alerts.append(alert)
            else:
                new_alerts.append(Alert(evaluation=evaluation, severity=severity, created_at=now))
        if remove_alert_ids:
            Alert.objects.filter(pk__in=remove_alert_ids).delete()
        if update_alerts:
            Alert.objects.bulk_update(update_alerts, ["severity"], batch_size=1000)
        if new_alerts:
            Alert.objects.bulk_create(new_alerts, batch_size=1000)
    return {
        "events": len(results),
        "levels": {
            "SUSPECT": level_counts[RiskLevel.SUSPECT],
            "HAUT_RISQUE": level_counts[RiskLevel.HAUT_RISQUE],
            "CRITIQUE": level_counts[RiskLevel.CRITIQUE],
        },
    }


class ActiveModelView(APIView):
    permission_classes = [IsAdminRole]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        model = MLModel.objects.filter(is_active=True).first()
        if model is None:
            return Response({"detail": "Aucun modèle actif."}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            "version": model.version,
            "algorithm": model.algorithm,
            "trained_at": model.trained_at,
            "thresholds": (model.metrics or {}).get("seuils"),
            "metrics": model.metrics,
        })


class RulesView(ReadAdminOrResponsableWriteAdmin):
    def get(self, request):
        return Response(DetectionRuleSerializer(DetectionRule.objects.all(), many=True).data)

    def patch(self, request, pk):
        try:
            rule = DetectionRule.objects.get(pk=pk)
        except DetectionRule.DoesNotExist:
            return Response({"detail": "Règle introuvable."}, status=status.HTTP_404_NOT_FOUND)
        serializer = DetectionRuleSerializer(rule, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class ConfigView(ReadAdminOrResponsableWriteAdmin):
    def get(self, request):
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        return Response(_config_payload(config))

    def put(self, request):
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        serializer = DetectionConfigSerializer(config, data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class DetectionListsView(ReadAdminOrResponsableWriteAdmin):
    def get(self, request):
        list_type = request.query_params.get("list_type")
        allowed = [choice[0] for choice in DetectionListEntry.ListType.choices]
        if list_type and list_type not in allowed:
            raise ValidationError({"list_type": "Type de liste invalide."})
        queryset = DetectionListEntry.objects.select_related("created_by").all()
        if list_type:
            queryset = queryset.filter(list_type=list_type)
        paginator = ListPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response([_list_payload(entry) for entry in page])

    def post(self, request):
        data = request.data
        list_type = data.get("list_type")
        kind = data.get("kind")
        if list_type not in DetectionListEntry.ListType.values:
            raise ValidationError({"list_type": "Type de liste invalide."})
        if kind not in DetectionListEntry.Kind.values:
            raise ValidationError({"kind": "Type d'élément invalide."})
        comment = data.get("comment", "")
        if not isinstance(comment, str):
            raise ValidationError({"comment": "Le commentaire doit être du texte."})
        comment = comment.strip()
        if len(comment) > 500:
            raise ValidationError({"comment": "Le commentaire ne peut dépasser 500 caractères."})
        expires_days = data.get("expires_days")
        expires_at = None
        if expires_days not in (None, ""):
            if isinstance(expires_days, bool):
                raise ValidationError({"expires_days": "La durée doit être un nombre entier."})
            try:
                days = int(expires_days)
            except (TypeError, ValueError):
                raise ValidationError({"expires_days": "La durée doit être un nombre entier."})
            if not 1 <= days <= 3650:
                raise ValidationError({"expires_days": "La durée doit être comprise entre 1 et 3650 jours."})
            expires_at = timezone.now() + timedelta(days=days)

        if kind == DetectionListEntry.Kind.IP:
            raw_ip = str(data.get("ip", "")).strip()
            try:
                ipaddress.ip_address(raw_ip)
            except ValueError:
                raise ValidationError({"ip": "Adresse IP invalide."})
            value = hmac.new(
                settings.IP_HASH_SECRET.encode(), raw_ip.encode(), hashlib.sha256,
            ).hexdigest()[:32]
            label = "Adresse IP pseudonymisée"
        elif kind == DetectionListEntry.Kind.PAYS:
            raw_value = data.get("value", "")
            if not isinstance(raw_value, str):
                raise ValidationError({"value": "Le pays doit être du texte."})
            value = raw_value.strip()
            if not value or len(value) > 100:
                raise ValidationError({"value": "Le pays est obligatoire (100 caractères maximum)."})
            value = value.casefold()
            label = value.title()
        else:
            raw_value = data.get("value", "")
            if not isinstance(raw_value, str):
                raise ValidationError({"value": "L'identifiant d'appareil doit être du texte."})
            value = raw_value.strip().casefold()
            if not re.fullmatch(r"[a-f0-9]{64}", value):
                raise ValidationError({"value": "Un identifiant d'appareil pseudonymisé de 64 caractères est obligatoire."})
            label = "Appareil pseudonymisé"
        if DetectionListEntry.objects.filter(list_type=list_type, kind=kind, value=value).filter(
            Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now())
        ).exists():
            raise ValidationError({"detail": "Cette entrée est déjà présente dans cette liste."})
        try:
            entry = DetectionListEntry.objects.create(
                list_type=list_type, kind=kind, value=value, label=label, comment=comment,
                expires_at=expires_at, created_by=request.user,
            )
        except IntegrityError:
            raise ValidationError({"detail": "Cette entrée existe déjà."})
        return Response(_list_payload(entry), status=status.HTTP_201_CREATED)


class DetectionListDetailView(ReadAdminOrResponsableWriteAdmin):
    def delete(self, request, pk):
        deleted, _ = DetectionListEntry.objects.filter(pk=pk).delete()
        if not deleted:
            return Response({"detail": "Entrée introuvable."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ModelsView(ReadAdminOrResponsableWriteAdmin):
    def get(self, request):
        return Response([_model_payload(model) for model in MLModel.objects.order_by("-trained_at", "-id")])


class TrainModelView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        serializer = TrainingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        params = serializer.validated_data
        events = dataio.events_frame(LoginEvent.objects.filter(
            source=LoginEvent.Source.DATASET,
            label__in=["normal", "suspect", "haut_risque"],
        ))
        if events.empty:
            return Response({"detail": "Aucun événement étiqueté à utiliser pour l'entraînement."},
                            status=status.HTTP_400_BAD_REQUEST)
        users = dataio.users_frame(events["user_id"].unique())
        feats = build_features(events, users)
        indexed = events.set_index("event_id")
        labels = indexed["label"].reindex(feats.index)
        timestamps = pd.to_datetime(indexed["timestamp"], utc=True).reindex(feats.index)
        attack_types = indexed["attack_type"].reindex(feats.index)
        try:
            artifact, metrics = training.train_detector(
                feats, labels, timestamps, n_estimators=params["n_estimators"],
                max_depth=params["max_depth"], attack_types=attack_types,
            )
        except (ValueError, KeyError) as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        folder = Path(settings.BASE_DIR) / "ml" / "artifacts"
        folder.mkdir(parents=True, exist_ok=True)
        version = "v" + timezone.now().strftime("%Y%m%d-%H%M%S")
        path = folder / f"detector_{version}.joblib"
        joblib.dump(artifact, path)
        try:
            with transaction.atomic():
                if params["activate"]:
                    MLModel.objects.filter(is_active=True).update(is_active=False)
                model = MLModel.objects.create(
                    version=version,
                    algorithm="Règles + Isolation Forest + Random Forest",
                    metrics=metrics,
                    file_path=str(path),
                    is_active=params["activate"],
                )
        except Exception:
            path.unlink(missing_ok=True)
            raise
        rescore = _rescore_all() if params["activate"] and params["rescore"] else None
        return Response(
            {"model": _model_payload(model), "rescore": rescore},
            status=status.HTTP_201_CREATED,
        )


class ActivateModelView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request, pk):
        try:
            model = MLModel.objects.get(pk=pk)
        except MLModel.DoesNotExist:
            return Response({"detail": "Modèle introuvable."}, status=status.HTTP_404_NOT_FOUND)
        try:
            Detector.load(model.file_path, version=model.version)
        except (OSError, ValueError, EOFError, KeyError, TypeError) as exc:
            return Response({"detail": f"Artefact du modèle illisible : {exc}"}, status=status.HTTP_400_BAD_REQUEST)
        with transaction.atomic():
            MLModel.objects.filter(is_active=True).exclude(pk=model.pk).update(is_active=False)
            model.is_active = True
            model.save(update_fields=["is_active"])
        return Response(_model_payload(model))


class FeaturesView(ReadAdminOrResponsableWriteAdmin):
    def get(self, request):
        return Response([
            {"name": name, "label": FEATURE_LABELS[name]}
            for name in FEATURE_COLUMNS
        ])


class ImportView(ReadAdminOrResponsableWriteAdmin):
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    max_upload_bytes = 10 * 1024 * 1024
    max_rows = 50_000

    def get(self, request):
        return Response({"columns": IMPORT_COLUMNS, "label_values": IMPORT_LABELS})

    def post(self, request):
        uploaded = request.FILES.get("file")
        if not uploaded:
            raise ValidationError({"file": "Un fichier CSV est obligatoire."})
        if uploaded.size > self.max_upload_bytes:
            raise ValidationError({"file": "Le fichier ne peut dépasser 10 Mo."})
        if Path(uploaded.name).suffix.casefold() != ".csv":
            raise ValidationError({"file": "Le fichier doit être au format CSV."})
        try:
            text = uploaded.read().decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValidationError({"file": "Le fichier doit être encodé en UTF-8."})
        if not text.strip():
            raise ValidationError({"file": "Le fichier CSV est vide."})
        sample = text[:4096]
        delimiter = ";"
        try:
            delimiter = csv.Sniffer().sniff(sample, delimiters=",;").delimiter
        except csv.Error:
            if "," in sample:
                delimiter = ","
        reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
        if not reader.fieldnames:
            raise ValidationError({"file": "La ligne d'en-tête CSV est obligatoire."})
        try:
            rows = list(reader)
        except csv.Error as exc:
            raise ValidationError({"file": f"CSV invalide : {exc}"})
        if len(rows) > self.max_rows:
            raise ValidationError({"file": f"Le fichier ne peut dépasser {self.max_rows} lignes."})
        header_map = {str(name).strip().casefold(): name for name in reader.fieldnames if name}
        aliases = {
            "ip_address": "ip", "ip_label": "ip", "device_fingerprint": "device",
            "operating_system": "os",
        }
        normalized_header = {aliases.get(key, key): value for key, value in header_map.items()}
        if "email" not in normalized_header or "timestamp" not in normalized_header:
            raise ValidationError({"file": "Les colonnes email et timestamp sont obligatoires."})

        imported = labelled = created_users = error_count = 0
        errors = []
        user_cache = {}
        device_cache = {}
        for row_number, raw_row in enumerate(rows, start=2):
            row = {
                normalized: str(raw_row.get(original) or "").strip()
                for normalized, original in normalized_header.items()
            }
            try:
                email = row.get("email", "").casefold()
                validate_email(email)
                if len(email) > 254:
                    raise ValueError("email dépasse 254 caractères")
                timestamp = parse_datetime(row.get("timestamp", ""))
                if timestamp is None or not timezone.is_aware(timestamp):
                    raise ValueError("timestamp doit être une date ISO avec fuseau horaire")
                label = row.get("label", "").casefold()
                if label and label not in IMPORT_LABELS:
                    raise ValueError(f"label doit être l'un de : {', '.join(IMPORT_LABELS)}")
                success = _parse_bool(row.get("success", "true"))
                country = row.get("country", "")
                city = row.get("city", "")
                if len(country) > 100 or len(city) > 100:
                    raise ValueError("country et city sont limités à 100 caractères")
                if len(row.get("attack_type", "")) > 30:
                    raise ValueError("attack_type ne peut dépasser 30 caractères")
                if len(row.get("device", "")) > 255:
                    raise ValueError("device ne peut dépasser 255 caractères")
                if (len(row.get("device_type", "")) > 30 or len(row.get("os", "")) > 50
                        or len(row.get("browser", "")) > 50):
                    raise ValueError("device_type, os ou browser dépasse la longueur maximale")
                latitude, longitude = _parse_coordinates(row.get("latitude", ""), row.get("longitude", ""))
                raw_ip = row.get("ip", "")
                if raw_ip:
                    ipaddress.ip_address(raw_ip)
                    normalized_ip = raw_ip
                else:
                    normalized_ip = None
                ip_hash = hmac.new(
                    settings.IP_HASH_SECRET.encode(), normalized_ip.encode(), hashlib.sha256,
                ).hexdigest()[:32] if normalized_ip else ""
                user = user_cache.get(email)
                if user is None:
                    user = User.objects.filter(email__iexact=email).first()
                    if user is None:
                        user = User.objects.create_user(email=email, password=None)
                        created_users += 1
                    user_cache[email] = user
                device = None
                device_value = row.get("device", "")
                if device_value:
                    fingerprint = hmac.new(
                        settings.IP_HASH_SECRET.encode(), f"device:{device_value}".encode(), hashlib.sha256,
                    ).hexdigest()
                    cache_key = (user.pk, fingerprint)
                    device = device_cache.get(cache_key)
                    if device is None:
                        device, _ = Device.objects.get_or_create(
                            user=user, fingerprint=fingerprint,
                            defaults={
                                "device_type": row.get("device_type", "")[:30],
                                "os": row.get("os", "")[:50],
                                "browser": row.get("browser", "")[:50],
                            },
                        )
                        device_cache[cache_key] = device
                LoginEvent.objects.create(
                    user=user, device=device, timestamp=timestamp, ip_hash=ip_hash,
                    country=country, city=city, latitude=latitude, longitude=longitude,
                    success=success, label=label, attack_type=row.get("attack_type", "")[:30],
                    source=LoginEvent.Source.DATASET,
                )
                imported += 1
                labelled += bool(label)
            except (DjangoValidationError, ValueError, TypeError) as exc:
                error_count += 1
                if len(errors) < 20:
                    errors.append(f"Ligne {row_number} : {exc}")
        if imported == 0:
            return Response({
                "detail": "Aucune ligne valide n'a été importée.",
                "imported": 0,
                "labelled": 0,
                "created_users": created_users,
                "error_count": error_count,
                "errors": errors,
            }, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "imported": imported,
            "labelled": labelled,
            "created_users": created_users,
            "error_count": error_count,
            "errors": errors,
        }, status=status.HTTP_201_CREATED)


def _parse_bool(value):
    normalized = str(value).strip().casefold()
    if normalized in ("true", "1", "yes", "oui", "success", "réussi"):
        return True
    if normalized in ("false", "0", "no", "non", "failed", "échec"):
        return False
    raise ValueError("success doit être vrai ou faux")


def _parse_coordinates(latitude, longitude):
    if not latitude and not longitude:
        return None, None
    try:
        lat, lon = float(latitude), float(longitude)
    except (TypeError, ValueError):
        raise ValueError("latitude et longitude doivent être numériques")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("latitude ou longitude hors limites")
    return lat, lon


class RescoreView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        try:
            return Response(_rescore_all())
        except NoActiveModel as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
