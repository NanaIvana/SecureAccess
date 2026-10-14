# SecureAccess

Plateforme sécurisée de détection intelligente des connexions suspectes
(Master 2 Data Science, IUSJ). Stack : Django, Django REST Framework, PostgreSQL, React.

## Prérequis
Python 3.11+, PostgreSQL 17, Node.js LTS, Git.

## Installation du backend (Windows PowerShell)

1. Cloner le dépôt, puis : `cd secureaccess\backend`
2. Environnement virtuel :
   `python -m venv venv` puis `.\venv\Scripts\Activate.ps1`
3. Dépendances : `pip install -r requirements.txt`
4. Base de données : dans **SQL Shell (psql)**, connecté en `postgres` :
```sql
   CREATE DATABASE secureaccess;
   CREATE USER secureaccess_user WITH PASSWORD 'votre_mot_de_passe';
   ALTER DATABASE secureaccess OWNER TO secureaccess_user;
   \c secureaccess
   GRANT ALL ON SCHEMA public TO secureaccess_user;
```
5. Copier `.env.example` en `.env`, puis le remplir. Générer les deux clés avec :
   `python -c "import secrets; print(secrets.token_urlsafe(50))"`
6. `python manage.py migrate`
7. `python manage.py createsuperuser`
8. Jeu de données synthétique : `python manage.py generate_dataset --reset`
9. Entraînement du modèle : `python manage.py train_model`
10. Évaluation des événements et alertes : `python manage.py score_events --reset`
11. Lancer le serveur : `python manage.py runserver` (admin : http://127.0.0.1:8000/admin/)

Les comptes générés ont pour mot de passe de démonstration `Demo2026!`.
Le fichier `.env`, la base de données et le modèle entraîné restent locaux à chaque poste.

## Organisation de l'équipe
- Une branche par fonctionnalité : `feature/<sujet>` ; jamais de travail direct sur `main`.
- Avant de commencer : `git pull`. Petits commits, messages clairs, pull request relue par un autre membre.
- Ne jamais committer `.env`, `venv/`, les CSV générés ni les fichiers de modèle.

## Structure
- `backend/apps/accounts` : utilisateurs et rôles
- `backend/apps/events` : événements de connexion, génération du jeu de données
- `backend/apps/detection` : features, règles, modèle de Machine Learning, score
- `backend/apps/alerts` : alertes
- `backend/apps/dashboard` : indicateurs du tableau de bord
- `backend/apps/audit` : journal d'audit