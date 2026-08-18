$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
[System.Windows.Forms.Application]::EnableVisualStyles()

$packageRoot = $PSScriptRoot
$scriptsRoot = Join-Path $packageRoot "scripts"
$bitsScript = Join-Path $scriptsRoot "start-pst-bits-transfer.ps1"

function Quote-Argument {
    param([string]$Value)
    return '"' + $Value.Replace('"', '\"') + '"'
}

function Browse-Pst {
    $dialog = New-Object System.Windows.Forms.OpenFileDialog
    $dialog.Title = "Chon file PST tren may ao/share"
    $dialog.Filter = "Outlook Data File (*.pst)|*.pst|All files (*.*)|*.*"
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $sourceBox.Text = $dialog.FileName
    }
}

function Browse-Destination {
    $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
    $dialog.Description = "Chon thu muc local tren may user"
    if ($dialog.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) {
        $destinationBox.Text = $dialog.SelectedPath
    }
}

function Show-JobStatus {
    $destination = $destinationBox.Text.Trim().Trim('"')
    if (-not $destination -or -not [System.IO.Directory]::Exists($destination)) {
        [System.Windows.Forms.MessageBox]::Show("Chua co thu muc dich hop le.", "InterLOG PST Transfer") | Out-Null
        return
    }
    $receipt = Get-ChildItem -LiteralPath $destination -Filter "*.pst.bits-receipt.json" -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $receipt) {
        [System.Windows.Forms.MessageBox]::Show("Khong tim thay job BITS trong thu muc dich.", "InterLOG PST Transfer") | Out-Null
        return
    }
    try {
        $data = Get-Content -LiteralPath $receipt.FullName -Raw | ConvertFrom-Json
        $done = [double]($data.bytesTransferred)
        $total = [double]($data.bytesTotal)
        if ($total -le 0) { $total = [double]($data.expectedBytes) }
        $percent = if ($total -gt 0) { ($done / $total) * 100 } else { 0 }
        $message = "Trang thai: $($data.status)`r`nTien do: $([math]::Round($percent,1))%`r`nDa chuyen: $([math]::Round($done/1GB,2)) / $([math]::Round($total/1GB,2)) GB`r`nDich: $($data.destinationPath)"
        if ($data.errorDescription) { $message += "`r`n`r`nLoi: $($data.errorDescription)" }
        if ($data.errorCode) { $message += "`r`nMa loi: $($data.errorCode)" }
        [System.Windows.Forms.MessageBox]::Show($message, "Job chuyen PST nen") | Out-Null
        $statusLabel.Text = "Trang thai: $($data.status) - $([math]::Round($percent,1))%"
    }
    catch {
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "Khong doc duoc receipt") | Out-Null
    }
}

function Start-BackgroundTransfer {
    if (-not $exportDone.Checked) {
        [System.Windows.Forms.MessageBox]::Show("Hay xac nhan export da xong va Outlook tren VM da dong.", "Chua xong buoc 1") | Out-Null
        return
    }
    $source = $sourceBox.Text.Trim().Trim('"')
    $destination = $destinationBox.Text.Trim().Trim('"')
    if (-not $source.EndsWith(".pst", [System.StringComparison]::OrdinalIgnoreCase) -or -not [System.IO.File]::Exists($source)) {
        [System.Windows.Forms.MessageBox]::Show("Khong truy cap duoc PST nguon:`r`n$source", "PST nguon khong hop le") | Out-Null
        return
    }
    if (-not $destination) {
        [System.Windows.Forms.MessageBox]::Show("Hay chon thu muc local tren may user.", "Thieu thu muc dich") | Out-Null
        return
    }
    if ($destination.StartsWith("\\")) {
        [System.Windows.Forms.MessageBox]::Show("Thu muc dich phai nam local tren may user, vi du D:\MAIL BACKUP.", "Sai chieu copy") | Out-Null
        return
    }
    if (-not [System.IO.File]::Exists($bitsScript)) {
        [System.Windows.Forms.MessageBox]::Show("Thieu script: $bitsScript", "Goi cong cu bi thieu file") | Out-Null
        return
    }

    [System.IO.Directory]::CreateDirectory($destination) | Out-Null
    $arguments = "-NoProfile -ExecutionPolicy Bypass -File $(Quote-Argument $bitsScript) -SourcePst $(Quote-Argument $source) -DestinationDirectory $(Quote-Argument $destination)"
    if ($verifyHash.Checked) { $arguments += " -VerifyHash" }
    $info = New-Object System.Diagnostics.ProcessStartInfo
    $info.FileName = "powershell.exe"
    $info.Arguments = $arguments
    $info.UseShellExecute = $false
    $info.CreateNoWindow = $true
    $info.RedirectStandardOutput = $true
    $info.RedirectStandardError = $true
    $startButton.Enabled = $false
    $statusLabel.Text = "Dang tao job BITS nen..."
    $form.Refresh()
    try {
        $process = [System.Diagnostics.Process]::Start($info)
        $output = $process.StandardOutput.ReadToEnd()
        $errorOutput = $process.StandardError.ReadToEnd()
        $process.WaitForExit()
        if ($process.ExitCode -ne 0) {
            throw ($errorOutput + "`r`n" + $output).Trim()
        }
        $result = $null
        try { $result = $output.Trim() | ConvertFrom-Json } catch {}
        if ($result -and $result.status -eq "ALREADY_RUNNING") {
            $statusLabel.Text = "JOB CU VAN DANG CHAY - khong tao job trung"
            [System.Windows.Forms.MessageBox]::Show("Job cua PST nay da ton tai va van dang chay.`r`n`r`nKhong tao them job. Bam Kiem tra job nen de xem tien do.", "Job da dang chay") | Out-Null
        }
        elseif ($result -and $result.status -eq "COMPLETE_EXISTING") {
            $statusLabel.Text = "HOAN TAT - file dich da day du"
            [System.Windows.Forms.MessageBox]::Show("PST dich da ton tai va co dung kich thuoc.", "Da hoan tat") | Out-Null
        }
        else {
            $statusLabel.Text = "JOB DANG CHAY NGAM - co the dong cong cu"
            [System.Windows.Forms.MessageBox]::Show("Windows BITS da nhan job.`r`n`r`nCo the dong cong cu. Mat mang se tu resume.", "Da chay ngam") | Out-Null
        }
    }
    catch {
        $statusLabel.Text = "LOI - xem thong bao"
        [System.Windows.Forms.MessageBox]::Show($_.Exception.Message, "Khong tao duoc job BITS") | Out-Null
    }
    finally {
        $startButton.Enabled = $true
    }
}

