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

## Maintenance

- Logs : `docker compose logs -f conduit`
- Mise à jour : `docker compose pull && docker compose up -d`
- Sauvegarde : le volume `conduit_data` (petit) — `docker run --rm -v pi-matrix_conduit_data:/d -v $PWD:/b alpine tar czf /b/conduit-backup.tgz -C /d .`

> Le `server_name` (`MATRIX_DOMAIN`) est **permanent** : ne le change jamais
> après le premier démarrage (il est gravé dans les IDs).
