$ErrorActionPreference = 'Stop'

# Reuse an existing healthy n8n instance instead of starting a duplicate.
try {
    $existingHealth = Invoke-RestMethod -Uri 'http://127.0.0.1:5678/healthz' -TimeoutSec 2
    $existingPage = Invoke-WebRequest -Uri 'http://127.0.0.1:5678/' -UseBasicParsing -TimeoutSec 2
    if ($existingHealth.status -eq 'ok' -and $existingPage.Content -match '(?i)n8n') {
        Write-Host 'n8n sudah berjalan. Buka http://localhost:5678 untuk memakai layanan yang sudah aktif.'
        exit 0
    }
} catch {
    # No healthy existing instance: continue with the normal startup below.
}

. (Join-Path $PSScriptRoot 'n8n-common.ps1')
if (-not (Test-Path -LiteralPath $N8nExe)) { throw 'Jalankan Pasang-n8n.ps1 terlebih dahulu.' }
Write-Host 'n8n lokal: http://localhost:5678. Biarkan jendela ini terbuka.'
& $NodeExe $N8nExe start

if ($LASTEXITCODE -ne 0) { throw 'n8n berhenti dengan kesalahan. Periksa pesan di atas.' }
