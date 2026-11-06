from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0003_loginevent_user_agent")]
    operations = [migrations.AddField(
        model_name="loginevent", name="location_source",
        field=models.CharField(choices=[("IP_GEOIP", "Géolocalisation IP locale"), ("PROFILE_FALLBACK", "Ville de référence du compte"), ("DEMO_SIMULATED", "Lieu simulé en démonstration"), ("UNKNOWN", "Localisation indisponible")], default="UNKNOWN", max_length=20),
    )]
