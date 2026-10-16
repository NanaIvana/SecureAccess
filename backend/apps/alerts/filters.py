from django_filters import rest_framework as filters

from .models import Alert


class AlertFilter(filters.FilterSet):
    """Ex. /api/alerts/?status=NOUVELLE&severity=CRITIQUE&date_min=2026-10-01"""
    date_min = filters.DateFilter(field_name="created_at", lookup_expr="date__gte")
    date_max = filters.DateFilter(field_name="created_at", lookup_expr="date__lte")
    user = filters.NumberFilter(field_name="evaluation__event__user_id")

    class Meta:
        model = Alert
        fields = ["status", "severity"]
