import csv
import hashlib
import hmac
import io
from datetime import datetime, time, timedelta
from xml.sax.saxutils import escape

from django.conf import settings
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.accounts.permissions import IsAdminOrResponsable
from apps.alerts.models import Alert, AlertStatus, Severity
from apps.detection.models import MLModel, RiskLevel
from apps.events.models import LoginEvent


RULE_NAMES = {
    "R1_force_brute": "Force brute",
    "R2_voyage_impossible": "Voyage impossible",
    "R3_source_multi_comptes": "Source ciblant plusieurs comptes",
    "R4_nouveau_pays": "Nouveau pays",
    "R5_nouvel_appareil": "Nouvel appareil",
    "R6_heure_inhabituelle": "Heure inhabituelle",
    "R7_succes_apres_echecs": "Succès après des échecs",
}

KPI_LABELS = {
    "total": "Connexions",
    "successes": "Connexions réussies",
    "failures": "Échecs de connexion",
    "users": "Comptes actifs",
}


def _periods(request):
    date_from = request.query_params.get("date_from")
    date_to = request.query_params.get("date_to")
    if date_from or date_to:
        start_date, end_date = parse_date(date_from or ""), parse_date(date_to or "")
        if not start_date or not end_date or end_date < start_date:
            return None, None, Response(
                {"detail": "Les dates date_from et date_to doivent être valides et dans l'ordre."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        days = (end_date - start_date).days + 1
        if days > 366:
            return None, None, Response({"detail": "La période ne peut pas dépasser 366 jours."},
                                        status=status.HTTP_400_BAD_REQUEST)
    else:
        try:
            days = int(request.query_params.get("days", 30))
        except (TypeError, ValueError):
            return None, None, Response({"days": ["La durée doit être un nombre entier."]},
                                        status=status.HTTP_400_BAD_REQUEST)
        if days < 1 or days > 366:
            return None, None, Response({"days": ["La durée doit être comprise entre 1 et 366 jours."]},
                                        status=status.HTTP_400_BAD_REQUEST)
        end_date = timezone.localdate()
        start_date = end_date - timedelta(days=days - 1)

    start = timezone.make_aware(datetime.combine(start_date, time.min))
    end = timezone.make_aware(datetime.combine(end_date + timedelta(days=1), time.min))
    return (start, end, days), (start - timedelta(days=days), start), None


def _event_stats(start, end):
    events = LoginEvent.objects.filter(timestamp__gte=start, timestamp__lt=end)
    values = events.aggregate(
        total=Count("id"),
        successes=Count("id", filter=Q(success=True)),
        failures=Count("id", filter=Q(success=False)),
        users=Count("user_id", distinct=True),
        risky=Count("id", filter=Q(
            evaluation__level__in=[RiskLevel.SUSPECT, RiskLevel.HAUT_RISQUE]
        )),
    )
    total = values.pop("total")
    risky = values.pop("risky")
    values["total"] = total
    values["risky_rate"] = risky / total if total else 0
    return values, events


def _report_data(period, previous):
    start, end, days = period
    previous_start, previous_end = previous
    current_kpis, events = _event_stats(start, end)
    previous_kpis, _ = _event_stats(previous_start, previous_end)

    alert_rows = list(Alert.objects.filter(created_at__gte=start, created_at__lt=end))
    handled_rows = [alert for alert in alert_rows if alert.status in
                    (AlertStatus.TRAITEE, AlertStatus.FAUSSE_ALERTE)]
    handling_times = sorted(
        (alert.handled_at - alert.created_at).total_seconds() / 3600
        for alert in handled_rows if alert.handled_at
    )
    middle = len(handling_times) // 2
    median = None
    if handling_times:
        median = handling_times[middle] if len(handling_times) % 2 else (
            handling_times[middle - 1] + handling_times[middle]
        ) / 2
    by_severity = {severity: sum(alert.severity == severity for alert in alert_rows)
                   for severity, _ in Severity.choices}
    by_status = {value: sum(alert.status == value for alert in alert_rows)
                 for value, _ in AlertStatus.choices}

    timeline_rows = (events.filter(
        evaluation__level__in=[RiskLevel.SUSPECT, RiskLevel.HAUT_RISQUE]
    ).annotate(day=TruncDate("timestamp")).values("day", "evaluation__level")
      .annotate(count=Count("id")).order_by("day"))
    timeline_by_day = {}
    for row in timeline_rows:
        day = row["day"].isoformat()
        counts = timeline_by_day.setdefault(day, {"day": day, "suspect": 0, "high": 0})
        key = "suspect" if row["evaluation__level"] == RiskLevel.SUSPECT else "high"
        counts[key] = row["count"]

    rule_counts = {}
    for codes in events.exclude(evaluation__isnull=True).values_list("evaluation__triggered_rules", flat=True):
        for code in codes or []:
            rule_counts[code] = rule_counts.get(code, 0) + 1
    rules = [
        {"code": code, "name": RULE_NAMES.get(code, code), "count": count}
        for code, count in sorted(rule_counts.items(), key=lambda item: (-item[1], item[0]))
    ]

    countries = list(
        events.filter(evaluation__level__in=[RiskLevel.SUSPECT, RiskLevel.HAUT_RISQUE])
        .exclude(country="").values("country").annotate(n=Count("id")).order_by("-n", "country")[:10]
    )

    incidents = []
    incident_alerts = (Alert.objects.filter(created_at__gte=start, created_at__lt=end)
                       .select_related("evaluation", "evaluation__event", "evaluation__event__user")
                       .order_by("-evaluation__score")[:20])
    for alert in incident_alerts:
        event = alert.evaluation.event
        user_hash = hmac.new(
            settings.IP_HASH_SECRET.encode(), str(event.user_id).encode(), hashlib.sha256
        ).hexdigest()[:12]
        incidents.append({
            "id": alert.id,
            "date": event.timestamp,
            "user": f"Utilisateur-{user_hash}",
            "place": ", ".join(part for part in (event.city, event.country) if part) or "Lieu inconnu",
            "score": round(alert.evaluation.score),
            "reasons": alert.evaluation.reasons[:3],
            "status": alert.get_status_display(),
        })

    return {
        "period": {"start": start.date().isoformat(), "end": (end - timedelta(days=1)).date().isoformat(),
                   "days": days},
        "kpi_labels": KPI_LABELS,
        "kpis": current_kpis,
        "previous": previous_kpis,
        "alerts": {
            "total": len(alert_rows),
            "handled": len(handled_rows),
            "handled_rate": len(handled_rows) / len(alert_rows) if alert_rows else None,
            "median_handling_hours": median,
            "by_severity": by_severity,
            "by_status": by_status,
        },
        "blocked_users": User.objects.filter(blocked_until__gt=timezone.now()).count(),
        "timeline": list(timeline_by_day.values()),
        "incidents": incidents,
        "rules": rules,
        "countries": countries,
    }


def _pdf_response(filename, title, rows):
    output = io.BytesIO()
    document = SimpleDocTemplate(output, pagesize=A4, rightMargin=18 * mm, leftMargin=18 * mm,
                                topMargin=18 * mm, bottomMargin=18 * mm)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], alignment=TA_CENTER))
    story = [Paragraph(escape(title), styles["ReportTitle"]), Spacer(1, 8 * mm)]
    table_data = [[Paragraph(escape(str(key)), styles["BodyText"]),
                   Paragraph(escape(str(value)), styles["BodyText"])] for key, value in rows]
    table = Table(table_data, colWidths=[55 * mm, 115 * mm], repeatRows=0)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2f8")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 7),
    ]))
    story.append(table)
    document.build(story)
    response = HttpResponse(output.getvalue(), content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class ReportSummaryView(APIView):
    permission_classes = [IsAdminOrResponsable]

    def get(self, request):
        period, previous, error = _periods(request)
        if error:
            return error
        data = _report_data(period, previous)
        export = request.query_params.get("export")
        if export is None:
            return Response(data)
        if export == "pdf":
            rows = [
                ("Période", f"{data['period']['start']} — {data['period']['end']} ({data['period']['days']} jours)"),
                *[(label, data["kpis"][key]) for key, label in KPI_LABELS.items()],
                ("Part des connexions à risque", f"{data['kpis']['risky_rate']:.1%}"),
                ("Alertes", data["alerts"]["total"]),
                ("Alertes clôturées", data["alerts"]["handled"]),
                ("Comptes actuellement bloqués", data["blocked_users"]),
            ]
            return _pdf_response("rapport.pdf", "Rapport de synthèse SecureAccess", rows)
        if export == "csv":
            response = HttpResponse(content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = 'attachment; filename="rapport.csv"'
            response.write("\ufeff")
            writer = csv.writer(response)
            writer.writerow(["Indicateur", "Période", "Période précédente"])
            for key, label in KPI_LABELS.items():
                writer.writerow([label, data["kpis"][key], data["previous"][key]])
            writer.writerow(["Part des connexions à risque", data["kpis"]["risky_rate"],
                             data["previous"]["risky_rate"]])
            writer.writerow(["Alertes", data["alerts"]["total"], ""])
            writer.writerow(["Alertes clôturées", data["alerts"]["handled"], ""])
            return response
        return Response({"export": ["Valeurs acceptées : csv ou pdf."]}, status=status.HTTP_400_BAD_REQUEST)


def _protection_measures():
    active_model = MLModel.objects.filter(is_active=True).first()
    email_delivery = settings.EMAIL_BACKEND.endswith("smtp.EmailBackend") and bool(settings.EMAIL_HOST)
    return [
        {
            "group": "Authentification",
            "name": "Hachage des mots de passe",
            "status": "active",
            "detail": "Les mots de passe sont stockés avec Argon2 et les règles de complexité Django.",
        },
        {
            "group": "Authentification",
            "name": "Double authentification TOTP",
            "status": "partial",
            "detail": "Disponible pour les comptes; elle n'est active que lorsqu'elle est configurée ou imposée.",
        },
        {
            "group": "Authentification",
            "name": "Jetons de session à durée limitée",
            "status": "active",
            "detail": "Les jetons d'accès expirent après 15 minutes et les jetons de renouvellement sont révocables.",
        },
        {
            "group": "Accès et données",
            "name": "Contrôle d'accès par rôle",
            "status": "active",
            "detail": "Les autorisations sont vérifiées côté serveur pour chaque requête protégée.",
        },
        {
            "group": "Accès et données",
            "name": "Pseudonymisation des adresses IP",
            "status": "active",
            "detail": "Les événements conservent une empreinte HMAC de l'adresse, pas l'adresse IP en clair.",
        },
        {
            "group": "Surveillance",
            "name": "Détection des connexions à risque",
            "status": "active" if active_model else "partial",
            "detail": "Moteur hybride de règles et de machine learning."
                     if active_model else "Les règles et l'API sont disponibles; aucun modèle n'est actuellement actif.",
        },
        {
            "group": "Surveillance",
            "name": "Journal d'audit",
            "status": "active",
            "detail": "Les actions administratives et les actions sensibles sont enregistrées.",
        },
        {
            "group": "Infrastructure",
            "name": "Envoi des liens de réinitialisation",
            "status": "active" if email_delivery else "partial",
            "detail": "Le backend utilise SMTP configuré." if email_delivery else
                      "En développement, les liens sont écrits dans la console du backend; configurez SMTP en production.",
        },
        {
            "group": "Infrastructure",
            "name": "Redirection HTTPS",
            "status": "active" if settings.SECURE_SSL_REDIRECT else "partial",
            "detail": "La redirection HTTPS est activée." if settings.SECURE_SSL_REDIRECT else
                      "À activer derrière un proxy HTTPS avant tout déploiement public.",
        },
    ]


class ProtectionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        measures = _protection_measures()
        generated_at = timezone.now()
        if request.query_params.get("export") == "pdf":
            rows = [
                (measure["group"] + " — " + measure["name"],
                 measure["status"].upper() + ": " + measure["detail"])
                for measure in measures
            ]
            return _pdf_response("mesures-protection.pdf", "Mesures de protection SecureAccess", rows)
        return Response({"generated_at": generated_at, "measures": measures})
