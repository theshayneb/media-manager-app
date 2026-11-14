# Builds dist\MediaManager\MediaManager.exe (with ExifTool and ffmpeg bundled).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root
if (-not (Test-Path "vendor\exiftool\exiftool.exe")) { & "$PSScriptRoot\get-exiftool.ps1" }
if (-not (Test-Path "vendor\ffmpeg\ffmpeg.exe")) { & "$PSScriptRoot\get-ffmpeg.ps1" }
python -m PyInstaller --noconfirm --clean --windowed --name MediaManager `
    --collect-all pillow_heif `
    --add-data "vendor\exiftool;exiftool" `
    --add-data "vendor\ffmpeg;ffmpeg" `
    --add-data "media_manager\assets;media_manager\assets" `
    --add-data "photo_manager\assets;photo_manager\assets" `
    --add-data "music_manager\assets;music_manager\assets" `
    --icon "media_manager\assets\icon.ico" `
    media_manager\__main__.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed" }