$form = New-Object System.Windows.Forms.Form
$form.Text = "InterLOG PST Transfer - IT"
$form.Size = New-Object System.Drawing.Size(900, 690)
$form.MinimumSize = New-Object System.Drawing.Size(800, 650)
$form.StartPosition = "CenterScreen"
$form.BackColor = [System.Drawing.Color]::FromArgb(244,247,251)
$form.Font = New-Object System.Drawing.Font("Segoe UI", 10)

$title = New-Object System.Windows.Forms.Label
$title.Text = "Backup PST tu may ao ve may user"
$title.Font = New-Object System.Drawing.Font("Segoe UI", 20, [System.Drawing.FontStyle]::Bold)
$title.ForeColor = [System.Drawing.Color]::FromArgb(18,52,91)
$title.Location = New-Object System.Drawing.Point(24,18)
$title.AutoSize = $true
$form.Controls.Add($title)

$subtitle = New-Object System.Windows.Forms.Label
$subtitle.Text = "Mot quy trinh duy nhat - chay ngam, mat mang tu resume"
$subtitle.ForeColor = [System.Drawing.Color]::FromArgb(82,100,122)
$subtitle.Location = New-Object System.Drawing.Point(28,58)
$subtitle.AutoSize = $true
$form.Controls.Add($subtitle)

$step1 = New-Object System.Windows.Forms.GroupBox
$step1.Text = "BUOC 1 - Export dung du lieu tren may ao"
$step1.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
$step1.Location = New-Object System.Drawing.Point(24,92)
$step1.Size = New-Object System.Drawing.Size(835,185)
$form.Controls.Add($step1)

$instructions = New-Object System.Windows.Forms.Label
$instructions.Text = "1. Tren VM, mo Outlook Classic cua user.`r`n2. File > Open & Export > Import/Export > Export to a file > Outlook Data File (.pst).`r`n3. Chon dung Online Archive/mailbox/folder va bat Include subfolders.`r`n4. Luu vao o local cua VM, cho export xong roi dong Outlook."
$instructions.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$instructions.Location = New-Object System.Drawing.Point(16,28)
$instructions.Size = New-Object System.Drawing.Size(800,100)
$step1.Controls.Add($instructions)

$exportDone = New-Object System.Windows.Forms.CheckBox
$exportDone.Text = "Toi da export xong va da dong Outlook tren may ao"
$exportDone.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$exportDone.Location = New-Object System.Drawing.Point(18,137)
$exportDone.AutoSize = $true
$step1.Controls.Add($exportDone)

$step2 = New-Object System.Windows.Forms.GroupBox
$step2.Text = "BUOC 2 - Chuyen PST ve may user bang Windows BITS"
$step2.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
$step2.Location = New-Object System.Drawing.Point(24,292)
$step2.Size = New-Object System.Drawing.Size(835,270)
$form.Controls.Add($step2)

$sourceLabel = New-Object System.Windows.Forms.Label
$sourceLabel.Text = "PST tren may ao:"
$sourceLabel.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$sourceLabel.Location = New-Object System.Drawing.Point(18,38)
$sourceLabel.AutoSize = $true
$step2.Controls.Add($sourceLabel)

