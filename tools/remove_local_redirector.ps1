# Run this script from an elevated PowerShell window.
$ErrorActionPreference = "Stop"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Administrator privileges are required. Open PowerShell as Administrator and run this script again."
}

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$HostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$Marker = "# FIFA17-LOCAL-FUT"
$HostName = "winter15.gosredirector.ea.com"

$Lines = Get-Content $HostsPath -ErrorAction Stop
$Lines = $Lines | Where-Object { ($_ -notmatch [regex]::Escape($Marker)) -and ($_ -notmatch "^\s*(127\.0\.0\.1|0\.0\.0\.0)\s+$([regex]::Escape($HostName))(\s|$)") }
Set-Content -Path $HostsPath -Value $Lines -Encoding ASCII

$ThumbprintPath = "$Root\certs\fifa17_local_ca_thumbprint.txt"
if (Test-Path $ThumbprintPath) {
    $Thumbprint = (Get-Content $ThumbprintPath -Raw).Trim()
    if ($Thumbprint) {
        Get-ChildItem Cert:\LocalMachine\Root |
            Where-Object { $_.Thumbprint -eq $Thumbprint } |
            Remove-Item -Force -ErrorAction SilentlyContinue
    }
}

# Backward-compatible cleanup for the CA name used by the initial prototype.
Get-ChildItem Cert:\LocalMachine\Root |
    Where-Object { $_.Subject -eq "CN=FIFA 17 Local FUT Development CA" } |
    Remove-Item -Force -ErrorAction SilentlyContinue

ipconfig /flushdns | Out-Null
Write-Host "Removed FIFA 17 local redirector hosts entry and this project's trusted CA." -ForegroundColor Green
