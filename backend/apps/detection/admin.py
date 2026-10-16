from django.contrib import admin

from .models import MLModel, RiskEvaluation, UserProfile


@admin.register(RiskEvaluation)
class RiskEvaluationAdmin(admin.ModelAdmin):
    list_display = ("id", "event", "level", "score", "model_version")
    list_filter = ("level",)
    raw_id_fields = ("event",)


admin.site.register(MLModel)
admin.site.register(UserProfile)
