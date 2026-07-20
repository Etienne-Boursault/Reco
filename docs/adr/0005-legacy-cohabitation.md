# ADR 0005 — Cohabitation legacy `Reco`/`Episode` et nouvelle couche `Item`/`Mention`

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco

## Contexte

Le pipeline historique manipule `Reco`/`Episode` (cf. `tools/domain/_legacy.py`).
La phase P1.2 introduit une couche `Item`/`Mention` (ports + repos JSON
+ codecs + service de migration) pour préparer un futur backend SQLite et
la dédup éditoriale (cf. ADRs 0002, 0003).

On ne peut pas tout convertir d'un coup :
- Les scripts d'extraction (`extract_recos.py`), de match YT
  (`match_youtube.py`), d'enrichissement (`enrich_tmdb.py`,
  `enrich_music.py`), de review (`review_server`) écrivent et lisent
  encore le format `Reco`. Les réécrire = risque + downtime des outils.
- Le site Astro consomme la collection `recos` (107 pages buildées).
  Couper le contrat avant d'avoir validé Item/Mention bout-en-bout serait
  prématuré.
- Les fixtures de tests (~25 fichiers `recos/*.json`) sont sources de
  vérité légales pour de nombreux tests unitaires.

## Décision

On accepte une **cohabitation contrôlée** des deux couches pendant la
transition. Période visée : **P1.2.D → fin Phase 3** (estimée Q3 2026,
revisitée à chaque CR de phase).

Règles :

1. **SSOT côté `Reco`** jusqu'à fin P1.2 : les recos JSON sous
   `src/content/recos/<source>/` restent la **source de vérité écrite**.
   Items+Mentions sont **dérivés** par la migration (idempotent,
   ré-exécutable).
2. **Lecture seule côté `Item`/`Mention`** pendant P1.2 : le site Astro
   peut commencer à lire les nouvelles collections (gain : dédup, liens
   éthiques unifiés) mais aucun outil legacy n'écrit dans
   `src/content/{items,mentions}`.
3. **Inversion progressive en Phase 3** : à partir de Phase 3, l'écriture
   bascule côté `Item`/`Mention` ; les recos legacy deviennent
   read-only et seront archivées une fois la dernière dépendance levée.
4. **Pas de double écriture** : on ne fait JAMAIS écrire les deux
   couches en parallèle par un même script ; risque de désynchronisation
   silencieuse trop élevé.

## Conséquences

- Positives :
  - Pas de big-bang : chaque outil migré séparément avec tests dédiés.
  - Migration `recos → items+mentions` 100% testée (1601 tests, 100% cov)
    avant de toucher au pipeline d'extraction.
  - Possibilité de revenir en arrière (les recos legacy sont intactes).
- Négatives :
  - Duplication temporaire (deux couches en mémoire pendant ~6 mois).
  - Risque d'oubli de re-migration (un commit qui touche aux recos sans
    relancer la migration → Item/Mention désynchronisés).
  - Documentation `DATA_SCHEMA.md` doit décrire les deux modèles.
- Notes :
  - Garde-fou : un hook `pre-commit` (ou un job CI) pourrait vérifier
    que `--verify` passe après tout changement aux recos. À évaluer en
    Phase 2.
  - **Revisite** : à la fin de la Phase 3 (estimée Q3 2026), décider
    si on archive complètement les recos legacy ou si on garde une
    compatibilité ascendante longue.
