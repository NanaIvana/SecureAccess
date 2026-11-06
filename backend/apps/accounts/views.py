"""
FICHIER : apps/accounts/views.py

RÔLE
    Les points d'entrée (endpoints) de l'API liés aux comptes :
      POST /api/auth/login/             connexion (e-mail + mot de passe) -> jetons JWT
      POST /api/auth/refresh/           renouvelle le jeton d'accès (voir urls.py)
      POST /api/auth/logout/            déconnexion : invalide le jeton de renouvellement
      GET  /api/me/                     profil de l'utilisateur connecté
      GET  /api/health/                 état de l'application et de la base (public)
      GET  /api/users/                  liste des comptes (administrateur)
      GET  /api/users/{id}/             détail d'un compte (administrateur)
      PATCH /api/users/{id}/            changer le rôle / activer-désactiver (administrateur)
      POST /api/users/{id}/block/       bloquer temporairement un compte (administrateur)
      POST /api/users/{id}/unblock/     débloquer un compte (administrateur)

    Chaque action administrative est enregistrée dans le journal d'audit.

UTILISÉ PAR : apps/accounts/urls.py
"""
import base64
import hashlib
import hmac
import io
import logging
from functools import lru_cache
import re
import secrets
import smtplib
import struct
import time
from datetime import timedelta
from urllib.parse import urlencode

import qrcode
from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.contrib.auth.tokens import default_token_generator
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.core import signing
from django.core.signing import BadSignature, SignatureExpired
from django.db import connection, transaction
from django.db.models import Count, Max, Min, Q
from django.db.models.functions import ExtractHour
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django_filters import rest_framework as filters
from rest_framework.exceptions import AuthenticationFailed
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from apps.audit.services import log_action
from apps.detection.models import (
    DetectionConfig, ProgressiveLockout, RiskEvaluation, RiskLevel, UserProfile,
)
from apps.detection.service import NoActiveModel, evaluate_events
from apps.events.models import Device, LoginEvent, Notification
from apps.events.serializers import LoginEventSerializer, NotificationSerializer

from .models import ProfileType, Role, User
from .permissions import IsAdminRole
from .serializers import (
    LoginSerializer, MeUpdateSerializer, UserCreateSerializer, UserSerializer, UserUpdateSerializer,
)

logger = logging.getLogger(__name__)


@lru_cache(maxsize=2)
def _geoip_reader(path):
    from geoip2.database import Reader
    return Reader(path)


def _record_rate_limited_attempt(request):
    """Journalise les 429 pour les comptes connus, sans lancer le scoring coûteux."""
    email = request.data.get("email", "")
    if not isinstance(email, str) or not email.strip():
        return
    user = User.objects.filter(email__iexact=email.strip()).first()
    if not user:
        return
    remote_ip = _client_ip(request)
    ip_hash = hmac.new(settings.IP_HASH_SECRET.encode(), remote_ip.encode(), hashlib.sha256).hexdigest()[:32]
    LoginEvent.objects.create(
        user=user,
        timestamp=timezone.now(),
        ip_hash=ip_hash,
        user_agent=str(request.META.get("HTTP_USER_AGENT", ""))[:300],
        success=False,
        failure_reason="limite_de_taux",
        source=LoginEvent.Source.LIVE,
    )


class LoginIPThrottle(AnonRateThrottle):
    """Limite par IP et journalise les requêtes 429 pour les comptes identifiés."""
    scope = "login_ip"

    def allow_request(self, request, view):
        self.request = request
        return super().allow_request(request, view)

    def throttle_failure(self):
        _record_rate_limited_attempt(self.request)
        return False


class LoginAccountThrottle(AnonRateThrottle):
    """Limite aussi les tentatives par couple source + identifiant, sans révéler l'existence du compte."""
    scope = "login_account"

    def allow_request(self, request, view):
        self.request = request
        return super().allow_request(request, view)

    def get_cache_key(self, request, view):
        email = request.data.get("email", "")
        if not isinstance(email, str):
            email = ""
        normalized = email.strip().lower()[:254]
        source = self.get_ident(request)
        digest = hmac.new(settings.IP_HASH_SECRET.encode(), f"{source}|{normalized}".encode(), hashlib.sha256).hexdigest()
        return self.cache_format % {"scope": self.scope, "ident": digest}

    def throttle_failure(self):
        _record_rate_limited_attempt(self.request)
        return False


class TwoFactorThrottle(AnonRateThrottle):
    scope = "two_factor"


def _client_ip(request):
    """Return the client IP, trusting X-Forwarded-For only from configured proxies."""
    import ipaddress

    remote = str(request.META.get("REMOTE_ADDR", "")).strip()
    try:
        remote_obj = ipaddress.ip_address(remote)
    except ValueError:
        return ""

    trusted = getattr(settings, "GEOIP2_TRUSTED_PROXY_IPS", []) or []
    if not any(remote_obj == ipaddress.ip_address(value) for value in trusted):
        return str(remote_obj)

    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidates = []
    for value in forwarded.split(","):
        try:
            candidates.append(ipaddress.ip_address(value.strip()))
        except ValueError:
            continue
    # Walk from the proxy-facing end; discard configured trusted proxies.
    for candidate in reversed(candidates):
        if not any(candidate == ipaddress.ip_address(value) for value in trusted):
            return str(candidate)
    return str(candidates[0]) if candidates else str(remote_obj)


def _resolve_login_location(user, remote_ip):
    """Resolve public IPs with local GeoLite2; never invent a geographic location."""
    import ipaddress
    try:
        ip_obj = ipaddress.ip_address(str(remote_ip).strip())
    except (TypeError, ValueError):
        ip_obj = None

    db_path = str(getattr(settings, "GEOIP2_CITY_DB_PATH", "") or "").strip()
    if ip_obj and ip_obj.is_global and db_path:
        try:
            record = _geoip_reader(db_path).city(str(ip_obj))
            country_names = record.country.names or {}
            city_names = record.city.names or {}
            country = country_names.get("fr") or country_names.get("en") or record.country.iso_code or ""
            city = city_names.get("fr") or city_names.get("en") or ""
            latitude = record.location.latitude
            longitude = record.location.longitude
            # A valid database match may identify only a country/region, not a city.
            if country or city:
                return country or "Pays non déterminé", city or "Ville non déterminée", latitude, longitude, "IP_GEOIP"
        except Exception as exc:
            logger.warning("GeoLite2 lookup failed (%s); using registered account location.", exc.__class__.__name__)

    # Private/loopback IPs (localhost, LAN, Docker) cannot be located by GeoLite2.
    if user.home_country or user.home_city:
        return (user.home_country or "Pays non renseigné", user.home_city or "Ville non renseignée",
                user.home_lat, user.home_lon, "PROFILE_FALLBACK")
    return ("Pays non déterminé", "Localisation IP indisponible", None, None, "UNKNOWN")


