$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'n8n-common.ps1')
$runtime = Join-Path $PSScriptRoot '.n8n-runtime'
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$spec = '{"name":"n8n-lokal-runtime","private":true,"dependencies":{"n8n":"2.45.5"}}'
[IO.File]::WriteAllText((Join-Path $runtime 'package.json'), $spec)
$runtimeLock = Join-Path $PSScriptRoot 'n8n-runtime-lock.json'
if (Test-Path -LiteralPath $runtimeLock) { Copy-Item -LiteralPath $runtimeLock -Destination (Join-Path $runtime 'package-lock.json') }
$installCommand = if (Test-Path (Join-Path $runtime 'package-lock.json')) { 'ci' } else { 'install' }
$npmCache = Join-Path $PSScriptRoot '.tools/npm-cache'
$npm = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($npm) {
    Push-Location $runtime
    try { & $npm.Source $installCommand --cache $npmCache --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw 'Pemasangan n8n gagal. Baca pesan di atas.' } }
    finally { Pop-Location }
} else {
    $tools = Join-Path $PSScriptRoot '.tools'
    $npmCli = Join-Path $tools 'npm/package/bin/npm-cli.js'
    if (-not (Test-Path -LiteralPath $npmCli)) {
        New-Item -ItemType Directory -Force -Path (Join-Path $tools 'npm') | Out-Null
        $archive = Join-Path $tools 'npm.tgz'
        Invoke-WebRequest -Uri 'https://registry.npmjs.org/npm/-/npm-10.9.2.tgz' -OutFile $archive
        & tar -xf $archive -C (Join-Path $tools 'npm')
        if ($LASTEXITCODE -ne 0) { throw 'Ekstraksi npm gagal.' }
    }
    Push-Location $runtime
    try { & $NodeExe $npmCli $installCommand --cache (Join-Path $tools 'npm-cache') --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw 'Pemasangan n8n gagal. Baca pesan di atas.' } }
    finally { Pop-Location }
}
Write-Host 'Pemasangan selesai. Buka Mulai-n8n.cmd dan buat akun pemilik lokal.'
