# Mise en route et script de démonstration

## Lancer (2 terminaux)
Terminal 1 (backend, venv activé) :
    cd backend
    python manage.py runserver
Terminal 2 (frontend) :
    cd frontend
    python -m http.server 5173
Ouvrir http://localhost:5173 (le serveur doit tourner sur http://127.0.0.1:8000).

Comptes : votre compte ADMIN, et `responsable@secureaccess.test` (mot de passe de démo : voir README) pour montrer le rôle RESPONSABLE.

## Script (5 à 6 minutes)
1. **Synthèse** (ADMIN) : KPI, courbes, répartition des risques, comptes/pays les plus ciblés.
   Changer la période (7 / 30 / 90 jours).
2. **Simulateur** → « Connexion normale » : niveau *Normal*, aucune alerte.
3. **Simulateur** → « Force brute » : *Haut risque*, alerte créée, motifs affichés. Cliquer « Voir l'alerte ».
4. **Alerte** : lire les motifs, marquer « En cours » puis « Traitée » avec un commentaire ; « Bloquer le compte ».
5. **Administration** : le journal d'audit montre la simulation, le traitement et le blocage ; débloquer le compte.
6. **Modèle** : règles seules / modèle seul / hybride, matrice de confusion. Dire clairement : données simulées.
7. **Rôles** : se déconnecter, se connecter en RESPONSABLE : seule la Synthèse est visible ; l'API répond 403 sur le reste.
