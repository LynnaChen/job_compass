$ErrorActionPreference = 'Stop'
$pythonPath = Join-Path $PSScriptRoot '.venv\Scripts\pythonw.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = (Get-Command pythonw.exe).Source }
$command = '"' + $pythonPath + '" "' + (Join-Path $PSScriptRoot 'app.py') + '"'
New-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'JobCompassOpenSource' -Value $command -PropertyType String -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'data') -Force | Out-Null
@{installed=$true;method='Windows current-user login startup'} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'data\scheduler.json') -Encoding utf8
Write-Output 'Open-source edition login startup enabled for the current user.'
