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
router.register("notifications", views.NotificationViewSet, basename="notification")

urlpatterns = [
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("lab/attacks/", views.LabAttackView.as_view(), name="lab-attacks"),
    path("lab/attacks/demo/", views.PublicLabAttackView.as_view(), name="lab-attacks-demo"),
    path("auth/refresh/", TokenRefreshView.as_view(), name="token_refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/password-rules/", views.PasswordRulesView.as_view(), name="password-rules"),
    path("auth/change-password/", views.ChangePasswordView.as_view(), name="change-password"),
    path("auth/password-reset/", views.PasswordResetView.as_view(), name="password-reset"),
    path("auth/password-reset/confirm/", views.PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("auth/2fa/", views.TwoFactorSetupView.as_view(), name="two-factor-setup"),
    path("auth/2fa/confirm/", views.TwoFactorConfirmView.as_view(), name="two-factor-confirm"),
    path("auth/2fa/disable/", views.TwoFactorDisableView.as_view(), name="two-factor-disable"),
    path("auth/2fa/setup-login/", views.TwoFactorLoginSetupView.as_view(), name="two-factor-login-setup"),
    path("auth/2fa/verify/", views.TwoFactorVerifyView.as_view(), name="two-factor-verify"),
    path("me/", views.MeView.as_view(), name="me"),
    path("me/security/", views.MeSecurityView.as_view(), name="me-security"),
    path("health/", views.HealthView.as_view(), name="health"),
    path("", include(router.urls)),
]