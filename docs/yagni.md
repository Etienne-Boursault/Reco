# YAGNI — *You Aren't Gonna Need It*

## TL;DR

**N'implémente une fonctionnalité que quand tu en as réellement besoin, pas quand tu penses que tu en auras besoin plus tard.**

Le coût du code "pré-payé" est immédiat (complexité, bugs, audit, maintenance). Le bénéfice est hypothétique. Et quand le vrai besoin arrive, il ne ressemble presque jamais à ce que tu avais imaginé.

---

## Origine

- **Concepteurs** : Kent Beck, Ron Jeffries, Ward Cunningham, dans le cadre de l'*Extreme Programming* (XP), fin des années 1990.
- **Première apparition** : *Extreme Programming Explained: Embrace Change* (Kent Beck, 1999).
- **Cadre théorique** : un des principes fondateurs de XP, à côté de **DRY** (Don't Repeat Yourself) et **KISS** (Keep It Simple, Stupid).
- **Inspiration** : la programmation Lisp/Smalltalk des années 80, où l'on construisait des prototypes minimaux et on les faisait évoluer par refactoring incrémental.

Citation canonique de Ron Jeffries :

> *"Always implement things when you actually need them, never when you just foresee that you need them."*

---

## Pourquoi ce principe existe

### 1. Le besoin imaginé ≠ le besoin réel

Quand tu spécules sur un futur besoin, tu le projettes depuis ta connaissance actuelle. Quand le vrai besoin arrive (s'il arrive), le contexte a changé : nouvelles contraintes, nouveaux utilisateurs, nouvelles techno. Statistiquement, environ **60 à 90 %** des features "anticipées" ne sont jamais utilisées telles qu'imaginées (études Standish Group sur les projets logiciels).

### 2. Le code pré-payé a un coût immédiat

- **Lecture** : chaque ligne ajoutée doit être lue, comprise, naviguée par tous les futurs développeurs (y compris toi dans 3 mois).
- **Tests** : pour rester fiable, le code spéculatif doit être testé. Tests qui prennent du temps à écrire, à exécuter, à maintenir.
- **Refactoring** : à chaque évolution structurelle, le code spéculatif doit être pris en compte. Il ralentit les vraies évolutions.
- **Audit (sécurité, perf, concurrence)** : un mécanisme prévu pour un cas "futur" doit quand même résister aux audits du présent.
- **Charge cognitive** : un développeur qui lit `_get_source_lock(source_id)` se demande "pourquoi un lock ici ?" — et perd du temps à comprendre que c'est défensif et inutile.

### 3. Le code pré-payé bloque souvent la vraie solution

C'est le piège le plus pernicieux. Quand le vrai besoin arrive :

- Soit la solution pré-payée **ne correspond pas** au vrai besoin → il faut tout réécrire, en plus de tout désinstaller.
- Soit on est **prisonnier** de l'abstraction pré-payée et on bâtit dessus à tort → on accumule de la dette autour d'un fondement inadapté.

Exemple historique : Joel Spolsky raconte dans *Things You Should Never Do, Part I* (2000) comment Netscape a passé 3 ans à réécrire son moteur de rendu pour anticiper des besoins futurs, perdant le marché face à Internet Explorer pendant ce temps.

---

## YAGNI ne dit PAS…

C'est important de bien cadrer le principe.

### ❌ YAGNI ne dit pas "écris du code crade"
Tu dois toujours écrire du code propre, testé, documenté. YAGNI dit juste : n'ajoute pas de **fonctionnalité** qui ne sert pas maintenant.

### ❌ YAGNI ne dit pas "n'anticipe jamais rien"
Tu peux et dois anticiper les **changements probables** dans ta phase de design. La différence est subtile :
- *Anticipation YAGNI-compatible* : écrire du code que tu peux **facilement modifier** quand le besoin arrivera.
- *Anticipation anti-YAGNI* : écrire dès maintenant le code que tu pourrais **avoir besoin** plus tard.

### ❌ YAGNI ne s'oppose pas à SOLID / Clean Architecture
SOLID et Clean Architecture parlent de **structure** (comment organiser le code). YAGNI parle de **portée** (combien de code écrire). Tu peux suivre SOLID en restant YAGNI : tu fais l'effort de structurer ce que tu écris, sans écrire ce dont tu n'as pas besoin.

### ❌ YAGNI ne s'applique pas à la sécurité, la performance critique, la robustesse de base
Si tu écris un service public, tu DOIS gérer les inputs invalides, les XSS, les DoS — même si "personne ne va attaquer". Ce ne sont pas des features spéculatives, ce sont des invariants de qualité. La sécurité n'est pas YAGNI.

---

## Exemples concrets

### ✅ Application correcte (cas réel : projet Reco)

**Contexte** : un outil local de revue de recommandations (`review_server.py`) qui tourne sur `localhost:8000` pour un seul utilisateur.

**Code pré-payé "au cas où on passerait en multi-thread"** :
```python
from collections import defaultdict
import threading

_SOURCE_LOCKS: dict[str, threading.Lock] = defaultdict(threading.Lock)

def _get_source_lock(source_id: str) -> threading.Lock:
    return _SOURCE_LOCKS[source_id]

def merge_cluster(...):
    with _get_source_lock(source_id):
        return _merge_cluster_locked(...)
```

**Pourquoi c'est anti-YAGNI** :
- Le serveur utilise `HTTPServer` (mono-thread), pas `ThreadingHTTPServer`.
- Aucune demande multi-thread n'a jamais été formulée.
- Le jour où le besoin multi-utilisateur arrivera, la vraie réponse sera une DB centralisée + API REST + frontend découplé — pas ce serveur monolithique. Les locks actuels seront jetés.
- En attendant, ils ajoutent : 30 LOC, un audit nécessaire, un point de confusion pour les lecteurs ("pourquoi un lock ici ? le serveur est-il vraiment threadé ?").

**Fix YAGNI-compatible** : retirer tous les locks. Ajouter en tête du module :
```python
# Single-threaded by design (HTTPServer, not ThreadingHTTPServer).
# Outil local mono-utilisateur — pas de protection de concurrence intentionnelle.
```

Si un jour on passe en threaded → on rajoute les locks à ce moment-là, **en connaissant le vrai besoin** et en pouvant tester les vraies races.

### ✅ Autre exemple : abstractions prématurées

**Anti-YAGNI** :
```python
class StorageBackend(ABC):
    @abstractmethod
    def read(self, key: str) -> dict: ...
    @abstractmethod
    def write(self, key: str, value: dict) -> None: ...

class FileStorageBackend(StorageBackend):
    def read(self, key): return json.loads(Path(key).read_text())
    def write(self, key, value): Path(key).write_text(json.dumps(value))

# "Un jour on pourra brancher Redis / DynamoDB / S3"
```

**YAGNI** :
```python
def read_json(path: Path) -> dict:
    return json.loads(path.read_text())

def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value))
```

Si un jour S3 arrive, on remplace les 2 fonctions par une couche d'abstraction **conçue pour le vrai besoin S3** (régions, retry, credentials, etc.). L'abstraction `StorageBackend` prématurée aurait été inadaptée et aurait freiné le vrai design.

### ✅ Encore un : config flexible "au cas où"

**Anti-YAGNI** :
```python
class Config:
    def __init__(self):
        self.theme = os.getenv("RECO_THEME", "dark")
        self.language = os.getenv("RECO_LANG", "fr")
        self.date_format = os.getenv("RECO_DATE_FMT", "%Y-%m-%d")
        self.timezone = os.getenv("RECO_TZ", "Europe/Paris")
        self.feature_flags = parse_flags(os.getenv("RECO_FLAGS", ""))
        # ... 15 autres options
```

**YAGNI** : tu utilises Europe/Paris, en français, format ISO, thème sombre. Hardcode tout. Quand un jour tu veux un thème clair, tu ajoutes UNE option. Pas 15.

### ❌ Mauvaise application (cas où YAGNI ne s'applique pas)

- **Validation des inputs utilisateur** : "je sais que je suis le seul user, je n'ai pas besoin de valider". Mauvais — la sécurité de base est un invariant, pas une feature.
- **Tests** : "je rajouterai des tests quand j'en aurai besoin". Mauvais — les tests sont la condition de la maintenabilité, pas une feature.
- **Logging** : "je rajouterai des logs si je dois debugger". Mauvais — un minimum de logging est nécessaire dès qu'un système tourne en production.

---

## Comment l'appliquer en pratique

### En écriture de code

1. **Avant d'ajouter une feature**, demande-toi : *est-ce qu'un utilisateur l'a demandée maintenant ? est-ce qu'elle débloque une tâche en cours ?*
2. Si la réponse est non → **ne l'ajoute pas**.
3. **Avant d'ajouter une abstraction** (interface, factory, plugin system), demande-toi : *est-ce que j'ai au moins 2 implémentations concrètes différentes en ce moment ?*
4. Si la réponse est non → **inline le code**, abstrais plus tard.

### En revue de code (CR)

Cherche les marqueurs typiques d'anti-YAGNI :
- Commentaires `# pour quand on aura besoin de X`
- Paramètres optionnels jamais utilisés (`def foo(a, b, c=None, d=None, mode="default")`)
- Hiérarchies de classes avec 1 seule sous-classe
- Configuration flexible sans configuration variable
- Hooks / callbacks / events / signaux sans listeners
- "Utility frameworks" maison qui dupliquent ce que stdlib propose déjà
- Cache sans benchmark démontrant le besoin

### En refactoring

YAGNI dit aussi : **n'hésite pas à supprimer du code spéculatif** quand tu le découvres. Si une feature n'a jamais été utilisée depuis 6 mois, elle peut probablement disparaître. Git garde l'historique — tu peux toujours la ressortir si elle devient nécessaire.

---

## YAGNI vs ses faux amis

| Principe | Ce qu'il dit | Confusion fréquente |
|---|---|---|
| **YAGNI** | Pas de feature spéculative | "Pas de code propre" (FAUX) |
| **KISS** | Solutions simples > solutions complexes | "Solutions naïves" (FAUX, on parle de simplicité conceptuelle) |
| **DRY** | Pas de duplication de **connaissance** | "Pas de duplication de lignes" (FAUX, parfois la duplication est saine) |
| **Premature optimization is the root of all evil** (Knuth) | Pas d'optimisation perf avant mesure | "Pas d'attention à la perf" (FAUX) |
| **SOLID** | Comment structurer du code OO | "Toujours abstraire" (FAUX, SOLID dit *quand* abstraire) |

---

## Coût psychologique de YAGNI

Le piège classique : YAGNI demande de **laisser passer une opportunité visible** ("je suis là dans le code, j'ai 5 min, autant l'ajouter tout de suite").

C'est inconfortable. Notre cerveau préfère agir que de ne pas agir. Mais l'expérience montre que **80 % des "5 minutes maintenant" deviennent des "2 heures de debug 6 mois plus tard"**.

Discipline YAGNI = discipline de **laisser le code "incomplet" en apparence**, en sachant qu'il est complet pour son besoin actuel.

---

## Pour aller plus loin

- Kent Beck, *Extreme Programming Explained: Embrace Change* (1999, 2e éd. 2004)
- Martin Fowler, *Yagni* (article court, martinfowler.com/bliki/Yagni.html, 2015)
- Ron Jeffries, *We Tried Baseball and It Didn't Work* (2017) — sur la pratique de YAGNI dans la durée
- Joel Spolsky, *Things You Should Never Do, Part I* (2000) — contre-exemple Netscape

---

## En une phrase

> **Le meilleur code est celui que tu n'écris pas.**

Tout code écrit en spéculation est de la dette. La dette est OK quand elle est consciente et nécessaire. YAGNI dit simplement : **n'en ajoute pas par inadvertance**.

---

## Application concrète — Outil de relecture local (2026-06)

### Décision : Option A — single-thread strict

`tools/review_server.py` tourne sur `http.server.HTTPServer` (sérialise les requêtes, un seul thread). Le seul utilisateur, c'est moi (localhost). Donc :

- **Aucun lock n'est nécessaire** : `_RECO_PATH_CACHE`, `_merge_locks[source_id]`, `_get_source_lock(...)` étaient du *dead code* spéculatif (« et si un jour on passe à `ThreadingHTTPServer` ? »).
- **Aucune race condition possible** sur `_allocate_new_reco` (allocation d'un nouvel ID), sur `restore_last_backup` (consommation d'un dossier de backup), sur `merge_cluster` (mutation atomique d'un kept + suppression de losers).

### Ce qu'on a retiré

| Symbole | Raison |
|---------|--------|
| `threading.Lock`, `defaultdict(threading.Lock)` dans `reco_dedup_merge.py` | Pas de threads concurrents à protéger |
| `_get_source_lock(source_id)` | idem |
| `_merge_cluster_locked()` (fusionné dans `merge_cluster()`) | Plus de wrapper inutile |
| `_RECO_CACHE_LOCK = threading.Lock()` dans `review_server.py` | Cache lu/écrit dans le même thread |
| `with _RECO_CACHE_LOCK:` (4 occurrences) | idem |
| `test_get_source_lock_returns_same_instance` | Test sur du code mort |

### Ce qu'on garde quand même

- **Atomicité disque** via `_atomic_write_json` (tmp + fsync + rename) : ce n'est PAS contre la concurrence, c'est contre un crash brutal (Ctrl+C, panne) qui laisserait un JSON tronqué.
- **Backups + manifeste** : ce n'est PAS contre la concurrence non plus, c'est pour l'undo manuel.
- **Cleanup `.tmp` orphelins au démarrage** : un crash précédent peut avoir laissé un tmp.

### Si un jour on passe à du multi-thread

Le commit qui réintroduit la concurrence devra :
1. Réintroduire les locks via le module `threading`.
2. Mettre à jour ce paragraphe et le docstring de `review_server.py`.
3. Couvrir avec des tests de concurrence réels (pas juste des stubs comme l'ancien `test_get_source_lock_returns_same_instance`).

Tant que ce commit n'est pas fait, le code est **single-threaded by design**.
