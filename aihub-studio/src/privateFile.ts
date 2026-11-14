import { execFile } from 'node:child_process';
import { join } from 'node:path';
import { promisify } from 'node:util';

const exec = promisify(execFile);
const restrictWindowsFile = `
$ErrorActionPreference = 'Stop'
$path = $env:AIHUB_PRIVATE_FILE_PATH
$user = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
$project = [System.IO.Directory]::GetAccessControl($env:AIHUB_PRIVATE_PROJECT_PATH)
$owner = $project.GetOwner([System.Security.Principal.SecurityIdentifier])
# Native constructors avoid loading PowerShell's utility cmdlets for every
# atomic write. Keep the same unique SIDs, protected DACL and verification.
$allowed = [System.Collections.Generic.List[string]]::new()
foreach ($sid in @($user.Value, 'S-1-5-18', $owner.Value)) {
  if (-not $allowed.Contains($sid)) { $allowed.Add($sid) }
}
$acl = [System.Security.AccessControl.FileSecurity]::new()
# Preserve the newly created file's owner. Setting it again requires WRITE_OWNER,
# while the creator can safely restrict its DACL without transferring ownership.
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in $allowed) {
  $identity = [System.Security.Principal.SecurityIdentifier]::new($sid)
  $rule = [System.Security.AccessControl.FileSystemAccessRule]::new($identity, 'FullControl', 'Allow')
  $acl.AddAccessRule($rule)
}
[System.IO.File]::SetAccessControl($path, $acl)
$actual = [System.IO.File]::GetAccessControl($path)
$rules = @($actual.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
if (-not $actual.AreAccessRulesProtected -or $rules.Count -ne $allowed.Count) { exit 2 }
foreach ($rule in $rules) {
  if ($rule.IsInherited -or $rule.AccessControlType -ne 'Allow' -or
      $rule.FileSystemRights -ne 'FullControl' -or
      $rule.IdentityReference.Value -notin $allowed) { exit 2 }
}
`;

/** Restrict the empty temporary file before any private contents are written. */
export async function preparePrivateFile(path: string): Promise<void> {
  if (process.platform !== 'win32') return; // The creator already uses mode 0600.
  const env: NodeJS.ProcessEnv = { ...process.env, AIHUB_PRIVATE_FILE_PATH: path, AIHUB_PRIVATE_PROJECT_PATH: process.cwd() };
  // A parent PowerShell 7 module path is not a Windows PowerShell 5.1 runtime.
  delete env.PSModulePath;
  const powershell = join(process.env.SystemRoot || process.env.WINDIR || 'C:\\Windows',
    'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
  try {
    await exec(powershell, ['-NoProfile', '-NonInteractive', '-Command', restrictWindowsFile],
      { env, windowsHide: true, timeout: 10_000 });
  } catch {
    throw new Error('Could not restrict the private file to the execution account, project owner and SYSTEM. Windows PowerShell 5.1 (powershell.exe) and file ACL support are required; no private content was written.');
  }
}
