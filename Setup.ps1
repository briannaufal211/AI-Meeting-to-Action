param([string]$Python = 'python')
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
New-Item -ItemType Directory -Force -Path '.tmp' | Out-Null
$env:TEMP = (Resolve-Path '.tmp').Path
$env:TMP = $env:TEMP
if (-not (Get-Command $Python -ErrorAction SilentlyContinue) -and -not (Test-Path -LiteralPath $Python)) { throw 'Pasang Python 3.12 atau 3.13 terlebih dahulu.' }
if (-not (Test-Path '.venv/Scripts/python.exe')) {
    & $Python -m venv '.venv'
    if ($LASTEXITCODE -ne 0) { throw 'Pembuatan lingkungan Python gagal.' }
}
$requirements = if (Test-Path 'requirements-lock.txt') { 'requirements-lock.txt' } else { 'requirements.txt' }
& '.venv/Scripts/python.exe' -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'Pemasangan pustaka Python gagal. Periksa internet.' }
if (-not (Get-Command node -ErrorAction SilentlyContinue) -or -not (Get-Command npm.cmd -ErrorAction SilentlyContinue)) { throw 'Pasang Node.js LTS beserta npm, lalu jalankan Setup.ps1 kembali.' }
& npm.cmd install --ignore-scripts
if ($LASTEXITCODE -ne 0) { throw 'Pemasangan pustaka PowerPoint gagal.' }
if (-not (Test-Path '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env' }
Write-Host 'Pemasangan selesai. Isi OPENAI_API_KEY di .env, lalu buka Mulai.cmd.'
