"""
FICHIER : apps/audit/urls.py

RÔLE
    Routage de l'app audit : GET /api/audit/ et GET /api/audit/{id}/ (préfixe /api/ dans config/urls.py).
"""
from rest_framework.routers import SimpleRouter

from .views import AuditLogViewSet

router = SimpleRouter()
router.register("audit", AuditLogViewSet, basename="audit")

urlpatterns = router.urls