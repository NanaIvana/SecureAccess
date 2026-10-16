"""
FICHIER : apps/dashboard/views.py

RÔLE
    Agrégats du tableau de bord (lecture seule), accessibles aux rôles ADMIN et RESPONSABLE :
      GET /api/dashboard/kpis/              indicateurs clés et variation par rapport à la période précédente
      GET /api/dashboard/timeline/          connexions et alertes par jour
      GET /api/dashboard/risk-distribution/ répartition normal / suspect / haut risque
      GET /api/dashboard/top-targets/       comptes, sources et pays les plus concernés

    Paramètre commun : ?days=30 (7, 30, 90...). La période se termine au DERNIER événement
    connu (et non à la date du jour), pour que les données historiques restent affichées.
"""
from datetime import timedelta

from django.db.models import Count, Max, Q
from django.db.models.functions import TruncDate
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminOrResponsable
from apps.alerts.models import Alert, AlertStatus, Severity
from apps.detection.models import RiskEvaluation, RiskLevel
from apps.events.models import LoginEvent

DAYS_PARAM = OpenApiParameter("days", int, description="Longueur de la période en jours (défaut 30)")


def get_period(request):
    """(début, fin, début de la période précédente, nombre de jours) à partir de ?days=."""
    try:
        days = max(1, min(int(request.query_params.get("days", 30)), 365))
    except (TypeError, ValueError):
        days = 30
    end = LoginEvent.objects.aggregate(m=Max("timestamp"))["m"] or timezone.now()
    start = end - timedelta(days=days)
    return start, end, start - timedelta(days=days), days


def _variation(current, previous):
    """Variation relative en % (None si la période précédente est vide)."""
    if not previous:
        return None
    return round((current - previous) / previous * 100, 1)


def _window_stats(start, end):
    ev = LoginEvent.objects.filter(timestamp__gt=start, timestamp__lte=end).aggregate(
        total=Count("id"), failed=Count("id", filter=Q(success=False)))
    al = Alert.objects.filter(created_at__gt=start, created_at__lte=end).aggregate(
        total=Count("id"), critical=Count("id", filter=Q(severity=Severity.CRITIQUE)))
    total = ev["total"]
    return {"connexions": total, "taux_echec": round(ev["failed"] / total * 100, 2) if total else 0.0,
            "alertes": al["total"], "alertes_critiques": al["critical"]}


class KpisView(APIView):
    permission_classes = [IsAdminOrResponsable]

    @extend_schema(parameters=[DAYS_PARAM], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        start, end, prev_start, days = get_period(request)
        cur, prev = _window_stats(start, end), _window_stats(prev_start, start)
        kpis = {}
        for key in ("connexions", "alertes", "alertes_critiques"):
            kpis[key] = {"value": cur[key], "previous": prev[key], "variation_pct": _variation(cur[key], prev[key])}
        kpis["taux_echec"] = {"value": cur["taux_echec"], "previous": prev["taux_echec"],
                              "variation_points": round(cur["taux_echec"] - prev["taux_echec"], 2)}
        # Alertes encore à traiter (toutes périodes confondues).
        open_alerts = Alert.objects.filter(status__in=[AlertStatus.NOUVELLE, AlertStatus.EN_COURS]).aggregate(
            total=Count("id"), critical=Count("id", filter=Q(severity=Severity.CRITIQUE)))
        kpis["alertes_ouvertes"] = {"value": open_alerts["total"], "critiques": open_alerts["critical"]}
        return Response({"period": {"start": start, "end": end, "days": days}, "kpis": kpis})


class TimelineView(APIView):
    permission_classes = [IsAdminOrResponsable]

    @extend_schema(parameters=[DAYS_PARAM], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        start, end, _, days = get_period(request)
        logins = (LoginEvent.objects.filter(timestamp__gt=start, timestamp__lte=end)
                  .annotate(day=TruncDate("timestamp")).values("day")
                  .annotate(n=Count("id"), failed=Count("id", filter=Q(success=False))).order_by("day"))
        alerts = (Alert.objects.filter(created_at__gt=start, created_at__lte=end)
                  .annotate(day=TruncDate("created_at")).values("day")
                  .annotate(n=Count("id"), critical=Count("id", filter=Q(severity=Severity.CRITIQUE))).order_by("day"))
        by_day = {}
        for row in logins:
            by_day[row["day"]] = {"date": row["day"], "connexions": row["n"], "echecs": row["failed"],
                                  "alertes": 0, "critiques": 0}
        for row in alerts:
            entry = by_day.setdefault(row["day"], {"date": row["day"], "connexions": 0, "echecs": 0,
                                                   "alertes": 0, "critiques": 0})
            entry["alertes"], entry["critiques"] = row["n"], row["critical"]
        return Response({"period": {"start": start, "end": end, "days": days},
                         "points": [by_day[k] for k in sorted(by_day)]})


class RiskDistributionView(APIView):
    permission_classes = [IsAdminOrResponsable]

    @extend_schema(parameters=[DAYS_PARAM], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        start, end, _, days = get_period(request)
        rows = (RiskEvaluation.objects.filter(event__timestamp__gt=start, event__timestamp__lte=end)
                .order_by().values("level").annotate(n=Count("id")))
        counts = {lvl: 0 for lvl in (RiskLevel.NORMAL, RiskLevel.SUSPECT, RiskLevel.HAUT_RISQUE)}
        counts.update({r["level"]: r["n"] for r in rows})
        total = sum(counts.values())
        return Response({"period": {"start": start, "end": end, "days": days}, "total": total,
                         "distribution": [{"level": k, "count": v, "pct": round(v / total * 100, 2) if total else 0.0}
                                          for k, v in counts.items()]})


class TopTargetsView(APIView):
    permission_classes = [IsAdminOrResponsable]

    @extend_schema(parameters=[DAYS_PARAM], responses=OpenApiTypes.OBJECT)
    def get(self, request):
        start, end, _, days = get_period(request)
        risky = RiskEvaluation.objects.filter(event__timestamp__gt=start, event__timestamp__lte=end,
                                              level__in=[RiskLevel.SUSPECT, RiskLevel.HAUT_RISQUE]).order_by()
        high = Count("id", filter=Q(level=RiskLevel.HAUT_RISQUE))
        users = (risky.values("event__user_id", "event__user__email")
                 .annotate(n=Count("id"), high=high).order_by("-n")[:10])
        sources = (risky.values("event__ip_hash")
                   .annotate(n=Count("id"), high=high, comptes=Count("event__user_id", distinct=True))
                   .order_by("-n")[:10])
        countries = risky.values("event__country").annotate(n=Count("id"), high=high).order_by("-n")[:10]
        return Response({
            "period": {"start": start, "end": end, "days": days},
            "comptes": [{"user_id": r["event__user_id"], "email": r["event__user__email"], "alertes": r["n"],
                         "haut_risque": r["high"]} for r in users],
            "sources": [{"source": r["event__ip_hash"][:10], "evenements": r["n"], "haut_risque": r["high"],
                         "comptes_cibles": r["comptes"]} for r in sources],
            "pays": [{"pays": r["event__country"] or "?", "evenements": r["n"], "haut_risque": r["high"]}
                     for r in countries],
        })
