# scripts/check_and_update.ps1 — 새 13F-HR이 있으면 update(보고서 제외) → 섹터 보충 → export.
# 작업 스케줄러가 매일 실행한다 (등록·해제: _claude_docs/WORKFLOWS.md "새 공시 자동 확인·갱신").
# check-filings: exit 3 = 새 공시, 0 = 없음, 그 밖(1 Python 오류·2 확인 실패·-1 Python 실행 불가) = 갱신하지 않음.
# 로그: data/logs/check_and_update.log
# 갱신이 중간에 실패하면 data/logs/check_and_update.pending이 남아 다음 실행이 새 공시 없이도 다시 돈다.
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$py = Join-Path $PSScriptRoot 'py.ps1'
$log = Join-Path $root 'data\logs\check_and_update.log'
$pending = Join-Path $root 'data\logs\check_and_update.pending'
New-Item -ItemType Directory -Force (Split-Path $log) | Out-Null
$env:PYTHONUTF8 = '1'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Write-Log([string]$msg) {
    "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $msg" | Out-File -FilePath $log -Append -Encoding utf8
}

function Invoke-Step([string[]]$pyArgs) {
    Write-Log "> $($pyArgs -join ' ')"
    $global:LASTEXITCODE = -1  # Python을 띄우지 못하면 이 값이 남는다 (0으로 끝나 성공처럼 보이지 않게)
    & $py @pyArgs 2>&1 | ForEach-Object { "$_" } | Out-File -FilePath $log -Append -Encoding utf8
    return $LASTEXITCODE
}

$code = Invoke-Step @('-m', 'thirteen_f.cli', 'check-filings')
if ($code -ne 0 -and $code -ne 3) { Write-Log "check-filings 실패 (exit $code) — 갱신하지 않음"; exit $code }
if ($code -eq 0) {
    if (-not (Test-Path $pending)) { exit 0 }
    Write-Log '지난 갱신이 끝나지 않아 다시 실행'
}
New-Item -ItemType File -Force $pending | Out-Null

$steps = @(
    @('-m', 'thirteen_f.cli', 'update', '--skip-report'),
    @('scripts/supplement_sector.py'),
    @('-m', 'thirteen_f.cli', 'export')
)
foreach ($step in $steps) {
    $code = Invoke-Step $step
    if ($code -ne 0) { Write-Log "실패 (exit $code) — 중단"; exit $code }
}
Remove-Item $pending
Write-Log '갱신 완료'
