# run_all.ps1 — Lanceur autonome du pipeline Reco (Windows / PowerShell).
#
# Conçu pour tourner SANS SURVEILLANCE : chaque étape est idempotente et reprend
# où elle s'est arrêtée. Relancer le script reprend simplement le travail restant.
#
# Découpage clé :
#   - fetch + transcribe : AUCUNE clé API requise (Whisper tourne en local).
#   - extract            : nécessite ANTHROPIC_API_KEY (dans tools/.env).
#
# Usage :
#   .\run_all.ps1                                  # tout, tous les épisodes
#   .\run_all.ps1 -Limit 3                         # validation rapide (3 ép.)
#   .\run_all.ps1 -Steps "fetch,transcribe"        # sans clé API
#   .\run_all.ps1 -Batch                           # extraction via Batch API (-50%)
#   .\run_all.ps1 -ExtractModel claude-haiku-4-5   # modèle d'extraction moins cher
#
param(
  [string]$Source = "un-bon-moment",
  [int]$Limit = 0,                              # 0 = tous les épisodes
  [string]$Steps = "fetch,transcribe,extract",
  [string]$WhisperModel = "small",              # modèle de transcription (local)
  [string]$ExtractModel = "claude-sonnet-4-6",  # modèle LLM d'extraction
  [switch]$Batch                                # Message Batches API (-50% de coût)
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1. venv + dépendances ------------------------------------------------------
if (-not (Test-Path ".venv\Scripts\python.exe")) {
  Write-Host "Création du venv..." -ForegroundColor Cyan
  python -m venv .venv
}
$py = ".\.venv\Scripts\python.exe"

Write-Host "Installation/MAJ des dépendances..." -ForegroundColor Cyan
& $py -m pip install --quiet -r requirements.txt

# 2. Garde-fou clé API si l'étape extract est demandée -----------------------
if ($Steps -match "extract") {
  $hasKey = (Test-Path ".env") -and ((Get-Content ".env" -Raw) -match "ANTHROPIC_API_KEY=\S")
  if (-not $hasKey) {
    Write-Host "ATTENTION : ANTHROPIC_API_KEY absente de tools/.env." -ForegroundColor Yellow
    Write-Host "  L'étape 'extract' sera ignorée. Renseigne la clé puis relance." -ForegroundColor Yellow
    $Steps = ($Steps -split "," | Where-Object { $_.Trim() -ne "extract" }) -join ","
    if ([string]::IsNullOrWhiteSpace($Steps)) {
      Write-Host "Rien à faire sans clé. Arrêt." -ForegroundColor Yellow
      exit 0
    }
  }
}

# 3. Lancement du pipeline ---------------------------------------------------
$pipelineArgs = @(
  "run_pipeline.py", "--source", $Source, "--steps", $Steps,
  "--whisper-model", $WhisperModel, "--extract-model", $ExtractModel
)
if ($Limit -gt 0) { $pipelineArgs += @("--limit", "$Limit") }
if ($Batch) { $pipelineArgs += "--batch" }

Write-Host "Lancement : python $($pipelineArgs -join ' ')" -ForegroundColor Green
& $py @pipelineArgs

Write-Host "Terminé. N'oublie pas de relire les recos (status draft -> validated)." -ForegroundColor Green