def _record_live_login(user, request, device_data=None, success=True, reason="", return_event=False):
    remote_ip = _client_ip(request)
    ip_hash = hmac.new(
        settings.IP_HASH_SECRET.encode(), remote_ip.encode(), hashlib.sha256
    ).hexdigest()[:32]
    device = None
    if device_data:
        device, _ = Device.objects.get_or_create(
            user=user,
            fingerprint=device_data["fingerprint"],
            defaults={
                "device_type": device_data["device_type"],
                "os": device_data["os"],
                "browser": device_data["browser"],
            },
        )
    event_time = timezone.now()
    country, city, latitude, longitude, location_source = _resolve_login_location(user, remote_ip)
    if settings.DEMO_MODE and user.email.lower().endswith(".test"):
        # En démo uniquement, les scénarios peuvent simuler un pays/une ville.
        country = user.home_country or country
        city = user.home_city or city
        latitude = user.home_lat if user.home_lat is not None else latitude
        longitude = user.home_lon if user.home_lon is not None else longitude
        demo_country = request.headers.get("X-SecureAccess-Demo-Country")
        demo_city = request.headers.get("X-SecureAccess-Demo-City")
        if demo_country:
            country = str(demo_country)[:100]
            location_source = "DEMO_SIMULATED"
        if demo_city:
            city = str(demo_city)[:100]
            location_source = "DEMO_SIMULATED"
        if country == "France" and city == "Paris":
            latitude, longitude = 48.857, 2.352
        demo_clock = request.headers.get("X-SecureAccess-Demo-Time", "")
        if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", demo_clock):
            event_time = event_time.replace(hour=int(demo_clock[:2]), minute=int(demo_clock[3:]), second=0, microsecond=0)
    event = LoginEvent.objects.create(
        user=user,
        device=device,
        timestamp=event_time,
        ip_hash=ip_hash,
        user_agent=str(request.META.get("HTTP_USER_AGENT", ""))[:300],
        country=country,
        city=city,
        latitude=latitude,
        longitude=longitude,
        location_source=location_source,
        success=success,
        failure_reason=reason,
        source=LoginEvent.Source.LIVE,
    )
    try:
        evaluation = evaluate_events([event]).get(event.id)
    except NoActiveModel as exc:
        logger.warning("Live login event %s was stored without risk scoring: %s", event.id, exc)
        return (None, event) if return_event else None
    if evaluation is None:
        return (None, event) if return_event else None
    risk = {"level": evaluation.level, "score": evaluation.score}
    user.refresh_from_db(fields=["blocked_until"])
    if user.is_blocked():
        risk["blocked_until"] = user.blocked_until
        risk["retry_after_seconds"] = max(
            1, int((user.blocked_until - timezone.now()).total_seconds() + 0.999),
        )
    return (risk, event) if return_event else risk


def _risk_level(risk):
    return str((risk or {}).get("level", "")).upper()


def _is_critical(risk):
    return _risk_level(risk) in {"CRITIQUE", "CRITICAL"}


def _is_high_risk(risk):
    return _risk_level(risk) in {"HAUT_RISQUE", "HIGH_RISK", "CRITIQUE", "CRITICAL"}


def _two_factor_challenge(user, device_data, *, step_up=False, event=None):
    payload = {"user_id": user.pk, "device": device_data}
    if step_up:
        payload.update({"step_up": True, "event_id": event.pk})
    return {
        "two_factor": {
            "challenge": signing.dumps(payload, salt="secureaccess.2fa-login"),
            "method": "totp" if user.two_factor_enabled else "setup",
            "reason": (
                "Une vérification supplémentaire est requise pour cette connexion à risque."
                if step_up else
                "La double authentification est requise pour ce compte."
            ),
        },
    }


def _risk_for_challenge(user, challenge):
    if not challenge.get("step_up"):
        return None
    event = LoginEvent.objects.filter(
        pk=challenge.get("event_id"),
        user=user,
        source=LoginEvent.Source.LIVE,
        success=True,
    ).select_related("evaluation").first()
    if event is None:
        return None
    try:
        evaluation = event.evaluation
    except RiskEvaluation.DoesNotExist:
        return None
    return {"level": evaluation.level, "score": evaluation.score}


def _critical_refusal_response(risk):
    return Response({
        "detail": "Connexion refusée en raison d'un risque critique.",
        "risk": risk,
    }, status=status.HTTP_403_FORBIDDEN)


def _login_source_hash(request):
    source = _client_ip(request)
    return hmac.new(
        settings.IP_HASH_SECRET.encode(), source.encode(), hashlib.sha256,
    ).hexdigest()[:32]


def _lockout_for_source(user, source_hash):
    if not source_hash:
        return None
    lockout = ProgressiveLockout.objects.filter(user=user, source_hash=source_hash).first()
    if lockout and lockout.locked_until and lockout.locked_until > timezone.now():
        return lockout
    return None


def _lockout_response(lockout):
    now = timezone.now()
    retry = max(1, int((lockout.locked_until - now).total_seconds() + 0.999))
    return Response({
        "detail": "Cette source est temporairement verrouillée après plusieurs échecs.",
        "retry_after_seconds": retry,
        "locked_until": lockout.locked_until,
    }, status=423)


