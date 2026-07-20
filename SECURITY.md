# Politique de sécurité

## Versions supportées

Seule la dernière version publiée sur la branche `main` est activement
maintenue. Les correctifs de sécurité ne sont pas rétro-portés sur les
tags antérieurs ; mettez à jour vers `main` (ou le dernier tag stable) si
vous hébergez une instance.

| Version       | Supportée |
| ------------- | --------- |
| `main` (HEAD) | ✅        |
| autres        | ❌        |

## Signaler une vulnérabilité

**Ne pas ouvrir d'issue publique** pour décrire une vulnérabilité.

Deux canaux de signalement, par ordre de préférence :

1. **GitHub Security Advisories** (privé) — onglet « Security » du dépôt,
   bouton « Report a vulnerability ». Recommandé : l'échange reste
   confidentiel, et un CVE peut être attribué à la résolution.
2. **E-mail** : `security@source-internet.fr` _(placeholder — à remplacer
   avant ouverture publique du dépôt)_. Chiffrez avec PGP si possible
   (clé publique à fournir avant ouverture du dépôt).

Merci d'inclure :

- Une description du problème et son impact estimé.
- Les étapes pour reproduire (PoC minimal apprécié).
- Les versions / commits affectés.
- Vos coordonnées pour le suivi (et préférence de mention au crédit).

## Fenêtre de réponse

- **48 h** : accusé de réception.
- **7 jours** : évaluation initiale (gravité, surface).
- **30 jours** : correctif ou plan de mitigation publié.

Si la vulnérabilité est critique et exposée, un advisory peut être
publié avant la fin de la fenêtre, en coordination avec le rapporteur.

## Reconnaissance

Les rapporteurs sont crédités dans le `CHANGELOG.md` et l'advisory GitHub
sauf demande contraire. Reco n'a pas (encore) de bug bounty monétaire.

## Périmètre

En périmètre :

- Le code du dépôt (`src/`, `tools/`, scripts CI).
- Les artefacts publiés (npm package `reco` si publié, images Docker).
- Le site de référence `source-internet.fr` pour les bugs qui exploitent
  une faiblesse du kit.

Hors périmètre :

- Les instances tierces qui forkent Reco (à signaler à leur opérateur).
- Les dépendances upstream — merci de remonter directement à l'éditeur
  (npm, PyPI), et de nous prévenir si Reco doit publier un advisory en
  cascade.
