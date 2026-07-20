# LLM local sur `llm.local`

Ce document decrit l'installation realisee sur la machine externe `llm.local`,
son usage depuis ce repo, et les resultats du premier benchmark sur les
transcripts de `un-bon-moment`.

Date du compte rendu : 2026-05-28.

## Objectif

Faire tourner un LLM local sur la machine `llm.local` pour extraire les
recommandations des transcripts du podcast, puis comparer les resultats avec
les extractions deja produites par deux modeles distants.

Le but final est de savoir si ce LLM local peut devenir le fournisseur par
defaut pour ce type de tache.

## Etat actuel

L'installation fonctionne.

Le serveur OpenAI-compatible de `llama.cpp` tourne avec le modele
`Qwen3-4B-Q4_K_M.gguf`. Depuis le 2026-06-21 il est gere par un service
`systemd` utilisateur (voir « Demarrage automatique » plus bas) et demarre
au boot ; avant cela il etait lance manuellement.

Endpoint :

```text
http://llm.local:8080/v1
```

Alias du modele :

```text
qwen3-4b-q4_k_m
```

Conclusion du premier benchmark : le setup est utilisable techniquement, mais
pas encore assez fiable ni assez rapide pour remplacer directement
`gpt-4o-mini`, Claude Haiku ou Claude Sonnet sur l'extraction de
recommandations. Le modele extrait trop de simples mentions comme des
recommandations.

## Machine cible

Machine externe :

```text
llm@llm.local
```

Caracteristiques observees :

```text
OS      : Ubuntu 24.04.4 LTS
CPU     : Intel Core i5-7200U, 4 threads
RAM     : 15 GiB
Swap    : 11 GiB
GPU     : NVIDIA GeForce GTX 950M
VRAM    : 4096 MiB
Driver  : NVIDIA 535.309.01
CUDA    : 12.2
Disque  : environ 71 GiB libres au moment de l'installation
```

Outils presents au moment de l'audit :

```text
git
cmake
nvcc
gcc
python3
curl
```

Connexion SSH depuis cette machine Windows :

```powershell
ssh -i $env:USERPROFILE\.ssh\reco_laptop -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 llm@llm.local
```

## Installation realisee

### 1. Recuperer `llama.cpp`

Sur `llm.local` :

```bash
cd ~
git clone --depth 1 https://github.com/ggml-org/llama.cpp
cd ~/llama.cpp
```

### 2. Compiler avec CUDA pour la GTX 950M

La GTX 950M correspond a l'architecture CUDA `50` / Maxwell. Le build doit
donc expliciter cette architecture.

```bash
cd ~/llama.cpp
cmake -B build -DGGML_CUDA=ON -DCMAKE_CUDA_ARCHITECTURES=50 -DCMAKE_BUILD_TYPE=Release
cmake --build build --target llama-server --config Release -j3
```

Version observee apres compilation :

```text
llama.cpp version: 1 (ba4dd0b), built with GNU 13.3.0
```

Log utile :

```text
~/llama_build.log
```

### 3. Telecharger le modele

Modele installe :

```text
~/models/Qwen3-4B-Q4_K_M.gguf
```

Taille observee :

```text
2.4G
```

Commande :

```bash
mkdir -p ~/models
curl -L -C - --fail \
  -o ~/models/Qwen3-4B-Q4_K_M.gguf \
  https://huggingface.co/Qwen/Qwen3-4B-GGUF/resolve/main/Qwen3-4B-Q4_K_M.gguf
```

Log utile :

```text
~/qwen_download.log
```

## Lancer le serveur

Commande stable observee :

```bash
cd ~/llama.cpp
nohup build/bin/llama-server \
  -m ~/models/Qwen3-4B-Q4_K_M.gguf \
  --alias qwen3-4b-q4_k_m \
  --host 0.0.0.0 \
  --port 8080 \
  -c 8192 \
  -np 1 \
  -ngl 99 \
  --reasoning off \
  --reasoning-budget 0 \
  > ~/llama_server.log 2>&1 < /dev/null &
```

Parametres importants :

- `--host 0.0.0.0` expose le serveur sur le reseau local.
- `--port 8080` fixe le port HTTP.
- `-c 8192` fixe le contexte a 8192 tokens. C'est le maximum stable observe.
- `-np 1` limite a une sequence parallele pour reduire la VRAM.
- `-ngl 99` offload autant de couches que possible sur le GPU.
- `--reasoning off --reasoning-budget 0` coupe le mode raisonnement de Qwen3.
  Sans cela, le modele produit plus facilement des sorties longues ou non JSON.