$sourceBox = New-Object System.Windows.Forms.TextBox
$sourceBox.Location = New-Object System.Drawing.Point(155,35)
$sourceBox.Size = New-Object System.Drawing.Size(550,28)
$sourceBox.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$step2.Controls.Add($sourceBox)

$sourceButton = New-Object System.Windows.Forms.Button
$sourceButton.Text = "Chon file..."
$sourceButton.Location = New-Object System.Drawing.Point(714,34)
$sourceButton.Size = New-Object System.Drawing.Size(100,31)
$sourceButton.Add_Click({ Browse-Pst })
$step2.Controls.Add($sourceButton)

$destinationLabel = New-Object System.Windows.Forms.Label
$destinationLabel.Text = "Luu tren may user:"
$destinationLabel.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$destinationLabel.Location = New-Object System.Drawing.Point(18,79)
$destinationLabel.AutoSize = $true
$step2.Controls.Add($destinationLabel)

$destinationBox = New-Object System.Windows.Forms.TextBox
$destinationBox.Text = Join-Path ([Environment]::GetFolderPath("Desktop")) "MAIL BACKUP"
$destinationBox.Location = New-Object System.Drawing.Point(155,76)
$destinationBox.Size = New-Object System.Drawing.Size(550,28)
$destinationBox.Font = New-Object System.Drawing.Font("Segoe UI", 10)
$step2.Controls.Add($destinationBox)

$destinationButton = New-Object System.Windows.Forms.Button
$destinationButton.Text = "Chon thu muc..."
$destinationButton.Location = New-Object System.Drawing.Point(714,75)
$destinationButton.Size = New-Object System.Drawing.Size(100,31)
$destinationButton.Add_Click({ Browse-Destination })
$step2.Controls.Add($destinationButton)

$example = New-Object System.Windows.Forms.Label
$example.Text = "Vi du: \\<IP-MAY-AO>\MailBackup\user_archive.pst  ->  D:\MAIL BACKUP\user"
$example.ForeColor = [System.Drawing.Color]::FromArgb(82,100,122)
$example.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$example.Location = New-Object System.Drawing.Point(155,109)
$example.AutoSize = $true
$step2.Controls.Add($example)

$verifyHash = New-Object System.Windows.Forms.CheckBox
$verifyHash.Text = "So SHA-256 sau khi copy (cham hon voi PST 50 GB)"
$verifyHash.Font = New-Object System.Drawing.Font("Segoe UI", 9)
$verifyHash.Location = New-Object System.Drawing.Point(155,137)
$verifyHash.AutoSize = $true
$step2.Controls.Add($verifyHash)

$startButton = New-Object System.Windows.Forms.Button
$startButton.Text = "BAT DAU CHAY NGAM / TU RESUME"
$startButton.Font = New-Object System.Drawing.Font("Segoe UI", 11, [System.Drawing.FontStyle]::Bold)
$startButton.Location = New-Object System.Drawing.Point(18,181)
$startButton.Size = New-Object System.Drawing.Size(330,52)
$startButton.Add_Click({ Start-BackgroundTransfer })
$step2.Controls.Add($startButton)

$statusButton = New-Object System.Windows.Forms.Button
$statusButton.Text = "Kiem tra job nen"
$statusButton.Location = New-Object System.Drawing.Point(360,191)
$statusButton.Size = New-Object System.Drawing.Size(145,34)
$statusButton.Add_Click({ Show-JobStatus })
$step2.Controls.Add($statusButton)

$openButton = New-Object System.Windows.Forms.Button
$openButton.Text = "Mo thu muc dich"
$openButton.Location = New-Object System.Drawing.Point(515,191)
$openButton.Size = New-Object System.Drawing.Size(145,34)
$openButton.Add_Click({
    $path = $destinationBox.Text.Trim().Trim('"')
    if ($path) {
        [System.IO.Directory]::CreateDirectory($path) | Out-Null
        Start-Process explorer.exe -ArgumentList (Quote-Argument $path)
    }
})
$step2.Controls.Add($openButton)

$statusLabel = New-Object System.Windows.Forms.Label
$statusLabel.Text = "Trang thai: San sang"
$statusLabel.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
$statusLabel.ForeColor = [System.Drawing.Color]::FromArgb(23,105,170)
$statusLabel.Location = New-Object System.Drawing.Point(28,580)
$statusLabel.Size = New-Object System.Drawing.Size(820,28)
$form.Controls.Add($statusLabel)

$note = New-Object System.Windows.Forms.Label
$note.Text = "Co the dong cong cu sau khi BITS nhan job. Mat mang/restart se tu resume khi user dang nhap lai. Khong xoa PST tren VM den khi receipt COMPLETE."
$note.ForeColor = [System.Drawing.Color]::FromArgb(19,115,51)
$note.Location = New-Object System.Drawing.Point(28,613)
$note.Size = New-Object System.Drawing.Size(820,40)
$form.Controls.Add($note)

[void]$form.ShowDialog()
