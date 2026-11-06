"""
FICHIER : apps/audit/views.py

RÔLE
    Expose le journal d'audit en lecture seule, réservé aux administrateurs :
      GET /api/audit/               liste paginée, la plus récente d'abord
      GET /api/audit/?action=BLOQUER_COMPTE   filtrer par type d'action
    Le journal n'est jamais modifiable via l'API (traçabilité).

UTILISÉ PAR : apps/audit/urls.py
"""
import csv

from django.http import HttpResponse
from django_filters import rest_framework as filters
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.permissions import IsAdminRole

from .models import AuditLog


class AuditLogFilter(filters.FilterSet):
    date_from = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    date_to = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")

    class Meta:
        model = AuditLog
        fields = ["action"]


class AuditLogSerializer(serializers.ModelSerializer):
    # E-mail de l'auteur de l'action (vide si le compte a été supprimé depuis).
    actor_email = serializers.EmailField(source="actor.email", read_only=True, default=None, allow_null=True)

    class Meta:
        model = AuditLog
        fields = ["id", "actor_email", "action", "target", "details", "created_at"]
        read_only_fields = fields


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = AuditLog.objects.select_related("actor")
    serializer_class = AuditLogSerializer
    permission_classes = [IsAdminRole]
    filterset_class = AuditLogFilter
    search_fields = ["actor__email", "target", "action"]
    ordering_fields = ["created_at"]

    @action(detail=False, methods=["get"])
    def actions(self, request):
        actions = AuditLog.objects.order_by("action").values_list("action", flat=True).distinct()
        return Response(list(actions))

    @action(detail=False, methods=["get"])
    def export(self, request):
        rows = self.filter_queryset(self.get_queryset())
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="audit.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["Date", "Auteur", "Action", "Cible", "Détails"])
        for row in rows.iterator():
            writer.writerow([
                row.created_at.isoformat(),
                row.actor.email if row.actor_id else "",
                row.action,
                row.target,
                row.details,
            ])
        return response