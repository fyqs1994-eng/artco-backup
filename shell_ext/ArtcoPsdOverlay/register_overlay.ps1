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
  Write-Host "Admin privileges required to write HKLM and register the shell extension. Requesting elevation..." -ForegroundColor Yellow
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
$proj = Join-Path $here "ArtcoPsdOverlay.csproj"

Write-Host "Building shell overlay extension..." -ForegroundColor Cyan
& dotnet build $proj -c $Configuration -p:Platform=$Platform
if ($LASTEXITCODE -ne 0) { throw "dotnet build failed" }


$dll = Join-Path $here "bin\$Platform\$Configuration\net48\ArtcoPsdOverlay.dll"
if (-not (Test-Path $dll)) { throw "Output DLL not found: $dll" }


$regasm = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\RegAsm.exe"
if (-not (Test-Path $regasm)) { throw "RegAsm not found (requires .NET Framework 4.x): $regasm" }


Write-Host "Registering COM via RegAsm..." -ForegroundColor Cyan
& $regasm /nologo /codebase $dll
if ($LASTEXITCODE -ne 0) { throw "RegAsm registration failed" }


# 这个 CLSID 必须与 PsdOverlayHandler.cs 的 Guid 一致
$clsid = "{B9A7A4E3-6B1C-4D3B-AE6C-0B6C8C0E9F33}"

# Overlay 优先级由 key 名称决定；前面加空格可提高优先级（避免被其它软件挤掉）
$keyName = "  Artco PSD"
$overlayKey = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\ShellIconOverlayIdentifiers\$keyName"

Write-Host "Writing ShellIconOverlayIdentifiers registry key..." -ForegroundColor Cyan
New-Item -Path $overlayKey -Force | Out-Null
Set-ItemProperty -Path $overlayKey -Name "(default)" -Value $clsid

Write-Host "Notifying Explorer to refresh associations..." -ForegroundColor Cyan

try {
  Add-Type -Namespace Win32 -Name Native -MemberDefinition @"
    [System.Runtime.InteropServices.DllImport(\"shell32.dll\")] public static extern void SHChangeNotify(int wEventId, int uFlags, System.IntPtr dwItem1, System.IntPtr dwItem2);
"@
  [Win32.Native]::SHChangeNotify(0x08000000, 0x0000, [IntPtr]::Zero, [IntPtr]::Zero) | Out-Null
} catch {}

Write-Host "Done. Restart Explorer (or sign out/in) to ensure the overlay appears." -ForegroundColor Green
Write-Host "If the overlay does not show up: Windows has limited overlay slots and OneDrive/Dropbox/SVN may take priority." -ForegroundColor Yellow

