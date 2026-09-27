# syntax=docker/dockerfile:1.6
#
# Reco — l'atelier de venus : l'environnement de la chaîne automatique.
#
# L'image ne contient PAS le code. Le dépôt est monté depuis
# /home/etienne/docker/reco/depot : un `git pull` met la chaîne à jour, et
# l'image ne se reconstruit que si tools/requirements.txt change (penser alors à
# changer l'étiquette dans compose.yml).
#
# Différences avec le Dockerfile racine (le kit self-hostable) : pas de build
# Astro, inutile ici, et trois outils que la chaîne exige :
#   - ffmpeg          transcribe.py convertit l'audio YouTube en mp3 ;
#   - deno            yt-dlp en a besoin pour YouTube, sinon des formats manquent
#                     (avertissement constaté sur venus le 2026-09-17) ;
#   - git, openssh    la publication pousse sur main.

FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        ffmpeg \
        git \
        openssh-client \
        unzip \
 && rm -rf /var/lib/apt/lists/*

# Même version et même empreinte que tools/gpu_test.sh : l'URL de release est
# immuable et l'archive est vérifiée avant d'être extraite.
ARG DENO_VERSION=v2.9.6
ARG DENO_SHA256=394f07f4da2bebe6ce6f1e7ce0fa16429b29b08c35e3fac3fe25972676dff4b2
RUN curl -fsSL -o /tmp/deno.zip \
        "https://github.com/denoland/deno/releases/download/${DENO_VERSION}/deno-x86_64-unknown-linux-gnu.zip" \
 && echo "${DENO_SHA256}  /tmp/deno.zip" | sha256sum -c - \
 && unzip -q /tmp/deno.zip -d /usr/local/bin \
 && rm /tmp/deno.zip \
 && deno --version

COPY tools/requirements.txt /tmp/requirements.txt
RUN pip install -r /tmp/requirements.txt && rm /tmp/requirements.txt

# `tools` pour les imports à plat (`from common import …`), la racine pour le
# paquet `tools.` (extract_recos, match_youtube). Les caches — modèle Whisper
# (1,6 Go), yt-dlp — vont dans /cache, monté HORS de ~/docker : ils se
# retéléchargent et n'ont rien à faire dans la sauvegarde de nuit.
ENV PYTHONPATH=/app:/app/tools \
    HOME=/cache \
    XDG_CACHE_HOME=/cache \
    HF_HOME=/cache/huggingface

# ssh exige une entrée utilisateur pour l'uid qui l'exécute : sans elle,
# `getpwuid` échoue et il abandonne sur « No user exists for uid 1000 ». L'image
# installait openssh POUR pousser, mais aucun uid 1000 n'existait — vérifié le
# 2026-09-27 dans l'image en service : la publication n'aurait jamais pu pousser.
# Le répertoire personnel pointe sur /cache, qui existe (volume) et est
# accessible en écriture : ssh y écrit son known_hosts.
RUN groupadd --gid 1000 reco \
 && useradd --uid 1000 --gid 1000 --no-create-home --home-dir /cache --shell /bin/sh reco

WORKDIR /app/tools
USER 1000:1000
