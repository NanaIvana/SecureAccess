"""
FICHIER : apps/alerts/views.py

RÔLE
      GET   /api/alerts/                   liste : alertes ouvertes d'abord, puis les plus critiques
      GET   /api/alerts/{id}/              détail : événement, appareil, lieu, score, motifs, historique
      PATCH /api/alerts/{id}/              changer le statut (EN_COURS / TRAITEE / FAUSSE_ALERTE) + commentaire
      POST  /api/alerts/{id}/block-user/   bloquer le compte concerné (corps : {"minutes": 60})
    Réservé aux administrateurs ; chaque action est écrite dans le journal d'audit.
"""
from datetime import timedelta

from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminRole
from apps.accounts.serializers import UserSerializer
from apps.audit.services import log_action

from .filters import AlertFilter
from .models import Alert, AlertStatus, Severity
from .serializers import AlertDetailSerializer, AlertSerializer, AlertUpdateSerializer


class AlertViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.UpdateModelMixin,
                   viewsets.GenericViewSet):
    permission_classes = [IsAdminRole]
    filterset_class = AlertFilter
    search_fields = ["evaluation__event__user__email"]
    ordering_fields = ["created_at"]
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
        log_action(request.user, "BLOQUER_COMPTE", user.email, {"minutes": minutes, "alerte": alert.id})
        return Response({"user": UserSerializer(user).data})
