# Ajoute les règles expertes Sprint 2 au catalogue administrable.
from django.db import migrations


def seed_rules(apps, schema_editor):
    Rule = apps.get_model("detection", "DetectionRule")
    rows = [
        ("PASSWORD_SPRAYING", "Password spraying", "Une source tente plusieurs comptes en 24 heures.", 85, 10, "comptes en 24 h", 90),
        ("FORCE_BRUTE_LENTE", "Force brute lente", "Échecs répétés sur un compte depuis plusieurs sources en 24 heures.", 85, 10, "échecs en 24 h", 100),
        ("ROBOT", "Client automatisé / robot", "User-Agent d'outil ou cadence de tentatives automatisée.", 80, 1, "signal automatisé", 110),
    ]
    for key, name, description, points, threshold, label, position in rows:
        Rule.objects.update_or_create(key=key, defaults={
            "name": name, "description": description, "points": points,
            "threshold": threshold, "threshold_label": label, "is_enabled": True,
            "is_extension": True, "position": position,
        })


class Migration(migrations.Migration):
    dependencies = [("detection", "0003_progressivelockout")]
    operations = [migrations.RunPython(seed_rules, migrations.RunPython.noop)]
