# Native Windows entrypoint. Keep the caller's cwd, environment and arguments.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$aihubNode = Get-Command node -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
if (-not $aihubNode) {
    [Console]::Error.WriteLine('Node.js 18 or newer is required. Install Node.js, then retry this entrypoint.')
    exit 1
}
$aihubNodeVersion = & $aihubNode.Source --version
$aihubVersionMatch = [regex]::Match([string]$aihubNodeVersion, '^v(\d+)\.')
if ($LASTEXITCODE -ne 0 -or -not $aihubVersionMatch.Success -or [int]$aihubVersionMatch.Groups[1].Value -lt 18) {
    [Console]::Error.WriteLine('Node.js 18 or newer is required. Update Node.js, then retry this entrypoint.')
    exit 1
}
# Node otherwise realpaths every user-directory ancestor before loading the
# installed entrypoint/modules; Windows restricted tokens may not list them.
# These options change module resolution, not sandbox permissions.
& $aihubNode.Source --preserve-symlinks --preserve-symlinks-main (Join-Path $PSScriptRoot 'aihub.mjs') @args
exit $LASTEXITCODE
