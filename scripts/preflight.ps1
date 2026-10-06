$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Environnement .venv introuvable."
}

$code = @'
from newsreel.config import Settings
from newsreel.h3_worker_contract import ModalH3Renderer
from newsreel.media import require_media_tools

settings = Settings.from_env()
ffmpeg, ffprobe = require_media_tools(settings)
print(f"FFmpeg OK: {ffmpeg}")
print(f"ffprobe OK: {ffprobe}")
ModalH3Renderer(settings.modal_app_name, settings.modal_function_name).check_available()
print(f"Modal OK: {settings.modal_app_name}/{settings.modal_function_name}")
print("Preflight NewsReel OK")
'@

$tempScript = Join-Path ([System.IO.Path]::GetTempPath()) ("newsreel-preflight-" + [guid]::NewGuid().ToString("N") + ".py")
try {
    [System.IO.File]::WriteAllText($tempScript, $code, [System.Text.UTF8Encoding]::new($false))
    & $python $tempScript
    if ($LASTEXITCODE -ne 0) {
        throw "Le preflight Python a échoué avec le code $LASTEXITCODE."
    }
}
finally {
    Remove-Item $tempScript -Force -ErrorAction SilentlyContinue
}
