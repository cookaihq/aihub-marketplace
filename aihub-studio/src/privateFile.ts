import { open } from 'node:fs/promises';
import { join } from 'node:path';
import { runCaptured } from './capturedProcess.js';

const createWindowsFiles = `
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent()
# Define just the native signature in memory. Add-Type would start a compiler
# for every private write, adding seconds and temporary compiler dependencies.
$assembly = [AppDomain]::CurrentDomain.DefineDynamicAssembly([System.Reflection.AssemblyName]::new('AIhubToken'), [System.Reflection.Emit.AssemblyBuilderAccess]::Run)
$module = $assembly.DefineDynamicModule('Token')
$type = $module.DefineType('AIhubToken', [System.Reflection.TypeAttributes]::Public)
$method = $type.DefinePInvokeMethod('GetTokenInformation', 'advapi32.dll',
  [System.Reflection.MethodAttributes]'Public, Static, PinvokeImpl', [System.Reflection.CallingConventions]::Standard,
  [bool], [Type[]]@([IntPtr], [int], [IntPtr], [int], [int].MakeByRefType()),
  [System.Runtime.InteropServices.CallingConvention]::Winapi, [System.Runtime.InteropServices.CharSet]::Auto)
$method.SetImplementationFlags([System.Reflection.MethodImplAttributes]::PreserveSig)
$native = $type.CreateType()
$length = 0
[void]$native::GetTokenInformation($identity.Token, 11, [IntPtr]::Zero, 0, [ref]$length)
if ($length -lt 4) { throw 'GetTokenInformation could not size TokenRestrictedSids.' }
$data = [System.Runtime.InteropServices.Marshal]::AllocHGlobal($length)
$restricted = [System.Collections.Generic.List[string]]::new()
try {
  if (-not $native::GetTokenInformation($identity.Token, 11, $data, $length, [ref]$length)) { throw 'GetTokenInformation could not read TokenRestrictedSids.' }
  $count = [System.Runtime.InteropServices.Marshal]::ReadInt32($data)
  $offset = 4; $stride = 8
  if ([IntPtr]::Size -eq 8) { $offset = 8; $stride = 16 }
  for ($i = 0; $i -lt $count; $i++) {
    $sid = [System.Runtime.InteropServices.Marshal]::ReadIntPtr($data, $offset + $i * $stride)
    $restricted.Add([System.Security.Principal.SecurityIdentifier]::new($sid).Value)
  }
} finally { [System.Runtime.InteropServices.Marshal]::FreeHGlobal($data) }
$project = [System.IO.Directory]::GetAccessControl($env:AIHUB_PRIVATE_PROJECT_PATH)
$allowed = [System.Collections.Generic.List[string]]::new()
foreach ($sid in @($identity.User.Value, 'S-1-5-18', $project.GetOwner([System.Security.Principal.SecurityIdentifier]).Value)) {
  if (-not $allowed.Contains($sid)) { $allowed.Add($sid) }
}
# Restricted access checks also require the current token's project capability.
# Select only account/capability SIDs already granted Modify on this project;
# never copy unrelated inherited ACEs, Everyone, Users or other broad groups.
foreach ($rule in $project.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier])) {
  $sid = $rule.IdentityReference.Value
  if ($sid -like 'S-1-5-21-*' -and $sid -in $restricted -and $rule.AccessControlType -eq 'Allow' -and
      ($rule.FileSystemRights -band [System.Security.AccessControl.FileSystemRights]::Modify) -eq [System.Security.AccessControl.FileSystemRights]::Modify -and
      -not $allowed.Contains($sid)) { $allowed.Add($sid) }
}
$acl = [System.Security.AccessControl.FileSecurity]::new()
$acl.SetAccessRuleProtection($true, $false)
foreach ($sid in $allowed) {
  $rule = [System.Security.AccessControl.FileSystemAccessRule]::new([System.Security.Principal.SecurityIdentifier]::new($sid), 'FullControl', 'Allow')
  $acl.AddAccessRule($rule)
}
foreach ($path in @($env:AIHUB_PRIVATE_FILE_PATH, $env:AIHUB_PRIVATE_SECOND_FILE_PATH)) {
  if ([string]::IsNullOrEmpty($path)) { continue }
  # Creation-time security avoids WRITE_DAC on an inherited file. CreateNew
  # refuses existing files, so neither a symlink nor a concurrent writer wins.
  $stream = [System.IO.FileStream]::new($path, [System.IO.FileMode]::CreateNew,
    [System.Security.AccessControl.FileSystemRights]::FullControl, [System.IO.FileShare]::Read,
    4096, [System.IO.FileOptions]::None, $acl)
  $stream.Dispose()
  $actual = [System.IO.File]::GetAccessControl($path)
  $rules = @($actual.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))
  if (-not $actual.AreAccessRulesProtected -or $rules.Count -ne $allowed.Count) { exit 2 }
  foreach ($rule in $rules) {
    if ($rule.IsInherited -or $rule.AccessControlType -ne 'Allow' -or
        $rule.FileSystemRights -ne 'FullControl' -or $rule.IdentityReference.Value -notin $allowed) { exit 2 }
  }
}
`;

/** Create empty files with their private security already in place, before writing contents. */
export async function createPrivateFile(path: string, secondPath?: string, signal?: AbortSignal): Promise<void> {
  if (process.platform !== 'win32') {
    for (const target of secondPath ? [path, secondPath] : [path]) {
      const handle = await open(target, 'wx', 0o600); await handle.close();
    }
    return;
  }
  const env: NodeJS.ProcessEnv = { ...process.env, AIHUB_PRIVATE_FILE_PATH: path,
    AIHUB_PRIVATE_SECOND_FILE_PATH: secondPath ?? '', AIHUB_PRIVATE_PROJECT_PATH: process.cwd() };
  // PowerShell 5.1 can hang before entering even a one-line script when TEMP
  // points beyond MAX_PATH. Keep the host's runtime temp environment; target
  // files (including long paths) still receive their creation-time private ACL.
  // A parent PowerShell 7 module path is not a Windows PowerShell 5.1 runtime.
  delete env.PSModulePath;
  const powershell = join(process.env.SystemRoot || process.env.WINDIR || 'C:\\Windows',
    'System32', 'WindowsPowerShell', 'v1.0', 'powershell.exe');
  try {
    // This ACL bootstrap emits no private contents. Captures for media tools
    // are created by this guard, before the media process starts.
    await runCaptured(powershell, ['-NoProfile', '-NonInteractive', '-Command', createWindowsFiles],
      { env, windowsHide: true, timeout: 10_000, signal });
  } catch (cause) {
    throw new Error('Could not create a private file for the execution account, project owner, SYSTEM and current project capability. Windows PowerShell 5.1 (powershell.exe) and file ACL support are required; no private content was written.', { cause });
  }
}
