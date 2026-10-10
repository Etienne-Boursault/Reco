#!/bin/sh
# Un passage de la chaîne Reco sur venus. Lancé par cron (cf. README.md).
#
# Ordre : mise à jour du dépôt, détection, transcription, extraction, puis
# finalisation des épisodes que l'humain vient de relire. Chaque étape tourne
# dans un conteneur jetable (`docker compose run --rm`).
#
# L'extraction et la finalisation prennent le verrou pipeline que la page de
# validation tient tant qu'elle tourne (tools/review_lock.py). On n'arrête donc
# `reco-review` que le temps de ces étapes — une à deux minutes — et seulement
# si `a-extraire` ou `a-finaliser` répond qu'il y a du travail.
set -u
cd /home/etienne/docker/reco || exit 1
mkdir -p logs
exec >>"logs/tick-$(date +%Y-%m).log" 2>&1

# Un seul passage à la fois : une transcription dure ~17 min, et le cron repasse
# toutes les 10 min le dimanche.
exec 9>/tmp/reco-tick.lock
flock -n 9 || exit 0

horodater() { printf '%s — %s\n' "$(date -Iseconds)" "$*"; }
outil() {
  docker compose run --rm -T pipeline \
    python traiter_nouveaux_episodes.py --source un-bon-moment "$@"
}

horodater "passage"
git -C depot pull --ff-only --quiet \
  || horodater "git pull impossible : passage sur la copie locale"
outil detecter   || horodater "détection en échec"
outil transcrire || horodater "transcription en échec"
if outil a-extraire; then
  horodater "extraction : arrêt de la page de validation"
  docker compose stop review
  outil extraire || horodater "extraction en échec"
  docker compose start review
fi
# Les liens sont cherchés AVANT la relecture, pour que la page les montre. Sans
# verrou : l'étape n'écrit que les liens nouveaux, dans la reco relue à
# l'instant d'écrire — la page de validation reste ouverte pendant ce temps.
if outil a-chercher-liens; then
  outil chercher-liens || horodater "recherche de liens en échec"
fi
if outil a-finaliser; then
  horodater "finalisation : arrêt de la page de validation"
  docker compose stop review
  outil finaliser || horodater "finalisation en échec"
  docker compose start review
fi
# La publication ne prend pas le verrou : elle ne touche pas au corpus, elle le
# pousse. Elle retire en revanche les fichiers de l'épisode du clone jusqu'à la
# fusion de la PR — la page de validation ne l'affichera plus, sa relecture étant
# terminée. Inutile donc de l'arrêter.
if outil a-publier; then
  outil publier || horodater "publication en échec"
fi

# Moniteur « push » Uptime Kuma : sans lui, une chaîne qui s'arrête ne se
# remarque qu'au prochain épisode manqué. Kuma tourne sur venus et ne peut pas
# interroger la page de validation, ouverte au seul VPN — c'est donc au passage
# de se signaler. On extrait la seule variable utile du .env plutôt que de le
# sourcer : le fichier porte aussi des clés d'API, qui n'ont rien à faire dans
# l'environnement de tout ce que lance ce script. Un ping raté n'est jamais fatal.
KUMA=$(sed -n 's/^RECO_KUMA_PUSH_URL=//p' .env 2>/dev/null | tail -1)
if [ -n "${KUMA}" ]; then
  curl -fsS -m 10 -o /dev/null "${KUMA}" || horodater "ping Kuma en échec"
fi
