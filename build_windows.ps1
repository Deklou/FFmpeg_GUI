# Exécuter depuis Windows PowerShell : .\build_windows.ps1
$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot

if (!(Test-Path '.\requirements.txt') -or !(Test-Path '.\main.py')) {
    throw 'Place ce script dans le dossier racine de FFmpeg_GUI (avec main.py et requirements.txt).'
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    $python = 'py'
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = 'python'
} else {
    throw 'Python est introuvable. Installe Python pour compiler l’application.'
}

Write-Host 'Installation des dépendances de compilation...'
& $python -m pip install -r requirements.txt pyinstaller
if ($LASTEXITCODE -ne 0) { throw 'Echec installation des dépendances.' }

Write-Host 'Compilation de FFmpeg GUI...'
& $python -m PyInstaller --noconfirm --clean --onedir --windowed --name FFmpeg_GUI main.py
if ($LASTEXITCODE -ne 0) { throw 'Echec compilation PyInstaller.' }

$releaseDir = Join-Path $PSScriptRoot 'dist\FFmpeg_GUI'
$exe = Join-Path $releaseDir 'FFmpeg_GUI.exe'
if (!(Test-Path $exe)) { throw "Exécutable absent : $exe" }

$zip = Join-Path $PSScriptRoot 'dist\FFmpeg_GUI_Windows_portable.zip'
if (Test-Path $zip) { Remove-Item $zip -Force }
Compress-Archive -Path (Join-Path $releaseDir '*') -DestinationPath $zip -CompressionLevel Optimal
Write-Host "Exécutable : $exe"
Write-Host "ZIP portable : $zip"
Write-Host 'FFmpeg est à télécharger séparément sur https://ffmpeg.org/download.html'
