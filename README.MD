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
   En développement, les liens de réinitialisation sont imprimés dans la console Django.
   Pour les envoyer par e-mail en production, configurez les paramètres SMTP et `FRONTEND_URL`
   dans le `.env` du backend. La clé `DJANGO_SECRET_KEY` doit rester stable : elle protège
   aussi les secrets TOTP chiffrés.
6. `python manage.py migrate`
7. `python manage.py createsuperuser`
8. Jeu de données synthétique : `python manage.py generate_dataset --reset`
9. Entraînement du modèle : `python manage.py train_model`
10. Évaluation des événements et alertes : `python manage.py score_events --reset`
11. Lancer le serveur : `python manage.py runserver` (admin : http://127.0.0.1:8000/admin/)

## Installation du frontend

Dans un second terminal : `cd secureaccess\frontend`, puis `npm install` et `npm run dev`.
Le fichier `frontend\.env` doit contenir uniquement les variables destinées au navigateur :

```env
VITE_API_URL=http://localhost:8000/api
VITE_SESSION_IDLE_MINUTES=15
```

Ne copiez pas les identifiants PostgreSQL, la clé Django ou les secrets de hachage dans le
fichier `.env` du frontend. Vite ne devrait jamais recevoir de secrets serveur.
Les origines locales `http://localhost:5173` et `http://127.0.0.1:5173` sont autorisées par
défaut dans `CORS_ALLOWED_ORIGINS`.

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
- `backend/apps/reports` : rapports de synthèse et état des mesures de protection

## Sprint 2 — frontend et alertes

La console React comporte une entrée latérale **Alertes** (`/console/alertes`) réservée à ADMIN.
La page permet de parcourir les statuts (à traiter, nouvelles, en cours, traitées, fausses alertes),
de filtrer par gravité, règle, compte et période, de consulter les détails et motifs, d'exporter en CSV
et de traiter les alertes. La fiche d'alerte expose les signaux retournés par le moteur, l'historique
récent, le traitement, le blocage temporaire du compte et l'ajout du pays observé à la liste de blocage.
Le compteur latéral est alimenté par `GET /api/alerts/counts/`.

Le client API React est centralisé dans `frontend/src/api/client.js` : jeton JWT, renouvellement
automatique, gestion de session expirée, messages d'erreur et téléchargements authentifiés.
Les routes console et espace client sont protégées par rôle dans `frontend/src/App.jsx`.
Le backend reste l'autorité pour les permissions : masquer un menu n'est jamais considéré comme
une mesure de sécurité.

### Lancement local (Windows PowerShell)

**Backend**
```powershell
cd backend
py -3.11 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
# Compléter .env avec une base PostgreSQL et deux secrets aléatoires distincts.
python -c "import secrets; print(secrets.token_urlsafe(50))"
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Dans un second terminal, après avoir préparé les données et un modèle actif :
```powershell
cd backend
.\venv\Scripts\Activate.ps1
python manage.py generate_dataset --reset
python manage.py train_model
python manage.py score_events --reset
python manage.py create_demo_accounts
```

**Frontend**
```powershell
cd frontend
Copy-Item .env.example .env
npm ci
npm run dev
```
Ouvrir `http://localhost:5173`. L'API doit répondre sur `http://localhost:8000/api/health/`.
La documentation interactive est disponible sur `http://localhost:8000/api/docs/`.

### Vérifications à faire avant la revue

1. `npm ci` puis `npm run build` dans `frontend/`.
2. `python manage.py check` et `python manage.py test` dans `backend/`.
3. Vérifier `/api/health/`, `/api/docs/`, puis se connecter avec un compte ADMIN.
4. Tester la liste d'alertes, les filtres de dates/statuts, le détail, le traitement, le blocage du compte
   et l'ajout du pays à la liste de blocage.
5. Vérifier avec un compte UTILISATEUR qu'un accès direct à `/console/alertes` est refusé par l'interface
   et que les endpoints ADMIN renvoient bien HTTP 403 côté serveur.

**Limites de validation de cette livraison :** le code Python a passé une vérification de syntaxe.
La construction React et les tests Django n'ont pas pu être exécutés dans cet environnement de travail
(dépendances npm interrompues et dépendances Django non installées dans l'environnement actif).
La validation finale doit donc être faite sur le poste de l'équipe avec PostgreSQL, les dépendances,
les migrations et un modèle de détection actif. Les données et modèles fournis sont synthétiques.

### Sécurité du dépôt

L'archive d'origine contenait un fichier `backend/.env` et un environnement virtuel local.
Ils ne sont pas inclus dans cette archive de livraison. Recréez votre propre `.env` à partir de
`backend/.env.example`. Si l'archive d'origine a été partagée, considérez les identifiants et clés
qu'elle contenait comme compromis et faites tourner les mots de passe PostgreSQL, `DJANGO_SECRET_KEY`
et `IP_HASH_SECRET`. Ne versionnez jamais `.env`, `venv/`, `node_modules/` ou des secrets.


## Sprint 2 — comptes scolaires et scénarios de connexion réels

En développement local uniquement, activez `DEMO_MODE=True` dans `backend/.env` et `VITE_DEMO_MODE=true` dans `frontend/.env` pour afficher les accès rapides, autoriser les en-têtes de scénario (pays/ville/heure) et utiliser l'API `/api/lab/attacks/`. Cette option doit rester désactivée en production. Créez les comptes de démonstration après le jeu de données et l'entraînement du modèle, pour conserver une référence de connexion normale séparée du jeu d'entraînement.

Après les migrations, créez les trois comptes scolaires :

```powershell
cd backend
python manage.py migrate
python manage.py create_demo_accounts
```

Les comptes sont `enseignant@demo.secureaccess.test`, `secretaire@demo.secureaccess.test` et `administration@demo.secureaccess.test`. Mot de passe de démonstration initial : `DemoSchool2026!`. Ils restent des comptes client (`UTILISATEUR`) avec un profil institutionnel distinct. Le compte `ADMIN` créé avec `createsuperuser` reste le compte de console. Changez ces mots de passe avant toute utilisation hors démonstration.

Le formulaire de connexion propose des accès rapides en développement. Les scénarios « normal » utilisent une empreinte de démonstration déjà connue. « Force brute · échecs » préremplit un mauvais mot de passe : soumettez-le trois fois, puis cliquez « Connexion après échecs » pour faire évaluer une connexion réussie après des échecs récents. Le mode test « Force brute » dans Ma sécurité rejoue six échecs réels et vérifie le verrouillage au 6e essai. « Nouvel appareil » renouvelle l'empreinte du navigateur. « Compte compromis » envoie des en-têtes de lieu/heure simulés, acceptés uniquement si `DEMO_MODE=True` et pour les comptes `.test`.

Dans l'espace client d'un compte `.test`, le panneau « Mode test de sécurité » appelle `POST /api/lab/attacks/` et rejoue les scénarios sur le vrai pipeline `POST /api/auth/login/`. La force brute effectue six échecs réels et peut verrouiller le couple compte/source.

La commande `python manage.py attack_suite` exécute une suite d'essais sur le vrai endpoint et affiche un tableau attaque → décision. Elle nécessite `DEMO_MODE=True` et annule les données temporaires à la fin.

Le champ `profile_type` distingue enseignant, secrétaire, étudiant, personnel et administration scolaire ; il est administré par le compte ADMIN. Les rôles techniques `ADMIN`, `RESPONSABLE` et `UTILISATEUR` continuent de contrôler les autorisations.


## Sprint 2 — sécurité des comptes, e-mails et géolocalisation

### E-mails de sécurité
En développement, `EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend` affiche les e-mails dans le terminal backend. Pour l'envoi réel, configurez dans `backend/.env` : `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` et `DEFAULT_FROM_EMAIL`. Utilisez un mot de passe d'application SMTP, jamais le mot de passe personnel. Les e-mails sont envoyés lors d'un blocage et d'un déblocage explicite. Un compte bloqué par une décision de sécurité doit aussi activer la double authentification avant son prochain accès.

### Localisation des connexions
La localisation réelle d'une IP publique nécessite une base GeoIP locale MaxMind GeoLite2 City. Définissez `GEOIP2_CITY_DB_PATH` vers le fichier `GeoLite2-City.mmdb` et installez `geoip2` (`pip install geoip2`). Les IP privées/localhost ne sont pas géolocalisables : l'application utilise alors la ville/pays de référence du compte et marque explicitement cette valeur comme solution de repli dans le détail de connexion, ou affiche « Localisation IP indisponible ». En mode démo, les en-têtes de simulation restent réservés aux comptes `.test`. Aucune IP brute n'est enregistrée ni transmise à un service tiers.

### Laboratoire d'attaques à l'écran de connexion
Le sélecteur « Laboratoire d'attaques » est affiché en développement avec `VITE_DEMO_MODE=true`. Il appelle `/api/lab/attacks/demo/`, qui exige `DJANGO_DEBUG=True` et `DEMO_MODE=True` côté backend et reste limité aux comptes `@demo.secureaccess.test`. Les événements sont conservés pour consultation dans Connexions/Alertes. Ne laissez jamais `DEMO_MODE=True` en production.

### Mise à jour
Après remplacement des fichiers, exécutez `python manage.py migrate`, `python manage.py check`, puis `python manage.py test`. Pour l'interface : `npm run build`.

## Configuration SMTP et GeoLite2

Pour activer les vrais e-mails de sécurité et la géolocalisation IP, suivre le guide [`docs/CONFIGURATION_EMAIL_GEOIP.md`](docs/CONFIGURATION_EMAIL_GEOIP.md). Le test SMTP est disponible avec `python manage.py send_test_email --to adresse@exemple.com`. La base MaxMind GeoLite2 City doit être téléchargée séparément et son chemin défini par `GEOIP2_CITY_DB_PATH` dans `backend/.env`.

## GeoLite2 IP geolocation verification

For actual public-IP geolocation, obtain the licensed free MaxMind GeoLite2 City database and place `GeoLite2-City.mmdb` in `backend/data/`. Then run from the backend virtual environment:

```powershell
pip install -r requirements.txt
python manage.py check_geoip --ip 1.1.1.1
```

Set `GEOIP2_CITY_DB_PATH` in `backend/.env` only if the database is stored elsewhere. Localhost/private IP addresses cannot be geolocated; those events intentionally display the account's registered city/country as `PROFILE_FALLBACK`. Behind a reverse proxy, set `GEOIP2_TRUSTED_PROXY_IPS` only to proxy IPs you control.
