#!/usr/bin/env bash
# stop_mac.sh — Arrête le worker Mac proprement.
# L'épisode en cours est perdu (whisper-cli tué), les déjà-faits restent.
# Pour reprise : relancer worker_mac_large.sh (skip auto des transcripts existants).
pkill -f worker_mac_large 2>/dev/null && echo "worker_mac_large stoppé" || echo "worker_mac_large pas en cours"
pkill -f whisper-cli 2>/dev/null && echo "whisper-cli stoppé" || true
pkill -f yt-dlp 2>/dev/null && echo "yt-dlp stoppé" || true
pkill -f "http.server 8003" 2>/dev/null && echo "serveur :8003 stoppé" || true
echo "Done."