def _record_failed_source_attempt(user, source_hash):
    config, _ = DetectionConfig.objects.get_or_create(pk=1)
    if config.lockout_failures == 0:
        return None
    now = timezone.now()
    reset_after = timedelta(hours=24)
    with transaction.atomic():
        lockout, _ = ProgressiveLockout.objects.select_for_update().get_or_create(
            user=user,
            source_hash=source_hash,
            defaults={
                "window_started_at": now,
                "failure_count": 0,
                "level": 0,
                "last_failure_at": now,
            },
        )
        if lockout.locked_until and lockout.locked_until > now:
            return lockout
        if lockout.last_failure_at < now - reset_after:
            lockout.level = 0
        window = timedelta(minutes=config.lockout_window_minutes)
        if lockout.window_started_at < now - window:
            lockout.failure_count = 0
            lockout.window_started_at = now
        lockout.failure_count += 1
        lockout.last_failure_at = now
        lockout.locked_until = None
        if lockout.failure_count >= config.lockout_failures:
            lockout.level = min(lockout.level + 1, 3)
            multiplier = (1, 3, 12)[lockout.level - 1]
            duration = min(config.lockout_minutes * multiplier, 60 * 24)
            lockout.locked_until = now + timedelta(minutes=duration)
            lockout.failure_count = 0
            lockout.window_started_at = now
        lockout.save(update_fields=[
            "window_started_at", "failure_count", "level", "locked_until", "last_failure_at",
        ])
    return lockout if lockout.locked_until else None


def _clear_source_lockout(user, source_hash):
    ProgressiveLockout.objects.filter(user=user, source_hash=source_hash).delete()


def _blocked_account_response(user, risk=None):
    remaining = max(1, int((user.blocked_until - timezone.now()).total_seconds() + 0.999))
    payload = {
        "detail": "Compte temporairement bloqué.",
        "blocked_until": user.blocked_until,
        "retry_after_seconds": remaining,
    }
    if risk:
        risk["decision"] = "REFUSE"
        payload["risk"] = risk
        payload["decision"] = "REFUSE"
    return Response(payload, status=423)


def _notify_user(user, kind, title, message):
    return Notification.objects.create(user=user, kind=kind, title=title, message=message)


def _send_security_email(user, subject, message):
    """Send security notices without exposing secrets or breaking login if SMTP is down."""
    if not user.email:
        return False
    try:
        sent = send_mail(subject, message, settings.DEFAULT_FROM_EMAIL, [user.email], fail_silently=False)
        return bool(sent)
    except Exception:
        logger.exception("SecureAccess could not send a security email to user id=%s", user.pk)
        return False


def notify_account_blocked(user, minutes, reason="activité de connexion suspecte"):
    user.two_factor_required = True
    user.save(update_fields=["two_factor_required"])
    _notify_user(user, Notification.Kind.COMPTE_BLOQUE, "Compte temporairement bloqué",
                 f"Votre compte a été temporairement bloqué pendant {minutes} minute(s) en raison de {reason}. "
                 "Après le déblocage, une double authentification sera obligatoire avant le prochain accès.")
    _send_security_email(
        user, "SecureAccess — votre compte a été temporairement bloqué",
        f"Bonjour {user.full_name or user.email},\n\nNous avons temporairement bloqué votre compte SecureAccess pendant {minutes} minute(s) "
        f"à la suite de {reason}. Si vous n'êtes pas à l'origine de ces tentatives, contactez l'administrateur de votre établissement.\n\n"
        "Pour protéger votre compte, une double authentification sera exigée après le déblocage.\n\nL'équipe SecureAccess",
    )


def notify_account_unblocked(user):
    _notify_user(user, Notification.Kind.COMPTE_BLOQUE, "Compte débloqué",
                 "Votre compte est de nouveau accessible. Une double authentification est obligatoire lors de votre prochaine connexion.")
    _send_security_email(
        user, "SecureAccess — votre compte est de nouveau accessible",
        f"Bonjour {user.full_name or user.email},\n\nVotre compte SecureAccess a été débloqué. Vous pouvez à présent vous connecter. "
        "Une étape de double authentification vous sera demandée pour sécuriser votre accès.\n\n"
        "Si vous ne reconnaissez pas cette action, contactez immédiatement l'administrateur de votre établissement.\n\nL'équipe SecureAccess",
    )


class LoginView(TokenObtainPairView):
    """Connexion publique (pas de jeton nécessaire pour se connecter)."""
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_classes = [LoginIPThrottle, LoginAccountThrottle]

    def post(self, request, *args, **kwargs):
        email = request.data.get("email")
        user = User.objects.filter(email__iexact=email).first() if isinstance(email, str) else None
        source_hash = _login_source_hash(request)
        if user:
            source_lockout = _lockout_for_source(user, source_hash)
            if source_lockout:
                # Journalise aussi l'essai bloqué (sans jamais enregistrer le mot de passe).
                _record_live_login(user, request, success=False, reason="verrouillage_progressif")
                return _lockout_response(source_lockout)
        serializer = self.get_serializer(data=request.data)
        try:
            serializer.is_valid(raise_exception=True)
        except AuthenticationFailed:
            if user:
                globally_blocked = user.is_blocked()
                reason = "compte_bloque" if globally_blocked else "mot_de_passe_incorrect"
                _record_live_login(
                    user, request, getattr(serializer, "device_data", None),
                    success=False, reason=reason,
                )
                user.refresh_from_db(fields=["blocked_until"])
                if user.is_blocked():
                    return _blocked_account_response(user)
                if not globally_blocked:
                    # Le 5e échec est journalisé ; le 6e appel rencontre le verrouillage au début de la vue.
                    _record_failed_source_attempt(user, source_hash)
            raise
        user = serializer.user
        # Un blocage temporaire vient d'expirer : prévenir l'utilisateur lors de son premier retour.
        if user.blocked_until and user.blocked_until <= timezone.now():
            user.blocked_until = None
            user.two_factor_required = True
            user.save(update_fields=["blocked_until", "two_factor_required"])
            notify_account_unblocked(user)
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        # Même une connexion qui doit ensuite passer par la 2FA est journalisée et évaluée.
        risk, event = _record_live_login(
            user, request, serializer.device_data, return_event=True,
        )
        if risk:
            risk["decision"] = (
                "REFUSE" if config.refuse_critical and _is_critical(risk)
                else "STEP_UP" if (user.two_factor_enabled or user.two_factor_required or
                                   (config.step_up_high_risk and _is_high_risk(risk)))
                else "ALLOW_WITH_ALERT" if _risk_level(risk) != "NORMAL"
                else "ALLOW"
            )
        if user.is_blocked():
            return _blocked_account_response(user, risk)
        if config.refuse_critical and _is_critical(risk):
            return _critical_refusal_response(risk)
        if user.two_factor_enabled or user.two_factor_required:
            challenge = _two_factor_challenge(user, serializer.device_data)
            challenge["risk"] = risk
            return Response(challenge)
        if config.step_up_high_risk and _is_high_risk(risk):
            challenge = _two_factor_challenge(user, serializer.device_data, step_up=True, event=event)
            challenge["risk"] = risk
            return Response(challenge)
        data = serializer.validated_data
        data["risk"] = risk
        _clear_source_lockout(user, source_hash)
        return Response(data)



