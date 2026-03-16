param(
  [string]$Configuration = "Release",
  [string]$Platform = "x64"
)

function Test-IsAdmin {
  $currentIdentity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($currentIdentity)
  return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

if (-not (Test-IsAdmin)) {
  Write-Host "Admin privileges required to remove HKLM keys and unregister the shell extension. Requesting elevation..." -ForegroundColor Yellow
  $argsList = @(
    "-ExecutionPolicy", "Bypass",
    "-File", "`"$PSCommandPath`"",
    "-Configuration", $Configuration,
    "-Platform", $Platform
  )
  Start-Process powershell -Verb RunAs -ArgumentList $argsList
  exit
}


$here = Split-Path -Parent $PSCommandPath
$dll = Join-Path $here "bin\$Platform\$Configuration\net48\ArtcoPsdOverlay.dll"

$regasm = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"
if (-not (Test-Path $regasm)) { throw "RegAsm not found (requires .NET Framework 4.x): $regasm" }


# 删除 overlay key（与 register 脚本一致）
$keyName = "  Artco PSD"
$overlayKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\$keyName"
if (Test-Path $overlayKey) {
  Write-Host "Removing ShellIconOverlayIdentifiers registry key..." -ForegroundColor Cyan
  Remove-Item -Path $overlayKey -Recurse -Force
}

if (Test-Path $dll) {
  Write-Host "Unregistering COM via RegAsm /unregister..." -ForegroundColor Cyan
  & $regasm /nologo /unregister $dll
}

Write-Host "Done. Restart Explorer (or sign out/in) to ensure changes take effect." -ForegroundColor Green

