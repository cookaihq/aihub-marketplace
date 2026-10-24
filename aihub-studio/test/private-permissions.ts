import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { stat } from 'node:fs/promises';
import { promisify } from 'node:util';

const exec = promisify(execFile);

/** Inspect OS permissions independently of the production writer. */
export async function assertPrivateFile(path: string): Promise<void> {
  if (process.platform !== 'win32') {
    assert.equal((await stat(path)).mode & 0o777, 0o600);
    return;
  }
  const env: NodeJS.ProcessEnv = { ...process.env, AIHUB_TEST_PERMISSION_PATH: path };
  delete env.PSModulePath;
  const script = `
$ErrorActionPreference = 'Stop'
$acl = [System.IO.File]::GetAccessControl($env:AIHUB_TEST_PERMISSION_PATH)
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rules = @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
$valid = $acl.AreAccessRulesProtected -and $rules.Count -eq 2
foreach ($rule in $rules) {
  $valid = $valid -and -not $rule.IsInherited -and $rule.AccessControlType -eq 'Allow' -and
    $rule.FileSystemRights -eq 'FullControl' -and $rule.IdentityReference.Value -in @($sid, 'S-1-5-18')
}
if (-not $valid) { throw 'File is not restricted to the current user and SYSTEM' }
`;
  await exec('powershell.exe', ['-NoProfile', '-NonInteractive', '-Command', script],
    { env, windowsHide: true, timeout: 10_000 });
}
