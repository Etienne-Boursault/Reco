# Homeserver Matrix (Conduit) sur le Pi — notifications Reco

Pack clé en main pour héberger un **homeserver Matrix léger** sur le Raspberry
Pi. Le bot y poste les notifs (nouveaux épisodes, signalements) et tu les
reçois dans **Element** (mobile/desktop). Léger : Conduit ≈ un binaire Rust,
~50–150 Mo RAM, quelques dizaines de Mo de disque pour cet usage.

## 0. Prérequis (à lire avant tout)

- **Docker + Docker Compose** sur le Pi, et **jq** (`sudo apt install jq`).
- Un **sous-domaine** (ex. `matrix.unebonnere.co`) avec un enregistrement
  **A/AAAA** vers l'**IP publique** du Pi.
- Les **ports 80 et 443** joignables depuis Internet (Caddy fait le HTTPS
  automatique via Let's Encrypt), car **GitHub Actions** (dans le cloud) doit
  pouvoir joindre le homeserver pour poster les notifs d'épisodes.
  - Box perso : redirection de ports 80/443 → Pi. Vérifie que ton FAI te donne
    une vraie IP publique (parfois IPv6 seulement).
  - Pas d'IP publique / CGNAT : mets un **micro-VPS FR** (Scaleway/OVH) en
    frontal + tunnel **WireGuard** vers le Pi (cf. discussion souveraineté).

## 1. Configuration

```bash
cd deploy/pi-matrix
cp .env.example .env
nano .env          # remplis MATRIX_DOMAIN, tokens, BOT_*, MY_USER_ID
```

Génère des secrets solides :

```bash
openssl rand -hex 24   # -> MATRIX_REGISTRATION_TOKEN
openssl rand -hex 24   # -> BOT_PASS
```

## 2. Démarrage

```bash
docker compose up -d
docker compose logs -f caddy    # vérifie l'obtention du certificat TLS
```

Teste que le homeserver répond :

```bash
curl -s https://$MATRIX_DOMAIN/_matrix/client/versions | jq .
```

## 3. Crée TON compte (dans Element)

Installe **Element** (mobile/desktop), « Créer un compte », serveur
personnalisé = `https://matrix.unebonnere.co`. Utilise le
**MATRIX_REGISTRATION_TOKEN** quand il est demandé. Ton identifiant sera
`@toi:matrix.unebonnere.co` → reporte-le dans `.env` (`MY_USER_ID`).

## 4. Crée le bot + le salon

```bash
./register-bot.sh          # crée le bot, affiche RECO_MATRIX_TOKEN
./create-room.sh           # crée le salon, t'y invite, affiche RECO_MATRIX_ROOM
```

Accepte l'invitation au salon **« Reco — notifications »** dans Element, puis
teste :

```bash
RECO_MATRIX_ROOM='!ton-room:matrix.unebonnere.co' ./send-test.sh
```

→ tu dois voir « ✅ Test Reco… » apparaître dans Element.

## 5. Referme la registration (important)

Une fois **toi + le bot** créés, empêche toute nouvelle inscription :

```bash
# dans docker-compose.yml, passe :
#   CONDUIT_ALLOW_REGISTRATION: "false"
docker compose up -d
```

## 6. Branche les notifs Reco

Dans le repo GitHub → **Settings → Secrets and variables → Actions**, ajoute :

| Secret | Valeur |
|--------|--------|
| `RECO_MATRIX_HOMESERVER` | `https://matrix.unebonnere.co` |
| `RECO_MATRIX_TOKEN` | (sortie de `register-bot.sh`) |
| `RECO_MATRIX_ROOM` | (sortie de `create-room.sh`) |

Les **notifs d'épisodes** marchent alors immédiatement (cron hebdo ou
*Actions → RSS poll → Run workflow*). Les **notifs de signalements**
s'activeront quand le site tournera en SSR (étape déploiement Infomaniak).

## 7. Branche les notifs de SIGNALEMENTS (hébergement Infomaniak)

Les trois mêmes valeurs servent **deux fois** : à GitHub Actions (§6, notifs de
nouveaux épisodes) et à l'hébergement Infomaniak — les signalements sont postés
par le site lui-même, quand un visiteur remplit le formulaire.

Elles ne se **trouvent** pas chez Infomaniak : elles sont **produites sur le
Pi** (§4), et seulement **déclarées** côté hébergement.

| Variable | D'où vient la valeur |
|---|---|
| `RECO_MATRIX_HOMESERVER` | `https://` + le `MATRIX_DOMAIN` de ton `.env` du Pi, soit `https://matrix.unebonnere.co`. `register-bot.sh` le réaffiche. |
| `RECO_MATRIX_TOKEN` | sortie de `./register-bot.sh` — le jeton d'accès du bot. |
| `RECO_MATRIX_ROOM` | sortie de `./create-room.sh` — commence par `!`. |

**Token perdu ?** Ne relance pas `register-bot.sh`, le compte existe déjà :
reconnecte le bot pour en obtenir un neuf (`BOT_USER` / `BOT_PASS` sont dans le
`.env` du Pi).

```bash
curl -s -XPOST https://matrix.unebonnere.co/_matrix/client/v3/login   -H 'Content-Type: application/json'   -d "{\"type\":\"m.login.password\",\"identifier\":{\"type\":\"m.id.user\",\"user\":\"$BOT_USER\"},\"password\":\"$BOT_PASS\"}"   | jq -r .access_token
```

**Room id perdu ?** Dans Element : le salon → Paramètres → Avancé → « ID interne
du salon ».

### Où les poser chez Infomaniak

`npm start` vaut `node --env-file-if-exists=.env ./server.mjs`. Le site lit donc
**les variables d'environnement du processus** ET, si le fichier existe, un
`.env` à la racine du dossier déployé. Deux voies :

1. **Les variables d'environnement de l'application Node.js**, dans le Manager
   Infomaniak — même écran que la version de Node et la commande de démarrage.
   À préférer : la valeur ne traîne pas dans un fichier du dossier web.
2. **Un fichier `.env` à la racine**, déposé par SSH ou FTP, si cet écran
   n'expose pas de variables. Il n'est **jamais** commité (`.gitignore`).

Dans les deux cas, **redémarre l'application** ensuite : le processus garde
sinon l'environnement avec lequel il a démarré.

### Vérifier que ça marche

Aucun redémarrage n'est nécessaire pour tester le homeserver lui-même :

```bash
RECO_MATRIX_ROOM='!ton-room:matrix.unebonnere.co' ./send-test.sh
```

Côté site, envoie un signalement depuis `/signaler` : le message doit arriver
dans Element. S'il n'arrive pas, ce n'est **jamais** une erreur visible par le
visiteur — `notifyReportMatrix` est silencieux quand la config manque ou que le
réseau échoue, par choix (un signalement ne doit pas échouer parce que Matrix
est tombé). Regarde les logs de l'application.

> Le site attend d'autres variables en production, sans rapport avec Matrix :
> `SITE_URL`, `RECO_SSR=1`, et `REPORTS_IP_SALT` (≥ 16 caractères, sinon le
> compteur anti-abus est réinitialisé à chaque redémarrage).

## Maintenance

- Logs : `docker compose logs -f conduit`
- Mise à jour : `docker compose pull && docker compose up -d`
- Sauvegarde : le volume `conduit_data` (petit) — `docker run --rm -v pi-matrix_conduit_data:/d -v $PWD:/b alpine tar czf /b/conduit-backup.tgz -C /d .`

> Le `server_name` (`MATRIX_DOMAIN`) est **permanent** : ne le change jamais
> après le premier démarrage (il est gravé dans les IDs).
