# ADR 0003 — Identité typée (`BookIdentity` / `FilmIdentity`) — DIFFÉRÉ

- Statut : Différée (réévaluer si >5 sources externes par type)
- Date : 2026-06-10
- Décideurs : équipe Reco

## Contexte

Critique archi #6 : `ExternalIds` est un dataclass plat regroupant TOUS
les ids externes possibles (`tmdb`, `tmdb_type`, `spotify`,
`musicbrainz`, `openlibrary`, `isbn`, `justwatch`). Un livre n'a pas de
`tmdb`, un film n'a pas d'`isbn` — la structure mélange domaines.

Refactor envisagé : composition par type.

```python
@dataclass(frozen=True)
class BookIdentity:
    isbn: str | None = None
    openlibrary: str | None = None

@dataclass(frozen=True)
class FilmIdentity:
    tmdb: int | None = None
    tmdb_type: Literal["movie", "tv"] | None = None
    justwatch: str | None = None

@dataclass(frozen=True)
class MusicIdentity:
    spotify: str | None = None
    musicbrainz: str | None = None
```

## Décision

**Différer**. Raisons :

1. Coût : ~3-4 h de refactor + impact migration sur 100% des callsites
   `external_ids`. La couche persistence Phase 1 n'est pas encore écrite,
   donc on évite le double travail si on doit re-typer plus tard.
2. Bénéfice : marginal sur le MVP 5-10 podcasts. La structure plate reste
   lisible tant qu'on a <5 ids par type.
3. Trigger de revisite : si on dépasse **5 sources externes** pour au
   moins un type (ex. AniList + AniDB + MAL + Kitsu + Crunchyroll pour
   les animés), on reconsidère.

## Conséquences

- `ExternalIds` reste plat pour Phase 1.
- Tickets ouverts : aucun aujourd'hui — flag à poser quand le 5e id
  arrive.
- Lien : ADR 0002 (multi-types) — décision indépendante mais connexe.

## Addendum 2026-06-10 — seuil de collision SHA256[:8]

`generate_item_id` utilise `sha256(canonical)[:8]` (32 bits) avec
suffixage `-N` en cas de collision. Estimation de collision (Birthday
problem) :

| N items | Collision probability |
|---------|----------------------|
| 1 000   | ~0.01%               |
| 10 000  | ~1.2%                |
| 20 000  | ~4.6%                |
| 50 000  | ~25%                 |
| 100 000 | ~69%                 |

**Politique** : tant qu'on reste sous **20k items** (~50 podcasts ×
~400 recos uniques), 8 hex chars suffisent. Le suffixage `-N` absorbe
la dérive jusqu'à ce seuil.

**Trigger de revisite** : à 50k items, passer à `sha256(canonical)[:12]`
(48 bits → collision <0.001% à 100k). La migration sera trivial car
les ids ne sont pas re-générés (cf. `IdentityRegistry.seed`).
