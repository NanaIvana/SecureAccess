# Configuration des e-mails réels et de la géolocalisation IP

Cette configuration est destinée au développement local. Ne publiez jamais le fichier `.env`, un mot de passe d'application ou une clé MaxMind.

## 1. Envoyer de vrais e-mails avec Gmail SMTP

SecureAccess envoie ses notifications depuis Django avec SMTP. L'intégration Gmail de ChatGPT n'est pas utilisée par l'application.

1. Utilisez une adresse Gmail dédiée comme expéditeur (ou votre adresse de test).
2. Activez la validation en deux étapes sur le compte Google.
3. Créez un **mot de passe d'application Google** depuis la sécurité du compte Google. Copiez les 16 caractères fournis. Le mot de passe Gmail normal ne fonctionne pas.
4. Copiez `backend/.env.example` vers `backend/.env` si ce fichier n'existe pas, puis renseignez au minimum :

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=votre-adresse@gmail.com
EMAIL_HOST_PASSWORD=mot-de-passe-application-16-caracteres
DEFAULT_FROM_EMAIL=SecureAccess <votre-adresse@gmail.com>
EMAIL_TIMEOUT=15
```

Ne mettez pas les chevrons autour de l'adresse réelle dans `EMAIL_HOST_USER`. Pour `EMAIL_HOST_PASSWORD`, collez le mot de passe d'application sans espaces. N'ajoutez pas de guillemets sauf si votre valeur en a besoin.

5. Redémarrez Django, puis testez l'envoi réel :

```powershell
python manage.py send_test_email --to votre-adresse-de-reception@gmail.com
```

6. Vérifiez la boîte de réception et les courriers indésirables. Le message « accepté par SMTP » signifie que le serveur SMTP a accepté l'envoi, pas que le fournisseur du destinataire garantit la livraison.

Les notifications de blocage et de déblocage réutilisent le même SMTP. Les erreurs SMTP sont consignées dans le terminal backend et ne font pas échouer la connexion ou l'action de sécurité.

## 2. Géolocalisation réelle par IP avec GeoLite2

SecureAccess utilise la base locale **GeoLite2 City** de MaxMind. L'adresse IP n'est pas envoyée à un service externe. Le résultat IP est une estimation de ville/région, jamais une adresse personnelle ni une position GPS exacte.

### Installer la base (obligatoire)

1. Créez un compte gratuit MaxMind : https://www.maxmind.com/en/geolite2/signup
2. Téléchargez **GeoLite2 City** au format `.mmdb` depuis votre compte MaxMind. Le fichier doit s'appeler `GeoLite2-City.mmdb`.
3. Dans votre projet, créez `backend/data/` et placez-y ce fichier. Le chemin par défaut est alors automatiquement détecté : `backend/data/GeoLite2-City.mmdb`.
4. Si vous le stockez ailleurs, ajoutez dans `backend/.env` le chemin absolu Windows, par exemple :

```dotenv
GEOIP2_CITY_DB_PATH=C:/Users/LENOVO/Documents/secureaccess/backend/data/GeoLite2-City.mmdb
```

5. Vérifiez que `geoip2` est installé (`pip install -r requirements.txt`), puis lancez une vérification avec une IP publique réelle :

```powershell
python manage.py check_geoip --ip 1.1.1.1
```

La commande doit afficher « Base GeoLite2 City valide et recherche exécutée » et un lieu estimé. `1.1.1.1` sert uniquement à vérifier la lecture de la base; pour votre test applicatif, utilisez une IP publique du client.

6. Redémarrez Django et effectuez une nouvelle connexion. Ouvrez **Connexions** : `location_source` doit être `IP_GEOIP` quand la recherche aboutit.

### Proxy / hébergement public

Par défaut, SecureAccess utilise `REMOTE_ADDR`. Si vous déployez derrière un reverse proxy que vous contrôlez, configurez-le pour transmettre `X-Forwarded-For`, puis ajoutez uniquement l'adresse IP du proxy dans `backend/.env` :

```dotenv
GEOIP2_TRUSTED_PROXY_IPS=127.0.0.1
```

Remplacez cette valeur par l'IP réelle du proxy. Ne mettez pas les IP des visiteurs dans cette variable et ne faites jamais confiance à `X-Forwarded-For` sans proxy explicitement approuvé.

### Limites importantes en local

- `127.0.0.1`, `::1`, `192.168.x.x`, `10.x.x.x` et autres IP privées ne sont pas géolocalisables par GeoLite2. En local, SecureAccess affiche alors la ville de référence du compte avec la source `PROFILE_FALLBACK`.
- Si GeoLite2 ne contient pas la ville mais reconnaît le pays, l'interface affiche « Ville non déterminée, [pays] » au lieu d'un lieu vide.
- Pour tester une vraie géolocalisation du visiteur, il faut que le navigateur se connecte à un backend accessible publiquement et que le backend voie l'IP publique du visiteur (ou l'IP transmise par un proxy de confiance).
- Les en-têtes de ville/pays/heure simulés en mode démo ne sont pas une localisation réelle.

## 3. Débloquer un compte

Un administrateur peut débloquer le compte depuis **Utilisateurs** (bouton « Débloquer » sur la ligne) ou depuis la fiche d'une alerte/du compte. Le déblocage est journalisé. Par sécurité, le compte devra effectuer une double authentification lors de sa prochaine connexion.

## 4. Connexion normale des comptes de démonstration

Dans le backend, avec `DJANGO_DEBUG=True` et `DEMO_MODE=True` :

```powershell
python manage.py create_demo_accounts
```

Identifiants par défaut :

- `enseignant@demo.secureaccess.test`
- `secretaire@demo.secureaccess.test`
- `administration@demo.secureaccess.test`
- Mot de passe : `DemoSchool2026!`

La commande réinitialise les comptes de démonstration, leurs blocages et leur état 2FA. N'exécutez-la pas si vous souhaitez conserver les modifications de ces comptes de test.
