param([int]$ApiPort = 8000, [int]$FrontendPort = 5173, [string]$EvidenceDir = 'docs/evidence/round03')
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonExe = Join-Path $projectRoot '.venv/Scripts/python.exe'
$nodeDirectory = Get-ChildItem -LiteralPath (Join-Path $projectRoot '.tools') -Directory -Filter 'node-v24*-win-x64' | Sort-Object LastWriteTime -Descending | Select-Object -First 1
$nodeExe = if ($nodeDirectory) { Join-Path $nodeDirectory.FullName 'node.exe' } else { (Get-Command node -ErrorAction Stop).Source }
function Find-FreePort([int]$firstPort) {
    for ($candidate = $firstPort; $candidate -lt $firstPort + 100; $candidate++) {
        $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $candidate)
        try { $listener.Start(); return $candidate } catch {} finally { $listener.Stop() }
    }
    throw 'No free local port found'
}
$ApiPort = Find-FreePort $ApiPort
$FrontendPort = Find-FreePort $FrontendPort
$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$evidenceDirectory = Join-Path $projectRoot $EvidenceDir
New-Item -ItemType Directory -Path $evidenceDirectory -Force | Out-Null
$apiProcess = Start-Process -FilePath $pythonExe -ArgumentList @('-m','uvicorn','backend.app:app','--host','127.0.0.1','--port',"$ApiPort") -WorkingDirectory $projectRoot -WindowStyle Hidden -RedirectStandardOutput (Join-Path $evidenceDirectory "api_${stamp}_stdout.txt") -RedirectStandardError (Join-Path $evidenceDirectory "api_${stamp}_stderr.txt") -PassThru
$previousApiUrl = $env:CAMPUSBITE_API
try {
    $env:CAMPUSBITE_API = "http://127.0.0.1:$ApiPort"
    $viteScript = Join-Path $projectRoot 'frontend/node_modules/vite/bin/vite.js'
    $frontendProcess = Start-Process -FilePath $nodeExe -ArgumentList @("`"$viteScript`"",'--host','127.0.0.1','--port',"$FrontendPort",'--strictPort') -WorkingDirectory (Join-Path $projectRoot 'frontend') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $evidenceDirectory "vite_${stamp}_stdout.txt") -RedirectStandardError (Join-Path $evidenceDirectory "vite_${stamp}_stderr.txt") -PassThru
} finally { $env:CAMPUSBITE_API = $previousApiUrl }
$serverInfo = [ordered]@{started_at=(Get-Date).ToString('o');api_url="http://127.0.0.1:$ApiPort";frontend_url="http://127.0.0.1:$FrontendPort";api_pid=$apiProcess.Id;frontend_pid=$frontendProcess.Id}
$serverInfo | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $projectRoot '.tools/dev-server.json')
$serverInfo | ConvertTo-Json | Set-Content -Encoding UTF8 -LiteralPath (Join-Path $evidenceDirectory "servers_${stamp}.json")
for ($attempt = 0; $attempt -lt 30; $attempt++) {
    try {
        $apiResponse = Invoke-WebRequest -UseBasicParsing -Uri "$($serverInfo.api_url)/api/dishes" -TimeoutSec 2
        $frontendResponse = Invoke-WebRequest -UseBasicParsing -Uri $serverInfo.frontend_url -TimeoutSec 2
        if ($apiResponse.StatusCode -eq 200 -and $frontendResponse.StatusCode -eq 200) {
            Write-Output "API: $($serverInfo.api_url)"
            Write-Output "Frontend: $($serverInfo.frontend_url)"
            exit 0
        }
    } catch {}
    Start-Sleep -Milliseconds 500
}
throw 'Development services did not become ready; inspect the saved server logs.'
