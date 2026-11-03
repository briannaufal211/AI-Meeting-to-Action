$ErrorActionPreference = 'Stop'
$ProjectRoot = $PSScriptRoot
$nodeCommand = Get-Command node -ErrorAction SilentlyContinue
$NodeExe = if ($nodeCommand) { $nodeCommand.Source } else { $null }
if (-not $NodeExe -and (Test-Path (Join-Path $ProjectRoot '.env'))) {
    $nodeSetting = Get-Content -LiteralPath (Join-Path $ProjectRoot '.env') | Where-Object { $_ -match '^NODE_EXE=' } | Select-Object -First 1
    if ($nodeSetting) { $NodeExe = $nodeSetting.Substring(9).Trim().Trim('"') }
}
if (-not $NodeExe -or -not (Test-Path -LiteralPath $NodeExe)) { throw 'Node.js belum ditemukan. Pasang Node.js LTS atau isi NODE_EXE di .env.' }
$N8nExe = Join-Path $ProjectRoot '.n8n-runtime/node_modules/n8n/bin/n8n'
$env:PATH = (Split-Path -Parent $NodeExe) + ';' + $env:PATH
$env:N8N_USER_FOLDER = Join-Path $ProjectRoot 'data/n8n'
$env:N8N_HOST = 'localhost'
$env:N8N_LISTEN_ADDRESS = '127.0.0.1'
$env:N8N_PORT = '5678'
$env:N8N_PROTOCOL = 'http'
$env:N8N_EDITOR_BASE_URL = 'http://localhost:5678'
$env:N8N_WEBHOOK_URL = 'http://localhost:5678'
$env:N8N_SECURE_COOKIE = 'false'
$env:N8N_DIAGNOSTICS_ENABLED = 'false'
$env:N8N_DEFAULT_BINARY_DATA_MODE = 'filesystem'
$env:N8N_PAYLOAD_SIZE_MAX = '320'
$env:N8N_FORMDATA_FILE_SIZE_MAX = '300'
$env:GENERIC_TIMEZONE = 'Asia/Jakarta'
$env:TZ = 'Asia/Jakarta'
$mkdirCompat = (Join-Path $ProjectRoot 'windows-mkdir.cjs').Replace([char]92, [char]47)
$env:NODE_OPTIONS = '--max-old-space-size=4096 --require="' + $mkdirCompat + '"'
New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot '.tmp') | Out-Null
$env:TEMP = Join-Path $ProjectRoot '.tmp'
$env:TMP = $env:TEMP
