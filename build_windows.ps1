# FFmpeg GUI - Compilation Windows : un seul EXE avec icone
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

foreach ($file in @('main.py', 'requirements.txt', 'FFmpeg_GUI.ico')) {
    if (-not (Test-Path -LiteralPath $file -PathType Leaf)) {
        throw "Fichier requis introuvable : $file"
    }
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    $python = 'py'
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = 'python'
} else {
    throw 'Python introuvable.'
}

& $python -m pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw 'Installation des dependances echouee.' }

$iconPath = (Resolve-Path -LiteralPath '.\FFmpeg_GUI.ico').Path
& $python -m PyInstaller --noconfirm --clean --onefile --windowed --icon $iconPath --name FFmpeg_GUI main.py
if ($LASTEXITCODE -ne 0) { throw 'Compilation PyInstaller echouee.' }

$exe = Join-Path $PSScriptRoot 'dist\FFmpeg_GUI.exe'
if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "EXE introuvable apres compilation : $exe"
}
Write-Host "Compilation reussie : $exe" -ForegroundColor Green
Write-Host "Attention : l'ancien dossier dist\FFmpeg_GUI et l'ancien ZIP ne sont pas regeneres."
Write-Host 'FFmpeg est a installer separement : https://ffmpeg.org/download.html'
