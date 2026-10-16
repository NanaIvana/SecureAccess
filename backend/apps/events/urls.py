from rest_framework.routers import SimpleRouter

from .views import EventViewSet

router = SimpleRouter()
router.register("events", EventViewSet, basename="event")

urlpatterns = router.urls
