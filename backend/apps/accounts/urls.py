"""
FICHIER : apps/accounts/urls.py

RÔLE
    Table de routage de l'app accounts : associe chaque adresse (URL) à la vue qui la traite.
    Toutes ces adresses sont préfixées par /api/ (voir config/urls.py).
"""
from django.urls import include, path
from rest_framework.routers import SimpleRouter
from rest_framework_simplejwt.views import TokenRefreshView

from . import views

# Le routeur génère automatiquement /users/, /users/{id}/, /users/{id}/block/, etc.
router = SimpleRouter()
router.register("users", views.UserViewSet, basename="user")

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("me/", views.MeView.as_view(), name="me"),
    path("health/", views.HealthView.as_view(), name="health"),
    path("", include(router.urls)),
]