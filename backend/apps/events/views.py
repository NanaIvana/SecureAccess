"""
FICHIER : apps/events/views.py

RÔLE
      GET  /api/events/               historique des connexions (filtres, tri, pagination)
      GET  /api/events/{id}/          détail d'une connexion avec son évaluation du risque
      GET  /api/events/places/        lieux proposés au simulateur
      POST /api/events/simulate/      simule une tentative : enregistre, évalue, crée l'alerte
    Tout est réservé aux administrateurs (les journaux sont sensibles).
"""
import hashlib
import hmac
import random
import secrets
import csv
from datetime import timedelta

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import IsAdminRole
from apps.audit.services import log_action
from apps.detection.service import NoActiveModel, evaluate_events

from .datagen import CAMEROON_CITIES, FOREIGN_CITIES
from .filters import LoginEventFilter
from .models import Device, LoginEvent, Notification
from .serializers import LoginEventSerializer, SimulateSerializer

# Lieux proposés au simulateur : {nom de la ville: (pays, latitude, longitude)}
PLACES = {c[0]: ("Cameroun", c[1], c[2]) for c in CAMEROON_CITIES}
PLACES.update({c[0]: (c[1], c[2], c[3]) for c in FOREIGN_CITIES})


def _hash_ip(label):
    """Pseudonymise une « adresse » (jamais stockée en clair) avec la clé secrète du projet."""
    return hmac.new(settings.IP_HASH_SECRET.encode(), label.encode(), hashlib.sha256).hexdigest()[:32]


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = LoginEvent.objects.select_related("user", "device", "evaluation", "evaluation__alert")
    serializer_class = LoginEventSerializer
    permission_classes = [IsAdminRole]
    filterset_class = LoginEventFilter
    search_fields = ["user__email"]
    ordering_fields = ["timestamp"]

    def get_permissions(self):
        if self.action in ("list", "retrieve", "report", "confirm"):
            return [IsAdminRoleOrOwner()]
        return super().get_permissions()

    def get_queryset(self):
        queryset = super().get_queryset()
        if self.request.user.role != "ADMIN":
            queryset = queryset.filter(user=self.request.user)
        return queryset

    @action(detail=True, methods=["post"])
    def report(self, request, pk=None):
        event = self.get_object()
        if event.user_id != request.user.id:
            return Response({"detail": "Seul le propriétaire peut signaler cette connexion."},
                            status=status.HTTP_403_FORBIDDEN)
        comment = str(request.data.get("comment", "")).strip()[:1000]
        admins = list(User.objects.filter(role="ADMIN", is_active=True))
        if not admins:
            return Response({"detail": "Aucun administrateur actif ne peut recevoir ce signalement."},
                            status=status.HTTP_503_SERVICE_UNAVAILABLE)
        for admin in admins:
            Notification.objects.get_or_create(
                user=admin,
                event=event,
                kind=Notification.Kind.CONNEXION_INHABITUELLE,
                title="Connexion signalée par un utilisateur",
                defaults={
                    "message": f"{request.user.email} signale cette connexion comme inconnue."
                               + (f" Motif : {comment}" if comment else ""),
                },
            )
        log_action(request.user, "SIGNALER_CONNEXION", str(event.id), {"comment": comment})
        return Response({"detail": "La connexion a été signalée à l'équipe de sécurité."},
                        status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        event = self.get_object()
        if event.user_id != request.user.id:
            return Response({"detail": "Seul le propriétaire peut confirmer cette connexion."},
                            status=status.HTTP_403_FORBIDDEN)
        notification = Notification.objects.filter(
            user=request.user, event=event, needs_response=True, response=""
        ).first()
        if notification is None:
            return Response({"detail": "Aucune confirmation n'est attendue pour cette connexion."},
                            status=status.HTTP_400_BAD_REQUEST)
        notification.response = Notification.Response.CONFIRMEE
        notification.response_at = timezone.now()
        notification.read_at = notification.read_at or notification.response_at
        notification.save(update_fields=["response", "response_at", "read_at"])
        log_action(request.user, "CONFIRMER_CONNEXION", str(event.id))
        return Response({"detail": "Connexion confirmée."})

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def places(self, request):
        """Villes disponibles pour le simulateur (« domicile » = ville d'attache du compte)."""
        out = [{"city": "domicile", "country": "Ville d'attache du compte"}]
        out += [{"city": c, "country": v[0]} for c, v in PLACES.items()]
        return Response(out)

    @extend_schema(responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["get"])
    def countries(self, request):
        """Pays présents dans l'historique des connexions."""
        countries = (LoginEvent.objects.exclude(country="")
                     .order_by("country").values_list("country", flat=True).distinct())
        return Response(list(countries))

    @action(detail=False, methods=["get"])
    def export(self, request):
        if request.user.role != "ADMIN":
            return Response({"detail": "Accès réservé aux administrateurs."}, status=status.HTTP_403_FORBIDDEN)
        rows = self.filter_queryset(self.get_queryset()).select_related("user", "evaluation")
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="connexions.csv"'
        response.write("\ufeff")
        writer = csv.writer(response)
        writer.writerow(["Date", "Compte", "Pays", "Ville", "Réussie", "Score", "Niveau", "Règles"])
        for event in rows.iterator():
            evaluation = getattr(event, "evaluation", None)
            account = event.user.email
            if request.query_params.get("mode") == "analyse":
                account = hmac.new(
                    settings.IP_HASH_SECRET.encode(), str(event.user_id).encode(), hashlib.sha256
                ).hexdigest()[:16]
            writer.writerow([
                event.timestamp.isoformat(), account, event.country, event.city, event.success,
                evaluation.score if evaluation else "",
                evaluation.level if evaluation else "",
                ", ".join(evaluation.triggered_rules) if evaluation else "",
            ])
        return response

    @extend_schema(request=SimulateSerializer, responses=OpenApiTypes.OBJECT)
    @action(detail=False, methods=["post"])
    def simulate(self, request):
        """Simule une tentative de connexion (démonstration) et renvoie son évaluation du risque."""
        ser = SimulateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data

        try:
            user = User.objects.get(pk=d["user"])
        except User.DoesNotExist:
            return Response({"detail": "Compte introuvable."}, status=status.HTTP_400_BAD_REQUEST)

        if d["city"] == "domicile":
            country, city, lat, lon = user.home_country, user.home_city, user.home_lat, user.home_lon
        elif d["city"] in PLACES:
            city = d["city"]
            country, lat, lon = PLACES[city]
        else:
            return Response({"detail": "Ville inconnue : voir GET /api/events/places/."},
                            status=status.HTTP_400_BAD_REQUEST)

        # Horodatage de la tentative principale : maintenant, ou aujourd'hui à l'heure UTC demandée.
        now = timezone.now()
        main_ts = now.replace(hour=d["hour"], second=0, microsecond=0) if "hour" in d else now

        # Appareil : habituel (le premier de l'utilisateur) ou nouveau (jamais vu).
        if d["device"] == "new":
            device = Device.objects.create(user=user, fingerprint=secrets.token_hex(16), device_type="Ordinateur",
                                           os="Linux", browser="Chrome Headless")
        else:
            device = user.devices.order_by("id").first()

        # Même source pour toute la rafale (sinon une adresse aléatoire).
        ip = _hash_ip(d.get("ip_label") or f"sim-{random.getrandbits(48)}")

        def make(ts, success, reason=""):
            return LoginEvent.objects.create(
                user=user, device=device, timestamp=ts, ip_hash=ip, country=country, city=city,
                latitude=lat, longitude=lon, success=success, failure_reason=reason,
                source=LoginEvent.Source.SIMULATOR)

        # Les échecs précèdent la tentative principale (un toutes les 20 s).
        new_events = [make(main_ts - timedelta(seconds=(d["failures"] - i) * 20), False, "mot_de_passe_incorrect")
                      for i in range(d["failures"])]
        main = make(main_ts, d["success"], "" if d["success"] else "mot_de_passe_incorrect")
        new_events.append(main)

        try:
            # Une seule alerte pour toute la rafale : celle de la tentative principale.
            evaluate_events(new_events, alert_event_ids={main.id})
        except NoActiveModel as exc:
            for ev in new_events:
                ev.delete()
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)

        main = LoginEvent.objects.select_related("user", "device", "evaluation").get(pk=main.pk)
        alert = getattr(main.evaluation, "alert", None)
        log_action(request.user, "SIMULER_CONNEXION", user.email,
                   {"ville": city, "echecs": d["failures"], "niveau": main.evaluation.level})
        return Response({
            "event": LoginEventSerializer(main).data,
            "alert": {"id": alert.id, "severity": alert.severity, "status": alert.status} if alert else None,
            "failures_created": d["failures"],
        }, status=status.HTTP_201_CREATED)


class IsAdminRoleOrOwner(IsAdminRole):
    """Les utilisateurs accèdent à leurs propres événements, les admins à tous."""

    def has_object_permission(self, request, view, obj):
        return bool(request.user.is_authenticated and (
            request.user.role == "ADMIN" or obj.user_id == request.user.id
        ))

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)
