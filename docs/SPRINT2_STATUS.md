# SecureAccess — couverture Sprint 2

| Élément | Implémentation dans cette livraison |
|---|---|
| T-10 / T-11 — routage, JWT et espaces | Conservation du routage React, des gardes de rôle et de la redirection selon le rôle technique. |
| T-12 — mode test côté client | Panneau « Mode test de sécurité » dans « Ma sécurité » ; scénarios rejoués sur le vrai endpoint `/api/auth/login/`. |
| Profils institutionnels | Champ `profile_type` (enseignant, secrétaire, étudiant, personnel, administration scolaire), administrable par ADMIN et visible dans les comptes. |
| Comptes de démonstration | Commande `create_demo_accounts` créant trois comptes `.test`, un appareil connu et un profil horaire de référence. Le compte ADMIN reste séparé. |
| T-30 — journalisation LIVE | Événements LIVE pour connexions acceptées, mots de passe incorrects, comptes bloqués, verrouillages progressifs et 429 associés à un compte connu. User-Agent borné et IP pseudonymisée. |
| T-31 — évaluation et décision | Évaluation des connexions traitées par le endpoint ; décisions `ALLOW`, `ALLOW_WITH_ALERT`, `STEP_UP`, `REFUSE`. Le blocage automatique de 15 minutes est activé pour un événement LIVE réussi classé critique. |
| T-32 — API de laboratoire | `POST /api/lab/attacks/`, réservé à `DEMO_MODE=True` et aux comptes `.test` connectés. Les scénarios passent par `LoginView` ; aucun mot de passe n'est stocké dans les événements. |
| T-40 — verrouillage progressif | Après cinq échecs sur le même couple compte/source, le sixième essai est verrouillé ; durées progressives 5, 15 puis 60 minutes. |
| T-41 — limitation de débit | Limites distinctes : 60 requêtes/minute par IP et 20/minute par couple IP/identifiant. Les 429 sont journalisés pour les comptes connus sans lancer le scoring coûteux. |
| T-50 — signaux R8/R9/R10 | R8 password spraying (10 comptes distincts / 24 h), R9 force brute lente (10 échecs / 24 h et 3 sources), R10 client automatisé / cadence rapide. |
| T-51 — suite automatisée | `python manage.py attack_suite` rejoue neuf scénarios via le endpoint réel et affiche les codes HTTP, niveaux et décisions. Les données temporaires sont annulées à la fin. |
| Alertes | Compteurs par statut calculés indépendamment de l'onglet actif et rafraîchis toutes les 15 secondes ; test couvrant 4 nouvelles + 1 en cours = 5 à traiter. |
| Navigation / tableau de bord | Simulateur retiré du menu latéral ; navigation latérale défilable ; périodes 7, 30, 90, 120 et 180 jours ; graphiques de risque, horaire et taux de réussite/échec. |

## Conditions de démonstration

- `backend/.env` : `DEMO_MODE=True` en local seulement.
- `frontend/.env` : `VITE_DEMO_MODE=true` pour afficher les raccourcis de test dans Vite.
- Le modèle de détection doit être entraîné et activé avant les scénarios qui attendent un score ML. Sans modèle actif, les événements LIVE restent journalisés mais l'évaluation hybride n'est pas disponible.
- Les en-têtes de lieu/heure sont acceptés uniquement pour les comptes `.test` lorsque `DEMO_MODE=True`. Ne pas activer ce mode en production.

## Validation technique de cette archive

La compilation syntaxique Python, l'analyse syntaxique JS/JSX et des tests unitaires isolés des signaux R8/R9/R10 ont réussi. La suite Django et le build Vite n'ont pas pu être exécutés dans l'environnement de préparation : Django n'y était pas installé et l'installation npm a expiré. Exécuter `python manage.py test`, `python manage.py check` et `npm run build` sur l'environnement de l'équipe avant la démonstration.

## Correctifs et extensions — 6 novembre 2026

| Sujet | Mise à jour |
|---|---|
| Cohérence des compteurs d'alertes | `/api/alerts/counts/` ignore le statut de l'onglet actif mais respecte les filtres de recherche communs. Il retourne également `open` et `total`. Le badge latéral utilise le total `open`, identique à « À traiter ». Le filtre `open=true` reste disponible pour le badge global et les tests existants. |
| Localisation LIVE | Chaque nouvel événement LIVE tente une géolocalisation locale GeoLite2 pour une IP publique. Pour localhost/IP privée, la ville du profil est utilisée et la source est explicitement identifiée (`PROFILE_FALLBACK`). Les lieux de démo sont marqués `DEMO_SIMULATED`. Migration `events.0004_loginevent_location_source`. |
| Notifications e-mail | E-mail + notification interne au blocage automatique critique et au blocage manuel par l'administrateur ; e-mail de rétablissement au déblocage explicite ou au premier retour après expiration du blocage. En SMTP console, les e-mails apparaissent dans le terminal backend. |
| Double authentification après blocage | Tout blocage de compte active `two_factor_required`. Après déblocage, le compte doit configurer ou utiliser la 2FA avant de recevoir une session. |
| Laboratoire depuis la page de connexion | Nouveau sélecteur pour normal, force brute, password spraying, force brute lente, nouvel appareil, nouveau pays, horaire inhabituel, robot et voyage impossible. Résultats HTTP/décision affichés immédiatement ; les événements sont conservés pour Connexions et Alertes. Endpoint public restreint à `DEBUG=True` + `DEMO_MODE=True` et aux comptes `@demo.secureaccess.test`. |
| Suite `attack_suite` | Le client de test envoie désormais `HTTP_HOST=localhost` pour éviter `DisallowedHost: testserver` sur les configurations locales qui n'autorisent pas `testserver`. |

### Préparation supplémentaire requise

1. Appliquer la migration : `python manage.py migrate`.
2. Pour une localisation IP publique précise, installer `geoip2` (ajouté à `requirements.txt`), télécharger la base MaxMind GeoLite2 City selon les conditions de licence MaxMind, puis définir `GEOIP2_CITY_DB_PATH` dans `backend/.env`. Sans cette base, les IP privées/locales affichent la ville de référence du profil ; l'interface l'indique explicitement et ne prétend pas qu'il s'agit d'une géolocalisation IP.
3. Pour tester les e-mails sans SMTP, conserver `django.core.mail.backends.console.EmailBackend` et lire les messages dans le terminal backend. Pour envoyer réellement, configurer un serveur SMTP dans `backend/.env`.
4. Le laboratoire public nécessite `DJANGO_DEBUG=True`, `DEMO_MODE=True` côté backend et `VITE_DEMO_MODE=true` côté frontend. Ne jamais activer DEBUG/DEMO_MODE en production.

### Validation de cette révision

Vérifications effectuées dans l'environnement de préparation : compilation syntaxique de tous les fichiers Python, analyse syntaxique TS/JSX des fichiers React modifiés. Les tests Django et le build Vite ne sont pas déclarés réussis : Django et `node_modules` ne sont pas installés dans cet environnement. Exécuter les commandes ci-dessous dans l'environnement local du projet avant de considérer cette révision comme validée :

```powershell
cd backend
python manage.py migrate
python manage.py check
python manage.py test
python manage.py attack_suite

cd ..\frontend
npm run build
```
