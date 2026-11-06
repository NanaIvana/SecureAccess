# Ajoute le type de profil scolaire distinct du rôle technique de sécurité.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_user_two_factor_enabled_user_two_factor_required_and_more")]

    operations = [
        migrations.AddField(
            model_name="user",
            name="profile_type",
            field=models.CharField(
                choices=[("ENSEIGNANT", "Enseignant"), ("SECRETAIRE", "Secrétaire"),
                         ("ETUDIANT", "Étudiant"), ("PERSONNEL", "Personnel"),
                         ("ADMINISTRATION", "Administration scolaire")],
                default="PERSONNEL", max_length=20,
            ),
        ),
    ]
