# Conserve un User-Agent borné pour la détection des clients automatisés (sans données IP en clair).
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("events", "0002_notification")]
    operations = [migrations.AddField(model_name="loginevent", name="user_agent", field=models.CharField(blank=True, max_length=300))]
