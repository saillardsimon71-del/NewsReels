$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$modal = Join-Path $root ".venv\Scripts\modal.exe"
if (-not (Test-Path $modal)) {
    throw "CLI Modal introuvable dans .venv. Lancez: python -m pip install -r requirements-modal.txt"
}

& $modal deploy modal_h3.py
