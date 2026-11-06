"""
FICHIER : apps/alerts/views.py

RÔLE
      GET   /api/alerts/                   liste : alertes ouvertes d'abord, puis les plus critiques
      GET   /api/alerts/{id}/              détail : événement, appareil, lieu, score, motifs, historique
      PATCH /api/alerts/{id}/              changer le statut (EN_COURS / TRAITEE / FAUSSE_ALERTE) + commentaire
      POST  /api/alerts/{id}/block-user/   bloquer le compte concerné (corps : {"minutes": 60})
    Réservé aux administrateurs ; chaque action est écrite dans le journal d'audit.
"""
import csv
from datetime import timedelta

from django.db.models import Case, Count, IntegerField, Value, When
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminRole
from apps.accounts.views import notify_account_blocked
from apps.accounts.serializers import UserSerializer
from apps.audit.services import log_action

from .filters import AlertFilter
from .models import Alert, AlertStatus, Severity
from .serializers import AlertDetailSerializer, AlertSerializer, AlertUpdateSerializer


class AlertViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                   viewsets.GenericViewSet):
    permission_classes = [IsAdminRole]
    filterset_class = AlertFilter
    search_fields = ["evaluation__event__user__email", "evaluation__event__country",
                     "evaluation__event__city", "comment"]
    ordering_fields = ["created_at", "severity_rank", "evaluation__score"]
    http_method_names = ["get", "patch", "post", "head", "options"]

    def get_queryset(self):
        return (Alert.objects
                .select_related("evaluation__event__user", "evaluation__event__device", "handled_by")
                .annotate(
                    status_rank=Case(When(status=AlertStatus.NOUVELLE, then=Value(0)),
                                     When(status=AlertStatus.EN_COURS, then=Value(1)),
                                     default=Value(2), output_field=IntegerField()),
                    severity_rank=Case(When(severity=Severity.CRITIQUE, then=Value(0)),
                                       default=Value(1), output_field=IntegerField()))
                .order_by("status_rank", "severity_rank", "-created_at"))

    def get_serializer_class(self):
        if self.action == "list":
            return AlertSerializer
        if self.action == "partial_update":
            return AlertUpdateSerializer
        return AlertDetailSerializer

    def partial_update(self, request, *args, **kwargs):
        """Traiter une alerte : « en cours », « traitée » ou « fausse alerte », avec un commentaire."""
        alert = self.get_object()
        ser = AlertUpdateSerializer(alert, data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        before = alert.status
        new_status = ser.validated_data.get("status", before)
        extra = {}
        if new_status in (AlertStatus.TRAITEE, AlertStatus.FAUSSE_ALERTE):
            extra = {"handled_by": request.user, "handled_at": timezone.now()}
        elif new_status in (AlertStatus.EN_COURS, AlertStatus.NOUVELLE):
            extra = {"handled_by": request.user if new_status == AlertStatus.EN_COURS else None, "handled_at": None}
        ser.save(**extra)
        alert.refresh_from_db()
        log_action(request.user, "TRAITER_ALERTE", alert.evaluation.event.user.email,
                   {"alerte": alert.id, "avant": before, "apres": alert.status, "commentaire": alert.comment})
        return Response(AlertDetailSerializer(alert).data)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def counts(self, request):
        """Compteurs cohérents : filtres de recherche communs, jamais le statut de l'onglet."""
        params = request.query_params.copy()
        # Les onglets affichent tous les statuts simultanément : ignorer uniquement
        # le statut actif. Le filtre open=true reste utile au badge de la barre latérale.
        params.pop("status", None)
        params.pop("page", None)
        params.pop("ordering", None)
        queryset = Alert.objects.all()
        filtered = AlertFilter(data=params, queryset=queryset, request=request).qs
        term = (params.get("search") or "").strip()
        if term:
            from django.db.models import Q
            filtered = filtered.filter(
                Q(evaluation__event__user__email__icontains=term) |
                Q(evaluation__event__country__icontains=term) |
                Q(evaluation__event__city__icontains=term) |
                Q(comment__icontains=term)
            )
        counts = {row["status"]: row["count"] for row in
                  filtered.values("status").annotate(count=Count("id"))}
        return Response({"by_status": {key: counts.get(key, 0) for key, _ in AlertStatus.choices},
                         "open": counts.get(AlertStatus.NOUVELLE, 0) + counts.get(AlertStatus.EN_COURS, 0),
                         "total": sum(counts.values())})

    @action(detail=False, methods=["post"])
    def bulk(self, request):
        serializer = BulkAlertSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ids = list(dict.fromkeys(serializer.validated_data["ids"]))
        status_value = serializer.validated_data["status"]
        alerts = list(self.get_queryset().filter(id__in=ids))
        if len(alerts) != len(ids):
            return Response({"detail": "Une ou plusieurs alertes sont introuvables."},
                            status=status.HTTP_404_NOT_FOUND)

        now = timezone.now()
        for alert in alerts:
            previous = alert.status
            alert.status = status_value
            if status_value in (AlertStatus.TRAITEE, AlertStatus.FAUSSE_ALERTE):
                alert.handled_by, alert.handled_at = request.user, now
            else:
                alert.handled_by = request.user if status_value == AlertStatus.EN_COURS else None
                alert.handled_at = None
            alert.save(update_fields=["status", "handled_by", "handled_at"])
            log_action(request.user, "TRAITER_ALERTE", alert.evaluation.event.user.email,
                       {"alerte": alert.id, "avant": previous, "apres": status_value})
        return Response({"updated": len(alerts)})

    @action(detail=False, methods=["get"])
    def export(self, request):
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="alertes.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["Date", "Compte", "Gravité", "Score", "Pays", "Ville", "Motifs", "Statut"])
        for alert in self.filter_queryset(self.get_queryset()).iterator():
            event = alert.evaluation.event
            writer.writerow([
                alert.created_at.isoformat(),
                event.user.email,
                alert.severity,
                alert.evaluation.score,
                event.country,
                event.city,
                ", ".join(alert.evaluation.reasons or []),
                alert.status,
            ])
        return response

    @extend_schema(request=OpenApiTypes.OBJECT, responses=OpenApiTypes.OBJECT)
    @action(detail=True, methods=["post"], url_path="block-user")
    def block_user(self, request, pk=None):
        """Bloque temporairement le compte concerné par l'alerte (corps JSON : {"minutes": 60})."""
        alert = self.get_object()
        user = alert.evaluation.event.user
        if user.pk == request.user.pk:
            return Response({"detail": "Vous ne pouvez pas bloquer votre propre compte."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            minutes = int(request.data.get("minutes", 60))
        except (TypeError, ValueError):
            return Response({"detail": "« minutes » doit être un nombre entier."}, status=status.HTTP_400_BAD_REQUEST)
        if not 1 <= minutes <= 60 * 24 * 30:
            return Response({"detail": "La durée doit être comprise entre 1 minute et 30 jours."},
                            status=status.HTTP_400_BAD_REQUEST)
        user.blocked_until = timezone.now() + timedelta(minutes=minutes)
        user.save(update_fields=["blocked_until"])
        notify_account_blocked(user, minutes, "une alerte de sécurité confirmée par l'administrateur")
        log_action(request.user, "BLOQUER_COMPTE", user.email, {"minutes": minutes, "alerte": alert.id})
        return Response({"user": UserSerializer(user).data})


class BulkAlertSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)
    status = serializers.ChoiceField(choices=AlertStatus.choices)
