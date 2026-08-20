param(
    [Parameter(Mandatory=$true)][int]$JobId,
    [Parameter(Mandatory=$true)][string]$ReceiptPath,
    [string]$DashboardUrl = "http://127.0.0.1:8080",
    [switch]$Watch
)

$ErrorActionPreference = "Stop"
$lastContent = ""

do {
    if (Test-Path -LiteralPath $ReceiptPath -PathType Leaf) {
        $content = Get-Content -LiteralPath $ReceiptPath -Raw
        if ($content -and $content -ne $lastContent) {
            $null = $content | ConvertFrom-Json
            Invoke-RestMethod -Method Post `
                -Uri "$($DashboardUrl.TrimEnd('/'))/api/jobs/$JobId/receipt" `
                -ContentType "application/json; charset=utf-8" `
                -Body ([Text.Encoding]::UTF8.GetBytes($content)) | Out-Null
            $lastContent = $content
            Write-Host "Receipt da gui len dashboard: $(Get-Date -Format s)"
        }
    }
    if ($Watch) { Start-Sleep -Seconds 10 }
} while ($Watch)
