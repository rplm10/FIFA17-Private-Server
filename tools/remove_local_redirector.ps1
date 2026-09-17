# Run this script from an elevated PowerShell window.
$ErrorActionPreference = "Stop"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Administrator privileges are required. Open PowerShell as Administrator and run this script again."
}

$HostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$Marker = "# FIFA17-LOCAL-FUT"
$HostName = "winter15.gosredirector.ea.com"

$Lines = Get-Content $HostsPath -ErrorAction Stop
$Lines = $Lines | Where-Object { ($_ -notmatch [regex]::Escape($Marker)) -and ($_ -notmatch "^\s*(127\.0\.0\.1|0\.0\.0\.0)\s+$([regex]::Escape($HostName))(\s|$)") }
Set-Content -Path $HostsPath -Value $Lines -Encoding ASCII

Get-ChildItem Cert:\LocalMachine\Root |
    Where-Object { $_.Subject -eq "CN=FIFA 17 Local FUT Development CA" } |
    Remove-Item -Force -ErrorAction SilentlyContinue

ipconfig /flushdns | Out-Null
Write-Host "Removed FIFA 17 local redirector hosts entry and development CA." -ForegroundColor Green
