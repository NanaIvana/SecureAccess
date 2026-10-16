"""
FICHIER : config/urls.py

RÔLE
    Table de routage principale du projet : point de départ de toutes les adresses.
      /admin/        site d'administration Django
      /api/...       l'API REST (accounts, audit, events, alerts, dashboard, ml)
      /api/schema/   description OpenAPI de l'API (fichier lisible par les machines)
      /api/docs/     documentation interactive (Swagger) : on peut y tester l'API
"""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.accounts.urls")),
    path("api/", include("apps.audit.urls")),
    path("api/", include("apps.events.urls")),
    path("api/", include("apps.alerts.urls")),
    path("api/", include("apps.dashboard.urls")),
    path("api/", include("apps.detection.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]
