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
# Suivi des passages pour le tableau de bord (R2 B du 27/11/2026, TB-1 C du
# 28/11/2026) : une ligne JSON par passage dans passages.jsonl (début, fin, étapes
# lancées parce que leur sonde a répondu oui, étapes en échec), les 200 dernières.
# Pendant le passage, `en-cours` porte son début (effacé à la fin de la note).
# Le dossier est sous tools/output/, que Git ignore et que le conteneur de la page
# voit. Une erreur du suivi ne doit jamais arrêter la chaîne : l'écriture finit par
# `|| true`, et chaque variable a une valeur avant d'être lue (set -u).
BORD="${RECO_BORD_DIR:-depot/tools/output/bord}"
DEBUT=$(date -Iseconds)
LANCEES=""
ECHECS=""
lance() { LANCEES="${LANCEES:+${LANCEES},}\"$1\""; }
echec() { ECHECS="${ECHECS:+${ECHECS},}\"$1\""; shift; horodater "$@"; }
noter_passage() {
  mkdir -p "${BORD}" \
    && printf '{"debut":"%s","fin":"%s","lancees":[%s],"echecs":[%s]}\n' \
      "${DEBUT}" "$(date -Iseconds)" "${LANCEES}" "${ECHECS}" >>"${BORD}/passages.jsonl" \
    && tail -n 200 "${BORD}/passages.jsonl" >"${BORD}/passages.jsonl.tmp" \
    && mv "${BORD}/passages.jsonl.tmp" "${BORD}/passages.jsonl"     && rm -f "${BORD}/en-cours"
}
outil() {
  docker compose run --rm -T pipeline \
    python traiter_nouveaux_episodes.py --source un-bon-moment "$@"
}

horodater "passage"
# Le passage tourne : le tableau de bord le sait par ce fichier, que `noter_passage`
# efface à la fin (tour 1, F8 repris : sans lui, une longue transcription faisait crier
# au retard). Resté après un échec de la note, il passe pour un passage bloqué.
{ mkdir -p "${BORD}" && printf '%s
' "${DEBUT}" >"${BORD}/en-cours"; }   || horodater "suivi du passage en cours impossible" || true
git -C depot pull --ff-only --quiet \
  || echec git-pull "git pull impossible : passage sur la copie locale"
outil detecter   || echec detecter "détection en échec"
outil transcrire || echec transcrire "transcription en échec"
if outil a-extraire; then
  lance extraire
  horodater "extraction : arrêt de la page de validation"
  docker compose stop review
  outil extraire || echec extraire "extraction en échec"
  docker compose start review
fi
# Les liens sont cherchés AVANT la relecture, pour que la page les montre. Sans
# verrou : l'étape n'écrit que les liens nouveaux, dans la reco relue à
# l'instant d'écrire — la page de validation reste ouverte pendant ce temps.
if outil a-chercher-liens; then
  lance chercher-liens
  outil chercher-liens || echec chercher-liens "recherche de liens en échec"
fi
if outil a-finaliser; then
  lance finaliser
  horodater "finalisation : arrêt de la page de validation"
  docker compose stop review
  outil finaliser || echec finaliser "finalisation en échec"
  docker compose start review
fi
# La publication ne prend pas le verrou : elle ne touche pas au corpus, elle le
# pousse. Elle retire en revanche les fichiers de l'épisode du clone jusqu'à la
# fusion de la PR — la page de validation ne l'affichera plus, sa relecture étant
# terminée. Inutile donc de l'arrêter.
if outil a-publier; then
  lance publier
  outil publier || echec publier "publication en échec"
fi
# Relance des sorties annoncées (R4 B, 27/11/2026) : une fois par jour, après 6 h à
# Paris (l'étape se l'impose), elle cherche les liens des recos dont la date de sortie
# annoncée est arrivée, sur une copie d'origin/main, et pousse la branche
# `contenu/sorties-AAAA-MM-JJ`. Sans verrou ni arrêt de la page de validation : elle ne
# touche jamais au clone. Inerte sans RECO_SORTIES_ANNONCEES=1 dans le .env.
docker compose run --rm -T pipeline \
  python sorties_annoncees.py --notifier matrix \
  || echec sorties-annoncees "relance des sorties annoncées en échec"
# Le commentaire YouTube attend que la page de l'épisode soit en ligne : la
# sonde répond « oui » dès la PR fusionnée, l'étape repasse tant que le
# déploiement n'a pas fini. Inerte sans RECO_YT_COMMENTAIRES=1 dans le .env.
if outil a-commenter; then
  lance commenter
  outil commenter || echec commenter "commentaire YouTube en échec"
fi
# Une fois par semaine (l'étape se l'impose) : modèle d'extraction disparu, ou
# plus récent dans sa famille. Un message Matrix, jamais de bascule automatique.
outil veiller-modeles || echec veiller-modeles "veille des modèles en échec"

# Une fois par semaine : les runs de télémétrie restés « started » (arrêt brutal
# d'un conteneur) passent en « interrupted » au-delà de 24 h. Rien n'est effacé
# (cf. docs/workflow-metrics.md). La semaine ISO marque le passage déjà fait.
SEMAINE="logs/.recover-$(date +%G-W%V)"
if [ ! -e "${SEMAINE}" ]; then
  if docker compose run --rm -T pipeline python metrics_report.py recover >/dev/null; then
    touch "${SEMAINE}"
  else
    echec recover "récupération des runs interrompus en échec"
  fi
fi

noter_passage || horodater "suivi des passages impossible dans ${BORD}" || true

# Moniteur « push » Uptime Kuma : sans lui, une chaîne qui s'arrête ne se
# remarque qu'au prochain épisode manqué. La page de validation répond au réseau
# local et au VPN depuis le 2026-10-02, jamais à Internet ; mais qu'elle réponde
# ne dit pas que la chaîne passe : c'est donc au passage de se signaler. On extrait la seule variable utile du .env plutôt que de le
# sourcer : le fichier porte aussi des clés d'API, qui n'ont rien à faire dans
# l'environnement de tout ce que lance ce script. Un ping raté n'est jamais fatal.
KUMA=$(sed -n 's/^RECO_KUMA_PUSH_URL=//p' .env 2>/dev/null | tail -1)
if [ -n "${KUMA}" ]; then
  curl -fsS -m 10 -o /dev/null "${KUMA}" || horodater "ping Kuma en échec"
fi
