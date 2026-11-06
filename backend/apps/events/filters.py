from django_filters import rest_framework as filters

from .models import LoginEvent


class LoginEventFilter(filters.FilterSet):
    """Les filtres d'historique acceptent plusieurs niveaux séparés par des virgules."""
    date_from = filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="gte")
    date_to = filters.IsoDateTimeFilter(field_name="timestamp", lookup_expr="lte")
    level = filters.BaseInFilter(field_name="evaluation__level", lookup_expr="in")
    rule = filters.CharFilter(field_name="evaluation__triggered_rules", lookup_expr="contains")

    class Meta:
        model = LoginEvent
        fields = ["user", "success", "source", "country", "attack_type"]
