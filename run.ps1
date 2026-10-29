$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Building the offline data pack..."
py -m georesponse.datapack

Write-Host "Building the web app..."
Push-Location web
if (-not (Test-Path node_modules)) { npm install }
npm run build
Pop-Location

Write-Host "Serving http://127.0.0.1:4173/ (Ctrl+C to stop)"
py -m georesponse.cli static --port 4173