Log serveur :

```text
~/llama_server.log
```

Verifier que le process tourne :

```bash
pgrep -af llama-server
```

Verifier la VRAM :

```bash
nvidia-smi
```

## Verifier depuis Windows

Healthcheck :

```powershell
Invoke-WebRequest -UseBasicParsing -Uri http://llm.local:8080/health -TimeoutSec 10
```

Reponse attendue :

```json
{"status":"ok"}
```

Si `llm.local` ne se resout pas, utiliser l'IP locale observee :

```text
192.168.1.127
```

Exemple :

```powershell
Invoke-WebRequest -UseBasicParsing -Uri http://192.168.1.127:8080/health -TimeoutSec 10
```

## Appeler le modele directement

Le serveur expose une API compatible OpenAI.

Exemple PowerShell :

```powershell
$body = @{
  model = "qwen3-4b-q4_k_m"
  messages = @(
    @{ role = "system"; content = "Tu extrais uniquement les recommandations explicites." },
    @{ role = "user"; content = "Extrait les recommandations de ce court texte: On conseille le film Heat et le livre Dune." }
  )
  temperature = 0
  max_tokens = 300
} | ConvertTo-Json -Depth 10

Invoke-RestMethod `
  -Method Post `
  -Uri "http://llm.local:8080/v1/chat/completions" `
  -ContentType "application/json" `
  -Body $body
```

Equivalent avec l'IP :

```powershell
Invoke-RestMethod `
  -Method Post `
  -Uri "http://192.168.1.127:8080/v1/chat/completions" `
  -ContentType "application/json" `
  -Body $body
```

## Utilisation avec ce repo

Le script dedie est :

```text
tools/eval_local_llm.py
```

Il sert a comparer une extraction locale avec les recommandations deja
presentes dans `src/content/recos`.

Il ne modifie pas les fichiers publics de recommandations. Il ecrit un rapport
JSON dans :

```text
tools/output/local_llm_eval/
```

### Dry run

```powershell
tools\.venv\Scripts\python.exe tools\eval_local_llm.py --limit 10 --dry-run
```

### Smoke test rapide

```powershell
tools\.venv\Scripts\python.exe tools\eval_local_llm.py `
  --limit 1 `
  --max-chunks 1 `
  --chunk-chars 8000 `
  --timeout 900 `
  --base-url http://llm.local:8080/v1 `
  --model qwen3-4b-q4_k_m `
  --output tools\output\local_llm_eval\qwen3-4b-smoke-no-reasoning.json
```

### Benchmark 10 episodes

Commande utilisee pour le benchmark :

```powershell
tools\.venv\Scripts\python.exe tools\eval_local_llm.py `
  --limit 10 `
  --max-tokens 600 `
  --timeout 1200 `
  --base-url http://llm.local:8080/v1 `
  --model qwen3-4b-q4_k_m `
  --output tools\output\local_llm_eval\qwen3-4b-10-c8k-no-reasoning-m600.json
```

Option fallback si DNS instable :

```powershell
--base-url http://192.168.1.127:8080/v1
```

Parametres implicites importants du run :

```text
chunk-chars         : 8000
chunk-overlap-chars : 500
max-tokens          : 600
temperature         : 0
timeout             : 1200 secondes
```

## Resultats du benchmark

Fichier produit :

```text
tools/output/local_llm_eval/qwen3-4b-10-c8k-no-reasoning-m600.json
```

Synthese :

```text
Episodes testes      : 10
References existantes: 118
Extractions locales  : 285
Matches              : 65
Recall               : 55.1%
Precision proxy      : 22.8%
Duree                : environ 5h56
Chunks traites       : 206
Warnings             : 21 reponses locales non JSON ignorees
Erreurs              : 3
```

Details par episode :

```text
2026-05-25 S5E32 :  1/1  match, 16 local, recall 100.0%, precision  6.3%, erreurs 0
2026-05-18 S5E31 :  4/5  match, 28 local, recall  80.0%, precision 14.3%, erreurs 0
2026-05-11 S5E30 :  0/9  match, 23 local, recall   0.0%, precision  0.0%, erreurs 0
2026-05-04 S5E29 : 10/12 match, 34 local, recall  83.3%, precision 29.4%, erreurs 0
2026-04-27 S5E28 :  4/18 match, 19 local, recall  22.2%, precision 21.1%, erreurs 0
2026-04-20 S5E27 :  9/14 match, 30 local, recall  64.3%, precision 30.0%, erreurs 0
2026-04-13 S5E26 :  8/18 match, 28 local, recall  44.4%, precision 28.6%, erreurs 1
2026-04-06 S5E25 :  3/7  match, 24 local, recall  42.9%, precision 12.5%, erreurs 0
2026-03-30 S5E24 :  9/12 match, 35 local, recall  75.0%, precision 25.7%, erreurs 2
2026-03-23 S5E23 : 17/22 match, 48 local, recall  77.3%, precision 35.4%, erreurs 0
```

