from django.urls import path

from .views import (
    ActivateModelView,
    ActiveModelView,
    ConfigView,
    DetectionListDetailView,
    DetectionListsView,
    FeaturesView,
    ImportView,
    ModelsView,
    RescoreView,
    RulesView,
    TrainModelView,
)

urlpatterns = [
    path("detection/rules/", RulesView.as_view(), name="detection-rules"),
    path("detection/rules/<int:pk>/", RulesView.as_view(), name="detection-rule-detail"),
    path("detection/config/", ConfigView.as_view(), name="detection-config"),
    path("detection/lists/", DetectionListsView.as_view(), name="detection-lists"),
    path("detection/lists/<int:pk>/", DetectionListDetailView.as_view(), name="detection-list-detail"),
    path("detection/models/", ModelsView.as_view(), name="detection-models"),
    path("detection/models/train/", TrainModelView.as_view(), name="detection-model-train"),
    path("detection/models/<int:pk>/activate/", ActivateModelView.as_view(), name="detection-model-activate"),
    path("detection/features/", FeaturesView.as_view(), name="detection-features"),
    path("detection/import/", ImportView.as_view(), name="detection-import"),
    path("detection/rescore/", RescoreView.as_view(), name="detection-rescore"),
    path("ml/model/", ActiveModelView.as_view(), name="ml-model"),
]
