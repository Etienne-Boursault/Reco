# ADR 0006 — Préservation des types legacy `spectacle`/`lieu`/`video`

- Statut : Acceptée
- Date : 2026-06-10
- Décideurs : équipe Reco

## Contexte

`ItemType` (cf. `tools/domain/item.py`) définissait initialement 11
catégories d'œuvre (`livre`, `film`, `serie`, `musique`, `album`,
`artiste`, `podcast`, `jeu`, `bd`, `article`, `autre`). Les recos
historiques (~2866 enregistrements) utilisent 3 valeurs additionnelles :

- `spectacle` : stand-up, théâtre, one-man show (~80 recos)
- `lieu` : restaurant, ville, lieu géographique (~30 recos)
- `video` : vidéo YouTube spécifique (~20 recos)

Le parser de migration (`reco_parser._parse_types`) mappait ces 3 valeurs
vers `ItemType.OTHER` (alias silencieux). Ce comportement :

- **perd l'information sémantique** (impossible de retrouver les
  spectacles dans l'index Item) ;
- **casse le round-trip** : un round-trip recos → items → recos
  perdrait la valeur originale (`spectacle` deviendrait `autre`) ;
- **dégrade les liens éthiques** : `lieu` aurait pu pointer vers
  TripAdvisor, `video` vers YouTube directement ; mappés à OTHER, plus
  de spécialisation possible.

Options :

1. **Garder l'alias OTHER** : simple, mais perd l'info (rejeté).
2. **Étendre `ItemType` avec 3 valeurs first-class** (SHOW/PLACE/VIDEO) :
   préserve l'info, expose les 3 catégories au reste du domaine.
3. **Champ libre `Item.subtype: str | None`** : flexible mais ouvre la
   porte à la pollution typage (chaque dev son alias). YAGNI à ce stade.

## Décision

**Option 2 : extension de l'enum `ItemType`** avec 3 valeurs first-class :

- `ItemType.SHOW = "spectacle"`
- `ItemType.PLACE = "lieu"`
- `ItemType.VIDEO = "video"`

Zod schema (`src/content.config.ts::itemType`) mis à jour en miroir.
`_TYPE_ALIASES` du parser devient un dict vide (porte de sortie pour
des alias futurs s'ils émergent).

## Politique d'extension de `ItemType` (ADR 0006-bis)

**Critères cumulatifs** pour ajouter une nouvelle valeur :

1. Présence dans **au moins 10 recos** existantes (signal d'usage réel).
2. Différenciation **utile** : la nouvelle catégorie permet d'enrichir
   les liens (ex. TripAdvisor pour `lieu`) OU d'agréger les recos
   (page dédiée).
3. **Pas de chevauchement** sémantique avec une valeur existante. Si la
   différence est floue (`film` vs `documentaire`), préférer un sous-tag
   `Item.aliases` plutôt qu'un nouveau type.

Toute extension ouvre un nouvel ADR (0006-ter, etc.) avec recensement
des recos concernées + mise à jour du Zod schema + tests cross-stack.

## Conséquences

- Positives :
  - Round-trip recos → items → recos sans perte.
  - Sémantique préservée : les pages "Spectacles" / "Lieux" / "Vidéos"
    redeviennent possibles.
  - Migration P1.2.D produit 0 erreur de typage sur le dataset legacy.
- Négatives :
  - Le contrat public d'`ItemType` s'élargit (consommateurs doivent
    gérer 14 valeurs au lieu de 11).
  - Un type "trop spécifique" (ex. `lieu`) peut être tentant à utiliser
    abusivement (ex. tout endroit mentionné dans un transcript). La
    politique d'extension limite ce risque.
- Notes :
  - Test garde-fou : `test_item_type_includes_legacy_show_place_video`
    (`tests/test_domain_v2_fixes.py`) vérifie la présence des 3 valeurs.
  - Si Phase 3 fait émerger des nouveaux types légitimes, suivre la
    politique d'extension.
