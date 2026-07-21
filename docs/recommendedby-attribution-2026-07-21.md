# Attribution du prescripteur (`recommendedBy`) — investigation du 2026-07-21

Ce document explique **pourquoi le champ `recommendedBy` reste majoritairement
vide** sur les recos validées, et récapitule toutes les pistes testées pour le
remplir. Objectif : éviter qu'une session future re-tente les mêmes impasses.

## Le problème

`recommendedBy` = la personne qui a fait la recommandation dans l'épisode
(un des deux animateurs — Kyan Khojandi, Navo — ou un invité). Sur ~450 recos
validées, ce champ est vide.

**Cause racine :** les transcripts viennent de **Whisper large-v3, sans
diarisation**. Ils donnent les mots horodatés, jamais *qui* parle. Ce n'est pas
un échec de transcription — l'outil ne fait pas le « qui ». Le code le disait
déjà (`tools/review_doubts.py` : « attribution du locuteur impossible sans
diarization »). 303 des 452 vides portent le flag `attribution_suspect` avec des
notes de review explicites (« locuteur Kyan ou Éléonore, non déterminable ») :
les vides sont **délibérés**, pas des oublis.

## Piste 1 — attribution par le TEXTE (retenue, appliquée)

Un agent lit le transcript autour du timestamp de chaque reco et infère le
prescripteur du contexte conversationnel.

**Pilote de mesure** (3 épisodes, comparaison à la vérité terrain) :

| Configuration | Exactitude |
|---|---|
| Épisode à **invité unique** | **100 %** |
| Épisodes à **2+ invités** | ~80 % |

Toutes les erreurs sont des **inférences** (élimination par le genre/rôle) ;
aucune attribution à **ancrage dur** (la personne parle de sa propre œuvre, ou
est nommée explicitement) n'a jamais menti.

**Passe appliquée** aux 17 vrais épisodes à invité unique, règle d'ancrage dur
→ **17 attributions posées** (commit `f99428b`). Rendement ~26 %, volontairement
bas : « vide plutôt que faux ». Les épisodes multi-invités ne sont **pas**
traités (zone à ~20 % d'erreur).

**Effet de bord utile :** des « recos » se sont révélées être du **bruit
d'extraction tiré de l'intro** (« co-auteur de Bref/Bloqué/Serge le Mytho » =
présentation de Navo, pas une reco) → discardées (commit `c48ce9a`). À
surveiller : recos à timestamp < 90 s.

## Piste 2 — DIARISATION (testée à fond, ÉCHEC)

Séparer les voix pour savoir qui parle, puis mapper locuteur → nom.

**L'infra n'est PAS le problème.** Le portable (GTX 950M) est trop lent
(~1,3× le temps réel). Le **Mac M4 (MPS/Metal)** diarise **92 min d'audio en
~7 min** — vitesse viable en prod.

**Recette qui tourne** (Mac, venv Python 3.9) : `pyannote.audio` 3.4.0 (pipeline
classique `speaker-diarization-3.1`, pas le community-1 gated de la 4.x). Pièges
enchaînés à connaître :
- pinner **`huggingface_hub==0.25.2`** (le récent a retiré `use_auth_token`,
  qu'appelle pyannote 3.x en interne) ;
- **monkeypatcher `torch.load` en `weights_only=False` forcé** (torch ≥ 2.6 le
  met à True et rejette le checkpoint) ;
- décoder le WAV via **soundfile** et passer la forme d'onde (évite
  torchaudio/torchcodec) ;
- token via l'env **`HF_TOKEN`** (le nom du paramètre change entre 3.x et 4.x).

**Pourquoi ça échoue.** Sur l'épisode entier (15 recos à vérité connue), presque
tout tombe sur **un seul cluster** (le locuteur dominant = 45–65 % de toute la
parole). La diarisation **fusionne les voix masculines proches** : Kyan et
Cyprien = même cluster → attribution effondrée. Forcer `num_speakers=4` aggrave
la fusion. Seule la voix **féminine** (Fanny) se détache. Cause intrinsèque :
audio mono compressé, rires, chevauchements, voix de jeunes hommes proches.

Le mapping timestamp → locuteur, lui, fonctionnait (Cyprien cohérent 10/10) :
c'est la **séparation des voix** qui casse, pas l'alignement.

## Autres pistes évaluées (toutes écartées)

| Piste | Verdict |
|---|---|
| **Audio Acast** (au lieu de YouTube) | Acoustiquement **identiques** (canal latéral L-R à -29,6 dB des deux côtés). YouTube = le master Acast. Inutile. |
| **Stéréo / panning** | Le stéréo présent est de l'**ambiance** (~11 dB sous le mid), pas un placement par locuteur. Inexploitable. |
| **Diariseur commercial** (Deepgram, AssemblyAI…) | Le meilleur pari restant, mais nécessite une clé API (non disponible). |
| **Détection par la vidéo** (ASD) | Visages **nets et identifiables** → le signal existe et casserait le mur audio. MAIS montage en **plans larges 2-3 personnes** (pas de coupe sur le speaker) → pas de raccourci, il faut le pipeline complet (TalkNet + reco faciale + enrôlement). Plusieurs jours d'ingé → disproportionné. |

## Décision

**On acte.** `recommendedBy` garde ses 17 attributions sûres (passe texte) ; le
reste reste vide là où c'est incertain — ce qui est la bonne réponse (« vide
plutôt que faux »). Aucune piste connue n'offre un gain raisonnable au coût
raisonnable. À rouvrir seulement avec une **clé de diariseur commercial** (test
à quelques euros) ou un vrai budget d'ingénierie pour la voie vidéo.
