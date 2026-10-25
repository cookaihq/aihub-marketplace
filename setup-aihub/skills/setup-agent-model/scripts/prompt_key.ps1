param([Parameter(Mandatory=$true)][string]$Target)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$dialog = New-Object System.Windows.Forms.Form
$dialog.Text = 'Setup AIHub - local Key input'
$dialog.Size = New-Object System.Drawing.Size(600, 230)
$dialog.StartPosition = 'CenterScreen'
$dialog.FormBorderStyle = 'FixedDialog'
$dialog.MaximizeBox = $false
$dialog.MinimizeBox = $false
$label = New-Object System.Windows.Forms.Label
$label.Text = "AIhub Key will be saved to the confirmed native configuration:`r`n$Target"
$label.Location = New-Object System.Drawing.Point(16, 16)
$label.Size = New-Object System.Drawing.Size(550, 65)
$inputBox = New-Object System.Windows.Forms.TextBox
$inputBox.UseSystemPasswordChar = $true
$inputBox.Location = New-Object System.Drawing.Point(16, 88)
$inputBox.Size = New-Object System.Drawing.Size(550, 28)
$save = New-Object System.Windows.Forms.Button
$save.Text = 'Save'
$save.Location = New-Object System.Drawing.Point(380, 135)
$save.DialogResult = [System.Windows.Forms.DialogResult]::OK
$cancel = New-Object System.Windows.Forms.Button
$cancel.Text = 'Cancel'
$cancel.Location = New-Object System.Drawing.Point(475, 135)
$cancel.DialogResult = [System.Windows.Forms.DialogResult]::Cancel
$dialog.Controls.AddRange(@($label, $inputBox, $save, $cancel))
$dialog.AcceptButton = $save
$dialog.CancelButton = $cancel
$result = $dialog.ShowDialog()
if ($result -eq [System.Windows.Forms.DialogResult]::OK -and $inputBox.Text.Length -gt 0) {
    [Console]::Out.Write($inputBox.Text)
    $inputBox.Clear()
    $dialog.Dispose()
    exit 0
}
$dialog.Dispose()
exit 3
