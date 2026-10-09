$ErrorActionPreference = 'Stop'
$taskRoot = $PSScriptRoot
$taskPort = if ($env:LAB_PORT) { $env:LAB_PORT } else { '5188' }
$taskUrl = "http://127.0.0.1:$taskPort"
$taskReady = $false
try {
    $taskCheck = Invoke-RestMethod "$taskUrl/api/curriculum" -TimeoutSec 2
    $taskReady = $taskCheck.experiments.Count -eq 10
} catch { }
if (-not $taskReady) {
    $taskPython = if (Test-Path -LiteralPath "$taskRoot/.venv/Scripts/python.exe") { "$taskRoot/.venv/Scripts/python.exe" } else { (Get-Command python).Source }
    & $taskPython -c 'import reportlab, pypdf, matplotlib'
    if ($LASTEXITCODE -ne 0) { throw '缺少依赖。请先在此目录运行 python -m pip install -r requirements.txt' }
    Start-Process -FilePath $taskPython -ArgumentList @('server.py') -WorkingDirectory $taskRoot -WindowStyle Hidden -RedirectStandardOutput "$taskRoot/server.log" -RedirectStandardError "$taskRoot/server-error.log"
    for ($taskAttempt = 0; $taskAttempt -lt 20; $taskAttempt++) {
        Start-Sleep -Milliseconds 250
        try { $taskCheck = Invoke-RestMethod "$taskUrl/api/curriculum" -TimeoutSec 1; if ($taskCheck.experiments.Count -eq 10) { $taskReady = $true; break } } catch { }
    }
    if (-not $taskReady) { throw '本地服务未能启动，请查看 server-error.log。端口被占用时可设置 LAB_PORT。' }
}
Start-Process $taskUrl
