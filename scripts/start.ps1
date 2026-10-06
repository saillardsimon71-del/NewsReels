$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Environnement .venv introuvable. Suivez d'abord les instructions d'installation du README."
}

& $python bridge.py