Exemples de faux positifs observes :

```text
Dame Saw
Scred
Akeleton
Justin Trudeau
Jackie Chan
Marlon Brando
Spider-Man
YouTube
Tibo InShape
Prime Video
```

Ces elements semblent etre de simples mentions, pas des recommandations
explicites.

## Limites observees

### Qualite

Le modele local detecte une partie significative des recommandations, mais il
sur-extrait beaucoup. Le score de recall est correct pour un premier essai,
mais la precision proxy est trop basse pour un usage automatique en priorite.

En l'etat, il vaut mieux l'utiliser comme :

- outil de pre-filtrage ;
- fournisseur secondaire ;
- banc de test pour ameliorer les prompts et les filtres.

### Performance

Le benchmark de 10 episodes a dure environ 5h56, ce qui est lent pour un usage
de production sur un volume important.

### Memoire GPU

La configuration stable est :

```text
-c 8192 -np 1 -ngl 99
```

Un essai avec un contexte plus grand :

```text
-c 16384 -np 1 -ngl 99
```

a echoue par manque de VRAM avec une erreur `cudaMalloc failed`.

### Temperature

Pendant le benchmark long, la temperature GPU a ete observee autour de
88-92 degres Celsius. C'est a surveiller pour des runs prolonges.

### DNS local

Quelques erreurs venaient de la resolution de `llm.local`. Si cela revient,
utiliser directement :

```text
192.168.1.127
```

## Arreter le serveur

Methode recommandee :

```bash
pgrep -af llama-server
kill -TERM <PID>
```

Depuis Windows en SSH :

```powershell
ssh -i $env:USERPROFILE\.ssh\reco_laptop -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 llm@llm.local "pgrep -af llama-server"
ssh -i $env:USERPROFILE\.ssh\reco_laptop -o BatchMode=yes -o StrictHostKeyChecking=accept-new -o ConnectTimeout=8 llm@llm.local "kill -TERM <PID>"
```

Verification apres arret :

```powershell
Invoke-WebRequest -UseBasicParsing -Uri http://llm.local:8080/health -TimeoutSec 10
```

Si le serveur est bien arrete, la requete doit echouer ou expirer.

## Demarrage automatique (service systemd utilisateur)

Depuis le 2026-06-21, le serveur est gere par un service `systemd` *utilisateur*
(pas de `sudo` sur la machine, donc pas de service systeme). Il demarre au boot
et redemarre en cas de crash : plus besoin de le relancer apres un reboot.

- Unite : `~/.config/systemd/user/llama-server.service`
- Linger active : `loginctl enable-linger llm` (demarrage sans login)

Gestion (en SSH non-interactif, prefixer `XDG_RUNTIME_DIR=/run/user/1000`) :

```bash
systemctl --user status  llama-server
systemctl --user restart llama-server   # ex. apres changement de modele
systemctl --user stop    llama-server
journalctl --user -u llama-server -f
```

### Lancement manuel (fallback si le service est desactive)

Si le service est arrete/desactive, relancer le serveur manuellement :

```bash
cd ~/llama.cpp
nohup build/bin/llama-server \
  -m ~/models/Qwen3-4B-Q4_K_M.gguf \
  --alias qwen3-4b-q4_k_m \
  --host 0.0.0.0 \
  --port 8080 \
  -c 8192 \
  -np 1 \
  -ngl 99 \
  --reasoning off \
  --reasoning-budget 0 \
  > ~/llama_server.log 2>&1 < /dev/null &
```

## Recommandation actuelle

Ne pas encore utiliser ce LLM local comme fournisseur prioritaire pour
l'extraction finale des recommandations.

La prochaine etape utile serait de reduire les faux positifs avant de refaire
un benchmark :

- prompt plus strict sur la notion de recommandation explicite ;
- post-filtrage des entites seulement mentionnees ;
- seuil minimum sur le contexte autour de la reco ;
- eventuellement seconde passe de validation locale sur les candidats.

Si la precision remonte fortement, ce serveur pourra ensuite etre branche comme
provider local dans le pipeline principal d'extraction.
