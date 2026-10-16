from django.urls import path

from .views import ActiveModelView

urlpatterns = [path("ml/model/", ActiveModelView.as_view(), name="ml-model")]
