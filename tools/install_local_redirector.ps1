# Run this script from an elevated PowerShell window.
$ErrorActionPreference = "Stop"

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    throw "Administrator privileges are required. Open PowerShell as Administrator and run this script again."
}

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $Root

Write-Host "[1/4] Installing Python dependencies..."
python -m pip install -r requirements.txt

$ProfileMarker = "$Root\certs\gos_profile_v1.txt"
$NeedCerts = (-not (Test-Path "$Root\certs\fifa17_local_ca.crt")) -or
             (-not (Test-Path "$Root\certs\redirector.crt")) -or
             (-not (Test-Path $ProfileMarker))

if ($NeedCerts) {
    Write-Host "[2/4] Migrating to GOS-style local TLS certificates..."

    # Remove only the old development CA created by earlier versions of this project.
    Get-ChildItem Cert:\LocalMachine\Root |
        Where-Object { $_.Subject -eq "CN=FIFA 17 Local FUT Development CA" } |
        Remove-Item -Force -ErrorAction SilentlyContinue

    python tools\generate_certs.py
    if ($LASTEXITCODE -ne 0) { throw "Certificate generation failed." }
} else {
    Write-Host "[2/4] GOS-style local TLS certificates already exist."
}

Write-Host "[3/4] Trusting the local GOS development CA..."
Import-Certificate -FilePath "$Root\certs\fifa17_local_ca.crt" -CertStoreLocation "Cert:\LocalMachine\Root" | Out-Null

$HostsPath = "$env:SystemRoot\System32\drivers\etc\hosts"
$Marker = "# FIFA17-LOCAL-FUT"
$HostName = "winter15.gosredirector.ea.com"
$Lines = Get-Content $HostsPath -ErrorAction Stop
$Lines = $Lines | Where-Object { ($_ -notmatch [regex]::Escape($Marker)) -and ($_ -notmatch "^\s*(127\.0\.0\.1|0\.0\.0\.0)\s+$([regex]::Escape($HostName))(\s|$)") }
$Lines += "127.0.0.1`t$HostName`t$Marker"
Set-Content -Path $HostsPath -Value $Lines -Encoding ASCII

Write-Host "[4/4] Flushing DNS cache..."
ipconfig /flushdns | Out-Null

Write-Host ""
Write-Host "Installed local FIFA 17 redirector routing:" -ForegroundColor Green
Write-Host "  $HostName -> 127.0.0.1"
Write-Host "  certificate profile -> GOS 2015-compatible local development chain"
Write-Host ""
Write-Host "Next: python -m server.main"
