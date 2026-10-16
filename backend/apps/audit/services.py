"""
FICHIER : apps/audit/services.py

RÔLE
    Petite fonction utilitaire pour écrire dans le journal d'audit : « qui a fait quoi,
    sur quelle cible, quand ». À appeler à chaque action administrative sensible
    (blocage d'un compte, changement de rôle, traitement d'une alerte...).

EXEMPLE
    log_action(request.user, "BLOQUER_COMPTE", "jean.fotso001@demo.secureaccess.test", {"minutes": 60})

UTILISÉ PAR : apps/accounts/views.py (et plus tard apps/alerts)
"""
from .models import AuditLog


def log_action(actor, action, target="", details=None):
    """Enregistre une ligne dans le journal d'audit (acteur facultatif)."""
    AuditLog.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        action=action,
        target=target,
        details=details or {},
    )