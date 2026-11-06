# Mise en route et script de démonstration Sprint 2

## Préparation (une seule fois)

1. Dans `backend/.env`, configurez PostgreSQL et mettez `DEMO_MODE=True` pour la démonstration locale.
2. Dans `frontend/.env`, mettez `VITE_API_URL=http://localhost:8000/api` et `VITE_DEMO_MODE=true`.
3. Depuis `backend/` :

```powershell
python manage.py migrate
python manage.py createsuperuser
python manage.py generate_dataset --reset
python manage.py train_model
python manage.py score_events --reset
python manage.py create_demo_accounts
```

Le compte ADMIN créé par `createsuperuser` sert à la console. Les trois comptes de démonstration sont des comptes clients :

| Profil | Identifiant | Mot de passe initial |
|---|---|---|
| Enseignant | `enseignant@demo.secureaccess.test` | `DemoSchool2026!` |
| Secrétariat | `secretaire@demo.secureaccess.test` | `DemoSchool2026!` |
| Administration scolaire | `administration@demo.secureaccess.test` | `DemoSchool2026!` |

## Lancement (2 terminaux)

Terminal 1 :

```powershell
cd backend
.\venv\Scripts\Activate.ps1
python manage.py runserver
```

Terminal 2 :

```powershell
cd frontend
npm run dev
```

Ouvrir `http://localhost:5173`.

## Démonstration (6 à 8 minutes)

1. Se connecter à la console avec le compte ADMIN : lire les KPI, les courbes, les comptes les plus ciblés et les alertes ouvertes. Les périodes disponibles sont 7, 30, 90, 120 et 180 jours.
2. Se déconnecter puis ouvrir l'accès rapide « Enseignant · normal » sur la page de connexion. Vérifier la redirection vers `/espace` et l'enregistrement d'une connexion LIVE.
3. Se déconnecter, choisir « Nouvel appareil », puis se connecter : l'empreinte navigateur change et l'événement est réévalué.
4. Choisir « Force brute · échecs » : soumettre le mauvais mot de passe trois fois, puis cliquer « Connexion après échecs » pour tester une authentification réelle avec un historique d'échecs récent (alerte ou vérification supplémentaire possible).
5. Dans « Ma sécurité », saisir le mot de passe du compte de test et lancer « Force brute » : six échecs sont rejoués sur le vrai endpoint ; le sixième doit être verrouillé. Le tableau affiche code HTTP, décision, niveau, score et motifs.
6. Pour le scénario « Compte compromis », les en-têtes Paris / 03:00 sont utilisés uniquement pour les comptes `.test` lorsque `DEMO_MODE=True`.
7. Revenir dans la console ADMIN : ouvrir les alertes, lire les motifs, traiter ou marquer une fausse alerte, bloquer/débloquer un compte et vérifier le journal d'audit.
8. Lancer `python manage.py attack_suite` depuis `backend/` pour obtenir le tableau automatisé « attaque → décision » (9 scénarios). Les données temporaires de cette suite sont annulées à la fin.

## Sécurité et limites

- `DEMO_MODE` doit rester désactivé en production. Les comptes `.test` et leurs mots de passe sont réservés à la démonstration.
- Le modèle doit être entraîné et activé pour obtenir des scores ML. Sans modèle actif, les tentatives LIVE sont journalisées mais ne reçoivent pas de score hybride.
- Les événements du jeu de données synthétique sont marqués `DATASET` ; les tentatives du formulaire de connexion sont marquées `LIVE`.
