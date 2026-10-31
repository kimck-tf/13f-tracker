# scripts/py.ps1 — Smart App Control이 .venv\Scripts\python.exe(uv 런처)를 막을 때
# pyvenv.cfg의 home 인터프리터를 직접 실행한다. 사용: scripts\py.ps1 -m pytest tests/unit -q
$root = Split-Path $PSScriptRoot -Parent
$cfg = Get-Content (Join-Path $root '.venv\pyvenv.cfg')
$home_ = ($cfg | Select-String '^home = (.+)$').Matches[0].Groups[1].Value.Trim()
$python = Join-Path $home_ 'python.exe'
$env:PYTHONPATH = "$root;$root\src;$root\.venv\Lib\site-packages"
& $python @args
exit $LASTEXITCODE
