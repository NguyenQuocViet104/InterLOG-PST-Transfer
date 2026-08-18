$ErrorActionPreference = "SilentlyContinue"
Import-Module BitsTransfer

$createdNew = $false
$mutex = New-Object System.Threading.Mutex($true, "Local\InterLOGPstTransferMonitor", [ref]$createdNew)
if (-not $createdNew) {
    $mutex.Dispose()
    exit 0
}

function Save-Receipt {
    param([string]$Path, [object]$Receipt)
    if ($Path) {
        $Receipt.updatedAt = [datetimeoffset]::Now.ToString("o")
        $Receipt | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $Path -Encoding UTF8
    }
}

try {
    while ($true) {
        $jobs = @(Get-BitsTransfer | Where-Object { $_.DisplayName -like "InterLOG PST:*" })
        if ($jobs.Count -eq 0) { break }

        foreach ($job in $jobs) {
            $receiptPath = [string]$job.Description
            $receipt = $null
            if ($receiptPath -and [System.IO.File]::Exists($receiptPath)) {
                try { $receipt = Get-Content -LiteralPath $receiptPath -Raw | ConvertFrom-Json } catch {}
            }
            if ($null -eq $receipt) { continue }

            $receipt.status = [string]$job.JobState
            $receipt.bytesTransferred = [int64]$job.BytesTransferred
            $receipt.bytesTotal = [int64]$job.BytesTotal
            $receipt.errorDescription = if ($job.ErrorDescription) { [string]$job.ErrorDescription } else { $null }
            $receipt.errorCode = if ($job.ErrorCode) { [string]$job.ErrorCode } else { $null }
            Save-Receipt $receiptPath $receipt

            switch ([string]$job.JobState) {
                "Transferred" {
                    try { $sourceNow = Get-Item -LiteralPath $receipt.sourcePath -Force }
                    catch {
                        $receipt.status = "WAITING_SOURCE_VERIFICATION"
                        Save-Receipt $receiptPath $receipt
                        continue
                    }
                    if (
                        [int64]$sourceNow.Length -ne [int64]$receipt.expectedBytes -or
                        $sourceNow.LastWriteTimeUtc.ToString("o") -ne [string]$receipt.sourceLastWriteUtc
                    ) {
                        Suspend-BitsTransfer $job
                        $receipt.status = "SOURCE_CHANGED_STOPPED"
                        Save-Receipt $receiptPath $receipt
                        continue
                    }

                    Complete-BitsTransfer $job
                    $destination = Get-Item -LiteralPath $receipt.destinationPath -Force
                    if ([int64]$destination.Length -ne [int64]$receipt.expectedBytes) {
                        $receipt.status = "SIZE_MISMATCH"
                        Save-Receipt $receiptPath $receipt
                        continue
                    }

                    if ([bool]$receipt.verifyHash) {
                        $receipt.status = "VERIFYING_SHA256"
                        Save-Receipt $receiptPath $receipt
                        $sourceHash = (Get-FileHash $receipt.sourcePath -Algorithm SHA256).Hash.ToLowerInvariant()
                        $destinationHash = (Get-FileHash $receipt.destinationPath -Algorithm SHA256).Hash.ToLowerInvariant()
                        $receipt.sourceSha256 = $sourceHash
                        $receipt.destinationSha256 = $destinationHash
                        if ($sourceHash -ne $destinationHash) {
                            $receipt.status = "HASH_MISMATCH"
                            Save-Receipt $receiptPath $receipt
                            continue
                        }
                    }

                    $receipt.status = "COMPLETE"
                    $completedAt = [datetimeoffset]::Now.ToString("o")
                    if ($receipt.PSObject.Properties.Name -contains "completedAt") {
                        $receipt.completedAt = $completedAt
                    }
                    else {
                        $receipt | Add-Member -NotePropertyName completedAt -NotePropertyValue $completedAt
                    }
                    Save-Receipt $receiptPath $receipt
                }
                "Suspended" { Resume-BitsTransfer $job -Asynchronous | Out-Null }
                "TransientError" { Resume-BitsTransfer $job -Asynchronous | Out-Null }
                "Error" {
                    $receipt.status = "ERROR"
                    Save-Receipt $receiptPath $receipt
                }
            }
        }
        Start-Sleep -Seconds 10
    }
}
finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
