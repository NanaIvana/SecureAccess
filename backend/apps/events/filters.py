from django_filters import rest_framework as filters

from .models import LoginEvent


class LoginEventFilter(filters.FilterSet):
    """Filtres de l'historique : /api/events/?user=5&success=false&level=HAUT_RISQUE&date_min=2026-09-01"""
    date_min = filters.DateFilter(field_name="timestamp", lookup_expr="date__gte")
    date_max = filters.DateFilter(field_name="timestamp", lookup_expr="date__lte")
    level = filters.CharFilter(field_name="evaluation__level")

    class Meta:
        model = LoginEvent
        fields = ["user", "success", "source", "country"]
