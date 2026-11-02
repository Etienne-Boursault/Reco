#!/bin/sh
# Vérification hebdomadaire des liens externes du site (décision LV-2 du
# 2026-11-02). Lancé par cron la nuit du dimanche au lundi (cf. README.md).
#
# On vérifie le site CONSTRUIT, pas les données : une partie des liens publiés
# n'existe qu'au build (vidéo de l'épisode, fiche TMDB tirée de l'identifiant).
# Le build se fait dans un clone à part, ~/reco-liens/site, tiré du clone de la
# chaîne : on ne touche ni à son arbre de travail ni à son verrou.
#
# Le message Matrix ne part que si des liens sont morts depuis la dernière
# fois ; le rapport complet reste dans ~/reco-liens. Rien n'est retiré du site.
set -u
BASE=/home/etienne/reco-liens
DEPOT=/home/etienne/docker/reco/depot
mkdir -p "$BASE"
cd "$BASE" || exit 1
exec >>"$BASE/journal-$(date +%Y-%m).log" 2>&1
horodater() { printf '%s — %s\n' "$(date -Iseconds)" "$*"; }

horodater "début"
[ -d site/.git ] || git clone -q "$DEPOT" site || exit 1
git -C site pull -q --ff-only || { horodater "git pull refusé"; exit 1; }

# Astro demande Node >= 22.22 et venus a Node 20 : le build tourne dans une
# image Node à l'étiquette exacte (la CI construit en Node 24 elle aussi).
NODE_IMAGE=node:24.22.2-bookworm-slim
node_run() {
  docker run --rm --user 1000:1000 -e HOME=/tmp -e SITE_URL=https://unebonnere.co \
    -v "$BASE/site:/site" -w /site "$NODE_IMAGE" "$@"
}
# `npm ci` seulement quand les dépendances ont changé : il retélécharge tout.
empreinte=$(sha256sum site/package-lock.json | cut -c1-16)
if [ ! -d site/node_modules ] || [ "$(cat npm-empreinte 2>/dev/null)" != "$empreinte" ]; then
  node_run npm ci --no-audit --no-fund --loglevel=error || { horodater "npm ci en échec"; exit 1; }
  echo "$empreinte" > npm-empreinte
fi
node_run npm run build --silent >/dev/null || { horodater "build en échec"; exit 1; }

cd /home/etienne/docker/reco || exit 1
docker compose run --rm -T \
  -v "$BASE/site/dist:/dist:ro" -v "$BASE:/rapports" \
  pipeline python verifier_liens.py externes /dist \
  --recos /app/src/content/recos --etat /rapports/etat.json --sortie /rapports \
  --notifier matrix
horodater "fin ($?)"
