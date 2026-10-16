from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/kpis/", views.KpisView.as_view(), name="dashboard-kpis"),
    path("dashboard/timeline/", views.TimelineView.as_view(), name="dashboard-timeline"),
    path("dashboard/risk-distribution/", views.RiskDistributionView.as_view(), name="dashboard-risk"),
    path("dashboard/top-targets/", views.TopTargetsView.as_view(), name="dashboard-targets"),
]
