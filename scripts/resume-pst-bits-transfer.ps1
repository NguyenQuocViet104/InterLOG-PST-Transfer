param(
    [Parameter(Mandatory=$true)][string]$DestinationDirectory
)

$ErrorActionPreference = "Stop"
Import-Module BitsTransfer

function Start-TransferMonitor {
    $monitorPath = Join-Path $PSScriptRoot "monitor-pst-bits-transfers.ps1"
    Start-Process -FilePath "powershell.exe" -ArgumentList @(
        "-NoProfile", "-ExecutionPolicy", "Bypass", "-WindowStyle", "Hidden",
        "-File", ('"' + $monitorPath + '"')
    ) -WindowStyle Hidden
}

$destinationRoot = [System.IO.Path]::GetFullPath($DestinationDirectory.Trim().Trim('"'))
if (-not [System.IO.Directory]::Exists($destinationRoot)) {
    throw "Destination directory does not exist: $destinationRoot"
}

$receiptFile = Get-ChildItem -LiteralPath $destinationRoot -Filter "*.pst.bits-receipt.json" -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1
if (-not $receiptFile) { throw "No BITS receipt was found in: $destinationRoot" }

$receipt = Get-Content -LiteralPath $receiptFile.FullName -Raw | ConvertFrom-Json
$destination = [string]$receipt.destinationPath
$expectedBytes = [int64]$receipt.expectedBytes

if (
    [string]$receipt.status -eq "COMPLETE" -and
    [System.IO.File]::Exists($destination) -and
    (Get-Item -LiteralPath $destination -Force).Length -eq $expectedBytes
) {
    Write-Output (@{status="COMPLETE";destination=$destination;receipt=$receiptFile.FullName} | ConvertTo-Json -Compress)
    exit 0
}

$job = Get-BitsTransfer -ErrorAction SilentlyContinue |
    Where-Object { $_.JobId.ToString() -eq [string]$receipt.bitsJobId } |
    Select-Object -First 1

if (-not $job) {
    if ([System.IO.File]::Exists($destination) -and (Get-Item -LiteralPath $destination -Force).Length -eq $expectedBytes) {
        Write-Output (@{status="COMPLETE_EXISTING";destination=$destination;receipt=$receiptFile.FullName} | ConvertTo-Json -Compress)
        exit 0
    }
    throw "The BITS job no longer exists. Keep the receipt and source PST for diagnosis."
}

try { $source = Get-Item -LiteralPath ([string]$receipt.sourcePath) -Force }
catch {
    Write-Output (@{
        status="SOURCE_UNAVAILABLE"; jobId=$job.JobId.ToString(); jobState=[string]$job.JobState
        source=[string]$receipt.sourcePath; error=$_.Exception.Message
    } | ConvertTo-Json -Compress)
    exit 0
}

if ($source.Length -ne $expectedBytes -or $source.LastWriteTimeUtc.ToString("o") -ne [string]$receipt.sourceLastWriteUtc) {
    Write-Output (@{
        status="SOURCE_CHANGED"; jobId=$job.JobId.ToString(); source=$source.FullName
        expectedBytes=$expectedBytes; actualBytes=[int64]$source.Length
    } | ConvertTo-Json -Compress)
    exit 0
}

$before = [string]$job.JobState
if ($before -in @("Suspended", "TransientError", "Error")) {
    Resume-BitsTransfer -BitsJob $job -Asynchronous | Out-Null
}
Start-TransferMonitor

Write-Output (@{
    status="RESUME_REQUESTED"; jobId=$job.JobId.ToString(); previousState=$before
    bytesTransferred=[int64]$job.BytesTransferred; bytesTotal=[int64]$job.BytesTotal
    source=$source.FullName; destination=$destination; receipt=$receiptFile.FullName
} | ConvertTo-Json -Compress)
