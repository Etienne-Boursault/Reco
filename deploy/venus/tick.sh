#!/bin/sh
# Un passage de la chaîne Reco sur venus. Lancé par cron (cf. README.md).
#
# Ordre : mise à jour du dépôt, détection, transcription, extraction. Chaque
# étape tourne dans un conteneur jetable (`docker compose run --rm`).
#
# L'extraction prend le verrou pipeline que la page de validation tient tant
# qu'elle tourne (tools/review_lock.py). On n'arrête donc `reco-review` que le
# temps de cette étape — une à deux minutes — et seulement si `a-extraire`
# répond qu'il y a du travail.
set -u
cd /home/etienne/docker/reco || exit 1
mkdir -p logs
exec >>"logs/tick-$(date +%Y-%m).log" 2>&1

# Un seul passage à la fois : une transcription dure ~37 min, et le cron repasse
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
