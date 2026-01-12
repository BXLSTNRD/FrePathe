$ErrorActionPreference = "Stop"

# Ensure folders
if (!(Test-Path ".\data\projects")) { New-Item -ItemType Directory -Force -Path ".\data\projects" | Out-Null }
if (!(Test-Path ".\data\uploads")) { New-Item -ItemType Directory -Force -Path ".\data\uploads" | Out-Null }

# venv
if (!(Test-Path ".\.venv")) {
  python -m venv .venv
}

.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip | Out-Null
pip install -r requirements.txt | Out-Null

# Load keys from files
function Read-KeyFile($path) {
  if (!(Test-Path $path)) { return "" }
  return (Get-Content $path -Raw).Trim()
}

$env:FAL_KEY    = Read-KeyFile ".\fal_key.txt"
$env:OPENAI_KEY = Read-KeyFile ".\openai_key.txt"
$env:CLAUDE_KEY = Read-KeyFile ".\claude_key.txt"

Write-Host "Starting on http://127.0.0.1:8080"
uvicorn main:app --reload --host 127.0.0.1 --port 8080
