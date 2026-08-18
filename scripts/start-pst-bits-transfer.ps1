param(
    [Parameter(Mandatory=$true)][string]$SourcePst,
    [Parameter(Mandatory=$true)][string]$DestinationDirectory,
    [switch]$VerifyHash,
    [switch]$NoStartupRegistration
)

$ErrorActionPreference = "Stop"
Import-Module BitsTransfer

$source = [System.IO.Path]::GetFullPath($SourcePst.Trim().Trim('"'))
$destinationRoot = [System.IO.Path]::GetFullPath($DestinationDirectory.Trim().Trim('"'))
if ([System.IO.Path]::GetExtension($source) -ine ".pst") { throw "Source must be a .pst file: $source" }
[System.IO.Directory]::CreateDirectory($destinationRoot) | Out-Null

$sourceFileName = [System.IO.Path]::GetFileName($source)
$destination = [System.IO.Path]::Combine($destinationRoot, $sourceFileName)
$receiptPath = "$destination.bits-receipt.json"

# Prevent duplicate jobs. A running BITS job can hold the source file open,
# which used to be reported incorrectly as "Outlook is locking the PST".
if ([System.IO.File]::Exists($receiptPath)) {
    try {
        $oldReceipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json
        $activeStates = @("QUEUED", "CONNECTING", "TRANSFERRING", "TRANSFERRING_BACKGROUND", "TRANSIENTERROR", "SUSPENDED", "TRANSFERRED", "WAITING_SOURCE_VERIFICATION", "VERIFYING_SHA256")
        if ($activeStates -contains ([string]$oldReceipt.status).ToUpperInvariant()) {
            $oldJob = Get-BitsTransfer -ErrorAction SilentlyContinue | Where-Object { $_.JobId.ToString() -eq [string]$oldReceipt.bitsJobId } | Select-Object -First 1
            if ($oldJob) {
                Write-Output (@{status="ALREADY_RUNNING";jobId=$oldJob.JobId.ToString();jobState=[string]$oldJob.JobState;destination=$destination;receipt=$receiptPath} | ConvertTo-Json -Compress)
                exit 0
            }
        }
    }
    catch {}
}

if (-not [System.IO.File]::Exists($source)) { throw "Source PST is not accessible: $source" }
$sourceItem = Get-Item -LiteralPath $source -Force

if ([System.IO.File]::Exists($destination)) {
    $existing = Get-Item -LiteralPath $destination -Force
    if ($existing.Length -eq $sourceItem.Length) {
        Write-Output (@{status="COMPLETE_EXISTING"; destination=$destination} | ConvertTo-Json -Compress)
        exit 0
    }
    throw "A partial destination already exists. Move it aside before starting a new BITS job: $destination"
}

try {
    $lockTest = [System.IO.File]::Open($source,[System.IO.FileMode]::Open,[System.IO.FileAccess]::Read,[System.IO.FileShare]::None)
    $lockTest.Dispose()
}
catch { throw "Source PST is locked. Finish export and close Outlook on the VM first." }

$safeName = [System.IO.Path]::GetFileNameWithoutExtension($sourceItem.Name) -replace '[^A-Za-z0-9._-]', '_'
$receipt = [ordered]@{
    schemaVersion=1; engine="BITS"; status="QUEUED"; sourcePath=$source; destinationPath=$destination
    expectedBytes=[int64]$sourceItem.Length; sourceLastWriteUtc=$sourceItem.LastWriteTimeUtc.ToString("o")
    verifyHash=[bool]$VerifyHash; createdAt=[datetimeoffset]::Now.ToString("o"); updatedAt=[datetimeoffset]::Now.ToString("o")
    completedAt=$null
    bitsJobId=$null; bytesTransferred=0; bytesTotal=[int64]$sourceItem.Length
    sourceSha256=$null; destinationSha256=$null; errorDescription=$null; errorCode=$null
}
$receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $receiptPath -Encoding UTF8

$displayName = "InterLOG PST:{0}:{1}" -f $safeName, [guid]::NewGuid().ToString('N')
$job = Start-BitsTransfer -Source $source -Destination $destination -DisplayName $displayName -Description $receiptPath -Priority Low -Asynchronous
$receipt["bitsJobId"]=$job.JobId.ToString(); $receipt["status"]="TRANSFERRING_BACKGROUND"
$receipt | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $receiptPath -Encoding UTF8

$monitor = Join-Path $PSScriptRoot "monitor-pst-bits-transfers.ps1"
if (-not $NoStartupRegistration) {
    $runCommand = 'powershell.exe -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $monitor + '"'
    New-ItemProperty -Path "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run" -Name "InterLOGPstTransferMonitor" -Value $runCommand -PropertyType String -Force | Out-Null
}
Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile","-ExecutionPolicy","Bypass","-WindowStyle","Hidden","-File",('"'+$monitor+'"')) -WindowStyle Hidden
Write-Output (@{status="TRANSFERRING_BACKGROUND";jobId=$job.JobId.ToString();source=$source;destination=$destination;receipt=$receiptPath} | ConvertTo-Json -Compress)
