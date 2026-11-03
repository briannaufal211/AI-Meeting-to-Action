$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'n8n-common.ps1')
if (-not (Test-Path -LiteralPath $N8nExe)) { throw 'Pasang n8n terlebih dahulu.' }
$tokenPath = Join-Path $PSScriptRoot 'data/local-token.txt'
if (-not (Test-Path -LiteralPath $tokenPath)) { throw 'Jalankan Mulai.cmd sekali agar token aplikasi dibuat.' }
$token = [IO.File]::ReadAllText($tokenPath).Trim()
$tempCredential = Join-Path $PSScriptRoot '.tmp/n8n-local-credential.json'
$credential = @(@{id='diskusiLocalToken';name='Token lokal aplikasi diskusi';type='httpHeaderAuth';data=@{name='X-Local-Token';value=$token}})
[IO.File]::WriteAllText($tempCredential, (ConvertTo-Json -InputObject $credential -Depth 5))
try {
    & $NodeExe $N8nExe import:credentials --input=$tempCredential
    if ($LASTEXITCODE -ne 0) { throw 'Import credential gagal. Buat akun pemilik n8n dan coba kembali.' }
    $workflowFile = Join-Path $PSScriptRoot 'n8n-workflow.json'
    & $NodeExe $N8nExe import:workflow "--input=$workflowFile"
    if ($LASTEXITCODE -ne 0) { throw 'Import workflow gagal.' }
} finally {
    if (Test-Path -LiteralPath $tempCredential) { Remove-Item -LiteralPath $tempCredential }
}
$formWorkflowFile = Join-Path $PSScriptRoot 'n8n-form-workflow.json'
if (Test-Path -LiteralPath $formWorkflowFile) {
    & $NodeExe $N8nExe import:workflow "--input=$formWorkflowFile"
    if ($LASTEXITCODE -ne 0) { throw 'Import workflow form gagal.' }
}
Write-Host 'Workflow utama, form unggah, dan credential lokal diimpor. Buka n8n lalu Publish kedua workflow.'
