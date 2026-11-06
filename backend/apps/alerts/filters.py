from django_filters import rest_framework as filters

from .models import Alert, AlertStatus


class AlertFilter(filters.FilterSet):
    """Ex. /api/alerts/?status=NOUVELLE&severity=CRITIQUE&date_min=2026-10-01"""
    date_from = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="gte")
    date_to = filters.IsoDateTimeFilter(field_name="created_at", lookup_expr="lte")
    user = filters.NumberFilter(field_name="evaluation__event__user_id")
    rule = filters.CharFilter(field_name="evaluation__triggered_rules", lookup_expr="contains")
    open = filters.BooleanFilter(method="filter_open")

    class Meta:
        model = Alert
        fields = ["status", "severity"]

    def filter_open(self, queryset, name, value):
        if value:
            return queryset.filter(status__in=[AlertStatus.NOUVELLE, AlertStatus.EN_COURS])
        return queryset