class LabAttackView(APIView):
    """Rejoue des scénarios limités au compte de démonstration connecté via le vrai endpoint login."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if not settings.DEMO_MODE:
            return Response({"detail": "Le mode de démonstration est désactivé."}, status=status.HTTP_403_FORBIDDEN)
        if not request.user.email.lower().endswith(".test"):
            return Response({"detail": "Le mode test est réservé aux comptes de démonstration en .test."},
                            status=status.HTTP_403_FORBIDDEN)
        scenario = request.data.get("scenario")
        allowed = {"normal", "brute_force", "new_device", "compromised"}
        if scenario not in allowed:
            return Response({"detail": "Scénario non reconnu.", "allowed": sorted(allowed)},
                            status=status.HTTP_400_BAD_REQUEST)
        password = request.data.get("password", "")
        if scenario != "brute_force" and (not isinstance(password, str) or not password):
            return Response({"password": ["Le mot de passe réel du compte de démonstration est requis."]},
                            status=status.HTTP_400_BAD_REQUEST)

        from rest_framework.test import APIRequestFactory

        factory = APIRequestFactory()
        results = []
        total = 6 if scenario == "brute_force" else 1
        for index in range(total):
            known_device = request.user.devices.order_by("first_seen").first() if scenario == "normal" else None
            fingerprint_seed = (
                f"secureaccess-lab-{request.user.pk}-normal" if scenario == "normal"
                else f"secureaccess-lab-{request.user.pk}-{scenario}-{secrets.token_hex(12)}"
            )
            fingerprint = known_device.fingerprint if known_device else hashlib.sha256(fingerprint_seed.encode()).hexdigest()[:32]
            payload = {
                "email": request.user.email,
                "password": f"WrongPassword-{index}-NotTheRealOne!" if scenario == "brute_force" else password,
                "device": {"fingerprint": fingerprint, "device_type": "Ordinateur", "os": "Demo", "browser": "Chrome"},
            }
            headers = {
                "HTTP_USER_AGENT": "SecureAccess-Demo/1.0",
                "HTTP_X_SECUREACCESS_DEMO_TIME": "09:00",
            }
            if scenario == "compromised":
                headers.update({
                    "HTTP_X_SECUREACCESS_DEMO_COUNTRY": "France",
                    "HTTP_X_SECUREACCESS_DEMO_CITY": "Paris",
                    "HTTP_X_SECUREACCESS_DEMO_TIME": "03:00",
                })
            inner_request = factory.post(
                "/api/auth/login/", payload, format="json",
                REMOTE_ADDR=request.META.get("REMOTE_ADDR", "127.0.0.1"), **headers,
            )
            previous_event_id = LoginEvent.objects.filter(user=request.user, source=LoginEvent.Source.LIVE).order_by("-id").values_list("id", flat=True).first() or 0
            response = LoginView.as_view()(inner_request)
            event = LoginEvent.objects.filter(user=request.user, source=LoginEvent.Source.LIVE, id__gt=previous_event_id).order_by("-id").first()
            evaluation = None
            if event:
                try:
                    evaluation = event.evaluation
                except RiskEvaluation.DoesNotExist:
                    evaluation = None
            code = response.status_code
            if code == 200 and response.data.get("two_factor"):
                decision = "VERIFICATION_SUPPLEMENTAIRE"
            elif code == 200 and evaluation and evaluation.level != RiskLevel.NORMAL:
                decision = "AUTORISEE_AVEC_ALERTE"
            elif code == 200:
                decision = "AUTORISEE"
            elif code == 423:
                decision = "VERROUILLEE"
            elif code == 429:
                decision = "LIMITEE"
            else:
                decision = "REFUSEE"
            results.append({
                "attempt": index + 1,
                "http_status": code,
                "decision": decision,
                "level": evaluation.level if evaluation else None,
                "score": evaluation.score if evaluation else None,
                "reasons": evaluation.reasons if evaluation else [],
            })
        return Response({"scenario": scenario, "attempts": results, "count": len(results)})


class PublicLabAttackView(APIView):
    """Démo pédagogique publique, strictement limitée à DEMO_MODE et aux comptes .test."""
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]

    def post(self, request):
        if not settings.DEMO_MODE:
            return Response({"detail": "Le laboratoire est désactivé. Activez DEMO_MODE=True uniquement pour une démonstration locale."}, status=403)
        scenario = str(request.data.get("scenario", ""))
        allowed = {"normal", "brute_force", "password_spraying", "slow_brute_force", "new_device",
                   "new_country", "unusual_hour", "bot", "impossible_travel"}
        if scenario not in allowed:
            return Response({"detail": "Scénario non reconnu.", "allowed": sorted(allowed)}, status=400)
        base_email = str(request.data.get("email", "enseignant@demo.secureaccess.test")).lower()
        if not base_email.endswith("@demo.secureaccess.test"):
            return Response({"detail": "Seuls les comptes de démonstration sont autorisés."}, status=403)
        base_user = User.objects.filter(email=base_email, is_active=True).first()
        if not base_user:
            return Response({"detail": "Compte de démonstration introuvable. Exécutez create_demo_accounts."}, status=404)
        demo_password = str(request.data.get("password", "DemoSchool2026!"))
        # Chaque scénario repart d'un état propre ; ses événements, eux, restent visibles au tableau de bord.
        from apps.detection.models import ProgressiveLockout
        base_user.blocked_until = None
        base_user.two_factor_required = False
        base_user.save(update_fields=["blocked_until", "two_factor_required"])
        ProgressiveLockout.objects.filter(user=base_user).delete()
        from rest_framework.test import APIRequestFactory
        factory = APIRequestFactory()
        results = []
        targets = [base_user]
        if scenario == "password_spraying":
            # 11 comptes distincts, même source : les comptes de labo sont visibles dans la console.
            for i in range(1, 12):
                email = f"attack-lab-{i:02d}@demo.secureaccess.test"
                user, created = User.objects.get_or_create(email=email, defaults={
                    "full_name": f"Compte laboratoire {i}", "role": Role.UTILISATEUR,
                    "profile_type": ProfileType.ENSEIGNANT, "home_city": "Yaoundé", "home_country": "Cameroun",
                    "home_lat": 3.848, "home_lon": 11.502,
                })
                user.set_password(demo_password); user.save(update_fields=["password"])
                targets.append(user)
        elif scenario == "slow_brute_force":
            targets = [base_user] * 11
        elif scenario == "brute_force":
            targets = [base_user] * 6

        for index, user in enumerate(targets):
            if user.pk != base_user.pk:
                user.blocked_until = None
                user.two_factor_required = False
                user.save(update_fields=["blocked_until", "two_factor_required"])
                ProgressiveLockout.objects.filter(user=user).delete()
            password = demo_password
            ua = "Mozilla/5.0 (SecureAccess demo)"
            headers = {"HTTP_HOST": "localhost", "HTTP_USER_AGENT": ua,
                       "HTTP_X_SECUREACCESS_DEMO_TIME": "09:00",
                       "HTTP_X_SECUREACCESS_DEMO_COUNTRY": "Cameroun",
                       "HTTP_X_SECUREACCESS_DEMO_CITY": "Yaoundé"}
            remote_ip = "10.252.0.10"
            known_device = user.devices.order_by("first_seen").first()
            fingerprint = known_device.fingerprint if known_device else hashlib.sha256(f"public-lab-{user.pk}-known".encode()).hexdigest()[:32]
            if scenario == "brute_force": password = f"Wrong-Demo-{index}!"
            if scenario == "password_spraying": password = "Wrong-Spray-Demo!"
            if scenario == "slow_brute_force":
                password = f"Wrong-Slow-{index}!"; remote_ip = f"10.252.0.{10 + index % 3}"
            if scenario == "new_device": fingerprint = hashlib.sha256(secrets.token_bytes(24)).hexdigest()[:32]
            if scenario == "new_country":
                headers.update({"HTTP_X_SECUREACCESS_DEMO_COUNTRY": "France", "HTTP_X_SECUREACCESS_DEMO_CITY": "Paris"})
            if scenario == "unusual_hour": headers["HTTP_X_SECUREACCESS_DEMO_TIME"] = "03:00"
            if scenario == "bot": headers["HTTP_USER_AGENT"] = "python-requests/2.31"
            if scenario == "impossible_travel":
                headers.update({"HTTP_X_SECUREACCESS_DEMO_COUNTRY": "France", "HTTP_X_SECUREACCESS_DEMO_CITY": "Paris",
                                "HTTP_X_SECUREACCESS_DEMO_TIME": "03:00"})
            payload = {"email": user.email, "password": password,
                       "device": {"fingerprint": fingerprint, "device_type": "Ordinateur", "os": "Demo", "browser": "Chrome"}}
            inner = factory.post("/api/auth/login/", payload, format="json", REMOTE_ADDR=remote_ip, **headers)
            response = LoginView.as_view()(inner)
            data = getattr(response, "data", {}) or {}
            results.append({"attempt": index + 1, "account": user.email, "http_status": response.status_code,
                            "decision": "VERIFICATION_SUPPLEMENTAIRE" if data.get("two_factor") else
                                       "VERROUILLEE" if response.status_code == 423 else
                                       "LIMITEE" if response.status_code == 429 else
                                       "AUTORISEE_AVEC_ALERTE" if response.status_code == 200 and data.get("risk", {}).get("level") != "NORMAL" else
                                       "AUTORISEE" if response.status_code == 200 else "REFUSEE",
                            "risk": data.get("risk"), "detail": data.get("detail", "")})
        return Response({"scenario": scenario, "attempts": results, "count": len(results)}, status=200)


def _fernet():
    key = base64.urlsafe_b64encode(hashlib.sha256(settings.SECRET_KEY.encode()).digest())
    return Fernet(key)


def _decrypt_totp_secret(user):
    try:
        return _fernet().decrypt(user.two_factor_secret.encode()).decode()
    except (InvalidToken, ValueError) as exc:
        raise RuntimeError("La clé de chiffrement TOTP est invalide. Vérifiez DJANGO_SECRET_KEY.") from exc


def _totp_code(secret, at_time=None):
    counter = int((at_time if at_time is not None else time.time()) // 30)
    key = base64.b32decode(secret, casefold=True)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return f"{value % 1_000_000:06d}"


def _verify_totp(secret, code):
    if not isinstance(code, str) or len(code) != 6 or not code.isdigit():
        return False
    now = time.time()
    return any(hmac.compare_digest(_totp_code(secret, now + offset * 30), code) for offset in (-1, 0, 1))


def _totp_setup(user):
    secret = base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")
    user.two_factor_secret = _fernet().encrypt(secret.encode()).decode()
    user.save(update_fields=["two_factor_secret"])
    uri = f"otpauth://totp/SecureAccess:{user.email}?" + urlencode({
        "secret": secret,
        "issuer": "SecureAccess",
        "algorithm": "SHA1",
        "digits": 6,
        "period": 30,
    })
    qr = qrcode.QRCode(box_size=5, border=2)
    qr.add_data(uri)
    qr.make(fit=True)
    from qrcode.image.svg import SvgPathImage

    image = qr.make_image(image_factory=SvgPathImage)
    output = io.BytesIO()
    image.save(output)
    qr_svg = "data:image/svg+xml;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    return {"secret": secret, "qr_svg": qr_svg}


def _challenge_data(challenge):
    try:
        payload = signing.loads(challenge, salt="secureaccess.2fa-login", max_age=300)
        user = User.objects.get(pk=payload["user_id"], is_active=True)
    except (BadSignature, SignatureExpired, KeyError, TypeError, ValueError, User.DoesNotExist):
        return None, None
    if user.is_blocked():
        return None, None
    return user, payload


def _issue_tokens(user):
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    return {"refresh": str(refresh), "access": str(refresh.access_token), "user": UserSerializer(user).data}


class TwoFactorSetupView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.two_factor_enabled:
            return Response({"detail": "La double authentification est déjà active."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(_totp_setup(request.user))


class TwoFactorConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            secret = _decrypt_totp_secret(request.user)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not _verify_totp(secret, request.data.get("code")):
            return Response({"code": ["Code invalide ou expiré."]}, status=status.HTTP_400_BAD_REQUEST)
        request.user.two_factor_enabled = True
        request.user.save(update_fields=["two_factor_enabled"])
        log_action(request.user, "ACTIVER_DOUBLE_AUTH", request.user.email)
        _notify_user(request.user, Notification.Kind.DOUBLE_AUTH, "Double authentification activée",
                     "La double authentification a été activée sur votre compte.")
        return Response({"detail": "Double authentification activée."})


class TwoFactorDisableView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.two_factor_required:
            return Response({"detail": "La double authentification est imposée par l'administrateur."},
                            status=status.HTTP_403_FORBIDDEN)
        if not request.user.check_password(request.data.get("password", "")):
            return Response({"password": ["Mot de passe incorrect."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            secret = _decrypt_totp_secret(request.user)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not request.user.two_factor_enabled or not _verify_totp(secret, request.data.get("code")):
            return Response({"code": ["Code invalide ou double authentification inactive."]},
                            status=status.HTTP_400_BAD_REQUEST)
        request.user.two_factor_enabled = False
        request.user.two_factor_secret = ""
        request.user.save(update_fields=["two_factor_enabled", "two_factor_secret"])
        log_action(request.user, "DESACTIVER_DOUBLE_AUTH", request.user.email)
        _notify_user(request.user, Notification.Kind.DOUBLE_AUTH, "Double authentification désactivée",
                     "La double authentification a été désactivée sur votre compte.")
        return Response({"detail": "Double authentification désactivée."})


class TwoFactorLoginSetupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [TwoFactorThrottle]

    def post(self, request):
        user, challenge = _challenge_data(request.data.get("challenge"))
        allowed_step_up = bool(challenge and challenge.get("step_up"))
        if (
            user is None or user.two_factor_enabled
            or not (user.two_factor_required or allowed_step_up)
        ):
            return Response({"detail": "Étape de connexion invalide ou expirée."},
                            status=status.HTTP_400_BAD_REQUEST)
        if allowed_step_up and _risk_for_challenge(user, challenge) is None:
            return Response({"detail": "Étape de connexion invalide ou expirée."},
                            status=status.HTTP_400_BAD_REQUEST)
        return Response(_totp_setup(user))


class TwoFactorVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [TwoFactorThrottle]

    def post(self, request):
        user, challenge = _challenge_data(request.data.get("challenge"))
        step_up = bool(challenge and challenge.get("step_up"))
        if user is None or not (
            user.two_factor_enabled or user.two_factor_required or step_up
        ):
            return Response({"detail": "Étape de connexion invalide ou expirée."},
                            status=status.HTTP_400_BAD_REQUEST)
        step_up_risk = _risk_for_challenge(user, challenge) if step_up else None
        if step_up and step_up_risk is None:
            return Response({"detail": "Étape de connexion invalide ou expirée."},
                            status=status.HTTP_400_BAD_REQUEST)
        source_hash = _login_source_hash(request)
        source_lockout = _lockout_for_source(user, source_hash)
        if source_lockout:
            return _lockout_response(source_lockout)
        try:
            secret = _decrypt_totp_secret(user)
        except RuntimeError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        if not _verify_totp(secret, request.data.get("code")):
            _record_live_login(user, request, success=False, reason="code_double_auth_incorrect")
            user.refresh_from_db(fields=["blocked_until"])
            if user.is_blocked():
                return _blocked_account_response(user)
            lockout = _record_failed_source_attempt(user, source_hash)
            if lockout:
                return _lockout_response(lockout)
            return Response({"code": ["Code invalide ou expiré."]}, status=status.HTTP_400_BAD_REQUEST)
        if not user.two_factor_enabled:
            user.two_factor_enabled = True
            user.save(update_fields=["two_factor_enabled"])
            log_action(user, "ACTIVER_DOUBLE_AUTH", user.email)
            _notify_user(user, Notification.Kind.DOUBLE_AUTH, "Double authentification activée",
                         "La double authentification obligatoire a été activée sur votre compte.")
        config, _ = DetectionConfig.objects.get_or_create(pk=1)
        if step_up:
            risk = step_up_risk
        else:
            risk = _record_live_login(user, request, challenge.get("device"), success=True)
        if config.refuse_critical and _is_critical(risk):
            return _critical_refusal_response(risk)
        if user.is_blocked():
            return _blocked_account_response(user)
        data = _issue_tokens(user)
        data["risk"] = risk
        _clear_source_lockout(user, source_hash)
        return Response(data)


class PasswordResetView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        email = request.data.get("email")
        if not isinstance(email, str) or not email.strip():
            return Response({"email": ["Une adresse e-mail est requise."]}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.filter(email__iexact=email.strip(), is_active=True).first()
        if user:
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            token = default_token_generator.make_token(user)
            link = f"{settings.FRONTEND_URL.rstrip('/')}/reinitialiser?{urlencode({'uid': uid, 'token': token})}"
            try:
                send_mail(
                    "Réinitialisation de votre mot de passe SecureAccess",
                    f"Pour choisir un nouveau mot de passe, ouvrez ce lien (valable 24 heures) :\n{link}\n\n"
                    "Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.",
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    fail_silently=False,
                )
            except (OSError, smtplib.SMTPException):
                logger.exception("Password reset email delivery failed.")
                return Response({"detail": "Le service d'envoi d'e-mail est indisponible. Réessayez plus tard."},
                                status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return Response({
            "detail": "Si cette adresse correspond à un compte actif, un lien de réinitialisation a été envoyé."
        })


class PasswordResetConfirmView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        uid, token, password = request.data.get("uid"), request.data.get("token"), request.data.get("new_password")
        if not all(isinstance(value, str) and value for value in (uid, token, password)):
            return Response({"detail": "Le lien et le nouveau mot de passe sont requis."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id, is_active=True)
        except (ValueError, TypeError, User.DoesNotExist):
            user = None
        if user is None or not default_token_generator.check_token(user, token):
            return Response({"detail": "Le lien de réinitialisation est invalide ou expiré."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(password, user=user)
        except DjangoValidationError as exc:
            return Response({"new_password": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(password)
        user.save(update_fields=["password"])
        log_action(user, "REINITIALISER_MOT_DE_PASSE", user.email)
        _notify_user(user, Notification.Kind.MOT_DE_PASSE, "Mot de passe réinitialisé",
                     "Le mot de passe de votre compte a été réinitialisé.")
        return Response({"detail": "Votre mot de passe a été réinitialisé."})

class MeView(RetrieveUpdateAPIView):
    """Profil de la personne connectée (utile au frontend pour connaître son rôle)."""
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user

    def get_serializer_class(self):
        if self.request.method == "PATCH":
            return MeUpdateSerializer
        return UserSerializer

    def partial_update(self, request, *args, **kwargs):
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(UserSerializer(instance).data)


class MeSecurityView(APIView):
    """Résumé de sécurité du compte connecté et de ses dernières connexions."""

    def get(self, request):
        since = timezone.now() - timedelta(days=7)
        events = LoginEvent.objects.filter(user=request.user)
        recent = events.filter(timestamp__gte=since).select_related(
            "user", "device", "evaluation", "evaluation__alert"
        )
        stats = recent.aggregate(
            logins_7d=Count("id", filter=Q(success=True)),
            failures_7d=Count("id", filter=Q(success=False)),
            unusual_7d=Count("id", filter=Q(
                evaluation__level__in=[RiskLevel.SUSPECT, RiskLevel.HAUT_RISQUE, RiskLevel.CRITIQUE]
            )),
        )
        stats["devices"] = request.user.devices.count()
        latest = list(recent.order_by("-timestamp")[:10])
        blocked = request.user.is_blocked()
        unusual = stats["unusual_7d"] > 0
        status_value = "danger" if blocked else "high" if unusual else "ok"
        notices = []
        if blocked:
            notices.append({
                "title": "Compte temporairement bloqué",
                "text": f"Le blocage prend fin le {request.user.blocked_until:%d/%m/%Y à %H:%M} UTC.",
                "tone": "danger",
            })
        if unusual:
            notices.append({
                "title": "Connexion inhabituelle détectée",
                "text": "Consultez vos connexions récentes et signalez celles que vous ne reconnaissez pas.",
                "tone": "warn",
                "link": "connexions-perso",
            })

        serialized_events = []
        for event in latest:
            evaluation = getattr(event, "evaluation", None)
            level = evaluation.level if evaluation else None
            serialized_events.append({
                **LoginEventSerializer(event).data,
                "tone": "danger" if level == RiskLevel.HAUT_RISQUE else "warn" if level else "ok",
                "outcome": "Connexion réussie" if event.success else "Échec de connexion",
                "place": ", ".join(part for part in (event.city, event.country) if part) or "Lieu inconnu",
                "device": (f"{event.device.device_type} · {event.device.os} · {event.device.browser}"
                           if event.device else "Appareil inconnu"),
                "level_label": level or "NORMAL",
            })

        return Response({
            "status": status_value,
            "profile_type_label": request.user.get_work_profile_display(),
            "stats": stats,
            "notices": notices,
            "recent_events": serialized_events,
        })


class LogoutView(APIView):
    """Déconnexion : le jeton de renouvellement est mis sur liste noire (inutilisable ensuite)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response({"detail": "Le jeton de renouvellement est requis."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            RefreshToken(refresh).blacklist()
        except TokenError:
            return Response({"detail": "Jeton invalide ou déjà révoqué."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    queryset = Notification.objects.select_related("event")

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    @action(detail=False, methods=["get"])
    def unread(self, request):
        notifications = self.get_queryset()
        return Response({
            "unread": notifications.filter(read_at__isnull=True).count(),
            "pending": notifications.filter(needs_response=True, response="").count(),
        })

    @action(detail=True, methods=["post"], url_path="read")
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=["post"], url_path="read_all")
    def read_all(self, request):
        self.get_queryset().filter(read_at__isnull=True).update(read_at=timezone.now())
        return Response({"detail": "Notifications marquées comme lues."})

    @action(detail=True, methods=["post"])
    def respond(self, request, pk=None):
        notification = self.get_object()
        response_value = request.data.get("response")
        if response_value not in Notification.Response.values:
            return Response({"response": ["Valeur attendue : CONFIRMEE ou CONTESTEE."]},
                            status=status.HTTP_400_BAD_REQUEST)
        if not notification.needs_response:
            return Response({"detail": "Cette notification ne demande pas de réponse."},
                            status=status.HTTP_400_BAD_REQUEST)
        if notification.response:
            return Response({"detail": "Une réponse a déjà été enregistrée."},
                            status=status.HTTP_409_CONFLICT)
        notification.response = response_value
        notification.response_at = timezone.now()
        notification.read_at = notification.read_at or notification.response_at
        notification.save(update_fields=["response", "response_at", "read_at"])
        if response_value == Notification.Response.CONTESTEE and notification.event_id:
            log_action(request.user, "CONTESTER_CONNEXION", str(notification.event_id))
        else:
            log_action(request.user, "CONFIRMER_CONNEXION", str(notification.event_id or ""))
        return Response({
            "detail": "Connexion signalée à l'équipe de sécurité." if response_value == "CONTESTEE"
                      else "Connexion confirmée.",
            "notification": NotificationSerializer(notification).data,
        })


class PasswordRulesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "rules": [
                "Utilisez au moins 8 caractères.",
                "Évitez les mots de passe courants ou composés uniquement de chiffres.",
                "Choisissez un mot de passe qui ne ressemble pas à vos informations personnelles.",
            ]
        })


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        old_password = request.data.get("old_password")
        new_password = request.data.get("new_password")
        if not isinstance(old_password, str) or not isinstance(new_password, str) or not new_password:
            return Response({"detail": "Les mots de passe actuel et nouveau sont requis."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not request.user.check_password(old_password):
            return Response({"old_password": ["Le mot de passe actuel est incorrect."]},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new_password, user=request.user)
        except DjangoValidationError as exc:
            return Response({"new_password": exc.messages}, status=status.HTTP_400_BAD_REQUEST)
        request.user.set_password(new_password)
        request.user.save(update_fields=["password"])
        log_action(request.user, "CHANGER_MOT_DE_PASSE", request.user.email)
        _notify_user(request.user, Notification.Kind.MOT_DE_PASSE, "Mot de passe modifié",
                     "Le mot de passe de votre compte a été modifié.")
        return Response(status=status.HTTP_204_NO_CONTENT)


class HealthView(APIView):
    """Vérifie que l'API répond et que la base de données est joignable (accès public)."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def get(self, request):
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
            database = "ok"
        except Exception:
            database = "erreur"
        code = status.HTTP_200_OK if database == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
        return Response({"status": "ok" if database == "ok" else "degrade", "database": database}, status=code)


class UserFilter(filters.FilterSet):
    blocked = filters.BooleanFilter(method="filter_blocked")

    class Meta:
        model = User
        fields = ["role", "profile_type", "is_active"]

    def filter_blocked(self, queryset, name, value):
        if value:
            return queryset.filter(blocked_until__gt=timezone.now())
        return queryset


class UserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin,
                  mixins.DestroyModelMixin, viewsets.GenericViewSet):
    """Gestion des comptes, réservée aux administrateurs."""
    queryset = User.objects.annotate(
        events_count=Count("login_events", distinct=True),
        risky_count=Count(
            "login_events",
            filter=Q(login_events__evaluation__level__in=[
                RiskLevel.SUSPECT, RiskLevel.HAUT_RISQUE, RiskLevel.CRITIQUE,
            ]),
            distinct=True,
        ),
    ).order_by("id")
    serializer_class = UserSerializer
    permission_classes = [IsAdminRole]
    filterset_class = UserFilter
    search_fields = ["email", "full_name"]     # ex. /api/users/?search=fotso
    ordering_fields = ["email", "last_login", "events_count", "risky_count"]
    ordering = ["id"]
    http_method_names = ["get", "patch", "post", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action == "create":
            return UserCreateSerializer
        if self.action == "partial_update":
            return UserUpdateSerializer
        return UserSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        log_action(request.user, "CREER_COMPTE", user.email)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        """PATCH : modifier le rôle et/ou l'état actif d'un compte."""
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response({"detail": "Vous ne pouvez pas modifier votre propre compte ici."},
                            status=status.HTTP_400_BAD_REQUEST)
        serializer = UserUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        before = {"role": user.role, "is_active": user.is_active}
        serializer.save()
        log_action(request.user, "MODIFIER_COMPTE", user.email, {"avant": before, "apres": serializer.data})
        return Response(UserSerializer(user).data)

    def destroy(self, request, *args, **kwargs):
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response({"detail": "Vous ne pouvez pas supprimer votre propre compte."},
                            status=status.HTTP_400_BAD_REQUEST)
        email = user.email
        log_action(request.user, "SUPPRIMER_COMPTE", email)
        user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=["get"])
    def activity(self, request, pk=None):
        user = self.get_object()
        events = LoginEvent.objects.filter(user=user)
        stats = events.aggregate(
            total=Count("id"),
            failures=Count("id", filter=Q(success=False)),
            first=Min("timestamp"),
            last=Max("timestamp"),
        )
        by_level = {level: 0 for level, _ in RiskLevel.choices}
        by_level.update({
            row["evaluation__level"]: row["count"]
            for row in events.values("evaluation__level").annotate(count=Count("id"))
            if row["evaluation__level"]
        })
        hours_counts = {
            row["hour"]: row["count"]
            for row in events.filter(success=True).annotate(hour=ExtractHour("timestamp"))
            .values("hour").annotate(count=Count("id"))
        }
        profile = UserProfile.objects.filter(user=user).first()
        usual_hours = profile.usual_hours if profile and profile.usual_hours else [
            hour for hour, count in hours_counts.items() if count
        ]
        devices = [
            {"id": device.id, "device_type": device.device_type, "os": device.os,
             "browser": device.browser, "first_seen": device.first_seen}
            for device in user.devices.order_by("-first_seen")
        ]
        return Response({
            "user": UserSerializer(user).data,
            "profile": {"usual_hours": usual_hours},
            "stats": {**stats, "by_level": by_level},
            "devices": devices,
            "hours": [{"hour": hour, "count": hours_counts.get(hour, 0)} for hour in range(24)],
        })

    @action(detail=True, methods=["post"])
    def block(self, request, pk=None):
        """Bloque un compte pour N minutes (corps JSON : {"minutes": 60}). Effet immédiat."""
        user = self.get_object()
        if user.pk == request.user.pk:
            return Response({"detail": "Vous ne pouvez pas bloquer votre propre compte."},
                            status=status.HTTP_400_BAD_REQUEST)
        try:
            minutes = int(request.data.get("minutes", 60))
        except (TypeError, ValueError):
            return Response({"detail": "« minutes » doit être un nombre entier."}, status=status.HTTP_400_BAD_REQUEST)
        if not 1 <= minutes <= 60 * 24 * 30:  # entre 1 minute et 30 jours
            return Response({"detail": "La durée doit être comprise entre 1 minute et 30 jours."},
                            status=status.HTTP_400_BAD_REQUEST)
        user.blocked_until = timezone.now() + timedelta(minutes=minutes)
        user.save(update_fields=["blocked_until"])
        log_action(request.user, "BLOQUER_COMPTE", user.email, {"minutes": minutes})
        notify_account_blocked(user, minutes, "une décision de sécurité de l'administrateur")
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=["post"])
    def unblock(self, request, pk=None):
        """Débloque un compte immédiatement."""
        user = self.get_object()
        user.blocked_until = None
        user.two_factor_required = True
        user.save(update_fields=["blocked_until", "two_factor_required"])
        log_action(request.user, "DEBLOQUER_COMPTE", user.email)
        notify_account_unblocked(user)
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=["post"])
    def unlock(self, request, pk=None):
        user = self.get_object()
        reason = request.data.get("reason")
        if not isinstance(reason, str) or len(reason.strip()) < 5 or len(reason) > 1000:
            return Response(
                {"reason": ["Une justification d'au moins 5 caractères est obligatoire."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        deleted, _ = ProgressiveLockout.objects.filter(user=user).delete()
        log_action(
            request.user, "DEVERROUILLER_SOURCES", user.email,
            {"reason": reason.strip(), "sources_deverrouillees": deleted},
        )
        return Response(UserSerializer(user).data)