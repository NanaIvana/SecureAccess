# Active le blocage temporaire de 15 minutes pour les décisions critiques, comme prévu au Sprint 2.
from django.db import migrations, models


def enable_critical_block(apps, schema_editor):
    Config = apps.get_model("detection", "DetectionConfig")
    Config.objects.filter(pk=1).update(auto_block_critical=True, auto_block_minutes=15)


class Migration(migrations.Migration):
    dependencies = [("detection", "0004_seed_sprint2_rules")]
    operations = [
        migrations.AlterField(model_name="detectionconfig", name="auto_block_critical", field=models.BooleanField(default=True)),
        migrations.RunPython(enable_critical_block, migrations.RunPython.noop),
    ]
