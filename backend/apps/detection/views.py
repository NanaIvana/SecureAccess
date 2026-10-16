"""
FICHIER : apps/detection/views.py

RÔLE
    GET /api/ml/model/   modèle actif : version, algorithme, seuils et métriques d'évaluation
                         (règles seules / modèle seul / hybride) -- réservé aux administrateurs.
"""
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminRole

from .models import MLModel


class ActiveModelView(APIView):
    permission_classes = [IsAdminRole]

    @extend_schema(responses=OpenApiTypes.OBJECT)
    def get(self, request):
        model = MLModel.objects.filter(is_active=True).first()
        if model is None:
            return Response({"detail": "Aucun modèle actif. Lancez : python manage.py train_model"}, status=404)
        return Response({
            "version": model.version, "algorithm": model.algorithm, "trained_at": model.trained_at,
            "thresholds": model.metrics.get("seuils"), "metrics": model.metrics,
        })
