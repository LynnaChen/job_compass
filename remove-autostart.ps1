Remove-ItemProperty -Path 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run' -Name 'JobCompassOpenSource' -ErrorAction SilentlyContinue
@{installed=$false} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'data\scheduler.json') -Encoding utf8
