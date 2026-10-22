# ADR 0054 — Mesurer les exécutions du pipeline, sans rien reconstruire

- **Statut** : Acceptée
- **Date** : 2026-10-22
- **Décideurs** : équipe Reco (éditeur)
- **Liens** : PR #129 à #133, [`workflow-metrics.md`](../workflow-metrics.md),
  ADR 0011 (golden set), ADR 0052 (durées de conservation)

## Contexte

Un futur estimateur (« Reco Estimator ») doit chiffrer le traitement d'un
podcast : coût LLM, temps machine, temps de relecture humaine. Rien de tout
cela n'était mesuré. Les seules traces — `extractionHistory` des recos, journaux
de `tick.sh`, rapports du banc d'essai — sont soit dédupliquées (une entrée
d'historique peut représenter plusieurs appels), soit agrégées, soit
volatiles. Les 115 épisodes du corpus ont été traités par des chemins
différents (Acast puis YouTube, Haiku et gpt-4o-mini en juin, Opus ensuite,
reprises, expériences) : en tirer une moyenne mélangerait tout.

## Décision

- **Une base dédiée, append-only, hors du catalogue** :
  `tools/output/telemetry/reco_metrics.sqlite` (stdlib `sqlite3`, WAL, migrée par
  `user_version`). Enregistrer une métrique ne demande aucun commit ; vider un
  cache ne l'efface pas.
- **Mesurer à la source, sans changer les contrats** : runs et tentatives
  voyagent par `contextvars` ; les adaptateurs LLM rendent toujours leurs recos
  et écrivent l'usage de côté. Le vrai orchestrateur de production est
  `traiter_nouveaux_episodes.py`, une invocation par étape de `tick.sh` ; un run
  n'est écrit qu'à sa première étape.
- **`null` n'est pas `0`**, dans la base comme dans les rapports. Une somme sur
  une valeur absente est `null`.
- **L'intention n'est jamais devinée** : la chaîne déclare le chemin nominal et
  chaque tentative est qualifiée d'après l'historique de la base (première
  passe, reprise rattachée) ; ailleurs, `--intent` ou `unknown`. Banc d'essai :
  `experiment`.
- **Coût = jetons du fournisseur × tarif daté** (`telemetry/tarifs.json`), figé
  à la date de l'appel ; inconnu plutôt que zéro quand l'un manque. Le payeur
  (`cost_owner`) se déduit du client, donc de la clé.
- **Temps humain = battements d'un onglet visible et actif**, jamais la durée
  d'une requête ; union des intervalles ; `null` sans battement.
- **Cohorte de référence calculée, jamais déclarée** : un épisode est retenu
  si ses passes nominales ont réussi avec l'empreinte de configuration de
  référence, le même média et des mesures complètes ; sinon un code
  d'exclusion. Un profil déclaré n'est qu'une étiquette.
- **Aucune reconstruction** : les épisodes antérieurs sont `no_telemetry` ; seul
  leur état final (catalogue) est rapporté.

## Conséquences

- Positives : chaque exécution réelle est attribuable ; nominal, reprises,
  expériences et migrations se séparent ; l'export est directement lisible par
  un estimateur, et il dit sa couverture.
- Négatives : aucune donnée exploitable avant S6-E06 (2026-10-23) ; la cohorte
  saison 6 ne sera qualifiée qu'à partir de 3 épisodes mesurés. Le temps actif
  repose sur des seuils (15 s, 60 s) à calibrer contre une relecture
  chronométrée.
- Restent non mesurés : temps GPU, coût d'exploitation local, facture réelle,
  prix du cache et tarifs OpenAI, latence d'une requête de lot, temps humain par
  fiche.
- Rejeté : reconstruire les métriques historiques depuis `extractionHistory`
  (dédupliqué, donc faux pour un comptage d'appels) ; compter le temps humain à
  partir des requêtes HTTP ; laisser un profil déclaré remplacer l'empreinte de
  configuration (un changement de modèle non renommé serait passé inaperçu).
