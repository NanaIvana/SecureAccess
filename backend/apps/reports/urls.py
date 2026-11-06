from django.urls import path

from .views import ProtectionView, ReportSummaryView

urlpatterns = [
    path("reports/summary/", ReportSummaryView.as_view(), name="report-summary"),
    path("protection/", ProtectionView.as_view(), name="protection"),
]
